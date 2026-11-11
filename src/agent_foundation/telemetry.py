"""OpenTelemetry setup: the application owns every provider and exporter.

``configure_telemetry()`` builds the providers and sets them globally before ADK builds
its FastAPI app. Every exporter targets the Google Cloud Telemetry API over OTLP gRPC
with Application Default Credentials, and metrics export only when the resource has
``cloud.region``. To send telemetry to another backend, replace this module. ADK
contributes only its web UI processors, attached to these providers by the patch below.
"""

import logging
import os
import uuid

import google.auth
import google.auth.transport.requests
import grpc
from google.adk.cli import api_server
from google.adk.telemetry.setup import OTelHooks
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.grpc import AuthMetadataPlugin
from opentelemetry import _logs as logs
from opentelemetry import metrics, trace
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.resourcedetector.gcp_resource_detector import (
    GoogleCloudResourceDetector,
)
from opentelemetry.sdk._logs import (
    LoggerProvider,
    LogRecordProcessor,
    ReadWriteLogRecord,
)
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    CLOUD_REGION,
    FAAS_NAME,
    FAAS_VERSION,
    SERVICE_INSTANCE_ID,
    SERVICE_NAME,
    OTELResourceDetector,
    Resource,
    get_aggregated_resources,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

TELEMETRY_API_ENDPOINT = "https://telemetry.googleapis.com:443"
CLOUD_PLATFORM = "cloud.platform"
GCP_CLOUD_RUN = "gcp_cloud_run"
GCP_PROJECT_ID = "gcp.project_id"
EVENT_NAME = "event.name"
GCP_RESOURCE_TYPE = "gcp.resource_type"
K_CONFIGURATION = "K_CONFIGURATION"
GOOGLE_CLOUD_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
# Cloud Run startup and readiness probes
HEALTH_CHECK_PATH = "/health"


def build_resources(service_name: str, project_id: str) -> tuple[Resource, Resource]:
    """Build the traces/logs resource and the meter resource.

    Precedence, highest first: the environment's ``OTEL_SERVICE_NAME`` and
    ``OTEL_RESOURCE_ATTRIBUTES``, the arguments here and a per-worker
    ``service.instance.id``, then the GCP resource detector (``cloud.platform``,
    ``cloud.region``, ``faas.*`` on Cloud Run). On Cloud Run the traces/logs resource
    adds the ``cloud_run_revision`` monitored resource, so the Telemetry API places
    logs there instead of on ``generic_task``. The meter resource omits it: the
    Telemetry API drops metric points that carry ``gcp.resource_type``.

    Args:
        service_name: service.name
        project_id: gcp.project_id, required by the Telemetry API

    Returns:
        The traces/logs resource and the meter resource.
    """
    detected = get_aggregated_resources(
        [GoogleCloudResourceDetector()], initial_resource=Resource.get_empty()
    )
    defaults = Resource(
        {
            SERVICE_NAME: service_name,
            SERVICE_INSTANCE_ID: f"worker-{os.getpid()}-{uuid.uuid4().hex}",
            GCP_PROJECT_ID: project_id,
        }
    )
    environment = OTELResourceDetector().detect()
    meter_resource = (
        Resource.create().merge(detected).merge(defaults).merge(environment)
    )
    attributes = meter_resource.attributes
    # The detector uses K_CONFIGURATION to detect Cloud Run, never exports it
    configuration_name = os.environ.get(K_CONFIGURATION)
    if (
        attributes.get(CLOUD_PLATFORM) != GCP_CLOUD_RUN
        or configuration_name is None
        or not all(key in attributes for key in (FAAS_NAME, FAAS_VERSION, CLOUD_REGION))
    ):
        return meter_resource, meter_resource
    cloud_run_revision = Resource(
        {
            GCP_RESOURCE_TYPE: "cloud_run_revision",
            "project_id": project_id,
            "service_name": attributes[FAAS_NAME],
            "revision_name": attributes[FAAS_VERSION],
            "configuration_name": configuration_name,
            "location": attributes[CLOUD_REGION],
        }
    )
    return meter_resource.merge(cloud_run_revision), meter_resource


def google_channel_credentials() -> grpc.ChannelCredentials:
    """Build gRPC channel credentials from Application Default Credentials.

    Returns:
        TLS channel credentials carrying ADC call credentials.

    Raises:
        DefaultCredentialsError: When ADC is not configured.
    """
    try:
        credentials, _ = google.auth.default(scopes=GOOGLE_CLOUD_SCOPES)
    except DefaultCredentialsError:
        print("💻 Authenticate with 'gcloud auth application-default login'")
        raise
    # google-auth leaves AuthMetadataPlugin.__init__ unannotated
    auth_metadata_plugin = AuthMetadataPlugin(  # type: ignore[no-untyped-call]
        credentials=credentials, request=google.auth.transport.requests.Request()
    )
    return grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(),
        grpc.metadata_call_credentials(metadata_plugin=auth_metadata_plugin),
    )


class HealthCheckFilter(logging.Filter):
    """Drop uvicorn access log records for the health check path.

    Uvicorn's access records carry ``(client, method, path, http_version, status)``
    as arguments; the path may include a query string.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Keep every record except a health check access line."""
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return str(args[2]).split("?", 1)[0] != HEALTH_CHECK_PATH
        return True


class EventNameProcessor(LogRecordProcessor):
    """Copy each log record's event name into an ``event.name`` attribute.

    The Telemetry API drops the OTLP ``event_name`` field, and Cloud Trace's
    Input/Output view finds GenAI events by the ``event.name`` label. Must run
    before the export processor.
    """

    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        """Add ``event.name`` in place, keeping the record's attribute limits."""
        record = log_record.log_record
        attributes = record.attributes
        if (
            record.event_name
            and isinstance(attributes, BoundedAttributes)
            and EVENT_NAME not in attributes
        ):
            attributes[EVENT_NAME] = record.event_name

    def shutdown(self) -> None:
        """Nothing to release."""

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Nothing buffered.

        Args:
            timeout_millis: Unused

        Returns:
            Always True.
        """
        return True


def configure_telemetry(service_name: str, project_id: str, log_level: str) -> None:
    """Set the global providers and instrument logging.

    Must run before ``get_fast_api_app()``, so ADK's web UI processors attach to
    these providers. Every signal exports to the Telemetry API with Application
    Default Credentials, passing the endpoint explicitly so the SDK's
    ``OTEL_EXPORTER_OTLP_*`` variables cannot redirect it. Metrics export only when
    the resource has ``cloud.region`` (detected on Cloud Run, or set in
    ``OTEL_RESOURCE_ATTRIBUTES``), and the meter resource omits the
    ``cloud_run_revision`` attributes. Prints the endpoint, whether metrics are on
    and the exported resource. ``OTEL_SDK_DISABLED`` is left to the SDK.

    Args:
        service_name: service.name
        project_id: GCP project ID
        log_level: Root logger level
    """
    resource, meter_resource = build_resources(service_name, project_id)
    credentials = google_channel_credentials()
    region = meter_resource.attributes.get(CLOUD_REGION)
    metrics_status = (
        f"metrics on, cloud.region={region}"
        if region
        else "metrics off, no cloud.region"
    )
    print(f"📡 Telemetry export: {TELEMETRY_API_ENDPOINT} ({metrics_status})")
    print("✅ Telemetry resource:\n")
    for key, value in sorted(resource.attributes.items()):
        print(f"{key}={value!s}")
    print("\n")

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=TELEMETRY_API_ENDPOINT, credentials=credentials)
        )
    )
    trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(EventNameProcessor())
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=TELEMETRY_API_ENDPOINT, credentials=credentials)
        )
    )
    logs.set_logger_provider(logger_provider)

    if region:
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=TELEMETRY_API_ENDPOINT, credentials=credentials)
        )
        metrics.set_meter_provider(
            MeterProvider(resource=meter_resource, metric_readers=[metric_reader])
        )

    # Export failures log to the console only, never back into the log exporter
    sdk_logger = logging.getLogger("opentelemetry")
    sdk_logger.addHandler(logging.StreamHandler())
    sdk_logger.propagate = False

    logging.getLogger().setLevel(log_level)
    # A logger filter, so uvicorn's dictConfig (which replaces handlers) keeps it
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
    # Inject trace context into log records and attach the OTel handler to root
    LoggingInstrumentor().instrument(log_code_attributes=True)


# --- Monkey-patch: ADK's telemetry setup attaches web UI processors only ---
# get_fast_api_app() calls api_server._setup_telemetry(), which builds its own
# providers and OTLP/HTTP exporters when an OTEL_EXPORTER_OTLP_* endpoint is set
# and instruments the GenAI SDK. With our providers already set, its set_*_provider
# calls do nothing and the web UI processors riding in the same call are dropped,
# and log processors never attach to a provider set elsewhere on any path.
# Upstream: ADK 2.14.0 google/adk/cli/api_server.py _setup_telemetry; tracer reuse
# on the default path only: https://github.com/google/adk-python/pull/3548
# TODO: Remove when an ADK release attaches internal_processors to already-set
# providers on every path and skips its own providers and exporters.
def _attach_web_ui_processors(
    otel_to_cloud: bool = False,
    internal_processors: OTelHooks | None = None,
) -> None:
    """Attach ADK's web UI processors to the global providers, nothing else."""
    if internal_processors is None:
        return
    tracer_provider = trace.get_tracer_provider()
    logger_provider = logs.get_logger_provider()
    if not isinstance(tracer_provider, TracerProvider) or not isinstance(
        logger_provider, LoggerProvider
    ):
        msg = "configure_telemetry() must run before get_fast_api_app()"
        raise RuntimeError(msg)
    for span_processor in internal_processors.span_processors:
        tracer_provider.add_span_processor(span_processor)
    for log_record_processor in internal_processors.log_record_processors:
        logger_provider.add_log_record_processor(log_record_processor)


api_server._setup_telemetry = _attach_web_ui_processors
# --- End monkey-patch ---
