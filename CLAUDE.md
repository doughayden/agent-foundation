# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an ADK (Agent Development Kit) application containerized with Docker and optimized with `uv` package manager. The project demonstrates best practices for deploying Google ADK agents in production using multi-stage Docker builds, hot reloading for local development, and strict code quality standards.

**Key technologies:**
- **Google ADK**: Agent framework for LLM-powered applications using Gemini models
- **FastAPI**: Web server for agent API and optional web UI
- **uv**: Modern Python package manager with PEP 735 dependency groups
- **Docker**: Multi-stage builds with BuildKit cache optimization
- **Python 3.13**: Modern syntax with strict type checking

## Development Commands

### Running Locally

```bash
# Setup (one-time)
cp .env.example .env
# Edit .env and choose ONE authentication method:
#   - GOOGLE_API_KEY for Gemini Developer API
#   - GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION for Vertex AI

# Run server (default: API-only at http://localhost:8000)
uv run server

# Enable web UI (set SERVE_WEB_INTERFACE=true in .env)

# Debug mode with detailed logging
LOG_LEVEL=DEBUG uv run server
```

### Docker Compose (Recommended for Local Development)

```bash
# Start with hot reloading (changes to src/ sync instantly)
docker compose up --build --watch

# Stop
docker compose down

# View logs
docker compose logs -f app
```

**Watch mode behavior:**
- `src/` changes → instant sync (no rebuild)
- `pyproject.toml` or `uv.lock` changes → automatic rebuild

### Code Quality

```bash
# Format code
uv run ruff format

# Lint code
uv run ruff check

# Type check
uv run mypy

# Run all checks (one-liner)
uv run ruff format && uv run ruff check && uv run mypy
```

### Testing

```bash
# Run all tests
uv run pytest -v

# Run tests with coverage (100% required on non-excluded files)
uv run pytest --cov --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_context.py -v

# Run specific test function
uv run pytest tests/test_context.py::test_load_success -v
```

## Architecture

### ADK Agent Structure

The agent is configured in `src/adk_docker_uv/agent.py`:

```
root_agent (LlmAgent)
  ├── Model: gemini-2.5-flash (configurable via ROOT_AGENT_MODEL env var)
  ├── Tools: Custom tools from tools.py + PreloadMemoryTool
  └── Callbacks: LoggingCallbacks + add_session_to_memory
```

**Key components:**
- **agent.py**: LlmAgent configuration with callbacks
- **tools.py**: Custom tools for the agent
- **callbacks.py**: Lifecycle callbacks for logging and memory persistence (all return `None`)
- **prompt.py**: Agent instructions and descriptions (includes InstructionProvider pattern)
- **server.py**: FastAPI server with ADK integration
- **utils/env_parser.py**: Environment variable parsing utilities with validation

### FastAPI Server

The server (`src/adk_docker_uv/server.py`) provides:
- ADK agent API endpoints via `get_fast_api_app()`
- Optional web UI (controlled by `SERVE_WEB_INTERFACE` env var)
- Health check endpoint at `/health`
- Configurable CORS for localhost development

**Entry point:** `python -m adk_docker_uv.server` (calls `main()` which sets up logging and starts uvicorn)

### Multi-Stage Docker Build

The Dockerfile uses a two-stage build strategy:

1. **Builder stage** (`python:3.13-slim` + uv binary):
   - Copies uv binary from `ghcr.io/astral-sh/uv:0.9.6`
   - Installs dependencies with cache mount (`--mount=type=cache,target=/root/.cache/uv`)
   - Uses `--locked` flag to validate lockfile matches pyproject.toml
   - Separates dependency installation (`--no-install-project`) from code copy for optimal caching
   - Source code changes trigger ~5-10s rebuild (only install layer)

2. **Runtime stage** (clean `python:3.13-slim`):
   - Copies only `.venv` and source code from builder
   - Runs as non-root user (`app:app`)
   - Binds to `0.0.0.0:8000` for container networking
   - Final image: ~200MB (vs ~500MB single-stage)

**Key optimizations:**
- Cache mount persists `/root/.cache/uv` across builds (~80% speedup)
- Dependency layer rebuilds only when `pyproject.toml` or `uv.lock` changes
- Code layer rebuilds only when `src/` changes
- Documentation updates (README.md) don't trigger rebuilds (empty README created at build time)

See `docs/dockerfile-strategy.md` for detailed rationale.

### Logging

**File logging** (local development and Docker):
- Location: `.log/app.log`
- Rotation: 1 MB max size, 5 backup files
- Format: `[{asctime}] [{process}] [{levelname:>8}] [{name}.{funcName}:{lineno:>5}] {message}`
- Control: `LOG_LEVEL` env var (DEBUG, INFO, WARNING, ERROR)

**Callback logging:**
- `LoggingCallbacks` class in `callbacks.py` provides comprehensive lifecycle logging
- Logs agent start/end, LLM calls, tool invocations with full context
- Supports logger injection for testing

## Code Quality Standards

### Type Checking

**Strict mypy configuration** with comprehensive checks enabled:
- All functions must have complete type annotations
- Modern Python 3.13 syntax: `|` for unions, lowercase generics (`list[str]`)
- No untyped definitions or decorators allowed
- Pydantic models provide runtime validation

### Linting and Formatting

**Ruff configuration:**
- Line length: 88 characters (Black-compatible)
- Auto-fix enabled
- Enforces: pycodestyle, pyflakes, isort, flake8-bugbear, pyupgrade, pep8-naming, flake8-bandit, flake8-simplify, flake8-use-pathlib
- **Always use `Path` objects** for file operations (never `os.path`)

### Testing

**Requirements:**
- 100% coverage on all production code (excludes: `server.py`, `agent.py`)
- Tests organized by feature in separate files
- Shared fixtures in `conftest.py` (reusable, eliminates patching in individual tests)
- Duck-typed mocks that satisfy ADK protocols
- Async test support via pytest-asyncio

**Test patterns:**
- Use pytest's `capsys` fixture for capturing and validating stdout/stderr
- Use `patch.dict(os.environ, ...)` for environment variable testing
- Validate both success cases and error handling (invalid input, missing values, type mismatches)

## Environment Variables

### Required (choose ONE authentication method)

**Option 1: Gemini Developer API**
```bash
GOOGLE_API_KEY=your_api_key_here
```

**Option 2: Vertex AI (default)**
```bash
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
# Requires: gcloud auth application-default login
```

### Optional Configuration

```bash
# Enable web UI (default: false)
SERVE_WEB_INTERFACE=true

# Logging level (default: INFO)
LOG_LEVEL=DEBUG

# Server configuration (defaults: HOST=localhost, PORT=8000)
# Note: Dockerfile overrides HOST=0.0.0.0 for container networking
HOST=localhost
PORT=8000

# Override default agent model (default: gemini-2.5-flash)
ROOT_AGENT_MODEL=gemini-2.5-flash

# Session/memory persistence via Agent Engine (default: in-memory ephemeral)
AGENT_ENGINE_URI=agentengine://projects/123/locations/us-central1/reasoningEngines/456

# Artifact storage via GCS bucket (default: in-memory ephemeral)
ARTIFACT_SERVICE_URI=gs://your-artifact-storage-bucket

# CORS allowed origins (JSON array string)
# Parsed with validation and fallback to localhost defaults
# Invalid JSON falls back to default with warning
ALLOWED_ORIGINS='["https://your-domain.com", "http://localhost:3000"]'
```

## Dependency Management

**Standard workflow:**
```bash
# Add runtime dependency
uv add package-name

# Add dev dependency
uv add --group dev package-name

# Update all dependencies
uv lock --upgrade

# Update specific package
uv lock --upgrade-package package-name
```

**IMPORTANT: Version bump workflow** (see `~/.claude/rules/python-projects.md`):
1. Update `version` in `pyproject.toml`
2. **MUST run `uv lock`** to update lockfile
3. Commit both files together

**Why:** CI uses `uv sync --locked` which validates lockfile matches pyproject.toml and fails if out of sync.

## CI/CD

GitHub Actions workflows in `.github/workflows/`:
- **code-quality.yml**: Runs ruff format, ruff check, mypy
- **docker-build-push.yml**: Builds and pushes Docker images to registry
- **required-checks.yml**: Composite checks for branch protection

## Project-Specific Patterns

### Adding Custom Tools

Create tools in `src/adk_docker_uv/tools.py` and register in `agent.py`:

```python
from google.adk.tools import Tool

my_tool = Tool(
    name="my_tool",
    description="Tool description for LLM",
    func=my_tool_function,
)

# Add to root_agent.tools list in agent.py
```

### Agent Callbacks

The project uses callback pattern for cross-cutting concerns:
- `LoggingCallbacks`: Lifecycle logging at all stages
- `add_session_to_memory`: Automatic session persistence to memory service

All callbacks in this project return `None` and are non-intrusive (they only observe, not modify the agent flow).

### InstructionProvider Pattern

Uses ADK's InstructionProvider pattern for dynamic instruction generation at request time (enables current dates, session-aware customization).

**Signature:** `def instruction_provider(ctx: ReadonlyContext) -> str`
- Pass function reference to `LlmAgent(global_instruction=func)`, not a call
- `ctx` provides: `state` (read-only session), `agent_name`, `invocation_id`, `user_content`, `session`

**Testing:** Use `MockReadonlyContext` from `tests/conftest.py`. See `prompt.py` and `test_prompt.py` for examples.

### Environment Variable Parsing

Use `parse_json_list_env()` from `utils.env_parser` for safe JSON list parsing:

```python
from adk_docker_uv.utils import parse_json_list_env

# Parses JSON array with validation and fallback
origins = parse_json_list_env(
    env_key="ALLOWED_ORIGINS",
    default='["http://localhost"]',
)
```

**Features:**
- Validates both environment value and default are JSON arrays of strings
- Falls back to default on invalid JSON with warning to stdout
- Raises ValueError on invalid default (fail-fast at startup)
- Type-safe return type (`list[str]`) using TypeGuard

### Docker Compose Development

**File locations in container:**
- Source code: `/app/src` (synced from `./src`)
- Data directory: `/app/data` (mounted from `./data`, read-only)
- Logs: `/app/.log` (mounted from `./.log`, read-write)
- GCP credentials: `/gcloud/application_default_credentials.json` (mounted from `~/.config/gcloud/`)

**Note for Windows:** Update volume path in `docker-compose.yml` for GCP credentials (see comments in file).

**Security:** The compose file binds to `127.0.0.1:8000` (localhost only) to prevent external network access. To allow access from other machines, change to `8000:8000`, but this is not recommended for development with sensitive data.

### Testing Registry Images

Test exact CI/CD artifacts locally:

```bash
# One-time: Authenticate to registry
gcloud auth configure-docker <registry-location>-docker.pkg.dev

# Set image name and pull
export REGISTRY_IMAGE="<location>-docker.pkg.dev/<project>/<repo>/<image>:latest"
docker pull $REGISTRY_IMAGE

# Run with registry override
docker compose -f docker-compose.yml -f docker-compose.registry.yml up
```

Container runs with `-registry` suffix to distinguish from locally-built images.

## Documentation

- **README.md**: Quickstart and overview
- **docs/development.md**: Development workflows, code quality, testing
- **docs/docker-compose-workflow.md**: Hot reloading and local development
- **docs/dockerfile-strategy.md**: Multi-stage build architecture and rationale
- **docs/github-docker-setup.md**: CI/CD setup for Docker builds
