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

# Use .resolve() to handle symlinks and ensure absolute path across environments
AGENT_DIR = os.getenv("AGENT_DIR", str(Path(__file__).resolve().parent.parent))
AGENT_ENGINE = os.getenv("AGENT_ENGINE")
AGENT_ENGINE_URI = f"agentengine://{AGENT_ENGINE}" if AGENT_ENGINE else None
ARTIFACT_SERVICE_URI = os.getenv("ARTIFACT_SERVICE_URI")
ALLOWED_ORIGINS = parse_json_list_env(
    env_key="ALLOWED_ORIGINS",
    default='["http://127.0.0.1", "http://127.0.0.1:8000"]',
)
SERVE_WEB_INTERFACE = os.getenv("SERVE_WEB_INTERFACE", "false").lower() == "true"
RELOAD_AGENTS = os.getenv("RELOAD_AGENTS", "false").lower() == "true"

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=AGENT_ENGINE_URI,
    artifact_service_uri=ARTIFACT_SERVICE_URI,
    memory_service_uri=AGENT_ENGINE_URI,
    allow_origins=ALLOWED_ORIGINS,
    web=SERVE_WEB_INTERFACE,
    reload_agents=RELOAD_AGENTS,
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
        RELOAD_AGENTS: Whether to reload agents on file changes (true/false)
        AGENT_ENGINE: Agent Engine instance for session and memory
        ARTIFACT_SERVICE_URI: GCS bucket for artifact storage
        ALLOWED_ORIGINS: JSON array string of allowed CORS origins
        HOST: Server host (default: 127.0.0.1, set to 0.0.0.0 for containers)
        PORT: Server port (default: 8000)
    """
    # Use /tmp for logs in Cloud Run (read-only filesystem), .log for local dev
    log_dir = "/tmp" if os.getenv("K_SERVICE") else ".log"  # noqa: S108
    setup_file_logging(log_level=os.getenv("LOG_LEVEL", "INFO"), log_dir=log_dir)

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 8000)),
    )

    return


if __name__ == "__main__":
    main()
