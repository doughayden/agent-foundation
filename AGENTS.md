# AGENTS.md

Guidance for AI agents. **CRITICAL: Update this file when establishing project patterns.**

## How to Maintain This File

**Pointer over enumeration.** Reference the source of truth instead of duplicating its contents. Lists of files, env vars, resources, workflows, dependencies, etc. go stale when implementations change but the concept does not. Stale lists waste tokens in every future session and mislead readers. Pointers stay valid as long as the source exists.

- ✅ "Required env vars: see `ServerEnv` in `config.py` and `docs/environment-variables.md`"
- ❌ "Required: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, AGENT_NAME, ..."
- ✅ "GCP APIs added in `terraform/main/services.tf`"
- ❌ "Enabled APIs: cloudsql, run, iam, ..."

**Enumerate only when:** the list itself IS the concept (e.g., a security posture's guarantees), discoverability would be hard, or items are load-bearing rules every session must know without reading more files. Default to *concept + location*, not *contents*.

**Template internals vs. consumer extensions.** This is a base template that downstream projects fork. Mark sections describing template internals so consumers understand they carry higher upstream-sync cost if customized — consumers may still modify anything, but expect merge complexity. Intended extension surfaces belong in **Consumer Extension Points** below.

**Root vs. directory files.** A rule that only matters while editing files in one directory goes in that directory's `AGENTS.md`; a rule a session can break without opening a file there (running a command, creating a file, changing another directory) stays here. Add new directory files to the table below.

## Directory Instructions

Read the matching file before working in its directory. Claude Code also loads it on demand when a session reads a file there with the `Read` tool.

| File | Covers | Ownership |
|---|---|---|
| `.github/workflows/AGENTS.md` | Orchestration, path filters, stage-success gate, required checks, workflow patterns, actionlint | Template Internals |
| `terraform/AGENTS.md` | Pre-bootstrap, bootstrap roots, main module, Cloud Run probes | Template Internals (except `services.tf`/`iam.tf`/`monitoring.tf` locals) |
| `tests/AGENTS.md` | Lanes, eval gate, smoke lane, conftests, fixtures, mocks, organization | Consumer-owned; eval-gate internals marked |

## Critical

- **Never commit to main** (branch protection enforced). Workflow: feature branch → PR → merge.
- **Version bumps:** Update `pyproject.toml` → `uv lock` (both files together required for CI `--locked` to pass).
- **Never lose `terraform/bootstrap/pre/terraform.tfstate`** (pre-bootstrap is local state only).

## Template Initialization (One-Time)

Base template repo. Run `uv run init_template.py --dry-run` (preview) or `uv run init_template.py` (apply). Script docstring contains complete usage/cleanup instructions. After use, delete `init_template.py`, `./.log/init_template_*.md`, README Bootstrap step 0, and this Template Initialization section.

## Quick Commands

```bash
# Local
uv run server                               # API at 127.0.0.1:8000, local .adk/ storage
LOG_LEVEL=DEBUG uv run server               # Debug mode
docker compose up --build --watch           # Against deployed resources (bastion tunnel)
uv run pytest --cov --cov-report=term-missing  # Tests + 100% coverage required
uv run pytest tests/eval -m "deterministic"  # Deterministic agent eval gate (real LLM, Vertex AI creds)

# Code quality (hooks run on commit; this checks the whole tree as CI does)
uv run pre-commit run --all-files
uv run pytest tests/integration                # Postgres lane (needs Docker)

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
> Python file references use basenames only: the single package under `src/` makes them unambiguous (`Glob src/*/<basename>`), and forks never rename paths here after `init_template.py`.

| To... | Edit | Notes |
|---|---|---|
| Add a custom tool | define `func` in `tools.py` + register in `agent.py` | `root_agent = LlmAgent(..., tools=[..., FunctionTool(func)])` |
| Add a plugin | `build_plugins()` in `plugins.py` | Returns the App's full plugin list; `agent.py` passes it as `App.plugins`. **Order matters**: ADK runs plugins in list order and a non-`None` return skips later plugins and the agent's callbacks. Cloud Run detection reads `K_CONFIGURATION` directly, never `ServerEnv` (`agent.py` stays settings-free for ADK's loader) |
| Add a callback | `callbacks.py` | ADK callbacks return `None` to observe, or a modified value to mutate/short-circuit — choose per intent |
| Customize agent instructions | `prompt.py` | InstructionProvider (signature and test pattern: `tests/AGENTS.md` ADK patterns). **Keep per-turn-volatile values (time, request IDs) out of it**: the string is the cached prefix, so volatility busts prompt caching every turn; expose time via a tool (`get_current_time`) |
| Add an agent eval case | `tests/eval/data/*.evalset.json` | Mark the test `deterministic` (PR gate, `test_config.json`) or `judge` (merge gate, `full_eval_config.json`); user-sim files have no gate. Validate non-flaky: run `uv run pytest tests/eval -m "deterministic"` ≥3 times. Authoring and commands: `docs/references/agent-evals.md` |
| Add an env var | field on `ServerEnv` in `config.py` (name = env var lowercased) + `docs/environment-variables.md` | Documentation is mandatory: see Environment Variables below |
| Enable a GCP API | `terraform/main/services.tf` | `google_project_service`; downstream resources `depends_on = [time_sleep.service_enablement_propagation["api.googleapis.com"]]` |
| Grant a WIF role | `terraform/main/iam.tf` | `google_project_iam_member`; downstream resources `depends_on = [time_sleep.wif_iam_propagation["roles/example"]]` |
| Tune or activate alerts | `alert_thresholds` / `alert_notification_channels` in `terraform/main/monitoring.tf` | Dry-run by default (no channel). Conditions read native Cloud Run metrics only, each mirroring a Metrics-tab chart: `docs/observability.md` Alerting |
| Override runtime config | GitHub Environment Variables → `TF_VAR_*` | See `coalesce()` call sites in `terraform/main/` for current overridable surface |
| Change the model call timeout | `ROOT_AGENT_MODEL_TIMEOUT_MS` in `agent.py`; judge criteria's `judge_model_config.http_options.timeout` in `full_eval_config.json` and `user_sim_config.json` | Per-call cap (ms) in evals AND the deployed service, never retried. Size it per `docs/development.md` Model Call Timeout, not a template default; eval retries: `docs/references/agent-evals.md` Timeouts and retries |
| Swap the LLM | `ROOT_AGENT_MODEL` in `agent.py` | A model string covers Gemini/Claude/Vertex-hosted; other connectors need the matching ADK extra and a connector instance ([ADK models](https://adk.dev/agents/models/)) |
| Add a CI lane for a subproject | new `.github/workflows/ci-<name>.yml` (copy `ci.yml`) | Unique top-level `name:`, scoped filters, new `<Name> / status` in branch protection: `docs/references/cicd.md` Subproject Builds |
| Add a subproject Docker image to the deploy pipeline | new `build-<name>` job in `ci-cd.yml` calling `docker-build.yml` with `image_name`/`context`; mirror the promote/resolve calls and pass the digest to `terraform-plan-apply.yml` as a new `TF_VAR_*` | Add the context path to the `changes` job's `deploy` filter or the job never fires. `.dockerignore` is read from the context root, so add `<context>/.dockerignore` if needed. Pattern and registry constraint: `docs/references/cicd.md` Subproject Builds |

**Template internals** (higher upstream-sync cost if customized — consumers may still modify, but expect merge complexity on future upstream syncs):
- `terraform/bootstrap/` — bootstrap roots and shared modules
- `.github/workflows/` — CI/CD orchestration
- `terraform/main/` files other than `services.tf`, `iam.tf` and the `monitoring.tf` locals

## Architecture Overview

**ADK App** (`agent.py`): `App` composes `LlmAgent` (LLM wrapper with instructions, subagent options, custom tools, callbacks) and the plugins from `build_plugins()` (`plugins.py`): `GlobalInstructionPlugin` (dynamic instruction generation via InstructionProvider), then `LoggingPlugin` (stdout lifecycle trace, only off Cloud Run, since it prints user content outside the capture settings). Exact model wiring in `agent.py`, plugin list in `plugins.py`.

**Package exports** (`__init__.py`): PEP 562 `__getattr__` lazy-loads `agent`, so ADK's loader puts `.env` into `os.environ` before `agent.py` runs module-level code.

**Module roles:** `agent.py` (composition), `tools.py` / `callbacks.py` / `prompt.py` / `plugins.py` (consumer extension points — see Consumer Extension Points), `server.py` (FastAPI + ADK via `get_fast_api_app()`), `config.py` (pydantic-settings `ServerEnv`, type-safe fail-fast), `telemetry.py` (OpenTelemetry init).

**Memory:** Read via the `load_memory` function tool (LLM queries on-demand; ADK auto-appends a usage instruction when the tool is registered). Write via the `add_session_to_memory` after-agent callback.

**Session Service:** Cloud SQL Postgres (private IP) via ADK `DatabaseSessionService`; `get_fast_api_app()` routes `postgresql://` URIs automatically (no application code). Auth Proxy sidecar, IAM auth, no passwords. Scaling (tier first, then pooling), retention sweep, posture: `docs/references/cloud-sql.md`, `docs/references/security-posture.md`.

**asyncpg type strictness:** Direct SQL against the session DB must bind typed columns as native Python objects — asyncpg's codecs reject ISO strings for `timestamptz` (and other typed columns) with `DataError`. sqlite via aiosqlite tolerates strings, so sqlite-only tests miss the bug. Use `text(...).bindparams(bindparam("x", type_=DateTime(timezone=True)))` to force dialect-aware conversion.

**Networking:** private IP via Private Services Access, Cloud Run on direct VPC egress, COS bastion for IAP-tunnel developer access. Resources and bastion detail: `docs/references/deployment.md` Main Module, `docs/references/security-posture.md`.

**Docker:** multi-stage, uv pinned, non-root. Layering and cache strategy: `docs/references/dockerfile-strategy.md`.

**Observability:** `configure_telemetry()` (`telemetry.py`) must run **before** `get_fast_api_app()`: it owns all providers, and a monkey-patch of ADK's `api_server._setup_telemetry` only attaches the web UI processors. Google Cloud only: every signal goes to the Telemetry API over OTLP gRPC with scoped ADC, endpoint passed explicitly (`OTEL_EXPORTER_OTLP_*` endpoints ignored); other backends replace `telemetry.py`. Resource from the GCP detector plus `OTEL_RESOURCE_ATTRIBUTES`; on Cloud Run the `cloud_run_revision` log labels map from detected `faas.*`/`cloud.region` (plus `K_CONFIGURATION`, which the detector does not expose). Metrics only when the resource has `cloud.region`. `OTEL_SDK_DISABLED` is left to the SDK. **Sampler must record under an unsampled remote parent** (`build_sampler()`): ADK continues Cloud Run's `traceparent` (sampled at most 0.1 req/s per instance), so the SDK default records only turns that land on a sampled request; `OTEL_TRACES_SAMPLER` replaces it. Never put `gcp.resource_type` on the meter resource (Telemetry API drops the metrics). Only `server.py` configures telemetry; `adk web`/`api_server`/`run` don't. Design, precedence, metrics routing: `docs/references/opentelemetry-architecture.md`.

## Environment Variables

**CRITICAL:** Any new env var introduced to the codebase MUST be documented in `docs/environment-variables.md`. No exceptions. Include purpose, default, where to set, and required/optional. `ServerEnv` in `config.py` is the typed source of truth; `docs/environment-variables.md` is the canonical reference.

**Settings shape:** `ServerEnv(BaseSettings)` (`config.py`), field name = env var lowercased (no aliases), no `env_file`. `initialize_environment()` runs `load_dotenv(find_dotenv(usecwd=True))` (working directory, override off) as the single `.env` mechanism, so **the shell wins** and every `os.environ` reader sees `.env` (`docs/environment-variables.md` Precedence). Code outside the models takes settings as arguments, never `os.getenv`. Tests: `isolated_environ` (no-op `load_dotenv`), `create_dotenv` for `.env` cases (real lookup from a patched working directory).

## Code Quality

**Workflow:** hooks run on every `git commit` (after `uv run pre-commit install`). Before pushing:
```bash
uv run pytest --cov && uv run pytest tests/integration   # + eval lane when agent behavior changes; smoke needs a deployed URL
uv run pre-commit run --all-files                         # whole tree, as CI runs it (hook changes, upstream syncs)
```

**Hook order:** mutators before readers: `ruff-check --fix` → `ruff-format` → mypy (`docs/development.md` Pre-commit Hooks). **NEVER set `[tool.ruff] fix = true`** — a bare `ruff check` then rewrites and exits 0, so a lint gate passes every auto-fixable rule; pass `--fix` per call site.

**Pre-commit:** fix-in-place hooks in `.pre-commit-config.yaml`; CI's `code-quality` job runs the same suite (`--all-files --show-diff-on-failure`), so the merge gate cannot drift from local hooks. **Never add a separate CI step for a tool a hook already runs** — change the hook. **`terraform validate` is deliberately NOT a hook** (per-root init; CI validates). Version sources per hook (`autoupdate` is a no-op for `language: system`) and tenv: `docs/development.md` Pre-commit Hooks.

**Terraform version:** `.terraform-version` (exact `X.Y.Z`) is the single pin for tenv and every CI `setup-terraform` step; `TestTerraformVersionPin` (`tests/unit/test_pinned_versions.py`) fails on a hard-coded `terraform_version`. **NEVER set a Terraform version literal in a workflow.** `required_version` in each root stays a range. **Add a pin-parity case there whenever a pin gains a second home.**

- **mypy:** `strict = true` (plus `warn_unreachable`, outside the strict set) and the `pydantic.mypy` plugin, over `src/` and `tests/`. Never re-enumerate flags `--strict` already implies. `no_implicit_reexport` rejects names a package does not re-export (ADK's lazy `google.adk.tools`, `google.adk.models`): import from the defining submodule. `# type: ignore[code]` only where the fix sits upstream, with the reason on the line above.
- **ruff:** 88 char line length, enforces bandit/simplify/use-pathlib. **Always use `Path` objects** (never `os.path`).
- **pytest:** 100% coverage on production code. Exclusions in `pyproject.toml`: `exclude_also` line patterns first; a file omit only for wiring another lane runs, named in its comment (`docs/references/code-quality.md` Coverage Configuration). Fixtures in `conftest.py`, async via pytest-asyncio.

**Type narrowing:** **NEVER use `cast()`** - always use `isinstance()` checks for type narrowing (provides both mypy inference and runtime safety).

**Code quality exclusions:**
- `# noqa` - Use specific codes (`# noqa: S105`) with justification. Common: S105 (test mocks), S104 (0.0.0.0 in Docker), E501 (URLs).
- `# pragma: no cover` - Only for provably unreachable defensive code (e.g., Pydantic validation guarantees). Never for "hard to test" code.

## Testing Patterns

Test-writing rules (lanes, eval gate, fixtures, mocks, organization): `tests/AGENTS.md`. These apply before you open a test file:

**Tools:** pytest, pytest-cov (100% required), pytest-asyncio, pytest-mock (`MockerFixture`, `MockType`)

| Lane | Needs | Deterministic | Local command |
|---|---|---|---|
| `tests/unit` | in-process only (mocks at boundaries) | yes | `uv run pytest` (default) |
| `tests/integration` | real external resource (Postgres) | yes | `uv run pytest tests/integration` |
| `tests/smoke` | live deployed URL | yes | `uv run pytest tests/smoke` |
| `tests/eval` | real LLM + Vertex AI creds (costs money) | `deterministic` yes; `judge` no | `uv run pytest tests/eval -m "deterministic"` |

- **Coverage:** 100% on production code; every `src/` change ships its tests
- **No shared `tests/conftest.py` — keep it absent even for a benign shared value**: a later edit could add a `pytest_configure` there and silently suppress the real-cred smoke and eval lanes' credentials
- **Never add pytest to pre-commit hooks** — hooks stay static-checks-only
- **Eval lane is not runnable as a sandboxed action** (Vertex egress + ADC read): run it in CI or your own terminal, never by widening the sandbox

## Dependencies

```bash
uv add pkg                      # Runtime
uv add --group dev pkg          # Dev
uv lock --upgrade               # Update all
```

**Python version:** `.python-version` is the source; `TestPythonVersionParity` asserts every other pin. **NEVER set a Python version in a workflow** (`uv python install X`, setup-uv `python-version:`, `UV_PYTHON`, `--python`). One interpreter, no CI matrix. Pins and bump procedure: `docs/development.md` Python Version.

**uv version:** `[tool.uv] required-version` is a RANGE (the exact pin's minor series; `==` blocks every uv command for anyone whose uv moved). Dockerfile uv image and every `setup-uv` `version:` hold one exact version; `TestUvVersionPins` asserts both. The `uv-lock` hook is `language: system` (the developer's uv, CI's setup-uv uv), so it carries no pin. **Pick a uv the pinned `setup-uv` lists in its checksum table**, never pass `checksum:`. Bump procedure: `docs/development.md` uv Version.

## CI/CD & Deployment

**Deployment Modes:** Dev-only (default, `production_mode: false` in ci-cd.yml config job) deploys to dev on merge. Production mode (`production_mode: true`) deploys dev+stage on merge, prod on an admin-pushed `prod-vX.Y.Z` promotion tag (on the commit a `vX.Y.Z` release tag marks; `v*` alone deploys nothing) with approval gate. See [Infrastructure Guide](docs/infrastructure.md).

**Template Internals:** orchestration, the stage-success gate, required checks and workflow patterns: `.github/workflows/AGENTS.md`. Terraform bootstrap and main module: `terraform/AGENTS.md`.

## Local Development

**`uv run server`:** local dev path, first run in `docs/getting-started.md` (before bootstrap). URIs unset → ADK `.adk/` storage (persistent sessions/artifacts, in-process memory).

**Compose:** use deployed resources (app + IAP tunnel → Cloud SQL at `localhost:5432`). Details: `docs/development.md` Connect to Deployed Resources.

**Test deployed service:** `gcloud run services proxy <agent_name>-<environment> --project <project> --region <region> --port 8000`.

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
- Never name the Python version in docs (prose or examples); point to `.python-version`, use `X.Y` in snippets. Literals drift on every bump
- Update `docs/README.md` when adding docs
- Keep guides digestible (<300 lines). Move details to `references/`.

**Callouts:** Use GFM callout blocks (`> [!TYPE]`) sparingly — only when content genuinely warrants elevated attention. Don't use callouts for normal information. (`NOTE` = you should know this, `TIP` = this could help you, `IMPORTANT` = do this, `WARNING` = don't do that, `CAUTION` = this will destroy something)
