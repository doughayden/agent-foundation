"""Environment configuration for the server.

``initialize_environment()`` loads a ``.env`` file into ``os.environ`` without
overriding variables already set, then ``ServerEnv`` and ``TelemetryEnv`` read the
environment. A value set in the shell or by the platform is never replaced by a stale
local file, and every reader of ``os.environ`` (ADK, the OpenTelemetry SDK) sees the
``.env`` values.
"""

import json
import sys
from typing import Literal, Self

from dotenv import load_dotenv
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TELEMETRY_API_ENDPOINT = "https://telemetry.googleapis.com:443"


class ServerEnv(BaseSettings):
    """Environment configuration for local server development and deployment.

    Provides configuration for both local development and Cloud Run deployment,
    with sensible defaults for local development.

    Attributes:
        google_cloud_project: GCP project ID for authentication and observability
        google_cloud_location: Vertex AI model endpoint location
        agent_name: Unique agent identifier for resources and logs
        log_level: Logging verbosity level
        serve_web_interface: Whether to serve the ADK web interface
        reload_agents: Whether to reload agents on file changes (local dev only)
        session_service_uri: Session service URI (e.g., postgresql+asyncpg://user@host:5432/db)
        memory_service_uri: Memory service URI (e.g., agentengine://...)
        artifact_service_uri: GCS bucket URI for artifact storage
        allow_origins: JSON array string of allowed CORS origins
        host: Server host (127.0.0.1 for local, 0.0.0.0 for containers)
        port: Server port
        otel_instrumentation_genai_capture_message_content: GenAI message content
            capture mode, read by ADK
    """

    google_cloud_project: str = Field(
        ...,
        description="GCP project ID for authentication and observability",
    )

    google_cloud_location: str = Field(
        default="global",
        description="Vertex AI model endpoint location (global or a region)",
    )

    agent_name: str = Field(
        ...,
        description="Unique agent identifier for resources and logs",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging verbosity level",
    )

    serve_web_interface: bool = Field(
        default=False,
        description="Whether to serve the ADK web interface",
    )

    reload_agents: bool = Field(
        default=False,
        description="Whether to reload agents on file changes (local dev only)",
    )

    session_service_uri: str | None = Field(
        default=None,
        description="Session service URI (e.g., postgresql+asyncpg://user@host:5432/db)",
    )

    memory_service_uri: str | None = Field(
        default=None,
        description="Memory service URI (e.g., agentengine://...)",
    )

    artifact_service_uri: str | None = Field(
        default=None,
        description="GCS bucket URI for artifact storage",
    )

    allow_origins: str = Field(
        default='["http://127.0.0.1:8000", "http://localhost:8000"]',
        description=(
            "JSON array string of allowed CORS origins. "
            "Include both because developers may access the server via localhost "
            "or 127.0.0.1 (or because certain proxy setups use one or the other), "
            "and ports must match exactly in ADK>=1.27.3"
        ),
    )

    host: str = Field(
        default="127.0.0.1",
        description=(
            "Network interface for uvicorn to bind. "
            "Use 127.0.0.1 (loopback) for local dev, 0.0.0.0 for containers. "
            "Note: browsers resolve localhost URLs to this IP"
        ),
    )

    port: int = Field(
        default=8000,
        description="Server port",
    )

    otel_instrumentation_genai_capture_message_content: Literal[
        "NO_CONTENT", "EVENT_ONLY", "SPAN_ONLY", "SPAN_AND_EVENT"
    ] = Field(
        ...,
        description="ADK GenAI message content capture mode",
    )

    model_config = SettingsConfigDict(
        # .env also carries variables other readers own (ADK, compose, the genai SDK)
        extra="ignore",
    )

    @field_validator("allow_origins")
    @classmethod
    def validate_allow_origins_format(cls, v: str) -> str:
        """Validate allow_origins is valid JSON array with at least one string."""
        try:
            origins = json.loads(v)
        except json.JSONDecodeError as e:
            msg = f"ALLOW_ORIGINS must be valid JSON: {e}"
            raise ValueError(msg) from e

        if not isinstance(origins, list):
            msg = "ALLOW_ORIGINS must be a JSON array"
            raise ValueError(msg)

        if not origins:
            msg = "ALLOW_ORIGINS must contain at least one origin"
            raise ValueError(msg)

        if not all(isinstance(o, str) for o in origins):
            msg = "ALLOW_ORIGINS must be an array of strings"
            raise ValueError(msg)

        if not all(o.strip() for o in origins):
            msg = "ALLOW_ORIGINS must be an array of non-empty strings"
            raise ValueError(msg)

        return v

    def print_config(self) -> None:
        """Print server configuration for user verification."""
        print("\n\n✅ Environment variables loaded for server:\n")
        print(f"GOOGLE_CLOUD_PROJECT:  {self.google_cloud_project}")
        print(f"GOOGLE_CLOUD_LOCATION: {self.google_cloud_location}")
        print(f"AGENT_NAME:            {self.agent_name}")
        print(f"LOG_LEVEL:             {self.log_level}")
        print(f"SERVE_WEB_INTERFACE:   {self.serve_web_interface}")
        print(f"RELOAD_AGENTS:         {self.reload_agents}")
        print(f"SESSION_SERVICE_URI:   {self.session_service_uri}")
        print(f"MEMORY_SERVICE_URI:    {self.memory_service_uri}")
        print(f"ARTIFACT_SERVICE_URI:  {self.artifact_service_uri}")
        print(f"HOST:                  {self.host}")
        print(f"PORT:                  {self.port}")
        print(f"ALLOW_ORIGINS:         {self.allow_origins}")
        print(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "
            f"{self.otel_instrumentation_genai_capture_message_content}\n\n"
        )

    @property
    def allow_origins_list(self) -> list[str]:
        """Parse allow_origins JSON string to list.

        Returns:
            List of allowed origin strings
        """
        result = json.loads(self.allow_origins)
        # Should never fail due to field_validator, but satisfies type checker
        if not isinstance(result, list):  # pragma: no cover
            msg = "Invalid allow_origins format"
            raise TypeError(msg)
        return result


class TelemetryEnv(BaseSettings):
    """Environment configuration for OpenTelemetry export and resource identity.

    Resolves each signal's OTLP gRPC endpoint: traces and logs fall back to the
    Google Cloud Telemetry API. Metrics without a collector go to the Telemetry API
    only when the resource has ``cloud.region``, which ``telemetry.py`` decides. An
    empty string counts as unset.

    Attributes:
        otel_sdk_disabled: Turn off all export (the OpenTelemetry SDK off switch)
        otel_exporter_otlp_endpoint: Collector endpoint for every signal
        otel_exporter_otlp_traces_endpoint: Collector endpoint for traces only
        otel_exporter_otlp_logs_endpoint: Collector endpoint for logs only
        otel_exporter_otlp_metrics_endpoint: Collector endpoint for metrics only
        telemetry_api_endpoint: Google Cloud Telemetry API endpoint
        otel_resource_attributes: Comma-separated key=value resource attributes that
            override the template's, parsed by the SDK resource detector (like
            service.name=my-agent,service.namespace=alice-local)
        k_service: Cloud Run service name, set by Cloud Run
        k_revision: Cloud Run revision, the OpenTelemetry service.version
        k_configuration: Cloud Run configuration name, set by Cloud Run
        cloud_run_region: Cloud Run region, set by Terraform; becomes cloud.region
    """

    otel_sdk_disabled: bool = Field(
        default=False,
        description="Disable the OpenTelemetry SDK: no-op providers, no export",
    )

    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        description="OTLP gRPC collector endpoint for every signal",
    )

    otel_exporter_otlp_traces_endpoint: str | None = Field(
        default=None,
        description="OTLP gRPC collector endpoint for traces",
    )

    otel_exporter_otlp_logs_endpoint: str | None = Field(
        default=None,
        description="OTLP gRPC collector endpoint for logs",
    )

    otel_exporter_otlp_metrics_endpoint: str | None = Field(
        default=None,
        description="OTLP gRPC collector endpoint for metrics",
    )

    telemetry_api_endpoint: str = Field(
        default=TELEMETRY_API_ENDPOINT,
        description="Google Cloud Telemetry API endpoint",
    )

    otel_resource_attributes: str | None = Field(
        default=None,
        description=(
            "Comma-separated key=value resource attributes, like "
            "service.name=my-agent,service.namespace=alice-local"
        ),
    )

    k_service: str | None = Field(
        default=None,
        description="Cloud Run service name, set by Cloud Run; unset off Cloud Run",
    )

    k_revision: str = Field(
        default="local",
        description="Cloud Run revision name, set by Cloud Run; unset means local",
    )

    k_configuration: str | None = Field(
        default=None,
        description="Cloud Run configuration name, set by Cloud Run",
    )

    cloud_run_region: str | None = Field(
        default=None,
        description="Cloud Run region, set by Terraform on the service",
    )

    model_config = SettingsConfigDict(
        # .env also carries variables other readers own (ADK, compose, the genai SDK)
        extra="ignore",
        env_ignore_empty=True,
    )

    @model_validator(mode="after")
    def require_cloud_run_identity(self) -> Self:
        """Require every Cloud Run resource label once K_SERVICE is set."""
        if self.k_service is not None and (
            self.k_configuration is None or self.cloud_run_region is None
        ):
            msg = (
                "K_SERVICE is set, so K_CONFIGURATION and CLOUD_RUN_REGION are "
                "required to place telemetry on the cloud_run_revision resource"
            )
            raise ValueError(msg)
        return self

    @property
    def traces_endpoint(self) -> str:
        """Traces endpoint: signal var, then generic var, then the Telemetry API."""
        return (
            self.otel_exporter_otlp_traces_endpoint
            or self.otel_exporter_otlp_endpoint
            or self.telemetry_api_endpoint
        )

    @property
    def logs_endpoint(self) -> str:
        """Logs endpoint: signal var, then generic var, then the Telemetry API."""
        return (
            self.otel_exporter_otlp_logs_endpoint
            or self.otel_exporter_otlp_endpoint
            or self.telemetry_api_endpoint
        )

    @property
    def metrics_endpoint(self) -> str | None:
        """Metrics collector endpoint: signal var, then generic var, else None."""
        return (
            self.otel_exporter_otlp_metrics_endpoint or self.otel_exporter_otlp_endpoint
        )

    def print_config(self) -> None:
        """Print telemetry destinations and identity for user verification."""
        print("✅ Telemetry configuration:\n")
        if self.otel_sdk_disabled:
            print("OTEL_SDK_DISABLED:     true (no telemetry export)")
        else:
            print(f"TRACES ENDPOINT:       {self.traces_endpoint}")
            print(f"LOGS ENDPOINT:         {self.logs_endpoint}")
            metrics = self.metrics_endpoint or (
                f"{self.telemetry_api_endpoint} when cloud.region is set, else off"
            )
            print(f"METRICS ENDPOINT:      {metrics}")
        print(f"OTEL_RESOURCE_ATTRIBUTES: {self.otel_resource_attributes}")
        print(f"K_SERVICE:             {self.k_service}")
        print(f"K_REVISION:            {self.k_revision}")
        print(f"K_CONFIGURATION:       {self.k_configuration}")
        print(f"CLOUD_RUN_REGION:      {self.cloud_run_region}\n\n")


def _validated[T: (ServerEnv, TelemetryEnv)](settings_class: type[T]) -> T:
    """Build and print a settings model, exiting with code 1 when it is invalid."""
    try:
        settings = settings_class()
    except ValidationError as e:
        print("\n❌ Environment validation failed:\n")
        print(e)
        sys.exit(1)
    settings.print_config()
    return settings


def initialize_environment() -> tuple[ServerEnv, TelemetryEnv]:
    """Load ``.env``, then validate and print the server and telemetry settings.

    ``load_dotenv()`` searches upward from this package for ``.env`` and never
    overrides a variable already set, so the shell and the platform win.

    Returns:
        Validated server and telemetry configuration.

    Raises:
        SystemExit: Exits with code 1 if either model fails validation.
    """
    load_dotenv()
    return _validated(ServerEnv), _validated(TelemetryEnv)
