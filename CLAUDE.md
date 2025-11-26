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
# Default (backward compatible for local development): ["http://127.0.0.1", "http://127.0.0.1:8000"]
# Set via TF_VAR_allow_origins in CI/CD to override
ALLOW_ORIGINS='["https://your-domain.com", "http://127.0.0.1:3000"]'
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

**Three-workflow pattern** in `.github/workflows/`:
- **ci-cd.yml**: Orchestrator (meta → build → deploy)
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

**Version tag trigger rationale:**
- Tag creation happens after release PR is reviewed and merged (code already vetted)
- Automatic workflow trigger ensures version-tagged images are built consistently
- Tag is immutable pointer to already-reviewed code on main
- Standard industry practice for automated release workflows
- Security: Tags can only be pushed by authorized users, optional tag protection rules available

**Authentication:** Workload Identity Federation (no service account keys). WIF configured by Terraform bootstrap.

**GitHub Variables (auto-created by bootstrap):**
- `GCP_PROJECT_ID`, `GCP_LOCATION`, `IMAGE_NAME`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`, `ARTIFACT_REGISTRY_URI`, `ARTIFACT_REGISTRY_LOCATION`
- `TERRAFORM_STATE_BUCKET`

**Note:** These are Variables (not Secrets) - resource identifiers, not credentials. Security via IAM policies.

## Image Digest Deployment

### Why Digests Instead of Tags

Docker tags are mutable references that can point to different images over time. This creates a deployment problem:

**Problem with tag-based deployment:**
- Tag `latest` points to image A
- Code is updated, image B built with same tag `latest`
- Terraform deploys with tag `latest`, but Cloud Run still runs image A
- No redeployment occurs (tag is already deployed)
- New code never reaches Cloud Run

**Solution with digest-based deployment:**
- Every Docker image has an immutable SHA256 digest (`sha256:abc123...`)
- Each rebuild produces a unique digest (even same source code, different build timestamp)
- Terraform detects digest change and redeploys
- Every build guarantees a new Cloud Run revision

### How Digest Deployment Works

**Build phase** (`docker-build.yml`):
1. Docker build step outputs digest: `sha256:abc123def456...`
2. Extract registry and image name from first tag: `registry.location.pkg.dev/project/repo/image`
3. Construct full digest URI: `registry.location.pkg.dev/project/repo/image@sha256:abc123def456...`
4. Output digest URI as workflow output

**Deployment phase** (`ci-cd.yml`):
1. Pass digest URI to Terraform: `TF_VAR_docker_image="registry/image@sha256:..."`
2. Terraform updates Cloud Run service with new digest
3. Cloud Run detects image change, creates new revision automatically

### Digest vs Tag Summary

| Aspect | Tag | Digest |
|--------|-----|--------|
| Format | `registry/image:tag` | `registry/image@sha256:hash` |
| Mutability | Mutable (can be reassigned) | Immutable (unique per image) |
| Deployment trigger | Only if tag changes | Always (digest is unique per build) |
| Use case | Development, releases | Production deployment |

### Traceability: From Digest to Commit

Trace a deployed image back to source code:

```bash
# Get currently running image digest from Cloud Run
RUNNING_IMAGE=$(gcloud run services describe adk-docker-uv \
  --region us-central1 \
  --format='value(spec.template.spec.containers[0].image)')

# Get all tags pointing to that digest
gcloud artifacts docker images describe "${RUNNING_IMAGE}" \
  --format="value(tags)" | tr ',' '\n'

# The tags include commit SHA or version: pr-123-abc..., sha-abc..., v0.4.0, etc.
# Match against git commits: git log --format=%H --grep="sha-abc..."
```

### Implementation Details

**GitHub Actions outputs:**
- `digest_uri`: Complete digest URI (`registry/image@sha256:abc123...`)
- Output from `docker-build.yml` workflow passed to `terraform-plan-apply.yml`
- Constructed from build digest and image registry/name

**Terraform integration:**
- `docker_image` variable accepts both tag-based and digest-based URIs
- Digest format: `registry/image@sha256:full-hash`
- Example: `us-central1-docker.pkg.dev/my-project/my-repo/adk-docker-uv@sha256:1a2b3c4d...`

## Terraform Infrastructure

The project includes two Terraform modules for infrastructure management:

### Bootstrap Module (`terraform/bootstrap/`)

**Purpose:** One-time CI/CD infrastructure setup.

**Resources created:**
- Workload Identity Federation (pool + provider)
- Artifact Registry with cleanup policies (keep 5 recent, keep buildcache forever)
- **GCS bucket for main module's Terraform state** (auto-named with random suffix)
- GitHub Actions Variables (all CI/CD config auto-created)

**State management:** Local state by default (no backend.tf). Optional GCS backend for team collaboration.

**Configuration:** Reads `.env` using `dotenv` provider (version 1.2.9 pinned). Run once from local terminal.

**IAM roles to GitHub Actions:**
- `roles/aiplatform.user`, `roles/artifactregistry.writer`, `roles/storage.objectUser` (state bucket)

### Main Module (`terraform/main/`)

**Purpose:** Cloud Run deployment (runs in GitHub Actions CI/CD).

**Resources created:**
- Service account with IAM roles
- **Vertex AI Reasoning Engine** (session/memory persistence)
- **GCS bucket for artifacts** (auto-named with random suffix)
- Cloud Run service with environment variables

**State management:** Remote state in GCS (bucket created by bootstrap). Backend config via `-backend-config` flag.

**Configuration:** All inputs via `TF_VAR_*` environment variables (no dotenv). GitHub Actions maps Variables to TF_VAR_*.

**Docker image recycling:** `docker_image` variable nullable - defaults to previous deployment's image for infrastructure-only updates.

**Key features:**
- Agent Engine resource ID passed to Cloud Run via `AGENT_ENGINE` env var
- Production safety: `RELOAD_AGENTS` hardcoded to false

### Terraform Naming Conventions

- **Variable naming**: Use `project` (not `project_id`) for GCP project identifier
- **Local variables**: Prefer descriptive names (`local.agent_name`, `local.location`)
- **Resource IDs**: Use `agent_name` as base for consistent naming across resources

### Running Terraform

**Pattern:** Use `-chdir` flag (run from repo root).

```bash
# Bootstrap (one-time, local execution)
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap plan
terraform -chdir=terraform/bootstrap apply
# Creates GitHub Variables, GCS state bucket, WIF, Artifact Registry

# Main (CI/CD execution - see workflows)
# Local execution not recommended, but possible:
export TF_VAR_project="project-id"
export TF_VAR_location="us-central1"
export TF_VAR_agent_name="adk-docker-uv"
export TF_VAR_terraform_state_bucket="terraform-state-..."
export TF_VAR_docker_image="registry/image:tag"  # nullable
terraform -chdir=terraform/main init -backend-config="bucket=${TF_VAR_terraform_state_bucket}"
terraform -chdir=terraform/main workspace select --or-create default
terraform -chdir=terraform/main plan
terraform -chdir=terraform/main apply
```

**Workspaces:**
- Bootstrap: Uses `default` workspace (workspaces not recommended for local state)
- Main: Uses workspaces for environment isolation (default/dev/stage/prod)

**Key differences:**
- Bootstrap: Local state (no backend.tf), reads `.env`, run locally
- Main: Remote state in GCS, TF_VAR_* inputs, runs in CI/CD

### Terraform Variable Overrides (CI/CD Runtime Configuration)

**Pattern:** GitHub Actions maps workflow Variables to `TF_VAR_*` environment variables passed to Terraform.

**Key insight - Empty string handling:**
- GitHub Actions defaults unset Variables to empty string (`""`)
- Terraform `nullable=true` treats `""` as null
- `coalesce()` function applies sensible defaults when variables are null

**Available runtime configuration overrides:**
These variables can be set in GitHub Actions when needed for production configuration:

- `TF_VAR_log_level`: Override default LOG_LEVEL for Cloud Run service
- `TF_VAR_serve_web_interface`: Enable/disable web UI for running service
- `TF_VAR_allow_origins`: Override CORS origins (JSON array string) - restores default `["http://127.0.0.1", "http://127.0.0.1:8000"]` if unset
- `TF_VAR_root_agent_model`: Change agent model at deployment time
- `TF_VAR_artifact_service_uri`: Override GCS bucket for artifact storage
- `TF_VAR_agent_engine`: Override Vertex AI Reasoning Engine resource ID

**Backward compatibility note:** The `ALLOW_ORIGINS` default is intentionally set to maintain local development compatibility. Changing this requires explicit override via `TF_VAR_allow_origins`.

See `docs/terraform-infrastructure.md` section "Terraform Variable Overrides" for detailed examples.

### IAM and Permissions Model

**Project-level IAM assumption:**
This deployment assumes a dedicated GCP project per deployment environment. All Terraform-provisioned resources are in the same GCP project. This simplifies IAM configuration and makes resource quotas and billing transparent.

**Cross-project bucket access limitation:**
Storage access is controlled by project-level IAM roles (e.g., `roles/storage.bucketViewer`, `roles/storage.objectUser`). These roles only grant access to buckets in the same project. To use an artifact bucket in a different GCP project:
- The IAM binding must be configured outside the Terraform module
- The service account needs explicit cross-project IAM roles on the external bucket
- Use `ARTIFACT_SERVICE_URI` variable to reference the external bucket

**App service account roles** (created by main module):
- `roles/aiplatform.user`: Access Vertex AI Reasoning Engine (session persistence)
- `roles/storage.bucketViewer`: List buckets in project
- `roles/storage.objectUser`: Read/write to auto-created artifact bucket (same project only)
- `roles/logging.logWriter`: Write logs to Cloud Logging
- `roles/cloudtrace.agent`: Write traces to Cloud Trace
- `roles/telemetry.tracesWriter`: Write telemetry traces
- `roles/serviceusage.serviceUsageConsumer`: API usage tracking

**GitHub Actions WIF roles** (created by bootstrap module):
- `roles/aiplatform.user`: Deploy and manage Vertex AI resources
- `roles/artifactregistry.writer`: Push Docker images to Artifact Registry
- `roles/iam.serviceAccountUser`: Required for Cloud Run to attach service accounts during deployment
- `roles/storage.admin`: Manage GCS buckets and Terraform state

**Documentation:** See `docs/terraform-infrastructure.md` section "IAM and Permissions Model" for security implications and cross-project configuration guidance.

### Cloud Run Startup Probe Configuration

**Critical insight - Startup probe must allow time for credential initialization:**

The Cloud Run container needs time to initialize credentials before the artifact service can authenticate to GCS. Aggressive startup probes cause immediate deployment failure with no visibility into the root cause.

**Correct configuration** (in `terraform/main/main.tf`):
- `failure_threshold=5, period_seconds=20, timeout_seconds=15, initial_delay_seconds=20`
- Uses HTTP health check at `/health` endpoint (not TCP socket)
- Total window: 120 seconds to reach healthy state
- Health endpoint returns `{"status": "ok"}` when server is ready

**Why this matters:**
- Overly aggressive config (e.g., `failure_threshold=1, period_seconds=180`) fails immediately
- Symptom: Container exits with DEADLINE_EXCEEDED, logging unavailable (crashes before log initialization)
- Root cause: Cloud Run metadata server credential setup takes ~30-60s, GCS auth fails before then
- Image works locally because docker/docker-compose don't require Cloud Run credential initialization

**Debugging approach:**
1. If Cloud Run deployment fails silently, test locally with identical env vars: `docker compose up`
2. Image working locally but failing in Cloud Run indicates credential/timing issue
3. Cloud Run logs appear in Logging, but startup failures may have zero app-level logs
4. Increase startup probe `initial_delay_seconds` and `failure_threshold` if credential setup takes longer

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

- **README.md**: Quickstart and overview
- **docs/development.md**: Development workflows, code quality, testing
- **docs/docker-compose-workflow.md**: Hot reloading and local development
- **docs/dockerfile-strategy.md**: Multi-stage build architecture and rationale
- **docs/terraform-infrastructure.md**: Comprehensive Terraform setup guide
  - "Bootstrap Module Setup": One-time infrastructure creation (WIF, Artifact Registry, state bucket)
  - "Main Module Setup": Cloud Run deployment with Agent Engine and artifact storage
  - "Terraform Variable Overrides": Runtime configuration options via GitHub Actions
  - "IAM and Permissions Model": Service account roles and cross-project access patterns
- **docs/cicd-setup.md**: CI/CD workflow automation (build and deployment)
