"""Environment configuration for the server.

``ServerEnv`` reads the process environment, then a ``.env`` file in the working
directory. The environment wins over ``.env``, so a value set in the shell or by the
platform is never replaced by a stale local file.
"""

import json
import sys
from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerEnv(BaseSettings):
    """Environment configuration for local server development and deployment.

    Provides configuration for both local development and Cloud Run deployment,
    with sensible defaults for local development.

    Attributes:
        google_cloud_project: GCP project ID for authentication and observability
        google_cloud_location: Vertex AI region (e.g., us-central1)
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
        otel_instrumentation_genai_capture_message_content: Capture LLM content in
            OpenTelemetry spans
        telemetry_namespace: OpenTelemetry service.namespace (environment grouping)
        k_revision: Cloud Run revision, the OpenTelemetry service.version
    """

    google_cloud_project: str = Field(
        ...,
        description="GCP project ID for authentication and observability",
    )

    google_cloud_location: str = Field(
        default="us-central1",
        description="Vertex AI region (e.g., us-central1)",
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

    otel_instrumentation_genai_capture_message_content: bool = Field(
        ...,
        description="OpenTelemetry message content capture setting",
    )

    telemetry_namespace: str = Field(
        default="local",
        description="OpenTelemetry service.namespace that groups traces by environment",
    )

    k_revision: str = Field(
        default="local",
        description="Cloud Run revision name, set by Cloud Run; unset means local",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
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
            f"{self.otel_instrumentation_genai_capture_message_content}"
        )
        print(f"TELEMETRY_NAMESPACE:   {self.telemetry_namespace}")
        print(f"K_REVISION:            {self.k_revision}\n\n")

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


def initialize_environment() -> ServerEnv:
    """Validate ``ServerEnv`` and print it, exiting on invalid configuration.

    Returns:
        Validated environment configuration.

    Raises:
        SystemExit: Exits with code 1 if validation fails.
    """
    try:
        env = ServerEnv()
    except ValidationError as e:
        print("\n❌ Environment validation failed:\n")
        print(e)
        sys.exit(1)

    env.print_config()
    return env
