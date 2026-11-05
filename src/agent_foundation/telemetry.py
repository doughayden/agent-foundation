"""OpenTelemetry setup: the application owns every provider and exporter.

``configure_telemetry()`` builds the providers and sets them globally before ADK builds
its FastAPI app. Each exporter gets an explicit OTLP gRPC endpoint: traces and logs go
to a configured collector or the Google Cloud Telemetry API, and metrics to a collector
or, when the resource has ``cloud.region``, the Telemetry API. ADK contributes only its
web UI processors, attached to these providers by the patch below.
"""

import functools
import logging
import os
import uuid

import google.auth
import google.auth.transport.requests
import grpc
from fastapi import FastAPI
from google.adk.cli import api_server
from google.adk.telemetry.setup import OTelHooks
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.grpc import AuthMetadataPlugin
from opentelemetry import _logs as logs
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.resourcedetector.gcp_resource_detector import (
    GoogleCloudResourceDetector,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    CLOUD_REGION,
    SERVICE_INSTANCE_ID,
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    SERVICE_VERSION,
    OTELResourceDetector,
    Resource,
    get_aggregated_resources,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import TelemetryEnv

GCP_PROJECT_ID = "gcp.project_id"
GCP_RESOURCE_TYPE = "gcp.resource_type"
# Deployed environments override it via OTEL_RESOURCE_ATTRIBUTES
DEFAULT_SERVICE_NAMESPACE = "local"


def build_resource(
    service_name: str,
    project_id: str,
    service_version: str,
    region: str | None,
) -> Resource:
    """Build the resource shared by every provider.

    Precedence, highest first: the environment's ``OTEL_SERVICE_NAME`` and
    ``OTEL_RESOURCE_ATTRIBUTES``, the arguments here, then the GCP resource detector.

    Args:
        service_name: service.name
        project_id: gcp.project_id
        service_version: service.version, the Cloud Run revision when deployed
        region: cloud.region when known (``CLOUD_RUN_REGION``)

    Returns:
        The merged resource.
    """
    detected = get_aggregated_resources(
        [GoogleCloudResourceDetector()], initial_resource=Resource.get_empty()
    )
    ours = Resource(
        {
            SERVICE_NAME: service_name,
            SERVICE_NAMESPACE: DEFAULT_SERVICE_NAMESPACE,
            SERVICE_VERSION: service_version,
            SERVICE_INSTANCE_ID: f"worker-{os.getpid()}-{uuid.uuid4().hex}",
            GCP_PROJECT_ID: project_id,
        }
        | ({CLOUD_REGION: region} if region else {})
    )
    environment = OTELResourceDetector().detect()
    return Resource.create().merge(detected).merge(ours).merge(environment)


def cloud_run_resource(settings: TelemetryEnv, project_id: str) -> Resource:
    """Return the attributes that place OTLP logs on ``cloud_run_revision``.

    The Telemetry API maps OTLP logs to ``generic_task`` unless the resource carries
    ``gcp.resource_type`` and the monitored resource's labels. Traces and logs only:
    the Telemetry API drops metric points that carry ``gcp.resource_type``.

    Args:
        settings: Telemetry settings carrying the Cloud Run identity
        project_id: GCP project ID

    Returns:
        The attributes on Cloud Run, an empty resource elsewhere.
    """
    if (
        settings.k_service is None
        or settings.k_configuration is None
        or settings.cloud_run_region is None
    ):
        return Resource.get_empty()
    return Resource(
        {
            GCP_RESOURCE_TYPE: "cloud_run_revision",
            "project_id": project_id,
            "service_name": settings.k_service,
            "revision_name": settings.k_revision,
            "configuration_name": settings.k_configuration,
            "location": settings.cloud_run_region,
        }
    )


def metrics_endpoint(settings: TelemetryEnv, resource: Resource) -> str | None:
    """Pick where metrics go: a collector, the Telemetry API, or nowhere.

    The Telemetry API needs a location on the resource, so it takes metrics only
    when the resource has ``cloud.region`` (detected on Cloud Run, from
    ``CLOUD_RUN_REGION``, or set in ``OTEL_RESOURCE_ATTRIBUTES``).

    Args:
        settings: Telemetry settings, read for the metrics collector endpoint
        resource: The meter provider's resource

    Returns:
        The collector endpoint if set, else the Telemetry API endpoint when the
        resource has a region, else None.
    """
    if settings.metrics_endpoint is not None:
        return settings.metrics_endpoint
    if CLOUD_REGION in resource.attributes:
        return settings.telemetry_api_endpoint
    return None


def google_channel_credentials() -> grpc.ChannelCredentials:
    """Build gRPC channel credentials from Application Default Credentials.

    Returns:
        TLS channel credentials carrying ADC call credentials.

    Raises:
        DefaultCredentialsError: When ADC is not configured.
    """
    try:
        credentials, _ = google.auth.default()
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


def configure_telemetry(
    settings: TelemetryEnv,
    service_name: str,
    project_id: str,
    log_level: str,
) -> None:
    """Set the global providers and instrument logging and asyncpg.

    Must run before ``get_fast_api_app()``, so ADK's web UI processors attach to
    these providers. Each exporter gets its resolved endpoint explicitly; Application
    Default Credentials are read once, and only for an exporter aimed at the
    Telemetry API. A meter provider is set only when ``metrics_endpoint()`` picks a
    destination; its resource omits the ``cloud_run_revision`` attributes.
    With ``OTEL_SDK_DISABLED`` the tracer and logger providers are still set (the SDK
    makes them no-ops), with no exporters, no credentials and no meter provider.

    Args:
        settings: Telemetry settings (endpoints, Cloud Run identity)
        service_name: service.name
        project_id: GCP project ID
        log_level: Root logger level
    """
    meter_resource = build_resource(
        service_name, project_id, settings.k_revision, settings.cloud_run_region
    )
    resource = meter_resource.merge(cloud_run_resource(settings, project_id))
    google_credentials = functools.cache(google_channel_credentials)

    def credentials_for(endpoint: str) -> grpc.ChannelCredentials | None:
        if endpoint == settings.telemetry_api_endpoint:
            return google_credentials()
        return None

    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    logger_provider = LoggerProvider(resource=resource)
    logs.set_logger_provider(logger_provider)

    if not settings.otel_sdk_disabled:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=settings.traces_endpoint,
                    credentials=credentials_for(settings.traces_endpoint),
                )
            )
        )
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(
                    endpoint=settings.logs_endpoint,
                    credentials=credentials_for(settings.logs_endpoint),
                )
            )
        )

    metrics_destination = metrics_endpoint(settings, meter_resource)
    if not settings.otel_sdk_disabled and metrics_destination is not None:
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=metrics_destination,
                credentials=credentials_for(metrics_destination),
            )
        )
        metrics.set_meter_provider(
            MeterProvider(resource=meter_resource, metric_readers=[metric_reader])
        )

    # Export failures log to the console only, never back into the log exporter
    sdk_logger = logging.getLogger("opentelemetry")
    sdk_logger.addHandler(logging.StreamHandler())
    sdk_logger.propagate = False

    logging.getLogger().setLevel(log_level)
    # Inject trace context into log records and attach the OTel handler to root
    LoggingInstrumentor().instrument(log_code_attributes=True)
    # opentelemetry-instrumentation-asyncpg leaves __init__ unannotated
    AsyncPGInstrumentor().instrument()  # type: ignore[no-untyped-call]


def instrument_app(app: FastAPI) -> None:
    """Add HTTP server spans and metrics to the FastAPI app."""
    FastAPIInstrumentor().instrument_app(app)


# --- Monkey-patch: ADK's telemetry setup attaches web UI processors only ---
# get_fast_api_app() calls api_server._setup_telemetry(), which builds its own
# providers and OTLP/HTTP exporters when an OTEL_EXPORTER_OTLP_* endpoint is set
# and instruments the GenAI SDK. With our providers already set, its set_*_provider
# calls do nothing and the web UI processors riding in the same call are dropped,
# and log processors never attach to a provider set elsewhere on any path.
# Upstream: ADK 2.13.0 google/adk/cli/api_server.py _setup_telemetry; tracer reuse
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
