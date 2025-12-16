# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branch Protection

**CRITICAL: Never commit to `main`.** Branch protection prevents direct pushes.

**Workflow:** Create feature branch → commit → push → PR → merge.

**Recovery from accidental main commit:** `git branch feature-name && git reset --hard origin/main && git checkout feature-name`

## Project Overview

This is a production-grade ADK (Agent Development Kit) application with enterprise infrastructure. The project demonstrates best practices for deploying Google ADK agents in production with automated CI/CD, managed state persistence, custom observability, and proven cloud infrastructure.

**Key technologies:**
- **Google ADK**: Agent framework for LLM-powered applications using Gemini models
- **FastAPI**: Web server for agent API and optional web UI
- **uv**: Modern Python package manager with PEP 735 dependency groups
- **Docker**: Multi-stage builds with BuildKit cache optimization
- **Python 3.13**: Modern syntax with strict type checking
- **Terraform**: Infrastructure as Code for reproducible deployments
- **Cloud Run**: Production hosting with regional redundancy and autoscaling
- **OpenTelemetry**: Custom instrumentation with trace-log correlation

## Development Commands

### Terraform Infrastructure Setup (One-Time)

```bash
# Configure .env: AGENT_NAME, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION,
# OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
# Configure terraform/bootstrap/terraform.tfvars: repository_owner, repository_name
terraform -chdir=terraform/bootstrap init/plan/apply
```

Creates: WIF, Artifact Registry, GCS state bucket, GitHub Actions Variables. Runtime resources (AGENT_ENGINE, ARTIFACT_SERVICE_URI) created by main module during deployment.

### Template Initialization (One-Time)

```bash
uv run init_template.py --dry-run  # Preview
uv run init_template.py            # Apply
```

Renames package, updates config/docs/badges, resets CODEOWNERS/version/changelog. Audit log: `init_template_results.md` (gitignored).

### Running Locally

Defaults to in-memory session, memory, and artifact services. For production-consistent testing with durable persistence, add cloud resource URIs to `.env` (see README Quickstart and CI/CD Infrastructure Setup).

```bash
# Optional runtime configuration (before running)
# Edit .env: SERVE_WEB_INTERFACE, LOG_LEVEL, etc.
# Optional cloud resources: AGENT_ENGINE, ARTIFACT_SERVICE_URI

# Run server (default: API-only at http://127.0.0.1:8000)
uv run server

# Debug mode
LOG_LEVEL=DEBUG uv run server
```

### Docker Compose (Recommended for Local Development)

```bash
docker compose up --build --watch  # Hot reload: src/ instant sync, deps auto-rebuild
docker compose down
docker compose logs -f app
```

### Code Quality

```bash
uv run ruff format  # Format
uv run ruff check   # Lint
uv run mypy         # Type check
uv run ruff format && uv run ruff check && uv run mypy  # All
```

### Testing

```bash
uv run pytest -v                                            # All tests
uv run pytest --cov --cov-report=term-missing               # With coverage (100% required)
uv run pytest tests/test_context.py -v                      # Specific file
uv run pytest tests/test_context.py::test_load_success -v   # Specific test
```

## Architecture

### ADK App and Agent Structure

The app and agent are configured in `src/agent_foundation/agent.py`:

```
app (App)
  ├── Plugins
  │   ├── GlobalInstructionPlugin: Dynamic instruction generation (return_global_instruction)
  │   └── LoggingPlugin: Agent lifecycle logging
  └── root_agent (LlmAgent)
      ├── Model: gemini-2.5-flash (configurable via ROOT_AGENT_MODEL env var)
      ├── Tools: Custom tools from tools.py + PreloadMemoryTool
      ├── Instruction: Base agent instruction (return_instruction_root)
      └── Callbacks: LoggingCallbacks + add_session_to_memory
```

**Key components:**
- **agent.py**: App container with plugins and LlmAgent configuration
- **tools.py**: Custom tools for the agent
- **callbacks.py**: Lifecycle callbacks for logging and memory persistence (all return `None`)
- **prompt.py**: Agent instructions and descriptions (includes InstructionProvider pattern for GlobalInstructionPlugin)
- **server.py**: FastAPI server with ADK integration
- **utils/config.py**: Pydantic-based environment configuration with validation
- **utils/observability.py**: OpenTelemetry setup for tracing and logging

### FastAPI Server

`src/agent_foundation/server.py`: ADK agent API endpoints (`get_fast_api_app()`), optional web UI (`SERVE_WEB_INTERFACE`), health check (`/health`), CORS for localhost.

**Entry point:** `python -m agent_foundation.server`

### Multi-Stage Docker Build

**Two-stage strategy:**
1. **Builder**: `python:3.13-slim` + uv binary, cache mount (`--mount=type=cache,target=/root/.cache/uv`), `--locked` validation, `--no-install-project` for layer optimization
2. **Runtime**: Clean slim image, non-root `app:app`, ~200MB final size

**Key optimizations:** Cache mount persists across builds (~80% speedup), dependency layer rebuilds only on `pyproject.toml`/`uv.lock` changes, code layer rebuilds only on `src/` changes. Empty README at build time prevents doc-only rebuilds.

See `docs/base-infra/dockerfile-strategy.md` for detailed rationale.

### Observability

OpenTelemetry exports traces to Cloud Trace (OTLP) and logs to Cloud Logging (auto trace correlation). Resource attributes: `service.name` (AGENT_NAME), `service.instance.id` (worker-{PID}-{UUID}), `service.namespace` (TELEMETRY_NAMESPACE, defaults "local", set to workspace in deployments), `service.version` (K_REVISION). Controls: LOG_LEVEL, OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT.

`LoggingCallbacks` logs agent lifecycle with trace context. See `docs/base-infra/observability.md`.

## Code Quality Standards

### Type Checking

Strict mypy: complete type annotations required, modern Python 3.13 syntax (`|` unions, lowercase generics `list[str]`), no untyped definitions/decorators, Pydantic runtime validation.

### Linting and Formatting

Ruff: 88 char line length, auto-fix, enforces pycodestyle/pyflakes/isort/flake8-bugbear/pyupgrade/pep8-naming/bandit/simplify/use-pathlib. **Always use `Path` objects** (never `os.path`).

### Testing

100% coverage on production code (excludes: `server.py`, `**/agent.py`, `**/__init__.py`). Tests by feature, shared fixtures in `conftest.py`, duck-typed mocks, pytest-asyncio. Patterns: `capsys` for stdout/stderr, `patch.dict(os.environ, ...)` for env vars, validate success + error cases.

## Environment Variables

**Required:**
```bash
# Google Cloud Vertex AI Model Authentication
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Agent identification and observability
AGENT_NAME=your-agent-name

# OpenTelemetry message content capture (true/false)
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=TRUE

# Auth: gcloud auth application-default login
```

**Key optional vars:** `SERVE_WEB_INTERFACE` (web UI), `LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR/CRITICAL, default: INFO), `TELEMETRY_NAMESPACE` (trace grouping, default: "local", auto-set to workspace in deployments), `RELOAD_AGENTS` (dev hot reload), `ROOT_AGENT_MODEL` (default: gemini-2.5-flash), `AGENT_ENGINE` (session persistence, URI prefix auto-added), `ARTIFACT_SERVICE_URI` (GCS bucket), `ALLOW_ORIGINS` (CORS config JSON array).

See `.env.example` for complete list.

## Dependency Management

```bash
uv add package-name              # Add runtime dep
uv add --group dev package-name  # Add dev dep
uv lock --upgrade                # Update all
uv lock --upgrade-package pkg    # Update specific
```

**Version bump:** Update `version` in `pyproject.toml` → `uv lock` → commit both. CI uses `uv sync --locked` (fails if out of sync).

## CI/CD

**Workflows:** ci-cd.yml (orchestrator: meta→build→deploy), metadata-extract.yml (metadata), docker-build.yml (build), terraform-plan-apply.yml (deploy), code-quality.yml (ruff/mypy), required-checks.yml (branch protection).

**Behavior:** PR = build `pr-{number}-{sha}`, terraform plan, post comment. Main = build `{sha}`+`latest`+`{version}`, deploy by digest. Tag push (`v*`) = version-tagged build. Deployment uses image **digest** (not tag) to ensure every rebuild triggers new Cloud Run revision. Concurrency: PRs cancel in-progress, main sequential, per-workspace Terraform locking.

**Auth:** WIF (no SA keys), configured by bootstrap. **GitHub Variables** (auto-created): GCP_PROJECT_ID, GCP_LOCATION, IMAGE_NAME, GCP_WORKLOAD_IDENTITY_PROVIDER, ARTIFACT_REGISTRY_URI, ARTIFACT_REGISTRY_LOCATION, TERRAFORM_STATE_BUCKET (resource IDs, not credentials).

### GitHub Actions Job Summaries

Workflows use `$GITHUB_STEP_SUMMARY` for formatted output. Key patterns: export GitHub context to shell vars for bash manipulation, capture expensive commands once, check for empty outputs before display, conditionally post to PR comments vs always write to summary.

**Implementations:** metadata-extract.yml (build context, image tags), terraform-plan-apply.yml (step status, plan output)

## Image Digest Deployment

Deploy with immutable digest (`registry/image@sha256:...`), not mutable tag. Digests unique per build, guarantee new Cloud Run revision. Flow: docker-build.yml outputs digest → ci-cd.yml → TF_VAR_docker_image → Cloud Run.

Multi-platform: manifest list digest (deployed) ≠ platform digest (running). Expected. See `docs/base-infra/validating-multiplatform-builds.md`.

## Terraform Infrastructure

**Two modules:**
1. **Bootstrap** (`terraform/bootstrap/`): One-time CI/CD setup. Creates WIF, Artifact Registry, GCS state bucket, GitHub Variables. Local state (default). Reads `.env` via dotenv provider (v1.2.9 pinned). Run from local terminal.

2. **Main** (`terraform/main/`): Cloud Run deployment. Creates service account, Vertex AI Reasoning Engine, GCS artifact bucket, Cloud Run service. Remote state in GCS. Inputs via `TF_VAR_*` (no dotenv). Runs in GitHub Actions. `docker_image` variable nullable (defaults to previous image for infra-only updates).

### Running Terraform

Use `-chdir` flag from repo root:
```bash
terraform -chdir=terraform/bootstrap init/plan/apply
```

**Naming:** GCP resources use `${var.agent_name}-${terraform.workspace}` (e.g., `my-agent-dev`). Service account IDs truncate agent_name to enforce GCP 30-char limit while preserving workspace suffix. Billing labels: `application`, `environment`. Workspaces: bootstrap=`default`, main=`default`/`dev`/`stage`/`prod`.

**Auto config:** Cloud Run gets `TELEMETRY_NAMESPACE=terraform.workspace` for trace grouping.

**Variable overrides:** GitHub Variables → `TF_VAR_*`. `coalesce()` skips empty strings/nulls. Overridable: log_level, serve_web_interface, allow_origins, root_agent_model, artifact_service_uri, agent_engine.

**IAM:** Dedicated GCP project per env. Project-level roles = same-project access only. Cross-project buckets need external IAM + `ARTIFACT_SERVICE_URI`. App SA roles: terraform/main/main.tf. WIF roles: terraform/bootstrap/main.tf.

**Cloud Run probe:** Allow credential init (~30-60s). Config: failure_threshold=5, period_seconds=20, initial_delay_seconds=20, timeout_seconds=15, total 120s. Debug: local works but Cloud Run fails = credential/timing.

See `docs/base-infra/terraform-infrastructure.md`.

## Project-Specific Patterns

### Adding Custom Tools

Create tools in `src/agent_foundation/tools.py` and register in `agent.py`:

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

Callback pattern: `LoggingCallbacks` (lifecycle logging), `add_session_to_memory` (session persistence). All return `None`, non-intrusive (observe only).

### InstructionProvider Pattern

Dynamic instruction generation: `def instruction_provider(ctx: ReadonlyContext) -> str`. Pass function ref to `GlobalInstructionPlugin(instruction_provider)`, not call. `ctx`: state, agent_name, invocation_id, user_content, session. Plugin applies instruction dynamically at runtime. Test with `MockReadonlyContext` (conftest.py).

### Environment Configuration

Pydantic-based config: `env = initialize_environment(ServerEnv)`. Type-safe validation, required field enforcement (fail-fast), factory pattern, comprehensive errors. Centralized in `utils/config.py`.

### Docker Compose Development

Container paths: `/app/src` (synced from `./src`), `/app/data` (from `./data`, read-only), `/gcloud/application_default_credentials.json` (from `~/.config/gcloud/`).

Windows: Update GCP creds volume path (see docker-compose.yml comments). Security: Binds to `127.0.0.1:8000` (localhost only).

### Testing Registry Images

```bash
gcloud auth configure-docker <registry-location>-docker.pkg.dev  # One-time
export REGISTRY_IMAGE="<location>-docker.pkg.dev/<project>/<repo>/<image>:latest"
docker pull $REGISTRY_IMAGE
docker compose -f docker-compose.yml -f docker-compose.registry.yml up
```

Container suffix: `-registry`.

### Testing Deployed Service

Proxy the deployed Cloud Run service to localhost for testing:

```bash
# Proxy to http://127.0.0.1:8000
gcloud run services proxy <service-name> --project <project-id> --region <region> --port 8000
```

Uses gcloud credentials (no manual token management). Service name: `${agent_name}-${workspace}` (e.g., `my-agent-default`). See `docs/base-infra/development.md`.

## Documentation

Base infrastructure docs in `docs/base-infra/`. Add agent-specific docs to `docs/` root.

- **docs/base-infra/bootstrap-setup.md**: One-time CI/CD infrastructure provisioning (minimal commands, troubleshooting)
- **docs/base-infra/environment-variables.md**: Complete environment variable reference (WHEN/WHY/HOW context)
- **docs/base-infra/development.md**: Development workflows, code quality, testing
- **docs/base-infra/cicd-setup.md**: CI/CD automation (build/deployment)
- **docs/base-infra/docker-compose-workflow.md**: Hot reloading, local development
- **docs/base-infra/dockerfile-strategy.md**: Multi-stage build rationale
- **docs/base-infra/terraform-infrastructure.md**: Terraform setup (bootstrap/main modules, variable overrides, IAM patterns)
- **docs/base-infra/validating-multiplatform-builds.md**: Multi-platform digest verification (specialized troubleshooting)
