# CLAUDE.md

Production-grade Google ADK agent with enterprise infrastructure: FastAPI, Terraform, Cloud Run, OpenTelemetry, Python 3.13.

## Critical

- **Never commit to main** (branch protection enforced). Workflow: feature branch → PR → merge.
- **Version bumps:** Update `pyproject.toml` → `uv lock` (both files together required for CI `--locked` to pass).

## Template Initialization (One-Time)

Base template repo. Run `uv run init_template.py --dry-run` (preview) or `uv run init_template.py` (apply). Script docstring contains complete usage/cleanup instructions. After use, suggest deleting `init_template.py`, `init_template_results.md`, README Bootstrap step 0, and this section from CLAUDE.md.

## Quick Commands

```bash
# Local
uv run server                               # API at 127.0.0.1:8000
LOG_LEVEL=DEBUG uv run server               # Debug mode
docker compose up --build --watch           # Hot reload
uv run pytest --cov --cov-report=term-missing  # Tests + 100% coverage required

# Code quality (all required)
uv run ruff format && uv run ruff check && uv run mypy

# Terraform
terraform -chdir=terraform/bootstrap init/plan/apply  # One-time CI/CD setup
terraform -chdir=terraform/main init/plan/apply       # Deploy
```

## Architecture Overview

**ADK App Structure** (`src/agent_foundation/agent.py`):
- `GlobalInstructionPlugin`: Dynamic instruction generation (InstructionProvider pattern)
- `LoggingPlugin`: Agent lifecycle logging
- `root_agent` (LlmAgent): gemini-2.5-flash (configurable `ROOT_AGENT_MODEL`), custom tools, callbacks

**Key modules:**
- `agent.py`: App/LlmAgent config
- `tools.py`: Custom tools
- `callbacks.py`: Lifecycle logging + session memory (all return `None`, non-intrusive)
- `prompt.py`: Instructions (InstructionProvider pattern for dynamic generation)
- `server.py`: FastAPI + ADK (`get_fast_api_app()`, optional web UI, health check)
- `utils/config.py`: Pydantic ServerEnv (type-safe, fail-fast)
- `utils/observability.py`: OpenTelemetry (Cloud Trace/Logging, trace correlation)

**Docker:** Multi-stage (builder + runtime). Cache mount in builder (~80% speedup), dependency layer on `pyproject.toml`/`uv.lock` changes only, code layer on `src/` changes. Non-root `app:app`, ~200MB final.

**Observability:** OpenTelemetry OTLP→Cloud Trace, structured logs→Cloud Logging. Resource attributes: `service.name` (AGENT_NAME), `service.instance.id` (worker-{PID}-{UUID}), `service.namespace` (TELEMETRY_NAMESPACE), `service.version` (K_REVISION).

## Environment Variables

**Required:** GOOGLE_GENAI_USE_VERTEXAI=TRUE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, AGENT_NAME, OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT (+ gcloud auth).

**Key optional:** SERVE_WEB_INTERFACE, LOG_LEVEL (DEBUG/INFO/WARNING/ERROR/CRITICAL), TELEMETRY_NAMESPACE (default "local", auto-set to workspace in deployments), ROOT_AGENT_MODEL, AGENT_ENGINE, ARTIFACT_SERVICE_URI, ALLOW_ORIGINS (JSON array).

## Code Quality

- **mypy:** Strict, complete type annotations, modern Python 3.13 (`|` unions, lowercase generics), no untyped definitions.
- **ruff:** 88 char line length, enforces bandit/simplify/use-pathlib. **Always use `Path` objects** (never `os.path`).
- **pytest:** 100% coverage on production code (excludes `server.py`, `**/agent.py`, `**/__init__.py`). Fixtures in `conftest.py`, async via pytest-asyncio.

## Dependencies

```bash
uv add pkg                      # Runtime
uv add --group dev pkg          # Dev
uv lock --upgrade               # Update all
```

## CI/CD & Deployment

**Workflows:** ci-cd.yml (orchestrator), docker-build.yml, terraform-plan-apply.yml, code-quality.yml. PR: build `pr-{sha}`, plan, comment. Main: build `{sha}`+`latest`+`{version}`, deploy. Tag: version-tagged build. **Deploy by immutable digest** (not tag) to guarantee new Cloud Run revision.

**Auth:** WIF (no SA keys). GitHub Variables auto-created: GCP_PROJECT_ID, GCP_LOCATION, IMAGE_NAME, GCP_WORKLOAD_IDENTITY_PROVIDER, ARTIFACT_REGISTRY_URI, ARTIFACT_REGISTRY_LOCATION, TERRAFORM_STATE_BUCKET.

**Job Summaries:** Use `$GITHUB_STEP_SUMMARY` for formatted output. Export GitHub context to shell, capture once, check for empty output.

## Terraform

**Two modules (use `-chdir` from repo root):**

1. **Bootstrap** (`terraform/bootstrap/`): One-time. WIF, Artifact Registry, GCS state bucket, GitHub Variables. Local state. Reads `.env` via dotenv (v1.2.9). Run locally.

2. **Main** (`terraform/main/`): Cloud Run deployment. Service account, Vertex AI Reasoning Engine, GCS bucket, Cloud Run service. Remote state in GCS. Inputs via `TF_VAR_*`. Runs in GitHub Actions.

**Naming:** Resources `${var.agent_name}-${terraform.workspace}`. Service account IDs truncate agent_name to 30 chars (GCP limit). Workspaces: bootstrap=`default`, main=`default`/`dev`/`stage`/`prod`. Cloud Run auto-sets `TELEMETRY_NAMESPACE=terraform.workspace`.

**Variable overrides:** GitHub Variables → `TF_VAR_*`. `coalesce()` skips empty/null. Overridable: log_level, serve_web_interface, allow_origins, root_agent_model, artifact_service_uri, agent_engine. `docker_image` nullable (defaults to previous for infra-only updates).

**IAM:** Dedicated GCP project per env. Project-level roles same-project only. Cross-project buckets need external IAM + `ARTIFACT_SERVICE_URI`. App SA roles in terraform/main/main.tf. WIF roles in terraform/bootstrap/main.tf.

**Cloud Run probe:** Config failure_threshold=5, period_seconds=20, initial_delay_seconds=20, timeout_seconds=15 (total 120s). Allow credential init (~30-60s). Debug: local works but Cloud Run fails = credential/timing issue.

## Project-Specific Patterns

**Custom Tools:** Create in `src/agent_foundation/tools.py`, register in `agent.py`. Tool(name, description, func).

**Callbacks:** `LoggingCallbacks` (lifecycle), `add_session_to_memory` (session persist). All return `None` (observe-only).

**InstructionProvider:** `def fn(ctx: ReadonlyContext) -> str`. Pass function ref (not called) to `GlobalInstructionPlugin(fn)`. Plugin calls at runtime. Test with `MockReadonlyContext`.

**Config:** Pydantic `initialize_environment(ServerEnv)` in `utils/config.py`. Type-safe, fail-fast validation.

**Docker Compose:** Volumes: `/app/src` (synced), `/app/data` (read-only), `/gcloud/application_default_credentials.json` (from `~/.config/gcloud/`). Windows: update GCP creds path. Binds `127.0.0.1:8000`.

**Test Registry Image:** `gcloud auth configure-docker` → pull → `docker compose -f docker-compose.yml -f docker-compose.registry.yml up`. Container suffix `-registry`.

**Test Deployed:** `gcloud run services proxy <service-name> --project <project> --region <region> --port 8000`. Service name: `${agent_name}-${workspace}`.

## Documentation References

Base infra docs: `docs/base-infra/`. Key files: bootstrap-setup.md, environment-variables.md, development.md, cicd-setup.md, docker-compose-workflow.md, dockerfile-strategy.md, terraform-infrastructure.md, validating-multiplatform-builds.md.
