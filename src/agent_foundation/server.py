"""FastAPI server module.

This module provides a FastAPI server for ADK agents with OpenTelemetry traces, logs
and metrics. Includes an optional ADK web interface for interactive agent testing.

Telemetry is configured before ``get_fast_api_app()`` so the application owns every
provider and the web UI's processors attach to them.
"""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from .config import initialize_environment
from .telemetry import configure_telemetry

# Load and validate environment configuration
env = initialize_environment()

configure_telemetry(
    service_name=env.agent_name,
    project_id=env.google_cloud_project,
    log_level=env.log_level,
)

# Use .resolve() to handle symlinks and ensure absolute path across environments
AGENT_DIR = os.getenv("AGENT_DIR", str(Path(__file__).resolve().parent.parent))

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=env.session_service_uri,
    artifact_service_uri=env.artifact_service_uri,
    memory_service_uri=env.memory_service_uri,
    allow_origins=env.allow_origins_list,
    web=env.serve_web_interface,
    reload_agents=env.reload_agents,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint for container orchestration.

    Returns:
        dict with status key indicating service health
    """
    return {"status": "ok"}


def main() -> None:
    """Run the FastAPI server with comprehensive observability.

    Starts the ADK agent server configured at import time. Features include:
    - Environment variable loading and validation via Pydantic
    - OpenTelemetry traces, logs and metrics over OTLP to Google Cloud
    - Optional ADK web interface for interactive agent testing
    - Session persistence with Cloud SQL via DatabaseSessionService
    - Memory persistence with Agent Engine
    - CORS configuration

    The server runs on the configured host and port with the ADK web interface
    (when enabled), providing interactive agent testing with full observability
    capabilities.

    Environment Variables:
        AGENT_DIR: Path to agent source directory (default: auto-detect from __file__)
        AGENT_NAME: Unique service identifier (required for observability)
        GOOGLE_CLOUD_PROJECT: GCP Project ID for trace and log export (required)
        GOOGLE_CLOUD_LOCATION: Vertex AI model endpoint location (default: global)
        LOG_LEVEL: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        SERVE_WEB_INTERFACE: Whether to serve the web interface (true/false)
        RELOAD_AGENTS: Whether to reload agents on file changes (true/false)
        SESSION_SERVICE_URI: Session service URI (e.g., postgresql+asyncpg://user@host:5432/db)
        MEMORY_SERVICE_URI: Memory service URI (e.g., agentengine://...)
        ARTIFACT_SERVICE_URI: GCS bucket for artifact storage
        ALLOW_ORIGINS: JSON array string of allowed CORS origins
        HOST: Server host (default: 127.0.0.1, set to 0.0.0.0 for containers)
        PORT: Server port (default: 8000)
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: GenAI content capture mode
    """
    uvicorn.run(
        app,
        host=env.host,
        port=env.port,
    )

    return


if __name__ == "__main__":
    main()
