"""Unit tests for the telemetry module."""

import logging
import os

import grpc
import pytest
from google.adk.cli import api_server
from google.adk.telemetry.setup import OTelHooks
from google.auth.exceptions import DefaultCredentialsError
from opentelemetry import _logs as logs
from opentelemetry import trace
from opentelemetry.resourcedetector.gcp_resource_detector import (
    GoogleCloudResourceDetector,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from pytest_mock import MockerFixture

from agent_foundation import telemetry
from agent_foundation.config import TELEMETRY_API_ENDPOINT

COLLECTOR = "http://localhost:4317"
CONFIGURE_ARGS = {
    "service_name": "test-agent",
    "project_id": "test-project",
    "log_level": "DEBUG",
}
CLOUD_RUN_ENV = {
    "K_SERVICE": "test-agent-dev",
    "K_REVISION": "test-agent-dev-00001-abc",
    "K_CONFIGURATION": "test-agent-dev",
    "CLOUD_RUN_REGION": "us-central1",
}


class TestWebUiPatch:
    """Tests for the ADK ``_setup_telemetry`` replacement."""

    def test_patch_replaces_adk_setup_telemetry(self) -> None:
        """Test that importing telemetry swaps ADK's setup for the attach-only one."""
        assert api_server._setup_telemetry is telemetry._attach_web_ui_processors

    def test_no_processors_is_a_no_op(self, mocker: MockerFixture) -> None:
        """Test that the web UI off path (no processors) touches no provider."""
        get_tracer_provider = mocker.patch.object(trace, "get_tracer_provider")

        telemetry._attach_web_ui_processors(otel_to_cloud=True)

        get_tracer_provider.assert_not_called()

    def test_processors_attach_to_global_providers(self, mocker: MockerFixture) -> None:
        """Test that span and log processors join the providers already set."""
        tracer_provider = TracerProvider()
        logger_provider = LoggerProvider()
        mocker.patch.object(trace, "get_tracer_provider", return_value=tracer_provider)
        mocker.patch.object(logs, "get_logger_provider", return_value=logger_provider)
        add_span = mocker.patch.object(tracer_provider, "add_span_processor")
        add_log = mocker.patch.object(logger_provider, "add_log_record_processor")
        span_processor = mocker.sentinel.span_processor
        log_processor = mocker.sentinel.log_processor

        telemetry._attach_web_ui_processors(
            internal_processors=OTelHooks(
                span_processors=[span_processor],
                log_record_processors=[log_processor],
            )
        )

        add_span.assert_called_once_with(span_processor)
        add_log.assert_called_once_with(log_processor)

    def test_unset_providers_raise(self, mocker: MockerFixture) -> None:
        """Test that building the app before configure_telemetry() fails loudly."""
        mocker.patch.object(
            trace, "get_tracer_provider", return_value=trace.ProxyTracerProvider()
        )

        with pytest.raises(RuntimeError, match="must run before get_fast_api_app"):
            telemetry._attach_web_ui_processors(internal_processors=OTelHooks())


class TestBuildResource:
    """Tests for resource precedence."""

    @pytest.fixture(autouse=True)
    def detected(self, mocker: MockerFixture) -> None:
        """Detector reports a region and a conflicting service name."""
        mocker.patch.object(
            GoogleCloudResourceDetector,
            "detect",
            return_value=Resource(
                {"cloud.region": "us-central1", "service.name": "detected"}
            ),
        )

    def test_our_values_override_detector(self, mocker: MockerFixture) -> None:
        """Test that settings beat detected attributes and detected ones remain."""
        mocker.patch.dict(os.environ, {}, clear=True)

        attributes = telemetry.build_resource(
            "test-agent", "test-project", "rev-1", None
        ).attributes

        assert attributes["service.name"] == "test-agent"
        assert attributes["service.namespace"] == "local"
        assert attributes["service.version"] == "rev-1"
        assert attributes["gcp.project_id"] == "test-project"
        assert attributes["cloud.region"] == "us-central1"
        assert str(attributes["service.instance.id"]).startswith(
            f"worker-{os.getpid()}-"
        )

    def test_consumer_environment_overrides_ours(self, mocker: MockerFixture) -> None:
        """Test that OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES win."""
        mocker.patch.dict(
            os.environ,
            {
                "OTEL_SERVICE_NAME": "consumer-service",
                "OTEL_RESOURCE_ATTRIBUTES": "service.namespace=consumer,team=core",
            },
            clear=True,
        )

        attributes = telemetry.build_resource(
            "test-agent", "test-project", "rev-1", None
        ).attributes

        assert attributes["service.name"] == "consumer-service"
        assert attributes["service.namespace"] == "consumer"
        assert attributes["team"] == "core"
        assert attributes["service.version"] == "rev-1"

    def test_region_argument_beats_detector(self, mocker: MockerFixture) -> None:
        """Test that CLOUD_RUN_REGION sets cloud.region over the detected one."""
        mocker.patch.dict(os.environ, {}, clear=True)

        attributes = telemetry.build_resource(
            "test-agent", "test-project", "rev-1", "europe-west1"
        ).attributes

        assert attributes["cloud.region"] == "europe-west1"

    def test_environment_region_beats_region_argument(
        self, mocker: MockerFixture
    ) -> None:
        """Test that cloud.region in OTEL_RESOURCE_ATTRIBUTES wins."""
        mocker.patch.dict(
            os.environ,
            {"OTEL_RESOURCE_ATTRIBUTES": "cloud.region=asia-east1"},
            clear=True,
        )

        attributes = telemetry.build_resource(
            "test-agent", "test-project", "rev-1", "europe-west1"
        ).attributes

        assert attributes["cloud.region"] == "asia-east1"


class TestCloudRunResource:
    """Tests for the ``cloud_run_revision`` resource attributes."""

    def test_cloud_run_attributes(self, create_telemetry_env) -> None:
        """Test that every monitored resource label comes from the settings."""
        settings = create_telemetry_env(CLOUD_RUN_ENV)

        cloud_run = telemetry.cloud_run_resource(settings, "test-project")

        assert dict(cloud_run.attributes) == {
            "gcp.resource_type": "cloud_run_revision",
            "project_id": "test-project",
            "service_name": "test-agent-dev",
            "revision_name": "test-agent-dev-00001-abc",
            "configuration_name": "test-agent-dev",
            "location": "us-central1",
        }

    def test_empty_off_cloud_run(self, create_telemetry_env) -> None:
        """Test that nothing is added when K_SERVICE is unset."""
        settings = create_telemetry_env({})

        cloud_run = telemetry.cloud_run_resource(settings, "test-project")

        assert dict(cloud_run.attributes) == {}


class TestMetricsEndpoint:
    """Tests for the metrics destination decision."""

    @pytest.mark.parametrize(
        ("variables", "attributes", "expected"),
        [
            ({"OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR}, {}, COLLECTOR),
            (
                {"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": COLLECTOR},
                {"cloud.region": "us-central1"},
                COLLECTOR,
            ),
            ({}, {"cloud.region": "us-central1"}, TELEMETRY_API_ENDPOINT),
            ({}, {}, None),
        ],
    )
    def test_destination(
        self,
        variables: dict[str, str],
        attributes: dict[str, str],
        expected: str | None,
        create_telemetry_env,
    ) -> None:
        """Test collector first, then the Telemetry API with a region, else off."""
        settings = create_telemetry_env(variables)

        assert telemetry.metrics_endpoint(settings, Resource(attributes)) == expected


class TestGoogleChannelCredentials:
    """Tests for ADC-backed gRPC channel credentials."""

    def test_returns_channel_credentials(self) -> None:
        """Test that ADC (mocked in pytest_configure) builds channel credentials."""
        assert isinstance(
            telemetry.google_channel_credentials(), grpc.ChannelCredentials
        )

    def test_missing_adc_reraises_with_hint(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that a missing ADC prints the login command and re-raises."""
        mocker.patch(
            "google.auth.default", side_effect=DefaultCredentialsError("no adc")
        )

        with pytest.raises(DefaultCredentialsError):
            telemetry.google_channel_credentials()

        assert "gcloud auth application-default login" in capsys.readouterr().out


class TestConfigureTelemetry:
    """Tests for provider and exporter wiring."""

    def test_defaults_send_traces_and_logs_to_google(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test the Telemetry API with ADC for traces and logs, and no metrics."""
        settings = create_telemetry_env({})
        credentials = mock_telemetry_sdk["google_channel_credentials"].return_value

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)

        google = {
            "endpoint": settings.telemetry_api_endpoint,
            "credentials": credentials,
        }
        mock_telemetry_sdk["OTLPSpanExporter"].assert_called_once_with(**google)
        mock_telemetry_sdk["OTLPLogExporter"].assert_called_once_with(**google)
        mock_telemetry_sdk["OTLPMetricExporter"].assert_not_called()
        mock_telemetry_sdk["set_meter_provider"].assert_not_called()
        mock_telemetry_sdk["google_channel_credentials"].assert_called_once_with()

    def test_collector_endpoint_gets_no_google_credentials(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test that a collector receives every signal with SDK-owned credentials."""
        settings = create_telemetry_env({"OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR})

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)

        collector = {"endpoint": COLLECTOR, "credentials": None}
        mock_telemetry_sdk["OTLPSpanExporter"].assert_called_once_with(**collector)
        mock_telemetry_sdk["OTLPLogExporter"].assert_called_once_with(**collector)
        mock_telemetry_sdk["OTLPMetricExporter"].assert_called_once_with(**collector)
        mock_telemetry_sdk["set_meter_provider"].assert_called_once_with(
            mock_telemetry_sdk["MeterProvider"].return_value
        )
        mock_telemetry_sdk["google_channel_credentials"].assert_not_called()

    def test_per_signal_endpoint_routes_only_that_signal(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test that a traces-only endpoint keeps logs on Google and metrics off."""
        settings = create_telemetry_env(
            {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": COLLECTOR}
        )

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)

        span_kwargs = mock_telemetry_sdk["OTLPSpanExporter"].call_args.kwargs
        log_kwargs = mock_telemetry_sdk["OTLPLogExporter"].call_args.kwargs
        assert span_kwargs == {"endpoint": COLLECTOR, "credentials": None}
        assert log_kwargs["endpoint"] == settings.telemetry_api_endpoint
        mock_telemetry_sdk["OTLPMetricExporter"].assert_not_called()
        mock_telemetry_sdk["google_channel_credentials"].assert_called_once_with()

    def test_sets_providers_with_shared_resource(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test that every provider is built on the resource and set globally."""
        settings = create_telemetry_env({"OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR})
        resource = mock_telemetry_sdk["build_resource"].return_value

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)

        mock_telemetry_sdk["build_resource"].assert_called_once_with(
            "test-agent", "test-project", "local", None
        )
        for provider in ("TracerProvider", "LoggerProvider"):
            mock_telemetry_sdk[provider].assert_called_once_with(resource=resource)
        mock_telemetry_sdk["MeterProvider"].assert_called_once_with(
            resource=resource,
            metric_readers=[
                mock_telemetry_sdk["PeriodicExportingMetricReader"].return_value
            ],
        )
        mock_telemetry_sdk["set_tracer_provider"].assert_called_once_with(
            mock_telemetry_sdk["TracerProvider"].return_value
        )
        mock_telemetry_sdk["set_logger_provider"].assert_called_once_with(
            mock_telemetry_sdk["LoggerProvider"].return_value
        )

    def test_metrics_go_to_google_with_a_region(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test that a resource region sends metrics to the Telemetry API."""
        settings = create_telemetry_env({})
        mock_telemetry_sdk["build_resource"].return_value = Resource(
            {"cloud.region": "us-central1"}
        )
        credentials = mock_telemetry_sdk["google_channel_credentials"].return_value

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)

        mock_telemetry_sdk["OTLPMetricExporter"].assert_called_once_with(
            endpoint=settings.telemetry_api_endpoint, credentials=credentials
        )
        mock_telemetry_sdk["set_meter_provider"].assert_called_once_with(
            mock_telemetry_sdk["MeterProvider"].return_value
        )
        mock_telemetry_sdk["google_channel_credentials"].assert_called_once_with()

    def test_on_cloud_run_meter_resource_omits_resource_type(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test traces and logs get cloud_run_revision, metrics only cloud.region."""
        settings = create_telemetry_env(CLOUD_RUN_ENV)
        mock_telemetry_sdk["build_resource"].return_value = Resource(
            {"cloud.region": "us-central1"}
        )

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)

        mock_telemetry_sdk["build_resource"].assert_called_once_with(
            "test-agent", "test-project", "test-agent-dev-00001-abc", "us-central1"
        )
        for provider in ("TracerProvider", "LoggerProvider"):
            resource = mock_telemetry_sdk[provider].call_args.kwargs["resource"]
            assert resource.attributes["gcp.resource_type"] == "cloud_run_revision"
            assert resource.attributes["location"] == "us-central1"
        meter_resource = mock_telemetry_sdk["MeterProvider"].call_args.kwargs[
            "resource"
        ]
        assert "gcp.resource_type" not in meter_resource.attributes
        assert meter_resource.attributes["cloud.region"] == "us-central1"

    def test_disabled_sdk_builds_no_exporters(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test that OTEL_SDK_DISABLED sets bare providers with no export."""
        settings = create_telemetry_env(
            {"OTEL_SDK_DISABLED": "true", "OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR}
        )

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)

        for exporter in ("OTLPSpanExporter", "OTLPLogExporter", "OTLPMetricExporter"):
            mock_telemetry_sdk[exporter].assert_not_called()
        mock_telemetry_sdk["google_channel_credentials"].assert_not_called()
        mock_telemetry_sdk["set_meter_provider"].assert_not_called()
        mock_telemetry_sdk["set_tracer_provider"].assert_called_once_with(
            mock_telemetry_sdk["TracerProvider"].return_value
        )
        mock_telemetry_sdk["set_logger_provider"].assert_called_once_with(
            mock_telemetry_sdk["LoggerProvider"].return_value
        )

    def test_disabled_sdk_still_accepts_web_ui_processors(
        self, create_telemetry_env, mocker: MockerFixture
    ) -> None:
        """Test that the patch attaches web UI processors to disabled providers."""
        settings = create_telemetry_env({"OTEL_SDK_DISABLED": "true"})
        set_tracer = mocker.patch.object(trace, "set_tracer_provider")
        set_logger = mocker.patch.object(logs, "set_logger_provider")
        mocker.patch.object(telemetry, "LoggingInstrumentor")
        mocker.patch.object(telemetry, "AsyncPGInstrumentor")
        credentials = mocker.patch.object(telemetry, "google_channel_credentials")
        sdk_logger = logging.getLogger("opentelemetry")
        mocker.patch.object(sdk_logger, "handlers", [])
        mocker.patch.object(sdk_logger, "propagate", True)
        mocker.patch.object(logging.getLogger(), "setLevel")

        telemetry.configure_telemetry(settings, **CONFIGURE_ARGS)
        tracer_provider = set_tracer.call_args.args[0]
        logger_provider = set_logger.call_args.args[0]
        mocker.patch.object(trace, "get_tracer_provider", return_value=tracer_provider)
        mocker.patch.object(logs, "get_logger_provider", return_value=logger_provider)
        add_span = mocker.patch.object(tracer_provider, "add_span_processor")
        add_log = mocker.patch.object(logger_provider, "add_log_record_processor")

        telemetry._attach_web_ui_processors(
            internal_processors=OTelHooks(
                span_processors=[mocker.sentinel.span_processor],
                log_record_processors=[mocker.sentinel.log_processor],
            )
        )

        credentials.assert_not_called()
        add_span.assert_called_once_with(mocker.sentinel.span_processor)
        add_log.assert_called_once_with(mocker.sentinel.log_processor)

    def test_instruments_logging_and_asyncpg(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test log correlation, root level and asyncpg spans are enabled."""
        telemetry.configure_telemetry(create_telemetry_env({}), **CONFIGURE_ARGS)

        mock_telemetry_sdk["root_set_level"].assert_called_once_with("DEBUG")
        logging_instrumentor = mock_telemetry_sdk["LoggingInstrumentor"].return_value
        logging_instrumentor.instrument.assert_called_once_with(
            log_code_attributes=True
        )
        asyncpg_instrumentor = mock_telemetry_sdk["AsyncPGInstrumentor"].return_value
        asyncpg_instrumentor.instrument.assert_called_once_with()

    def test_sdk_logger_writes_to_console_only(
        self, mock_telemetry_sdk, create_telemetry_env
    ) -> None:
        """Test that export errors cannot feed back into the log exporter."""
        telemetry.configure_telemetry(create_telemetry_env({}), **CONFIGURE_ARGS)

        sdk_logger = logging.getLogger("opentelemetry")
        assert sdk_logger.propagate is False
        assert [type(h) for h in sdk_logger.handlers] == [logging.StreamHandler]


class TestInstrumentApp:
    """Tests for FastAPI instrumentation."""

    def test_instruments_the_given_app(self, mocker: MockerFixture) -> None:
        """Test that the live app instance is instrumented."""
        instrumentor = mocker.patch.object(telemetry, "FastAPIInstrumentor")
        app = mocker.sentinel.app

        telemetry.instrument_app(app)

        instrumentor.return_value.instrument_app.assert_called_once_with(app)
