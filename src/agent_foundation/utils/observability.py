"""OpenTelemetry setup for local development and production deployment.

This module provides consolidated observability configuration used consistently
across local development and deployed environments. Uses custom resource
configuration for service identification with process-level granularity.

The custom setup coexists with ADK's internal telemetry infrastructure without
provider collisions, enabling ADK web UI traces (local development) and
Google Cloud observability (all environments).
"""

import logging
import os
import uuid
import warnings

import google.auth
import google.auth.transport.requests
import grpc
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.grpc import AuthMetadataPlugin
from google.cloud.logging_v2.services.logging_service_v2 import (
    LoggingServiceV2Client,
)
from opentelemetry import _events as events
from opentelemetry import _logs as logs
from opentelemetry import trace
from opentelemetry.exporter.cloud_logging import CloudLoggingExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs._internal import LogDeprecatedInitWarning
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import (
    SERVICE_INSTANCE_ID,
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    SERVICE_VERSION,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

warnings.filterwarnings("ignore", category=LogDeprecatedInitWarning)


def configure_otel_resource(agent_name: str, project_id: str) -> None:
    """Configure OpenTelemetry resource via environment variables.

    Builds and sets OTEL_RESOURCE_ATTRIBUTES with process-level tracking.
    This ensures consistent resource configuration across both local development
    (ADK creates TracerProvider) and deployment (we create TracerProvider).

    Args:
        agent_name: Unique service identifier
        project_id: GCP Project ID

    Environment Variables Set:
        OTEL_RESOURCE_ATTRIBUTES: Complete resource attributes including process ID

    Returns:
        None
    """
    print("🔭 Setting OpenTelemetry Resource attributes environment variable...")
    instance_id = f"worker-{os.getpid()}-{uuid.uuid4().hex}"
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = (
        f"{SERVICE_INSTANCE_ID}={instance_id},"
        f"{SERVICE_NAME}={agent_name},"
        f"{SERVICE_NAMESPACE}={os.getenv('TELEMETRY_NAMESPACE', 'local')},"
        f"{SERVICE_VERSION}={os.getenv('K_REVISION', 'local')},"
        f"gcp.project_id={project_id}"
    )

    return


def setup_opentelemetry(
    project_id: str,
    agent_name: str,
    log_level: str,
) -> None:
    """Set up complete OpenTelemetry observability with tracing and logging.

    Configures comprehensive observability for both local development and deployed
    environments with consistent behavior. Exports traces to Google Cloud Trace via
    OTLP and logs to Google Cloud Logging with automatic trace correlation.

    Uses custom resource configuration to set SERVICE_INSTANCE_ID based on process ID,
    providing granular service instance tracking. Coexists with ADK's internal
    telemetry providers without collision.

    Automatically calls configure_otel_resource() if resource env vars not already set,
    ensuring consistent resource configuration across all environments.

    Args:
        project_id: GCP Project ID for trace and log export
        agent_name: Unique service identifier
        log_level: Logging verbosity level as string

    Returns:
        None
    """
    # Configure resource via env vars if not already set
    # (local dev calls configure_otel_resource() before ADK, deployment calls it here)
    if resource := os.getenv("OTEL_RESOURCE_ATTRIBUTES"):
        print("🔭 OpenTelemetry Resource configured in environment:\n")
        print("\n".join(resource.split(",")), end="\n\n\n")
    else:
        configure_otel_resource(agent_name, project_id)

    # Defensive strategy for portability to projects without Pydantic pre-validation
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        print(f"⚠️ Received log_level: '{log_level}'. Defaulting to 'INFO'")
        log_level = "INFO"

    # Get Application Default Credentials for Cloud exporters
    try:
        credentials, _ = google.auth.default()
    except DefaultCredentialsError as e:
        print(f"❌ [observability] Error getting Application Default Credentials: {e}")
        print("💻 Try authenticating with 'gcloud auth application-default login'")
        raise e
    except Exception as e:
        print(f"❌ [observability] Unexpected error during authentication: {e}")
        raise e

    # Type narrowing: Validate quota project support (required for Cloud Logging client)
    if not hasattr(credentials, "with_quota_project"):
        raise TypeError(
            f"Credentials type {type(credentials).__name__} does not support "
            "with_quota_project method required for Cloud Logging"
        )

    # Set up OpenTelemetry Python SDK for logs and genai events
    # LoggerProvider auto-detects resource from OTEL_RESOURCE_ATTRIBUTES
    log_name: str = f"{agent_name}-otel-logs"
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            CloudLoggingExporter(
                project_id=project_id,
                default_log_name=log_name,
                client=LoggingServiceV2Client(
                    credentials=credentials.with_quota_project(project_id)
                ),
            ),
        )
    )
    logs.set_logger_provider(logger_provider)

    event_logger_provider = EventLoggerProvider(logger_provider)
    events.set_event_logger_provider(event_logger_provider)

    # Inject OTel trace attributes in LogRecords
    LoggingInstrumentor().instrument()

    # ADK uses the Google Gen AI SDK
    GoogleGenAiSdkInstrumentor().instrument()

    # Get the root logger and set the logging level
    root = logging.getLogger()
    root.setLevel(log_level)

    # Attach the OTel handler to the root logger
    otel_handler = LoggingHandler(logger_provider=logger_provider)
    root.addHandler(otel_handler)

    # Set up OTLP auth
    request = google.auth.transport.requests.Request()
    auth_metadata_plugin = AuthMetadataPlugin(credentials=credentials, request=request)
    channel_creds = grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(),
        grpc.metadata_call_credentials(metadata_plugin=auth_metadata_plugin),
    )

    # Construct the span processor
    endpoint = "https://telemetry.googleapis.com:443/v1/traces"
    span_processor = BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=endpoint,
            credentials=channel_creds,
        ),
    )

    # Add the span processor to the TracerProvider if it exists (not the default proxy)
    existing_tracer_provider = trace.get_tracer_provider()
    if isinstance(existing_tracer_provider, TracerProvider):
        existing_tracer_provider.add_span_processor(span_processor)
    else:
        # No existing provider (deployment case), create one
        # TracerProvider auto-detects resource from OTEL_RESOURCE_ATTRIBUTES
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(tracer_provider)

    return
