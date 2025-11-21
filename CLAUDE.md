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

### Terraform Infrastructure Setup (One-Time)

Initialize GCP and GitHub resources with Terraform:

```bash
# Configure .env with required values:
# - AGENT_NAME
# - GOOGLE_CLOUD_PROJECT
# - GOOGLE_CLOUD_LOCATION
# - GITHUB_REPO_NAME
# - GITHUB_REPO_OWNER

# Initialize Terraform and select workspace (run from repo root)
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap workspace select sandbox  # or: workspace new sandbox

# Preview changes
terraform -chdir=terraform/bootstrap plan

# Apply infrastructure
terraform -chdir=terraform/bootstrap apply

# Outputs include WIF provider name, registry URI, reasoning engine ID
```

The bootstrap module creates:
- Workload Identity Federation for GitHub Actions
- Artifact Registry repository with cleanup policies
- Vertex AI Reasoning Engine for session/memory
- GitHub Actions Variables (auto-configured)

### Template Initialization (One-Time)

If this repo was created from the template, initialize it first:

```bash
uv run init_template.py --dry-run  # Preview changes
uv run init_template.py            # Apply changes
```

Script renames package, updates config/docs, updates GitHub Actions badges, resets CODEOWNERS file, resets version to 0.1.0, resets changelog. Creates audit log at `init_template_results.md` (gitignored).

### Running Locally

```bash
# Setup (one-time)
cp .env.example .env
# Edit .env and choose ONE authentication method:
#   - GOOGLE_API_KEY for Gemini Developer API
#   - GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION for Vertex AI

# Run server (default: API-only at http://127.0.0.1:8000)
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

# Server configuration (defaults: HOST=127.0.0.1, PORT=8000)
# Note: Dockerfile overrides HOST=0.0.0.0 for container networking
HOST=127.0.0.1
PORT=8000

# Enable agent hot reloading on file changes (default: false)
# Development-only: enables file watching for .py and .yaml changes
RELOAD_AGENTS=true

# Override default agent model (default: gemini-2.5-flash)
ROOT_AGENT_MODEL=gemini-2.5-flash

# Session/memory persistence via Agent Engine (default: in-memory ephemeral)
# Note: URI prefix "agentengine://" is added automatically in code
AGENT_ENGINE=projects/123/locations/us-central1/reasoningEngines/456

# Artifact storage via GCS bucket (default: in-memory ephemeral)
ARTIFACT_SERVICE_URI=gs://your-artifact-storage-bucket

# CORS allowed origins (JSON array string)
# Parsed with validation and fallback to localhost defaults
# Invalid JSON falls back to default with warning
ALLOWED_ORIGINS='["https://your-domain.com", "http://127.0.0.1:3000"]'
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

**Authentication:** Workflows use Workload Identity Federation (no service account keys). Configuration managed by Terraform.

**GitHub Variables vs Secrets:**
- **Variables**: Non-sensitive identifiers (GCP_PROJECT_ID, GCP_WORKLOAD_IDENTITY_PROVIDER, ARTIFACT_REGISTRY_URI, IMAGE_NAME, ARTIFACT_REGISTRY_LOCATION)
- **Secrets**: Actual credentials only (not used with WIF - OIDC tokens provide authentication)
- Rationale: Identifiers are not secrets; GCP security model relies on IAM policies, not obscurity

## Terraform Infrastructure

The project includes two Terraform modules for infrastructure management:

### Bootstrap Module (`terraform/bootstrap/`)

**Purpose:** Initial infrastructure setup and GitHub Actions integration.

**Resources created:**
- `google_iam_workload_identity_pool`: WIF pool for GitHub Actions
- `google_iam_workload_identity_pool_provider`: GitHub OIDC provider with repository attribute condition
- `google_project_iam_member`: Direct principal binding (no service account impersonation)
- `google_artifact_registry_repository`: Docker repository with cleanup policies
- `google_vertex_ai_reasoning_engine`: Session and memory persistence service
- `github_actions_variable`: Auto-configured Variables from Terraform outputs

**Cleanup policies:**
1. Delete untagged images (intermediate layers)
2. Delete tagged images older than 30 days
3. **EXCEPT** keep 5 most recent versions (regardless of age)
4. **EXCEPT** keep buildcache indefinitely (critical for fast builds)

**Configuration:** Reads from `.env` file using `dotenv` provider, supports variable overrides.

**IAM roles granted to GitHub Actions:**
- `roles/aiplatform.user`: Vertex AI access
- `roles/artifactregistry.writer`: Push Docker images

### Main Module (`terraform/main/`)

**Purpose:** Cloud Run deployment configuration.

**Resources created:**
- `google_service_account`: Cloud Run service-attached identity
- `google_project_iam_member`: Service account permissions
- `google_cloud_run_v2_service`: Cloud Run deployment with scaling and resource configuration

**Key features:**
- Environment variables sourced from `.env`
- Request-based billing (cpu_idle = true)
- Service-level scaling configuration with max instances (100) and configurable min instances
- Health probes with TCP socket check on port 8000
- Production safety: `RELOAD_AGENTS` explicitly set to false

**Optional variable:** `docker_image` - Image URI from Artifact Registry (nullable with default for infrastructure-only applies)

### Terraform Naming Conventions

- **Variable naming**: Use `project` (not `project_id`) for GCP project identifier
- **Local variables**: Prefer descriptive names (`local.agent_name`, `local.location`)
- **Resource IDs**: Use `agent_name` as base for consistent naming across resources

### Running Terraform

**Workspace pattern:** Both modules use the `-chdir` flag (run from repo root) and workspace isolation.

```bash
# Bootstrap module (one-time setup)
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap workspace select sandbox  # or create: workspace new sandbox
terraform -chdir=terraform/bootstrap plan
terraform -chdir=terraform/bootstrap apply

# Main module (deployment updates)
terraform -chdir=terraform/main init
terraform -chdir=terraform/main workspace select sandbox
terraform -chdir=terraform/main plan -var="docker_image=<registry-uri>/<image>:tag"
terraform -chdir=terraform/main apply -var="docker_image=<registry-uri>/<image>:tag"
```

**Current workspaces:** Both `bootstrap` and `main` modules use `sandbox` workspace (example only - use any workspace name).

**Docker image recycling pattern:** The `main` module reads its own prior state (`data.terraform_remote_state.main`) to "recycle" the `docker_image` value from the last deployment. This allows infrastructure-only updates (scaling, env vars) without requiring the image URI to be passed explicitly. The `docker_image` variable uses `coalesce()` to fall back to the previous deployment's image if not provided.

**State management:** Backend configs are commented out by default (uses local state). For production, uncomment `backend.tf` and configure GCS bucket for state storage. When switching to GCS backend, also update the `data.terraform_remote_state.main` backend configuration to match.

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
    default='["http://127.0.0.1"]',
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
