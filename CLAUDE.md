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

Initialize GCP and GitHub resources with Terraform bootstrap:

```bash
# Configure .env with required values:
# - AGENT_NAME, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
# - GITHUB_REPO_NAME, GITHUB_REPO_OWNER

# Run bootstrap (from repo root, uses local state)
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap plan
terraform -chdir=terraform/bootstrap apply

# Outputs: WIF provider, registry URI, state bucket name, GitHub Variables created
```

Bootstrap creates CI/CD infrastructure:
- Workload Identity Federation for GitHub Actions
- Artifact Registry with cleanup policies
- **GCS bucket for main module's Terraform state**
- **GitHub Actions Variables** (all CI/CD config auto-created)

**Note:** Agent Engine created by main module (in CI/CD), not bootstrap.

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
# Edit .env: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
# Auth: gcloud auth application-default login

# Run server (default: API-only at http://127.0.0.1:8000)
uv run server

# Debug mode
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

**Two-stage strategy:**
1. **Builder**: `python:3.13-slim` + uv binary, cache mount (`--mount=type=cache,target=/root/.cache/uv`), `--locked` validation, `--no-install-project` for layer optimization
2. **Runtime**: Clean slim image, non-root `app:app`, ~200MB final size

**Key optimizations:** Cache mount persists across builds (~80% speedup), dependency layer rebuilds only on `pyproject.toml`/`uv.lock` changes, code layer rebuilds only on `src/` changes. Empty README at build time prevents doc-only rebuilds.

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

**Required (GCP auth only):**
```bash
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
# Auth: gcloud auth application-default login
```

**Key optional vars:** `SERVE_WEB_INTERFACE` (web UI), `LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR), `RELOAD_AGENTS` (dev hot reload), `ROOT_AGENT_MODEL` (default: gemini-2.5-flash), `AGENT_ENGINE` (session persistence, URI prefix auto-added), `ARTIFACT_SERVICE_URI` (GCS bucket), `ALLOW_ORIGINS` (JSON array, uses `parse_json_list_env()` with validation/fallback).

See `.env.example` for complete list.

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

**Workflow pattern** in `.github/workflows/`:
- **ci-cd.yml**: Orchestrator (meta → build → deploy)
- **metadata-extract.yml**: Reusable metadata extraction workflow
- **docker-build.yml**: Reusable build workflow
- **terraform-plan-apply.yml**: Reusable Terraform deployment
- **code-quality.yml**: Runs ruff format, ruff check, mypy
- **required-checks.yml**: Composite checks for branch protection

**Workflow behavior:**
- **PR:** Build `pr-{number}-{sha}` image, run `terraform plan`, post comment
- **Main:** Build `{sha}` + `latest` + `{version}` tags, deploy by **digest** to Cloud Run
- **Tag push (`v*`):** Triggers CI/CD to build version-tagged Docker image (e.g., `v0.4.0`)
- **Deployment:** Uses image **digest** (`registry/image@sha256:...`) instead of tag, ensuring every rebuild triggers new Cloud Run revision
- **Concurrency:** PRs cancel in-progress, main runs sequentially, per-workspace Terraform locking

**Version tag trigger:** Tag push (`v*`) triggers build after release PR merged. Safe because tags point to reviewed code, only authorized users can push tags.

**Auth:** Workload Identity Federation (no service account keys), configured by Terraform bootstrap.

**GitHub Variables (auto-created by bootstrap):**
- `GCP_PROJECT_ID`, `GCP_LOCATION`, `IMAGE_NAME`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`, `ARTIFACT_REGISTRY_URI`, `ARTIFACT_REGISTRY_LOCATION`
- `TERRAFORM_STATE_BUCKET`

**Note:** These are Variables (not Secrets) - resource identifiers, not credentials. Security via IAM policies.

### GitHub Actions Job Summaries

**What:** Use `$GITHUB_STEP_SUMMARY` environment variable to display formatted summaries in GitHub Actions UI (visible on workflow run page and PR summary).

**Key patterns:**

1. **GitHub context variable export** - Export context to shell variable for bash string manipulation:
   ```bash
   GITHUB_REF="${{ github.ref }}"
   # Now bash parameter expansion works: ${GITHUB_REF#refs/tags/}
   ```
   Why: GitHub expressions (`${{ }}`) cannot be used inside bash string operations.

2. **Capture-once pattern** - Execute expensive commands (e.g., `terraform output`) once, reuse in variables:
   ```bash
   SERVICE_ACCOUNT=$(terraform output -raw email 2>/dev/null || echo "")
   if [ -n "$SERVICE_ACCOUNT" ]; then
     echo "- **Service Account:** \`${SERVICE_ACCOUNT}\`" >> $GITHUB_STEP_SUMMARY
   fi
   ```
   Why: Avoids duplicate terraform invocations in conditional checks and output lines.

3. **Defensive empty checks** - Check for empty/missing outputs before displaying:
   ```bash
   if [ -n "${{ steps.plan.outputs.stdout }}" ]; then
     # Show plan output in details block
   fi
   ```
   Why: Prevents errors and empty sections when optional outputs are missing.

4. **Conditional sections** - Include/exclude sections based on workflow context (plan vs apply, PR vs main):
   ```bash
   if [ "${{ inputs.terraform_action }}" == "apply" ]; then
     echo "| 🚀 Apply | ${icon} | outcome |" >> $GITHUB_STEP_SUMMARY
   fi
   ```

**Implementation examples:**
- **Metadata job** (metadata-extract.yml): Shows build context (event type, branch/tag, commit SHA) and image tags as bulleted list
- **Terraform job** (terraform-plan-apply.yml): Shows workspace, action, step status table, plan output, deployed resources

## Image Digest Deployment

**Critical pattern:** Deploy with immutable digest (`registry/image@sha256:...`), not mutable tag. Tags are mutable - rebuilding same tag won't trigger Cloud Run redeployment. Digests are unique per build, guaranteeing new revision.

**Workflow:** `docker-build.yml` outputs digest URI → `ci-cd.yml` passes to Terraform via `TF_VAR_docker_image` → Cloud Run deploys new revision.

**Multi-platform digests:** Manifest list digest (deployed) ≠ platform-specific digest (running). This is expected. Workflow outputs manifest list, Cloud Run pulls and selects platform (linux/amd64). Service shows manifest digest, revision shows platform digest.

See [Validating Multi-Platform Docker Builds](docs/validating-multiplatform-builds.md) for verification workflows.

## Terraform Infrastructure

**Two modules:**
1. **Bootstrap** (`terraform/bootstrap/`): One-time CI/CD setup. Creates WIF, Artifact Registry, GCS state bucket, GitHub Variables. Local state (default). Reads `.env` via dotenv provider (v1.2.9 pinned). Run from local terminal.

2. **Main** (`terraform/main/`): Cloud Run deployment. Creates service account, Vertex AI Reasoning Engine, GCS artifact bucket, Cloud Run service. Remote state in GCS. Inputs via `TF_VAR_*` (no dotenv). Runs in GitHub Actions. `docker_image` variable nullable (defaults to previous image for infra-only updates).

### Running Terraform

**Pattern:** Use `-chdir` flag (run from repo root).

```bash
# Bootstrap (one-time, local execution)
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap plan
terraform -chdir=terraform/bootstrap apply
# Creates GitHub Variables, GCS state bucket, WIF, Artifact Registry
```

**Naming conventions:** Use `project` (not `project_id`), descriptive locals (`local.agent_name`), `agent_name` base for resource IDs.

**Workspaces:** Bootstrap uses `default`, main uses workspaces for environments (default/dev/stage/prod).

**Variable overrides (CI/CD):** GitHub Actions Variables → `TF_VAR_*` env vars. `coalesce()` skips empty strings and nulls, applies defaults. Override: `log_level`, `serve_web_interface`, `allow_origins` (JSON array), `root_agent_model`, `artifact_service_uri`, `agent_engine`.

See `docs/terraform-infrastructure.md` for detailed setup and IAM patterns.

**IAM model:** Dedicated GCP project per environment. Project-level IAM roles grant access to same-project resources only. Cross-project buckets require external IAM config + `ARTIFACT_SERVICE_URI` override.

**App service account roles:** See `terraform/main/main.tf` (Vertex AI, storage, logging, tracing).
**GitHub Actions WIF roles:** See `terraform/bootstrap/main.tf` (Vertex AI, Artifact Registry, IAM, storage).

**Cloud Run startup probe:** Must allow time for credential initialization (~30-60s). Config: `failure_threshold=5, period_seconds=20, initial_delay_seconds=20, timeout_seconds=15`, HTTP `/health` endpoint. Total window: 120s. Aggressive config causes DEADLINE_EXCEEDED with no logs. Debug: Test locally first (`docker compose up`), if works locally but fails in Cloud Run = credential/timing issue.

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
    env_key="ALLOW_ORIGINS",
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

- **docs/cicd-setup.md**: CI/CD automation (build/deployment)
- **docs/development.md**: Development workflows, code quality, testing
- **docs/docker-compose-workflow.md**: Hot reloading, local development
- **docs/dockerfile-strategy.md**: Multi-stage build rationale
- **docs/terraform-infrastructure.md**: Terraform setup (bootstrap/main modules, variable overrides, IAM patterns)
- **docs/validating-multiplatform-builds.md**: Multi-platform digest verification (specialized troubleshooting)
