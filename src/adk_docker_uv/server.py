"""FastAPI server module."""

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from .utils import parse_json_list_env, setup_file_logging

# Load environment variables
load_dotenv(override=True)

# AGENT_DIR: Configurable via env var for flexibility across environments
# Default: Use file-relative path (works in editable installs, Docker, and CI)
# Override: Set AGENT_DIR env var for custom deployments
AGENT_DIR = os.getenv("AGENT_DIR", str(Path(__file__).parent.parent))
AGENT_ENGINE_URI = os.getenv("AGENT_ENGINE_URI")
ARTIFACT_SERVICE_URI = os.getenv("ARTIFACT_SERVICE_URI")
ALLOWED_ORIGINS = parse_json_list_env(
    env_key="ALLOWED_ORIGINS",
    default='["http://localhost", "http://localhost:8000"]',
)
SERVE_WEB_INTERFACE = os.getenv("SERVE_WEB_INTERFACE", "false").lower() == "true"

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=AGENT_ENGINE_URI,
    artifact_service_uri=ARTIFACT_SERVICE_URI,
    memory_service_uri=AGENT_ENGINE_URI,
    allow_origins=ALLOWED_ORIGINS,
    web=SERVE_WEB_INTERFACE,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint for container orchestration.

    Returns:
        dict with status key indicating service health
    """
    return {"status": "ok"}


def main() -> None:
    """Main function to run a local agent.

    Provides a local development environment for testing agents.
    Features include:
    - Local web interface for agent interaction
    - Session and memory persistence with Agent Engine
    - CORS configuration for localhost development

    The function starts a local web server with the ADK web interface,
    allowing interactive agent testing.

    Environment Variables:
        AGENT_DIR: Path to agent source directory (default: auto-detect from __file__)
        LOG_LEVEL: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
        SERVE_WEB_INTERFACE: Whether to serve the web interface (true/false)
        AGENT_ENGINE_URI: Agent Engine instance for session and memory
        ARTIFACT_SERVICE_URI: GCS bucket for artifact storage
        ALLOWED_ORIGINS: JSON array string of allowed CORS origins
        HOST: Server host (default: localhost, set to 0.0.0.0 for containers)
        PORT: Server port (default: 8000)
    """
    setup_file_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))

    uvicorn.run(
        app,
        host=os.getenv("HOST", "localhost"),
        port=int(os.getenv("PORT", 8000)),
    )

    return


if __name__ == "__main__":
    main()
