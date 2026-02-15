"""Environment configuration models for application settings.

This module provides Pydantic models for type-safe environment variable validation
and configuration management.
"""

import json
import os
import sys
from typing import Literal

from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)


def initialize_environment[T: BaseModel](
    model_class: type[T],
    override_dotenv: bool = True,
    print_config: bool = True,
) -> T:
    """Initialize and validate environment configuration.

    Factory function that handles the common initialization pattern: load environment
    variables, validate with Pydantic model, handle errors, and optionally print
    configuration.

    Args:
        model_class: Pydantic model class to validate environment with.
        override_dotenv: Whether to override existing environment variables.
            Defaults to True for consistency and predictability.
        print_config: Whether to call print_config() method if it exists.
            Defaults to True.

    Returns:
        Validated environment configuration instance.

    Raises:
        SystemExit: If validation fails.

    Examples:
        >>> # Simple case (most common)
        >>> env = initialize_environment(ServerEnv)
        >>>
        >>> # Skip printing configuration
        >>> env = initialize_environment(ServerEnv, print_config=False)
    """
    load_dotenv(override=override_dotenv)

    # Load and validate environment configuration
    try:
        env = model_class.model_validate(os.environ)
    except ValidationError as e:
        print("\n❌ Environment validation failed:\n")
        print(e)
        sys.exit(1)

    # Print configuration for user verification if method exists
    if print_config and hasattr(env, "print_config"):
        env.print_config()

    return env


class ServerEnv(BaseModel):
    """Environment configuration for local server development and deployment.

    Provides configuration for both local development and Cloud Run deployment,
    with sensible defaults for local development.

    Attributes:
        google_cloud_project: GCP project ID for authentication and observability.
        google_cloud_location: Vertex AI region (e.g., us-central1).
        agent_name: Unique agent identifier for resources and logs.
        log_level: Logging verbosity level.
        serve_web_interface: Whether to serve the ADK web interface.
        reload_agents: Whether to reload agents on file changes (local dev only).
        agent_engine: Agent Engine instance ID for session and memory persistence.
        artifact_service_uri: GCS bucket URI for artifact storage.
        allow_origins: JSON array string of allowed CORS origins.
        host: Server host (127.0.0.1 for local, 0.0.0.0 for containers).
        port: Server port.
        otel_capture_content: OpenTelemetry message content capture setting.
    """

    google_cloud_project: str = Field(
        ...,
        alias="GOOGLE_CLOUD_PROJECT",
        description="GCP project ID for authentication and observability",
    )

    google_cloud_location: str = Field(
        default="us-central1",
        alias="GOOGLE_CLOUD_LOCATION",
        description="Vertex AI region (e.g., us-central1)",
    )

    agent_name: str = Field(
        ...,
        alias="AGENT_NAME",
        description="Unique agent identifier for resources and logs",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging verbosity level",
    )

    serve_web_interface: bool = Field(
        default=False,
        alias="SERVE_WEB_INTERFACE",
        description="Whether to serve the ADK web interface",
    )

    reload_agents: bool = Field(
        default=False,
        alias="RELOAD_AGENTS",
        description="Whether to reload agents on file changes (local dev only)",
    )

    agent_engine: str | None = Field(
        default=None,
        alias="AGENT_ENGINE",
        description="Agent Engine instance ID for session and memory persistence",
    )

    artifact_service_uri: str | None = Field(
        default=None,
        alias="ARTIFACT_SERVICE_URI",
        description="GCS bucket URI for artifact storage",
    )

    allow_origins: str = Field(
        default='["http://localhost", "http://localhost:8000"]',
        alias="ALLOW_ORIGINS",
        description=(
            "JSON array string of allowed CORS origins. "
            "Use 'localhost' for local dev (browsers send this as Origin header), "
            "not '127.0.0.1' (which OAuth clients might only allow over HTTPS)"
        ),
    )

    host: str = Field(
        default="127.0.0.1",
        alias="HOST",
        description=(
            "Network interface for uvicorn to bind. "
            "Use 127.0.0.1 (loopback) for local dev, 0.0.0.0 for containers. "
            "Note: browsers resolve localhost URLs to this IP"
        ),
    )

    port: int = Field(
        default=8000,
        alias="PORT",
        description="Server port",
    )

    otel_capture_content: bool = Field(
        ...,
        alias="OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
        description="OpenTelemetry message content capture setting",
    )

    model_config = ConfigDict(
        populate_by_name=True,  # Allow both field names and aliases
        extra="ignore",  # Ignore extra env vars (system vars, etc.)
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
        print(f"AGENT_ENGINE:          {self.agent_engine}")
        print(f"ARTIFACT_SERVICE_URI:  {self.artifact_service_uri}")
        print(f"HOST:                  {self.host}")
        print(f"PORT:                  {self.port}")
        print(f"ALLOW_ORIGINS:         {self.allow_origins}")
        print(f"OTEL_CAPTURE_CONTENT:  {self.otel_capture_content}\n\n")

    @property
    def agent_engine_uri(self) -> str | None:
        """Agent Engine URI with protocol prefix."""
        return f"agentengine://{self.agent_engine}" if self.agent_engine else None

    @property
    def allow_origins_list(self) -> list[str]:
        """Parse allow_origins JSON string to list.

        Returns:
            List of allowed origin strings.
        """
        result = json.loads(self.allow_origins)
        # Should never fail due to field_validator, but satisfies type checker
        if not isinstance(result, list):  # pragma: no cover
            msg = "Invalid allow_origins format"
            raise TypeError(msg)
        return result
