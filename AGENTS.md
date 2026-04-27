# AGENTS.md

Guidance for AI agents. **CRITICAL: Update this file when establishing project patterns.**

## How to Maintain This File

**Pointer over enumeration.** Reference the source of truth instead of duplicating its contents. Lists of files, env vars, resources, workflows, dependencies, etc. go stale when implementations change but the concept does not. Stale lists waste tokens in every future session and mislead readers. Pointers stay valid as long as the source exists.

- ✅ "Required env vars: see `ServerEnv` in `utils/config.py` and `docs/environment-variables.md`"
- ❌ "Required: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, AGENT_NAME, ..."
- ✅ "GCP APIs added in `terraform/main/services.tf`"
- ❌ "Enabled APIs: cloudsql, run, iam, ..."

**Enumerate only when:** the list itself IS the concept (e.g., a security posture's guarantees), discoverability would be hard, or items are load-bearing rules every session must know without reading more files. Default to *concept + location*, not *contents*.

**Template internals vs. consumer extensions.** This is a base template that downstream projects fork. Mark sections describing template internals so consumers understand they carry higher upstream-sync cost if customized — consumers may still modify anything, but expect merge complexity. Intended extension surfaces belong in **Consumer Extension Points** below.

**Global-rule duplication is intentional.** Code Quality, Testing Patterns, and Documentation Strategy sections duplicate baseline conventions that would normally live in user-global rules (e.g., `~/.claude/rules/`). Downstream consumer projects will NOT have those global rules loaded — duplication here ensures consistency across all forks. Do not trim these sections to reduce perceived redundancy.

## Critical

- **Never commit to main** (branch protection enforced). Workflow: feature branch → PR → merge.
- **Version bumps:** Update `pyproject.toml` → `uv lock` (both files together required for CI `--locked` to pass).

## Template Initialization (One-Time)

Base template repo. Run `uv run init_template.py --dry-run` (preview) or `uv run init_template.py` (apply). Script docstring contains complete usage/cleanup instructions. After use, delete `init_template.py`, `./.log/init_template_*.md`, README Bootstrap step 0, and this Template Initialization section.

## Quick Commands

```bash
# Local
docker compose up --build --watch           # File sync + auto-restart
uv run server                               # API at 127.0.0.1:8000
LOG_LEVEL=DEBUG uv run server               # Debug mode
uv run pytest --cov --cov-report=term-missing  # Tests + 100% coverage required

# Code quality (all required)
uv run ruff format && uv run ruff check --fix && uv run mypy && uv run pytest --cov

# Terraform (dev-only mode) - configure terraform.tfvars files first for pre and bootstrap
terraform -chdir=terraform/bootstrap/pre init && terraform -chdir=terraform/bootstrap/pre apply  # One-time state buckets (all envs)
terraform -chdir=terraform/bootstrap/dev init \           # One-time CI/CD setup — see backend.tf comment for full -backend-config command
  -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.dev')"
terraform -chdir=terraform/bootstrap/dev apply
terraform -chdir=terraform/main init/plan/apply           # Deploy (TF_VAR_environment=dev)
```

## Consumer Extension Points

Entry-point map for "I want to add X". Each row points to the file where the change should land.

> [!NOTE]
> Python file references below use basenames only (`tools.py`, `agent.py`, etc.). The template project has exactly one package under `src/`, so basenames are unambiguous — resolve with `Glob src/*/<basename>` or `Glob **/<basename>`. This keeps downstream forks from needing to rename package paths in AGENTS.md after `init_template.py` runs.

| To... | Edit | Notes |
|---|---|---|
| Add a custom tool | define `func` in `tools.py` + register in `agent.py` | `root_agent = LlmAgent(..., tools=[..., FunctionTool(func)])` |
| Add a callback | `callbacks.py` | All callbacks return `None` (observe-only); modify/short-circuit only when intentional |
| Customize agent instructions | `prompt.py` | InstructionProvider pattern (function ref, called at runtime) |
| Add an env var | `ServerEnv` in `utils/config.py` + `docs/environment-variables.md` | **CRITICAL:** every new env var MUST be in `docs/environment-variables.md` (purpose, default, where to set, required/optional) |
| Enable a GCP API | `terraform/main/services.tf` | `google_project_service`; downstream resources `depends_on = [time_sleep.service_enablement_propagation["api.googleapis.com"]]` |
| Grant a WIF role | `terraform/main/iam.tf` | `google_project_iam_member`; downstream resources `depends_on = [time_sleep.wif_iam_propagation["roles/example"]]` |
| Override runtime config | GitHub Environment Variables → `TF_VAR_*` | See `coalesce()` call sites in `terraform/main/` for current overridable surface |
| Swap the LLM | `ROOT_AGENT_MODEL` in `agent.py` | Gemini/Claude/Vertex-hosted work via model string out of the box. For LiteLlm / Apigee / Ollama / vLLM / LiteRT-LM connectors, install the matching ADK extra and pass a connector instance. See [ADK models](https://adk.dev/agents/models/). |

**Template internals** (higher upstream-sync cost if customized — consumers may still modify, but expect merge complexity on future upstream syncs):
- `terraform/bootstrap/` — bootstrap roots and shared modules
- `.github/workflows/` — CI/CD orchestration
- `terraform/main/` files other than `services.tf` and `iam.tf`

## Architecture Overview

Source package lives under `src/` (single package — file references below use basenames; resolve with `Glob src/*/<basename>`).

**ADK App** (`agent.py`): `App` composes `LlmAgent` (LLM wrapper with instructions, subagent options, custom tools, callbacks), `GlobalInstructionPlugin` (dynamic instruction generation via InstructionProvider), and `LoggingPlugin` (lifecycle observation). Exact model and plugin wiring in `agent.py`.

**Package exports** (`__init__.py`): PEP 562 `__getattr__` for explicit lazy loading. Declares `agent` in `__all__` but defers import until first access. Supports both ADK eval CLI and web server workflows while ensuring `.env` loads before `agent.py` executes module-level code.

**Module roles:** `agent.py` (composition), `tools.py` / `callbacks.py` / `prompt.py` (consumer extension points — see Consumer Extension Points), `server.py` (FastAPI + ADK via `get_fast_api_app()`), `utils/config.py` (Pydantic `ServerEnv`, type-safe fail-fast), `utils/observability.py` (OpenTelemetry init).

**Memory:** Read via the `load_memory` function tool (LLM queries on-demand; ADK auto-appends a usage instruction when the tool is registered). Write via the `add_session_to_memory` after-agent callback.

**Session Service:** Cloud SQL Postgres (private IP) via ADK `DatabaseSessionService`.
- `get_fast_api_app()` routes `postgresql://` URIs automatically — no application code needed
- Connection via Cloud SQL Auth Proxy sidecar (IAM auth, no passwords)
- Security posture and pool config: `terraform/main/database.tf`, `docs/references/cloud-sql.md`, `docs/references/security-posture.md`
- Scale path: bump instance tier first, then managed connection pooling (Enterprise Plus) when autoscaling demands it

**asyncpg type strictness:** Direct SQL against the session DB must bind typed columns as native Python objects — asyncpg's codecs reject ISO strings for `timestamptz` (and other typed columns) with `DataError`. sqlite via aiosqlite tolerates strings, so sqlite-only tests miss the bug. Use `text(...).bindparams(bindparam("x", type_=DateTime(timezone=True)))` to force dialect-aware conversion.

**Networking:** VPC with Private Services Access peering for Cloud SQL private IP.
- Cloud Run uses direct VPC egress to reach Cloud SQL via Auth Proxy sidecar
- Bastion host (e2-micro, COS, auto-updates) runs Auth Proxy for local developer access via IAP tunnel
- Bastion concerns: accepts non-loopback IAP tunnel connections, impersonates app SA for IAM auth, COS requires explicit iptables ACCEPT for port 5432 (default INPUT=DROP)
- Cloud NAT for bastion outbound
- See `terraform/main/network.tf` and `terraform/main/templates/bastion-cloud-init.yaml`

**Docker:** Multi-stage (builder + runtime). uv pinned in Dockerfile. Cache mount in builder (~80% speedup), dependency layer rebuilds on `pyproject.toml`/`uv.lock` changes only, code layer on `src/`. Non-root `app:app`, ~200MB final.

**Observability:** OTLP→Cloud Trace, structured logs→Cloud Logging. Resource attributes derived from environment variables plus per-worker instance ID. See `utils/observability.py`.

## Environment Variables

**CRITICAL:** Any new env var introduced to the codebase MUST be documented in `docs/environment-variables.md`. No exceptions. Include purpose, default, where to set, and required/optional. `ServerEnv` in `utils/config.py` is the typed source of truth; `docs/environment-variables.md` is the canonical reference.

## Code Quality

**Workflow (run before every commit):**
```bash
uv run ruff format && uv run ruff check --fix && uv run mypy && uv run pytest --cov
```

- **mypy:** Strict, complete type annotations, modern Python 3.13 (`|` unions, lowercase generics), no untyped definitions. Enforces: `no_implicit_optional`, `strict_equality`, `warn_return_any`, `warn_unreachable`.
- **ruff:** 88 char line length, enforces bandit/simplify/use-pathlib. **Always use `Path` objects** (never `os.path`).
- **pytest:** 100% coverage on production code. Coverage exclusions in `pyproject.toml`. Fixtures in `conftest.py`, async via pytest-asyncio.

**Type narrowing:** **NEVER use `cast()`** - always use `isinstance()` checks for type narrowing (provides both mypy inference and runtime safety).

**Code quality exclusions:**
- `# noqa` - Use specific codes (`# noqa: S105`) with justification. Common: S105 (test mocks), S104 (0.0.0.0 in Docker), E501 (URLs).
- `# pragma: no cover` - Only for provably unreachable defensive code (e.g., Pydantic validation guarantees). Never for "hard to test" code.

## Testing Patterns

**Tools:** pytest, pytest-cov (100% required), pytest-asyncio, pytest-mock (`MockerFixture`, `MockType`)

**pytest_configure()** - Only place using unittest.mock (runs before pytest-mock available). Mocks `dotenv.load_dotenv` and Google auth defaults to prevent real credential lookups during collection. See `tests/conftest.py` for the current mock set and the lifecycle docstring.
- No env var assignments needed (PEP 562 lazy loading, Pydantic validates only when called)
- If future imports trigger env var reads at collection time, use direct `os.environ["KEY"] = "value"` (never `setdefault()`)

**Fixtures:**
- Type hints: `MockerFixture` → `MockType` return (strict mypy in conftest.py)
- Factory pattern (not context managers): `def _factory() -> MockType` returned by fixture
- Environment mocking: `mocker.patch.dict(os.environ, env_dict)`
- Test functions: Don't type hint custom fixtures, optional hints on built-ins for IDE
- Naming: `Mock` prefix for test double classes (e.g., `MockState`); `mock_xxx` for instance fixtures; `create_mock_xxx` for factory fixtures returning `Callable`; no prefix for convenience fixtures returning real objects (e.g., `oauth_flow_config`); factory inner function named `_factory`

**ADK Mocks:** Custom mocks mirror real ADK interfaces and live in `tests/conftest.py` (readonly contexts, callback contexts, tool contexts, LLM request/response shapes, etc.). For edge cases requiring custom internal structure, add a specific named fixture.

**Mock Usage:** Never import mock classes directly in test files — always use or add a fixture in `conftest.py`.

**Organization:** Mirror source (`src/X.py` → `tests/test_X.py`). Class grouping. Descriptive names (`test_<what>_<condition>_<expected>`).

**Validation:** Pydantic `@field_validator` (validate at model creation). Tests expect `ValidationError` at `model_validate()`, not at property access. Property simplified with `# pragma: no cover` for impossible edge cases.

**Mypy override:**
```toml
[[tool.mypy.overrides]]
module = "tests.*"
disable_error_code = "arg-type"
```

**Coverage:** 100% on production code. Exclusions defined in `pyproject.toml`. Test behaviors (errors, edge cases, return values, logging), not just statements.

**Parameterization:** Thoughtfully. Inline loops OK for documenting complex behavior (e.g., boolean field parsing).

**ADK patterns:**
- **InstructionProvider:** Function `def fn(ctx: ReadonlyContext) -> str`. Pass function ref (not called) to `GlobalInstructionPlugin(fn)`. Plugin calls at runtime. Test with `MockReadonlyContext`.
- **Callbacks:** All return `None` (observe-only); other callbacks may modify/short-circuit. Memory callback persists session summaries to memory service.
- **Async callbacks:** `asyncio_mode = "auto"` in pyproject.toml, verify caplog.
- **Controlled errors:** `MockMemoryCallbackContext(should_raise, error_message)`.

## Dependencies

```bash
uv add pkg                      # Runtime
uv add --group dev pkg          # Dev
uv lock --upgrade               # Update all
```

**Key runtime:** `asyncpg` (async PostgreSQL for Cloud SQL sessions), ADK (core), google-cloud libraries (auth, observability). Full set in `pyproject.toml`.

**When updating versions:** Both `pyproject.toml` and `uv.lock` must be committed together for CI `--locked` to pass.

## CI/CD & Deployment

**Deployment Modes:** Dev-only (default, `production_mode: false` in ci-cd.yml config job) deploys to dev on merge. Production mode (`production_mode: true`) deploys dev+stage on merge, prod on git tag with approval gate. See [Infrastructure Guide](docs/infrastructure.md).

**Orchestration (Template Internals):** `ci-cd.yml` is the orchestrator; reusable workflows live in `.github/workflows/`. PR: build `pr-{sha}`, dev-plan, comment. Main: build `{sha}`+`latest`, deploy dev (+ stage in prod mode). Tag: prod deploy (prod mode only). **Deploy by immutable digest** (not tag) to guarantee a new Cloud Run revision. Option to deploy to dev on all PRs: single-line change to `ci-cd.yml` (remove `&& github.event_name == 'push'` from dev-apply condition).

**Auth:** WIF (no SA keys). Bootstrap auto-creates GitHub Variables for the WIF principal, project, region, registry, and state bucket. See bootstrap module outputs in `terraform/bootstrap/module/github/` for the current set.

**Job Summaries:** Use `mktemp`, `tee "$FILE"`, `${PIPESTATUS[0]}` for streaming + capture. Export GitHub context to shell vars, capture once, check for empty outputs.

## Terraform

**Pre-Bootstrap:** `terraform/bootstrap/pre/` — single-file Terraform root, run once before any bootstrap environment. Uses `terraform.tfvars` for configuration. Creates one GCS bucket per environment. Outputs `terraform_state_buckets` map used for bootstrap `-backend-config` and `terraform_state_bucket` input variable. **Local state only — do not lose `terraform/bootstrap/pre/terraform.tfstate`.**

**Bootstrap Structure (Template Internals):**
- Each environment (`dev/`, `stage/`, `prod/`) is a separate Terraform root calling shared modules (`gcp/`, `github/`)
- Each uses GCS remote state (from pre) and `terraform.tfvars` for configuration
- Creates: WIF, Artifact Registry, GitHub Environments, GitHub Environment Variables
- Enables APIs and grants WIF IAM roles sufficient for the base template ONLY — **do not modify to add custom services/roles** (extend in `terraform/main/services.tf` and `terraform/main/iam.tf`)

**Cross-Project IAM (Production Mode — Template Internals):** Stage and prod bootstrap roots grant cross-project Artifact Registry reader access for image promotion.
- `stage/main.tf`: stage WIF reads dev's registry. `prod/main.tf`: prod WIF reads stage's
- Uses WIF principals (not service accounts), complies with org policies restricting cross-project SA usage
- Variables: `promotion_source_project`, `promotion_source_artifact_registry_name`
- Binding: `google_artifact_registry_repository_iam_member` with `member = module.gcp.workload_identity_pool_principal_identifier`
- See `terraform/bootstrap/{stage,prod}/main.tf`

**Main Module (Template Internals except `services.tf`/`iam.tf`):** Cloud Run deployment in `terraform/main/` (may require downstream env var customization or extension). Provisions VPC + Cloud SQL private IP, bastion, app SA, Cloud Run with Auth Proxy sidecar, Agent Engine, and GCS bucket. See `terraform/main/` for resource definitions.
- Shared `local.cloud_sql_proxy_args` between bastion cloud-init and Cloud Run sidecar (bastion adds `--address=0.0.0.0`, `--impersonate-service-account`, COS iptables rule)
- Remote state in GCS; inputs from `TF_VAR_*` (GitHub Environment variables)
- Requires `TF_VAR_environment` (dev/stage/prod)
- Outputs: `bastion_instance`, `bastion_zone` (for docker-compose `.env`)

**Naming:** Resources `${var.agent_name}-${var.environment}`. Service account IDs truncate `agent_name` to 30 chars (GCP limit). Cloud Run auto-sets `TELEMETRY_NAMESPACE=var.environment`.

**Runtime Variable Overrides:** GitHub Environment Variables → `TF_VAR_*` → `coalesce()` skips empty/null. `docker_image` is nullable (defaults to previous for infra-only updates). Some infrastructure URIs (session/memory/artifact services, CORS) are hard-coded in Terraform (no override, requires intentional code commit for changes). See `coalesce()` call sites in `terraform/main/` for the current overridable surface.

**IAM Layering:** Dedicated GCP project per env. Project-level WIF roles same-project only (in `terraform/bootstrap/module/gcp/`). Cross-project Artifact Registry grants in environment bootstrap roots. App SA roles in `terraform/main/main.tf`. Additional WIF roles in `terraform/main/iam.tf` (consumer extension point).

**Main Module Extension Points (consumer-defined):**
- `terraform/main/services.tf` — add GCP APIs using `google_project_service`; `time_sleep.service_enablement_propagation` uses `for_each` over `services` — one 120s sleep per service, created only when that service is added (zero overhead when empty); some GCP services have async backend initialization after the API is marked enabled; resources needing a new service declare `depends_on = [time_sleep.service_enablement_propagation["api.googleapis.com"]]`
- `terraform/main/iam.tf` — add WIF principal IAM roles using `google_project_iam_member`; `time_sleep.wif_iam_propagation` uses `for_each` over `wif_additional_roles` — one 120s sleep per role, created only when that role is added (zero overhead when empty); resources needing a new role declare `depends_on = [time_sleep.wif_iam_propagation["roles/example"]]`; list multiple instances explicitly when a resource needs more than one new role
- WIF principal identifier available via `var.workload_identity_pool_principal_identifier` (passed from bootstrap's `WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER` GitHub Variable)

**Cloud Run probes (Template Internals):** App container probe configured to allow ~120s for credential init. Auth Proxy sidecar has no startup probe — Cloud Run restarts on crash, more reliable than probing. Shared proxy flags in `local.cloud_sql_proxy_args`; bastion-only flags (`--address=0.0.0.0`, `--impersonate-service-account`) in `terraform/main/templates/bastion-cloud-init.yaml`. Debug heuristic: local works but Cloud Run fails = credential or VPC egress issue.

## Local Development

**docker-compose:** IAP tunnel container tunnels to bastion Auth Proxy via `network_mode: "service:app"` so the app reaches Cloud SQL at `localhost:5432` (same as Cloud Run). Requires `BASTION_INSTANCE`, `BASTION_ZONE`, `GOOGLE_CLOUD_PROJECT` in `.env`. Developer IAM prerequisite: `roles/iap.tunnelResourceAccessor`. Editable install via `ARG editable=true`. Watch: `sync+restart` for `src/`, `rebuild` for deps. Binds `127.0.0.1:8000`. See `docs/references/docker-compose-workflow.md` for full workflow.

**Test deployed service:** `gcloud run services proxy <service-name> --project <project> --region <region> --port 8000`. Service name: `${agent_name}-${environment}` (e.g., `my-agent-dev`).

## Documentation Strategy

**CRITICAL:** Task-based organization (match developer mental model), not technical boundaries.

**Structure:**
- **README.md:** ~200 lines max. Quick start only. Points to docs/.
- **docs/*.md:** ~300 lines max. Action paths ("I want to..."). Index in `docs/README.md`.
- **docs/references/*.md:** No limit. Deep-dive technical docs. Optional follow-up. Index in `docs/references/README.md`.

**Rules:**
- Task-based, not tech-based (e.g., "Infrastructure" not "Terraform" + "CI/CD" separately)
- Hub-and-spoke navigation: `docs/README.md` and `docs/references/README.md` are the navigation indexes
- Inline cross-links only when critically contextual (hybrid approach)
- No "See Also" sections - rely on index navigation instead
- Single source of truth: env vars only in `docs/environment-variables.md`
- Update `docs/README.md` when adding docs
- Keep guides digestible (<300 lines). Move details to `references/`.

**Callouts:** Use GFM callout blocks (`> [!TYPE]`) sparingly — only when content genuinely warrants elevated attention. Don't use callouts for normal information. (`NOTE` = you should know this, `TIP` = this could help you, `IMPORTANT` = do this, `WARNING` = don't do that, `CAUTION` = this will destroy something)
