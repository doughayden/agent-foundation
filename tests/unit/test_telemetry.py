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
from opentelemetry._logs import LogRecord
from opentelemetry.resourcedetector.gcp_resource_detector import (
    GoogleCloudResourceDetector,
)
from opentelemetry.sdk._logs import LoggerProvider, ReadWriteLogRecord
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from pytest_mock import MockerFixture, MockType

from agent_foundation import telemetry

CONFIGURE_ARGS = {
    "service_name": "test-agent",
    "project_id": "test-project",
    "log_level": "DEBUG",
}
# What GoogleCloudResourceDetector reports on Cloud Run
CLOUD_RUN_DETECTED = {
    "cloud.platform": "gcp_cloud_run",
    "cloud.region": "us-central1",
    "faas.name": "test-agent-dev",
    "faas.version": "test-agent-dev-00001-abc",
    "faas.instance": "instance-1",
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


class TestBuildResources:
    """Tests for resource precedence and the Cloud Run monitored resource."""

    @pytest.fixture
    def detected(self, mocker: MockerFixture) -> MockType:
        """Detector reports Cloud Run attributes and a conflicting service name."""
        return mocker.patch.object(
            GoogleCloudResourceDetector,
            "detect",
            return_value=Resource({**CLOUD_RUN_DETECTED, "service.name": "detected"}),
        )

    def test_our_values_override_detector(self, detected, mocker) -> None:
        """Test that our values beat detected attributes and detected ones remain."""
        mocker.patch.dict(os.environ, {"K_CONFIGURATION": "test-agent-dev"}, clear=True)

        _, meter = telemetry.build_resources("test-agent", "test-project")

        attributes = meter.attributes
        assert attributes["service.name"] == "test-agent"
        assert attributes["gcp.project_id"] == "test-project"
        assert attributes["cloud.region"] == "us-central1"
        assert attributes["faas.version"] == "test-agent-dev-00001-abc"
        assert "service.namespace" not in attributes
        assert str(attributes["service.instance.id"]).startswith(
            f"worker-{os.getpid()}-"
        )

    def test_consumer_environment_overrides_ours(self, detected, mocker) -> None:
        """Test that OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES win."""
        mocker.patch.dict(
            os.environ,
            {
                "K_CONFIGURATION": "test-agent-dev",
                "OTEL_SERVICE_NAME": "consumer-service",
                "OTEL_RESOURCE_ATTRIBUTES": (
                    "service.namespace=consumer,team=core,cloud.region=asia-east1"
                ),
            },
            clear=True,
        )

        _, meter = telemetry.build_resources("test-agent", "test-project")

        assert meter.attributes["service.name"] == "consumer-service"
        assert meter.attributes["service.namespace"] == "consumer"
        assert meter.attributes["team"] == "core"
        assert meter.attributes["cloud.region"] == "asia-east1"

    def test_cloud_run_revision_on_traces_and_logs_only(self, detected, mocker) -> None:
        """Test that the monitored resource labels come from the detector and env."""
        mocker.patch.dict(os.environ, {"K_CONFIGURATION": "test-agent-dev"})

        resource, meter = telemetry.build_resources("test-agent", "test-project")

        assert {
            "gcp.resource_type": "cloud_run_revision",
            "project_id": "test-project",
            "service_name": "test-agent-dev",
            "revision_name": "test-agent-dev-00001-abc",
            "configuration_name": "test-agent-dev",
            "location": "us-central1",
        }.items() <= dict(resource.attributes).items()
        assert "gcp.resource_type" not in meter.attributes

    def test_same_resource_off_cloud_run(self, detected) -> None:
        """Test that nothing is added when the platform is not Cloud Run."""
        detected.return_value = Resource({"cloud.region": "us-central1"})

        resource, meter = telemetry.build_resources("test-agent", "test-project")

        assert resource is meter
        assert "gcp.resource_type" not in resource.attributes


class TestGoogleChannelCredentials:
    """Tests for ADC-backed gRPC channel credentials."""

    def test_returns_channel_credentials(self) -> None:
        """Test that ADC (mocked in pytest_configure) builds channel credentials."""
        assert isinstance(
            telemetry.google_channel_credentials(), grpc.ChannelCredentials
        )

    def test_requests_cloud_platform_scope(self, mocker: MockerFixture) -> None:
        """Test that ADC is requested with the cloud-platform scope."""
        default = mocker.patch(
            "google.auth.default",
            return_value=(mocker.sentinel.credentials, "test-project"),
        )

        telemetry.google_channel_credentials()

        default.assert_called_once_with(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
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


class TestEventNameProcessor:
    """Tests for copying the event name into an attribute."""

    @pytest.mark.parametrize(
        ("event_name", "attributes", "expected"),
        [
            ("gen_ai.event", {"a": 1}, {"event.name": "gen_ai.event", "a": 1}),
            ("gen_ai.event", None, {"event.name": "gen_ai.event"}),
            ("gen_ai.event", {"event.name": "ours"}, {"event.name": "ours"}),
            (None, {"a": 1}, {"a": 1}),
        ],
        ids=["adds", "no-attributes", "keeps-existing", "no-event-name"],
    )
    def test_on_emit(self, event_name, attributes, expected) -> None:
        """Test that the event name lands in ``event.name`` unless already set."""
        record = ReadWriteLogRecord(
            log_record=LogRecord(event_name=event_name, attributes=attributes)
        )

        telemetry.EventNameProcessor().on_emit(record)

        assert dict(record.log_record.attributes or {}) == expected

    def test_shutdown_and_flush_are_no_ops(self) -> None:
        """Test that the processor holds nothing to flush or release."""
        processor = telemetry.EventNameProcessor()

        processor.shutdown()

        assert processor.force_flush() is True


class TestConfigureTelemetry:
    """Tests for provider and exporter wiring."""

    def test_traces_and_logs_go_to_google_without_a_region(
        self, mock_telemetry_sdk, capsys
    ) -> None:
        """Test the Telemetry API with ADC, and no metrics without a region."""
        credentials = mock_telemetry_sdk["google_channel_credentials"].return_value

        telemetry.configure_telemetry(**CONFIGURE_ARGS)

        assert (
            f"Telemetry export: {telemetry.TELEMETRY_API_ENDPOINT} "
            "(metrics off, no cloud.region)"
        ) in capsys.readouterr().out
        google = {
            "endpoint": telemetry.TELEMETRY_API_ENDPOINT,
            "credentials": credentials,
        }
        mock_telemetry_sdk["OTLPSpanExporter"].assert_called_once_with(**google)
        mock_telemetry_sdk["OTLPLogExporter"].assert_called_once_with(**google)
        mock_telemetry_sdk["OTLPMetricExporter"].assert_not_called()
        mock_telemetry_sdk["set_meter_provider"].assert_not_called()
        mock_telemetry_sdk["google_channel_credentials"].assert_called_once_with()

    def test_sets_providers_with_their_resources(
        self, mock_telemetry_sdk, capsys
    ) -> None:
        """Test traces and logs share one resource and metrics get the meter one."""
        resource = Resource({"cloud.region": "us-central1", "gcp.resource_type": "x"})
        meter_resource = Resource({"cloud.region": "us-central1"})
        mock_telemetry_sdk["build_resources"].return_value = (resource, meter_resource)

        telemetry.configure_telemetry(**CONFIGURE_ARGS)

        mock_telemetry_sdk["build_resources"].assert_called_once_with(
            "test-agent", "test-project"
        )
        for provider in ("TracerProvider", "LoggerProvider"):
            mock_telemetry_sdk[provider].assert_called_once_with(resource=resource)
        mock_telemetry_sdk["MeterProvider"].assert_called_once_with(
            resource=meter_resource,
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
        assert "gcp.resource_type=x" in capsys.readouterr().out

    def test_event_name_processor_runs_before_export(self, mock_telemetry_sdk) -> None:
        """Test that ``event.name`` is set before the batch processor exports."""
        telemetry.configure_telemetry(**CONFIGURE_ARGS)

        add = mock_telemetry_sdk["LoggerProvider"].return_value.add_log_record_processor
        first, second = (call.args[0] for call in add.call_args_list)
        assert isinstance(first, telemetry.EventNameProcessor)
        assert second is mock_telemetry_sdk["BatchLogRecordProcessor"].return_value

    def test_metrics_go_to_google_with_a_region(
        self, mock_telemetry_sdk, capsys
    ) -> None:
        """Test that a resource region sends metrics to the Telemetry API."""
        region = Resource({"cloud.region": "us-central1"})
        mock_telemetry_sdk["build_resources"].return_value = (region, region)
        credentials = mock_telemetry_sdk["google_channel_credentials"].return_value

        telemetry.configure_telemetry(**CONFIGURE_ARGS)

        mock_telemetry_sdk["OTLPMetricExporter"].assert_called_once_with(
            endpoint=telemetry.TELEMETRY_API_ENDPOINT, credentials=credentials
        )
        mock_telemetry_sdk["set_meter_provider"].assert_called_once_with(
            mock_telemetry_sdk["MeterProvider"].return_value
        )
        assert "(metrics on, cloud.region=us-central1)" in capsys.readouterr().out

    def test_instruments_logging(self, mock_telemetry_sdk) -> None:
        """Test log correlation and the root level are set."""
        telemetry.configure_telemetry(**CONFIGURE_ARGS)

        mock_telemetry_sdk["root_set_level"].assert_called_once_with("DEBUG")
        logging_instrumentor = mock_telemetry_sdk["LoggingInstrumentor"].return_value
        logging_instrumentor.instrument.assert_called_once_with(
            log_code_attributes=True
        )

    def test_sdk_logger_writes_to_console_only(self, mock_telemetry_sdk) -> None:
        """Test that export errors cannot feed back into the log exporter."""
        telemetry.configure_telemetry(**CONFIGURE_ARGS)

        sdk_logger = logging.getLogger("opentelemetry")
        assert sdk_logger.propagate is False
        assert [type(h) for h in sdk_logger.handlers] == [logging.StreamHandler]


class TestHealthCheckFilter:
    """Tests for dropping health check access log lines."""

    @pytest.mark.parametrize(
        ("args", "kept"),
        [
            (("169.254.0.1:1", "GET", "/health", "1.1", 200), False),
            (("169.254.0.1:1", "GET", "/health?probe=1", "1.1", 200), False),
            (("127.0.0.1:1", "POST", "/run", "1.1", 200), True),
            (("127.0.0.1:1", "GET", "/apps/health-agent", "1.1", 200), True),
            (("127.0.0.1:1", "GET", "/healthz", "1.1", 200), True),
            (None, True),
        ],
        ids=["health", "health-query", "run", "health-substring", "healthz", "plain"],
    )
    def test_filter(self, args, kept) -> None:
        """Test that only the exact health check path is dropped."""
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, "", 0, "%s", args, None
        )

        assert telemetry.HealthCheckFilter().filter(record) is kept

    def test_attached_to_uvicorn_access_logger(self, mock_telemetry_sdk) -> None:
        """Test that configure_telemetry filters the uvicorn access logger."""
        telemetry.configure_telemetry(**CONFIGURE_ARGS)

        filters = logging.getLogger("uvicorn.access").filters
        assert [type(f) for f in filters] == [telemetry.HealthCheckFilter]
