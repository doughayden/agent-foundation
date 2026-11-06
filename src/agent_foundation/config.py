"""Environment configuration for the server.

``initialize_environment()`` loads a ``.env`` file into ``os.environ`` without
overriding variables already set, then ``ServerEnv`` reads the environment. A value
set in the shell or by the platform is never replaced by a stale local file, and
every reader of ``os.environ`` (ADK, the OpenTelemetry SDK) sees the ``.env``
values.
"""

import json
import sys
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings


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


def initialize_environment() -> ServerEnv:
    """Load ``.env``, then validate and print the server settings.

    ``load_dotenv()`` searches upward from this package for ``.env`` and never
    overrides a variable already set, so the shell and the platform win.

    Returns:
        Validated server configuration.

    Raises:
        SystemExit: Exits with code 1 if validation fails.
    """
    load_dotenv()
    try:
        env = ServerEnv()
    except ValidationError as e:
        print("\n❌ Environment validation failed:\n")
        print(e)
        sys.exit(1)
    env.print_config()
    return env
