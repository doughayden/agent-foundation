# CLAUDE.md

Guidance for AI agents. **CRITICAL: Update this file when establishing project patterns.**

## Critical

- **Never commit to main** (branch protection enforced). Workflow: feature branch → PR → merge.
- **Version bumps:** Update `pyproject.toml` → `uv lock` (both files together required for CI `--locked` to pass).

## Template Initialization (One-Time)

Base template repo. Run `uv run init_template.py --dry-run` (preview) or `uv run init_template.py` (apply). Script docstring contains complete usage/cleanup instructions. After use, delete `init_template.py`, `./.log/init_template_*.md`, README Bootstrap step 0, and this Template Initialization section.

## Quick Commands

```bash
# Local
uv run server                               # API at 127.0.0.1:8000
LOG_LEVEL=DEBUG uv run server               # Debug mode
docker compose up --build --watch           # Hot reload
uv run pytest --cov --cov-report=term-missing  # Tests + 100% coverage required

# Code quality (all required)
uv run ruff format && uv run ruff check && uv run mypy

# Terraform (dev-only mode)
terraform -chdir=terraform/bootstrap/dev init/plan/apply  # One-time CI/CD setup
terraform -chdir=terraform/main init/plan/apply           # Deploy (TF_VAR_environment=dev)
```

## Architecture Overview

**ADK App Structure** (`src/agent_foundation/agent.py`):
- `GlobalInstructionPlugin`: Dynamic instruction generation (InstructionProvider pattern)
- `LoggingPlugin`: Agent lifecycle logging
- `root_agent` (LlmAgent): gemini-2.5-flash (configurable `ROOT_AGENT_MODEL`), custom tools, callbacks

**Package exports** (`src/agent_foundation/__init__.py`): Intentionally does NOT export `agent` module (breaks from ADK recommendations). Forces ADK to use fallback discovery pattern, enabling lazy loading. Ensures .env loads before module-level code executes. Agent discovery still works correctly.

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

**Key optional:** SERVE_WEB_INTERFACE, LOG_LEVEL (DEBUG/INFO/WARNING/ERROR/CRITICAL), TELEMETRY_NAMESPACE (default "local", auto-set to environment in deployments), ROOT_AGENT_MODEL, AGENT_ENGINE, ARTIFACT_SERVICE_URI, ALLOW_ORIGINS (JSON array).

**CRITICAL:** Any new environment variable introduced to the codebase MUST be documented in `docs/environment-variables.md`. No exceptions. Include: purpose, default value, where to set, and whether required or optional.

## Code Quality

**Workflow (run before every commit):**
```bash
uv run ruff format && uv run ruff check --fix && uv run mypy && uv run pytest --cov
```

- **mypy:** Strict, complete type annotations, modern Python 3.13 (`|` unions, lowercase generics), no untyped definitions. Enforces: `no_implicit_optional`, `strict_equality`, `warn_return_any`, `warn_unreachable`.
- **ruff:** 88 char line length, enforces bandit/simplify/use-pathlib. **Always use `Path` objects** (never `os.path`).
- **pytest:** 100% coverage on production code (excludes `server.py`, `**/agent.py`, `**/prompt.py`, `**/__init__.py`). Fixtures in `conftest.py`, async via pytest-asyncio.

**Type narrowing:** **NEVER use `cast()`** - always use `isinstance()` checks for type narrowing (provides both mypy inference and runtime safety).

**Code quality exclusions:**
- `# noqa` - Use specific codes (`# noqa: S105`) with justification. Common: S105 (test mocks), S104 (0.0.0.0 in Docker), E501 (URLs).
- `# pragma: no cover` - Only for provably unreachable defensive code (e.g., Pydantic validation guarantees). Never for "hard to test" code.

## Testing Patterns

**Tools:** pytest, pytest-cov (100% required), pytest-asyncio, pytest-mock (`MockerFixture`, `MockType`)

**pytest_configure()** - Only place using unittest.mock (runs before pytest-mock available):
- Mock `dotenv.load_dotenv`, `google.auth.default`, `google.auth._default.default`
- Direct env assignment (`os.environ["KEY"] = "value"`, never `setdefault()`)
- Comprehensive docstring explaining pytest lifecycle (see tests/conftest.py)

**Fixtures:**
- Type hints: `MockerFixture` → `MockType` return (strict mypy in conftest.py)
- Factory pattern (not context managers): `def _factory() -> MockType` returned by fixture
- Environment mocking: `mocker.patch.dict(os.environ, env_dict)`
- Test functions: Don't type hint custom fixtures, optional hints on built-ins for IDE

**ADK Mocks** (mirror real interfaces exactly):
- MockState, MockContent, MockSession, MockReadonlyContext (with user_id property)
- MockMemoryCallbackContext (controlled behavior via constructor)
- MockLoggingCallbackContext, MockLlmRequest/Response, MockToolContext, MockBaseTool

**Mock Usage:** Fixtures first. Import mock classes only when creating fixtures for every variant adds more complexity than direct instantiation. Guideline: >3 variants → import class; standard cases → use/add fixture.

**Organization:** Mirror source (`src/X.py` → `tests/test_X.py`). Class grouping. Descriptive names (`test_<what>_<condition>_<expected>`).

**Validation:** Pydantic `@field_validator` (validate at model creation). Tests expect `ValidationError` at `model_validate()`, not at property access. Property simplified with `# pragma: no cover` for impossible edge cases.

**Mypy override:**
```toml
[[tool.mypy.overrides]]
module = "tests.*"
disable_error_code = ["arg-type"]
```

**Coverage:** 100% on production code. Omit `__init__.py`, `server.py`, `**/agent.py`, `utils/observability.py`. Test behaviors (errors, edge cases, return values, logging), not just statements.

**Parameterization:** Thoughtfully. Inline loops OK for documenting complex behavior (e.g., boolean field parsing).

**ADK patterns:**
- InstructionProvider: Test with MockReadonlyContext
- LoggingCallbacks: Return None (non-intrusive observation). Other callbacks can modify/short-circuit.
- Async callbacks: `@pytest.mark.asyncio`, verify caplog
- Controlled errors: MockMemoryCallbackContext constructor (should_raise, error_message)

## Dependencies

```bash
uv add pkg                      # Runtime
uv add --group dev pkg          # Dev
uv lock --upgrade               # Update all
```

## CI/CD & Deployment

**Deployment Modes:** Dev-only (default, `production_mode: false` in ci-cd.yml config job) deploys to dev on merge. Production mode (`production_mode: true`) deploys dev+stage on merge, prod on git tag with approval gate. See [Infrastructure Guide](docs/infrastructure.md).

**Workflows:** ci-cd.yml (orchestrator), config-summary.yml, docker-build.yml, metadata-extract.yml, pull-and-promote.yml, resolve-image-digest.yml, terraform-plan-apply.yml, code-quality.yml. PR: build `pr-{sha}`, dev-plan, comment. Main: build `{sha}`+`latest`, deploy dev (+ stage in prod mode). Tag: prod deploy (prod mode only). **Deploy by immutable digest** (not tag) to guarantee new Cloud Run revision. **Option to deploy to dev on all PRs:** single-line change to ci-cd.yml deploys on PR (remove `&& github.event_name == 'push'` from dev-apply condition).

**Auth:** WIF (no SA keys). GitHub Variables auto-created: GCP_PROJECT_ID, GCP_LOCATION, IMAGE_NAME, GCP_WORKLOAD_IDENTITY_PROVIDER, ARTIFACT_REGISTRY_URI, ARTIFACT_REGISTRY_LOCATION, TERRAFORM_STATE_BUCKET.

**Job Summaries:** Use `$GITHUB_STEP_SUMMARY` for formatted output. Export GitHub context to shell, capture once, check for empty output.

## Terraform

**Bootstrap Structure:** Each environment is a separate terraform root (`terraform/bootstrap/dev/`, `terraform/bootstrap/stage/`, `terraform/bootstrap/prod/`) calling shared modules (`terraform/bootstrap/module/gcp/` for GCP infrastructure, `terraform/bootstrap/module/github/` for GitHub automation). Each environment uses local state and terraform.tfvars for configuration. Creates: WIF, Artifact Registry, GCS state bucket, GitHub Environments, GitHub Environment Variables.

**Cross-Project IAM (Production Mode):** Stage and prod bootstrap roots grant cross-project Artifact Registry reader access for image promotion:
- `stage/main.tf`: Grants stage's WIF principal `roles/artifactregistry.reader` on dev's registry (for stage-promote: dev → stage)
- `prod/main.tf`: Grants prod's WIF principal `roles/artifactregistry.reader` on stage's registry (for prod-promote: stage → prod)
- Narrow scope: read-only role, registry-resource-bound (not project-level)
- Uses WIF principals (not service accounts): bypasses org policies restricting cross-project service account usage
- Variables: `promotion_source_project` (source GCP project ID), `promotion_source_artifact_registry_name` (source registry name, e.g., `agent-name-dev`)
- IAM binding: `google_artifact_registry_repository_iam_member` with `member = module.gcp.workload_identity_pool_principal_identifier`

**Main Module:** Cloud Run deployment (`terraform/main/`). Service account, Vertex AI Agent Engine, GCS bucket, Cloud Run service. Remote state in GCS. Inputs via `TF_VAR_*` from GitHub Environment variables. Runs in GitHub Actions. Requires `TF_VAR_environment` (dev/stage/prod) to set resource naming.

**Naming:** Resources `${var.agent_name}-${var.environment}`. Service account IDs truncate agent_name to 30 chars (GCP limit). Cloud Run auto-sets `TELEMETRY_NAMESPACE=var.environment`.

**Runtime Variable Overrides:** GitHub Environment Variables → `TF_VAR_*`. `coalesce()` skips empty/null. Overridable runtime config: log_level, serve_web_interface, root_agent_model, otel_instrumentation_genai_capture_message_content, adk_suppress_experimental_feature_warnings. `docker_image` nullable (defaults to previous for infra-only updates). **Infrastructure resources (AGENT_ENGINE, ARTIFACT_SERVICE_URI, CORS origins) are hard-coded in Terraform** (no variable overrides).

**IAM:** Dedicated GCP project per env. Project-level WIF roles same-project only (in terraform/bootstrap/module/gcp/main.tf). Cross-project Artifact Registry IAM grants in environment bootstrap roots (stage/main.tf, prod/main.tf) for image promotion. App SA roles in terraform/main/main.tf.

**Cloud Run probe:** Config failure_threshold=5, period_seconds=20, initial_delay_seconds=20, timeout_seconds=15 (total 120s). Allow credential init (~30-60s). Debug: local works but Cloud Run fails = credential/timing issue.

## Project-Specific Patterns

**Custom Tools:** Create in `src/agent_foundation/tools.py`, register in `agent.py`. Tool(name, description, func).

**Callbacks:** `LoggingCallbacks` (lifecycle), `add_session_to_memory` (session persist). All return `None` (observe-only).

**InstructionProvider:** `def fn(ctx: ReadonlyContext) -> str`. Pass function ref (not called) to `GlobalInstructionPlugin(fn)`. Plugin calls at runtime. Test with `MockReadonlyContext`.

**Config:** Pydantic `initialize_environment(ServerEnv)` in `utils/config.py`. Type-safe, fail-fast validation.

**Docker Compose:** Volumes: `/app/src` (synced), `/app/data` (read-only), `/gcloud/application_default_credentials.json` (from `~/.config/gcloud/`). Windows: update GCP creds path. Binds `127.0.0.1:8000`.

**Test Deployed:** `gcloud run services proxy <service-name> --project <project> --region <region> --port 8000`. Service name: `${agent_name}-${environment}` (e.g., `my-agent-dev`).

## Documentation Strategy

**CRITICAL:** Task-based organization (match developer mental model), not technical boundaries.

**Structure:**
- **README.md:** ~200 lines max. Quick start only. Points to docs/.
- **docs/*.md:** ~300 lines max. Action paths ("I want to..."). Core guides: getting-started, development, infrastructure, environment-variables, observability, troubleshooting, template-management.
- **docs/references/*.md:** No limit. Deep-dive technical docs. Optional follow-up.

**Rules:**
- Task-based, not tech-based (e.g., "Infrastructure" not "Terraform" + "CI/CD" separately)
- Hub-and-spoke navigation: docs/README.md and docs/references/README.md are navigation indexes
- Inline cross-links only when critically contextual (hybrid approach)
- No "See Also" sections - rely on index navigation instead
- Single source of truth: env vars only in docs/environment-variables.md
- Update docs/README.md when adding docs
- Keep guides digestible (<300 lines). Move details to references/.

## Documentation References

Task-based docs in `docs/`. Core: getting-started.md, development.md, infrastructure.md, environment-variables.md. Operations: observability.md, troubleshooting.md. Template: template-management.md. Detailed references: docs/references/ (bootstrap.md, protection-strategies.md, deployment.md, cicd.md, testing.md, code-quality.md, docker-compose-workflow.md, dockerfile-strategy.md).
