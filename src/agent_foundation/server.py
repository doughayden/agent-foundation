"""FastAPI server module.

This module provides a FastAPI server for ADK agents with comprehensive observability
features using custom OpenTelemetry setup. Includes an optional ADK web interface for
interactive agent testing.

The custom observability setup coexists with ADK's internal telemetry infrastructure,
enabling simultaneous ADK web UI traces and Google Cloud observability.
"""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from .utils import (
    ServerEnv,
    configure_otel_resource,
    initialize_environment,
    setup_opentelemetry,
)

# Load and validate environment configuration
env = initialize_environment(ServerEnv)

# Configure OpenTelemetry resource attributes environment variable
# This must happen before ADK creates its TracerProvider
configure_otel_resource(
    agent_name=env.agent_name,
    project_id=env.google_cloud_project,
)

# Use .resolve() to handle symlinks and ensure absolute path across environments
AGENT_DIR = os.getenv("AGENT_DIR", str(Path(__file__).resolve().parent.parent))

# ADK fastapi app will set up OTel using resource attributes from env vars
app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=env.agent_engine_uri,
    artifact_service_uri=env.artifact_service_uri,
    memory_service_uri=env.agent_engine_uri,
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

    Starts the ADK agent server with full OpenTelemetry observability using
    custom setup for trace correlation and Google Cloud export. Features include:
    - Environment variable loading and validation via Pydantic
    - Custom OpenTelemetry setup with trace correlation and Google Cloud export
    - Optional ADK web interface for interactive agent testing
    - Session and memory persistence with Agent Engine
    - Cloud trace and log export
    - CORS configuration

    The custom observability setup coexists with ADK's internal telemetry,
    providing both ADK web UI traces and Google Cloud observability simultaneously.

    The server runs on the configured host and port with the ADK web interface
    (when enabled), providing interactive agent testing with full observability
    capabilities.

    Environment Variables:
        AGENT_DIR: Path to agent source directory (default: auto-detect from __file__)
        AGENT_NAME: Unique service identifier (required for observability)
        GOOGLE_CLOUD_PROJECT: GCP Project ID for trace and log export (required)
        GOOGLE_CLOUD_LOCATION: Vertex AI region (default: us-central1)
        LOG_LEVEL: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        SERVE_WEB_INTERFACE: Whether to serve the web interface (true/false)
        RELOAD_AGENTS: Whether to reload agents on file changes (true/false)
        AGENT_ENGINE: Agent Engine instance for session and memory
        ARTIFACT_SERVICE_URI: GCS bucket for artifact storage
        ALLOW_ORIGINS: JSON array string of allowed CORS origins
        HOST: Server host (default: 127.0.0.1, set to 0.0.0.0 for containers)
        PORT: Server port (default: 8000)
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: OpenTelemetry capture
    """
    # Add our Cloud exporters and logging to ADK's TracerProvider
    setup_opentelemetry(
        project_id=env.google_cloud_project,
        agent_name=env.agent_name,
        log_level=env.log_level,
    )

    uvicorn.run(
        app,
        host=env.host,
        port=env.port,
    )

    return


if __name__ == "__main__":
    main()
