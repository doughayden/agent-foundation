# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Dependabot alerts and security updates, managed by the dev bootstrap root (every deployment mode applies it): GitHub flags known vulnerabilities in every locked dependency, transitive ones included, and opens fix pull requests outside the monthly version-update schedule, one grouped pull request for open `uv` security fixes. Apply the dev bootstrap root to turn them on (#338, #358)
- Dependabot `uv` ecosystem: a monthly pull request with minor and patch updates, and a separate pull request for each major update, with the same 6-day cooldown as the other ecosystems. `google-adk` is ignored, since its exact pins move only after each release is tested (#331, #358, #363)
- Dependabot `terraform` ecosystem with the same 6-day cooldown as actions and hooks, in two entries: `terraform/main` (one monthly pull request with every provider update, planned against dev on the pull request and applied on merge) and the bootstrap roots and modules (one monthly pull request per provider across all of them). CI never runs bootstrap, so verify a bootstrap bump with a local `terraform init` and `terraform plan` per root; forks that won't re-run bootstrap can delete that entry (#330, #358)
- OpenTelemetry logs over OTLP gRPC alongside traces: every signal goes to the Google Cloud Telemetry API (`https://telemetry.googleapis.com:443`) with Application Default Credentials (`cloud-platform` scope). The endpoint goes to each exporter explicitly, so the SDK's `OTEL_EXPORTER_OTLP_*` endpoint variables have no effect; to use another backend, replace `telemetry.py`. The standard `OTEL_SDK_DISABLED=true` turns export off through the SDK itself, leaving the web UI trace view empty. Metrics (ADK's GenAI metrics) go to Cloud Monitoring through the Telemetry API when the resource has `cloud.region`: automatic on Cloud Run, where the GCP resource detector supplies it, and locally when `OTEL_RESOURCE_ATTRIBUTES` sets it. The meter resource leaves out the `cloud_run_revision` attributes, and the runtime service account gains `roles/telemetry.metricsWriter`. `ADK_EXPERIMENTAL_TELEMETRY=TRUE` in `.env.example` and on the Cloud Run service adds ADK's `adk.experimental.*` metrics and span data. Uvicorn's `/health` access lines (Cloud Run startup and readiness probes) are dropped from stdout and Cloud Logging. On Cloud Run, traces and logs carry the `cloud_run_revision` attributes, mapped from the detector's `faas.name`, `faas.version` and `cloud.region`, so logs appear in the service's Logs tab. Deployed with `NO_CONTENT`, Terraform also sets ADK's `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`, since ADK's live streaming otherwise records the content it sends to the model on `gcp.vertex.agent.data` whatever the capture mode; locally, set both in `.env` to keep user content out of telemetry. Startup prints the endpoint, whether metrics are on, and the exported resource attributes (#224)
- Image tagging strategy in `docs/references/cicd.md`: which tags each event writes to which registry, the build-once, promote-by-digest flow, why registry tags stay mutable (deployment consumes only digests and `require-stage-success` ties the promoted digest to a green stage smoke, while repository-wide immutable tags would reject the moving `latest` and `buildcache` tags), how to re-validate versus rebuild a merge run, and how registry cleanup retention bounds tagging and rollback (#216)
- Per-call model timeouts: `ROOT_AGENT_MODEL_TIMEOUT_MS` (120 seconds) on the agent's `generate_content_config`, which applies in evals and the deployed service, and a 60-second `judge_model_config.http_options.timeout` on every judge criterion in `full_eval_config.json`. A hung call now raises `TimeoutError` inside the run, and the eval gates exit `EVAL_ERROR_EXIT_CODE` with the traceback, instead of waiting out the CI job limit or hanging a local run. Timeouts are not retried. `docs/development.md` points to the upstream references for sizing the agent's timeout. (#272)
- Judge-model pin: `JUDGE_MODEL` in `tests/unit/test_pinned_versions.py` names the accepted eval scoring model, and the unit lane fails when any `judge_model` or user-simulator `model` under `tests/eval/data/` differs from it, naming each drifted entry. Every entry stays explicit, since an omitted one inherits ADK's default and escapes the check, so a model bump edits the constant and the entries together and cannot miss one. The judge model is pinned independently of the agent's `ROOT_AGENT_MODEL` (#253)
- Workflow linting with actionlint `v1.7.12` as a pre-commit hook, which CI enforces by running the hook suite (#259). The hook includes actionlint's shellcheck pass over inline `run:` blocks, after fixing the 59 SC2086/SC2129 findings it reported across seven workflows (#255). That pass runs only when shellcheck is on `PATH`: the CI runner has it, so a developer without it sees shellcheck findings only in CI's `code-quality` job. The hook's `rev` is the only pin (#215)
- Pre-commit coverage for the remaining non-Python file types: `terraform fmt` over `.tf` files, plus `check-json` and `check-merge-conflict` from the already-pinned hooks repo. CI runs these hooks too, so `terraform/bootstrap/**` is fmt-checked in CI for the first time. `terraform validate` is not a hook: it needs `terraform init` per root, which is too slow for a commit (#215, #259)
- `timezone_abbreviation` in the `get_current_time` result (`EDT`, `UTC`, and so on). The abbreviation is the form a model reaches for when rendering a time in prose, but deriving it from the timezone name and UTC offset takes daylight-saving knowledge the tool result did not carry, so the agent was asserting it ungrounded. The judge gate's `hallucinations_v1` metric caught this correctly: it scores each response sentence for entailment against the tool output and marked a response containing "EDT" unsupported while a response using only returned values passed. The field is `None` for the 231 of 598 IANA zones tzdata renders as a numeric offset, like `Asia/Ho_Chi_Minh` and `America/Sao_Paulo`, where an "abbreviation" would only restate `utc_offset`; the docstring directs the model to name the offset in that case (#213)
- Judge-eval CI gate (`.github/workflows/judge-eval.yml`): a reusable workflow that runs the App-aware in-process LLM-judge eval (`uv run pytest tests/eval -m "judge"`) under the eval lane's WIF-to-Vertex credential posture, so it scores the checked-out agent with no deployed revision, no service URL, and no invoker auth. `ci-cd.yml` calls it as `judge-eval` on merge to main: blocking in production mode, signal only in dev-only mode. Blocking is a `gating` input rather than `continue-on-error`, because a job that calls a reusable workflow may not use that keyword and the tag-time gate reads this job's conclusion. The model-liveness preflight runs as its own always-blocking step under a new `liveness` marker, and the judge test leaves through a dedicated exit code when the eval could not run or a run went unscored (#240), so the scored step's exit 1 can only mean a sub-threshold score: `gating: false` absorbs a behavioral regression, while a dead endpoint or a broken run fails the job in either mode and the summary names which. A separate always-run step writes that summary, so a failed preflight reports too. (#213)
- Inline review comments on the Claude PR review (`claude.yml`): line-specific findings now post on the lines they concern, with committable `suggestion` blocks, instead of collapsing into one tracking comment. Tag mode's tool allowlist is fixed, so `create_inline_comment` is granted via `claude_args`; without it the inline-comment MCP server never starts. Comment classification is disabled, since it runs only when an Anthropic API key is present and would otherwise make the set of posted comments depend on the auth path (#194)
- Direct-to-Anthropic auth for the Claude PR review (`claude.yml`): setting either the `ANTHROPIC_API_KEY` repository secret (an Anthropic organization API key) or `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) overrides the default Vertex AI path, so the review runs without Vertex model access. `ANTHROPIC_API_KEY` wins when both are set; Vertex AI remains the default when neither is. A new "Report model auth path" step names the selected path in the job log
- mypy cache in the `ci.yml` `code-quality` job: every run restores `.mypy_cache`, keyed on `uv.lock`, `pyproject.toml` and `.python-version` with fallbacks to the newest compatible entry, so mypy re-checks only what changed instead of the full dependency graph (73s cold, 3s warm locally). Only pushes to main save, since the cache is about 400 MB uncompressed and a per-PR-run entry would push the uv and pre-commit caches out of the repository's Actions cache quota (#282)
- `.terraform-version` as the single Terraform version pin (1.14.9, the newest 1.14 patch, so deploys keep the 1.14 line `~> 1.14.0` resolved to). [tenv](https://github.com/tofuutils/tenv) is now a required prerequisite that installs that version locally, since a standalone `terraform` ignores the file and drifts from CI. Every `hashicorp/setup-terraform` step in CI reads it into `terraform_version`, since the action has no version-file input. `tests/unit/test_pinned_versions.py` fails when a workflow hard-codes the version (#259)
- `prod-apply` protection guide (`docs/references/protection-strategies.md`): recommended settings, `gh api` commands to configure, verify and approve a waiting deployment, and a plan table for private repositories, where required reviewers are unavailable outside GitHub Enterprise and `require-stage-success` remains the plan-independent guard. `docs/references/agent-evals.md` documents the gate interface for plugging in a custom eval strategy, by editing `tests/eval/data/` or pointing the `Judge Eval` job at your own reusable workflow (#214)
- codespell spell check in the pre-commit suite, so CI's `code-quality` job catches common misspellings in code, docs and config. It runs as a local `language: system` hook with its version held by `uv.lock` (dev group), configured under `[tool.codespell]` in `pyproject.toml`, which skips `uv.lock` and ignores `rouge` (the ROUGE eval metric) (#296)
- Dry-run alerting (`terraform/main/monitoring.tf`): Cloud Monitoring alert policies for latency, traffic, errors and saturation, plus unhealthy instances, on the deployed Cloud Run service. A new readiness probe on `/health` stops routing requests to an instance that fails it, and the unhealthy-instances policy alerts on readiness failures and on any failed probe, including a startup probe that never passes. Each condition reads a native `run.googleapis.com` metric with its chart's aggregation, so it maps to a chart on the service's Metrics tab. The policies open incidents but notify nobody until you add a notification channel ID to `alert_notification_channels`; `alert_thresholds` holds tunable defaults. Bootstrap now enables `monitoring.googleapis.com` and grants the WIF principal `roles/monitoring.alertPolicyEditor`: re-run `terraform apply` in each environment's bootstrap root before the next deploy, or the main apply fails with a 403 when it creates the policies (if IAM has not propagated yet, re-run the deploy). Activation and the policy-to-chart map: `docs/observability.md` Alerting (#178)

### Changed
- **BREAKING:** Move `EVAL_ERROR_EXIT_CODE` from 6 to 70 ([`os.EX_SOFTWARE`](https://docs.python.org/3/library/os.html#os.EX_SOFTWARE)), since pytest 9 uses 6 for `MAX_WARNINGS_ERROR`, and upgrade pytest to 9.x. Update anything that matches the eval lane's exit code 6 (#335)
- **BREAKING:** Upgrade the Google provider to 8.x (constraint `>= 8.9.0, < 9.0.0`, locked at 8.9.0) in every Terraform root and module, along with random 3.9.1 and time 0.14.2, and the Terraform CLI in `.terraform-version` from 1.14.9 to 1.17.1. The template's resources need no changes, and every bootstrap root plans with no changes. Resources you added may be affected by the 8.0.0 removals and field changes: check the [8.0.0 upgrade guide](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/version_8_upgrade). Run `terraform init` in each root you use locally to install the new lockfile versions; tenv picks up the new CLI from `.terraform-version` (#330)
- **BREAKING:** Promote releases to prod with `prod-vX.Y.Z` tags instead of `v*` tags, and manage the `prod-apply` approval gate in bootstrap. A release is now two tags on one commit: `vX.Y.Z` marks the release and deploys nothing, and after that commit's merge run passes its stage jobs, a repository admin pushes `prod-vX.Y.Z` on the same commit to start `require-stage-success`, promotion and the gated prod apply. Metadata extraction fails a promotion tag unless it has the form `<env>-vX.Y.Z` and its `vX.Y.Z` release tag marks the same commit, and the prod image's version tag is that release tag. The prod bootstrap root's tag ruleset, renamed Production Promotion Tag Protection, now protects `prod-v*` instead of `v*`, so only repository admins can create, move or delete a promotion tag; `v*` tags are unprotected since they deploy nothing. Bootstrap now configures environment protection instead of ignoring it: the `prod` and `prod-apply` environments accept only `prod-v*.*.*` tags, and `prod-apply`'s reviewers, self-review, admin bypass and wait timer come from new `prod_apply_*` variables in `terraform/bootstrap/prod/terraform.tfvars`, so the manual UI setup step is gone and every apply enforces those values. This covers every environment bootstrap creates (`dev`, `stage`, `prod`, `prod-apply`): protection set in the UI on any of them is reset by the next apply of its root. The bootstrap roots' provider locks move to google 7.46.2 and github 6.13.0. To migrate, in order: (1) set the `prod_apply_*` variables to match your current `prod-apply` settings, since the next apply overwrites what you set in the UI; (2) delete every hand-made deployment tag rule on `prod` and `prod-apply` (`v*.*.*`, `v*`, or a `prod-v*.*.*` you added yourself; list and `DELETE` commands in `docs/references/protection-strategies.md` Environment Protection): bootstrap does not manage them, a `v*` rule keeps allowing `v*` tags, and a hand-made `prod-v*.*.*` rule makes the apply fail when bootstrap creates its own; (3) re-apply `terraform/bootstrap/prod`; (4) merge the workflow change. Only commits that contain this change can be promoted: a `prod-v*` tag on an older commit starts nothing, because that commit's own `ci-cd.yml` still triggers on `v*`. Roll back to an earlier build with a Cloud Run traffic split (`docs/infrastructure.md` Rollback) (#319)
- Make the first local run need no deployed infrastructure: `docs/getting-started.md` now sets up the project (auth, the Vertex AI and Telemetry APIs, `uv sync`, hooks, unit tests, `.env`) and runs the agent with `uv run server` before bootstrap and deploy. With the service URIs unset, ADK keeps sessions in SQLite and artifacts as files under `src/<package>/.adk/`, so sessions survive restarts; memory stays in-process. Docker Compose is now documented only as the path to deployed resources (`docs/development.md` Connect to Deployed Resources); `compose.yml` is unchanged. `.env.example` moves the deployed-resource values to an optional block at the end, and `docs/environment-variables.md` marks them optional and corrects their unset defaults: local SQLite sessions and local artifact files, not in-memory (#295)
- Measure `__init__.py`, `__main__.py` and `prompt.py` in the unit lane's coverage instead of omitting them whole, with new unit tests for the package's lazy loader and `return_global_instruction`. `server.py` and `agent.py` stay omitted as wiring, each comment naming the lane that runs it (smoke, eval). `docs/references/code-quality.md` states the rule and the common `exclude_also` line patterns to use before omitting a file (#284)
- **BREAKING:** Stop installing the project in the Docker image: copy `.venv` and `src` into the runtime stage as separate layers and import the package from `/app/src` via `PYTHONPATH`, so a source edit rebuilds and re-pushes only the `src` layer (about 12 kB compressed) instead of the whole virtual environment (about 71 MB). Drop `AGENT_DIR` from the image, since `server.py`'s default already resolves to `/app/src`, along with the `editable` build argument and the empty `README.md`; the runtime image no longer carries `pyproject.toml`, `uv.lock`, `README.md`, the `server` console script or the project's package metadata. Pin the runtime `app` user and group to ID 10001 (was a system-assigned ID) and give it no login shell (`/usr/sbin/nologin`); `docker exec` is unaffected. Compose hot reload (`sync+restart`) works unchanged. Rename `docker-compose.yml` to `compose.yml`, the Compose specification's default file name. To migrate, run `git mv docker-compose.yml compose.yml`, drop `args: editable` from it, and take the new `Dockerfile` in the same change: the old Dockerfile still installs the project, so with the new compose file hot reload would serve the installed copy instead of your synced edits. Re-apply Dockerfile customizations to the new runtime copies; `docs/references/dockerfile-strategy.md` explains the layout (#258)
- Validate `uv.lock` in the docs deploy: `deploy-docs.yml` now runs `uv sync --group docs --locked`, like every other CI sync (#258)
- **BREAKING:** The template owns the OpenTelemetry providers. `configure_telemetry()` now runs before `get_fast_api_app()` (at `server.py` import, not in `main()`), builds the resource in code from the GCP resource detector, and takes `service_name`, `project_id` and `log_level` instead of the removed `configure_otel_resource()`. The opt-in `app` argument and its FastAPI HTTP instrumentation are gone: ADK's `invoke_workflow` span is the trace root. The template no longer reads `K_REVISION`. A documented monkey-patch of ADK's `api_server._setup_telemetry` attaches only the web UI's span and log processors to those providers, so ADK builds no providers, exporters or GenAI instrumentation of its own. Application logs move from the `<agent_name>-otel-logs` log to `otlp`, and GenAI events stay in `gen_ai.client.inference.operation.details`: update saved log queries, sinks and log-based metrics. Forks that customized `telemetry.py` or `server.py` re-apply their changes to the new startup order; `docs/references/opentelemetry-architecture.md` explains it (#224)
- **BREAKING:** Remove `TELEMETRY_NAMESPACE`. Set `service.namespace` through the standard `OTEL_RESOURCE_ATTRIBUTES` instead (unset by default); Terraform sets `OTEL_RESOURCE_ATTRIBUTES=service.namespace=<environment>` on the Cloud Run service. To migrate, replace `TELEMETRY_NAMESPACE=x` with `OTEL_RESOURCE_ATTRIBUTES=service.namespace=x` in `.env` (#224)
- `GOOGLE_CLOUD_LOCATION` defaults to `global` instead of `us-central1` when unset (#224)
- **BREAKING:** `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` takes only ADK's four capture modes, exactly: `NO_CONTENT`, `EVENT_ONLY`, `SPAN_ONLY` or `SPAN_AND_EVENT`. `ServerEnv` rejects anything else, including `TRUE` and `FALSE`, and every Terraform root validates the same set. ADK read `TRUE` as `EVENT_ONLY`, which puts content on GenAI event log records, not on spans. The bootstrap examples recommend `SPAN_AND_EVENT` for dev, to debug prompts, responses and tool calls, and `NO_CONTENT` for stage and prod. To migrate, replace `TRUE` with `EVENT_ONLY` and `FALSE` with `NO_CONTENT` in `.env`, in each bootstrap root's `terraform.tfvars`, and in the `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` GitHub Environment Variable (re-run the bootstrap apply or edit the variable directly), or the next bootstrap or deploy fails validation (#224)
- Upgrade the OpenTelemetry stack to the newest versions ADK 2.14.0 allows: SDK and API 1.45.2, contrib instrumentations 0.66b2, GCP exporters 1.15 and the GCP resource detector 1.14, now a direct dependency (#224, #363)
- Pin every external GitHub Action to a full commit SHA with its release in a trailing comment (`@<sha>  # vX.Y.Z`), `actions/*` and `google-github-actions/*` included, so a repointed tag cannot change what runs in workflows that hold `id-token: write`. Remote pre-commit hook revs are frozen the same way (`rev: <sha>  # frozen: vX.Y.Z`, the `pre-commit autoupdate --freeze` format), since CI runs the hooks too. Each pin is the release its previous tag resolved to, so behavior is unchanged. A new `.github/dependabot.yml` bumps the pins monthly through the `github-actions` and `pre-commit` ecosystems, one grouped pull request each, with a cooldown of the `exclude-newer` window plus one day. Pin any action or hook you add the same way; `docs/references/cicd.md` Action and Hook Pinning shows how (#252, #358)
- Trim `docs/getting-started.md` to the first-run path: bootstrap and deploy resource lists, the bootstrap variable list (now the `REQUIRED` block of `terraform.tfvars.example`), local-only mode and telemetry notes point to the guides that already cover them, and enabling the web interface on the deployed service moves to `TF_VAR_serve_web_interface` in `docs/environment-variables.md` (#279)
- **BREAKING:** `ServerEnv` is a pydantic-settings `BaseSettings` model, and a variable set in the environment now wins over the same key in `.env`. The old `load_dotenv(override=True)` let `.env` beat the shell, so `LOG_LEVEL=DEBUG uv run server` did nothing once `.env` set `LOG_LEVEL`; the server now matches ADK's own `.env` loader and the eval lane, which already let the environment win. `initialize_environment()` loads `.env` with `load_dotenv()` (no override) before `ServerEnv` reads the environment, so every reader, the OpenTelemetry SDK and ADK included, sees `.env` values (#224). `ServerEnv` ignores keys it does not define, field names are the variable names lowercased, with no aliases (`otel_capture_content` becomes `otel_instrumentation_genai_capture_message_content`), and `initialize_environment()` takes no arguments: the generic `model_class`, `override_dotenv` and `print_config` parameters are gone, with fail-fast validation and the startup printout unchanged. `pydantic-settings` is a new runtime dependency and `python-dotenv` stays a direct runtime dependency. To migrate, unset any shell-exported variable (like a global `GOOGLE_CLOUD_PROJECT`) that should not override `.env`, and in a fork that added fields, drop their `alias=` arguments; `docs/environment-variables.md` documents the precedence (#254)
- **BREAKING:** Rename `observability.py` to `telemetry.py` and `setup_opentelemetry()` to `configure_telemetry()`: the module produces and exports telemetry data, which is the term OpenTelemetry, ADK (`google.adk.telemetry`), and Google's Telemetry API use for this layer. Forks update the import and the call (#254)
- **BREAKING:** Pin uv consistently: `[tool.uv] required-version = ">=0.13,<0.14"` gives developers a minor-series range, while the `Dockerfile` uv image (was 0.10.11) and all six `setup-uv` steps (previously unpinned, installing the newest uv at run time) hold exact uv 0.13.6. `setup-uv` moves from the frozen `@v7` alias, whose checksum table stopped at uv 0.10.10 so every CI run installed an unverified binary, to a SHA-pinned v10.3.3 that lists 0.13.6, and takes v9's `prune-cache: false` default. `tests/unit/test_pinned_versions.py` fails when the exact pins disagree, a `setup-uv` step has no `version:`, or `required-version` stops being the pin's minor series. To migrate, install a uv 0.13.x or run `uvx uv@0.13.6 <command>`. The `uv-lock` pre-commit hook drops the pinned `uv-pre-commit` repo (was 0.11.14) for a `language: system` hook running the developer's uv, so CI runs it with the pinned `setup-uv` uv. `docs/development.md` documents the bump procedure (#260)
- Run the full pre-commit suite in CI: `ci.yml` `code-quality` replaces its separate ruff and mypy steps with `uv run pre-commit run --all-files --show-diff-on-failure`, so the merge gate is the same hook set a developer runs locally and cannot drift from it. A hook that would modify a file fails the job and prints the diff. The job now runs on every push and pull request, since the hooks check workflows, Terraform, and config files as well as code; `integration` and `agent-eval` keep the `code` path filter. pytest runs even when a hook fails, checkout sets `persist-credentials: false` because hooks run third-party code, and hook environments are cached (#259)
- Run `ruff check --fix` before `ruff format`, in the hooks and in every documented command. A lint fix can change layout (RET505 removing an `else` de-indents a block), and with the formatter first that result was never formatted, costing an extra commit attempt each time. Run the local suite as `uv run ruff check --fix && uv run ruff format && uv run mypy && uv run pytest --cov` (#259)
- Adopt mypy `strict = true` in place of the 13 enumerated flags, keeping `warn_unreachable` (outside the strict set) and `warn_unused_configs`, and add the `pydantic.mypy` plugin so `ServerEnv` construction is checked against its field types. mypy now checks `tests/` too (`files = ["src", "tests"]`, `explicit_package_bases`), with a `tests.*` override that disables only `arg-type`, `no-untyped-def` and `no-untyped-call`, and a `tests.*.conftest` override that re-enables the annotation checks, so `conftest.py` fixtures are type-checked rather than typed by convention. Strict mode's `no_implicit_reexport` rejects names imported from ADK's lazily loaded `google.adk.tools` and `google.adk.models`, so imports now come from the defining submodules. `types-PyYAML` joins the dev group, and `testcontainers` moves to 4.15.0, which ships type information, with the integration lane importing `PostgresContainer` from `testcontainers.community.postgres` (the old `testcontainers.postgres` path is deprecated). Forks with their own test code will see new mypy errors; `docs/references/code-quality.md` Test Suite Typing Strategy lists the fixes (#276)
- **BREAKING:** Move to Python 3.14. `requires-python` is now `>=3.14,<3.15`, and both Dockerfile stages use `python:3.14-slim`, so forks need a 3.14 interpreter (uv installs it on demand). A committed `.python-version` is the single interpreter source: workflow `uv python install` steps take no version argument, the single-entry `code-quality` matrix is gone (the job is now `Code Quality and Tests`; branch protection keys on `CI / status` only), and `tests/unit/test_pinned_versions.py` fails when `requires-python`, the ruff and mypy targets, or a Dockerfile `FROM` tag drifts from it, or a workflow sets its own Python version. Re-resolving for 3.14 moves the eval extra's `litellm` from 1.85.4, which excludes 3.14, to 1.96.2 (#264)
- Move the agent model (`ROOT_AGENT_MODEL`), the judge autoraters, and the user simulator from `gemini-2.5-flash`, retired on Vertex AI, to `gemini-3.5-flash`, chosen over `gemini-3.8-flash` for reliability under load. The liveness preflight sets `thinking_level: MINIMAL` (replacing `thinking_budget: 0`) with a 64-token output cap and a 60-second request timeout, so a hung endpoint aborts the eval lane fast. Accepted thinking levels vary by model, so re-check the preflight when swapping one (#253, #273)
- Probe Cloud Run startup from instance start every 5 seconds instead of waiting 20 seconds before the first probe. The app answers `/health` within about 8 seconds of a cold start, so the old initial delay held every new instance out of service for about 12 seconds longer than needed. The 120-second budget for credential setup is unchanged (24 attempts x 5 seconds) (#267)
- **BREAKING:** Upgrade `google-adk` from 2.4.0 to 2.14.0 (#262, #363). ADK 2.14.0 passes `FunctionTool` arguments annotated `Enum`, `Optional[Enum]` or `list[Enum]` as enum members instead of the model's raw strings, so compare a custom tool's enum parameters against members or `.value`. Its `DatabaseSessionService` creates new PostgreSQL JSON columns as `json` instead of `jsonb` (existing tables keep `jsonb`), so SQL outside ADK that relies on jsonb-only operators or GIN indexes fails against a fresh database. ADK 2.13.0 defaults its telemetry to the OpenTelemetry GenAI semconv v2 schema: an `invoke_workflow` span replaces `invocation` and the `call_llm` span is gone, so update any Cloud Trace queries or dashboards keyed on the old span names, or set `ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN=otel_semconv_1_36` to keep the legacy schema (ADK supports it until at least 2027-03-31). Eval inference stays App-aware, now through stock ADK: `AgentEvaluator`, the `adk eval` CLI, and the `adk web` eval tab build the eval runner from the agent module's `app`
- Rename `GOOGLE_GENAI_USE_VERTEXAI` to `GOOGLE_GENAI_USE_ENTERPRISE` across `.env.example`, `terraform/main/main.tf`, the `agent-eval` job in `ci.yml`, `judge-eval.yml`, and the docs. ADK 2.4.0 deprecated the old name, and every code path that resolves the variant warns on it, so a single judge eval run emitted 70 `DeprecationWarning`s and buried real warnings in CI logs. Both layers that read the variable already accept the new name and prefer it when both are set (ADK's `is_enterprise_mode_enabled`, `google-genai`'s `BaseApiClient`), so there is no transition period to manage and no reason to set both. The old name still resolves, so an existing local `.env` keeps working and keeps warning until it is edited; `docs/environment-variables.md` says so at the variable (#249)
- Raise `rubric_based_final_response_quality_v1` to `threshold: 0.9` in `tests/eval/data/full_eval_config.json`. The metric averages its two rubrics at equal weight, and ADK keys criteria by metric name so one threshold covers both. `concise` is near-certain to pass, which floors the score at `(R - 1) / R` = 0.5 and made the previous `0.7` clear with `answers_query` passing only two runs in five: an agent answering the user's actual question 40% of the time was passing the merge gate. 0.9 is what demands four of five on `answers_query` while `concise` stays the style hint it is. Both rubrics are kept so the template still demonstrates the multi-rubric shape; the arithmetic is documented in `docs/references/agent-evals.md` (#242)
- Raise `safety_v1` to `threshold: 1.0`. The metric delegates to the Vertex pointwise safety autorater, whose rubric is binary (1 safe, 0 unsafe), so averaged across `JUDGE_NUM_RUNS` the previous 0.8 was an allowance for one unsafe response in five. Because the per-invocation score has no partial-credit path, 1.0 tightens the gate at no flakiness cost (#242)
- Take ADK's sampling defaults for the judge metrics: `num_samples` and `judge_model_config` are removed from `tests/eval/data/full_eval_config.json`. Pinning the judge to `temperature: 0` and then paying for a 3-sample majority vote works against itself, since voting is self-consistency sampling and only extracts information when the samples can disagree. The config now sets a `judge_model` and a `threshold` and nothing else; forks wanting reproducibility over robustness should pair `temperature: 0` with `num_samples: 1` rather than mixing the two postures (#242)
- Drop the two deterministic criteria (`tool_trajectory_avg_score`, `response_match_score`) from `tests/eval/data/full_eval_config.json`. The PR gate already scores them from `test_config.json` at `DETERMINISTIC_NUM_RUNS`, and leaving them in the judge config re-scored them at `JUDGE_NUM_RUNS`, which silently turned an exact-match 1.0 threshold into a demand for five perfect trajectories where the PR gate demands two. That is a merge-only failure the PR gate can never reproduce, and it was justified nowhere; the merge gate now scores judge metrics only (#213)
- `--strict-markers` added to pytest `addopts`. The eval lane's markers select which CI step a test runs in, so an unregistered or misspelled marker now fails collection instead of emitting a warning and routing the test into the wrong step (#213)
- Drop `final_response_match_v2` from the shipped judge config (`tests/eval/data/full_eval_config.json`). It asks an LLM whether the response matches the case's `expected_response`, but the gate case asks for the current time and its reference is deliberately clock-free so ROUGE stays stable, so the reference names the timezone while every actual response states a time it lacks. The judge has no stable basis and splits roughly evenly: measured over four runs it scored exactly 0.5 against a 0.7 threshold every time, with the verdict uncorrelated with any observable difference. A ROUGE gate needs a clock-free reference and a semantic judge needs a complete one, and one case cannot serve both. The remaining judge metrics are reference-free and scored the case stably across the same runs (#213)
- Run counts are per gate: `JUDGE_NUM_RUNS = 5` and `DETERMINISTIC_NUM_RUNS = 2` replace the single shared value of 2 in `tests/eval/test_agent_eval.py`. Judge verdicts are binary per rubric, so a metric's achievable scores are the multiples of `1 / (rubrics x num_runs x invocations)`: at 2 runs a single-rubric, single-invocation metric can only score 0, 0.5, or 1, and every threshold above 0.5 silently demands unanimity while reading as if it tolerates one bad draw. Five runs give the average enough resolution for the shipped thresholds to mean what they say. The deterministic gate keeps 2: its tool-trajectory threshold wants unanimity, and ROUGE-1 is spaced finely enough to average at that size. ADK runs the passes serially, so the judge gate costs roughly 2.5x the wall clock it did (#213)
- `require-stage-success` now requires `Judge Eval` alongside `Apply Stage` and `Smoke Stage` for the tagged SHA, so a behavioral regression blocks the prod tag. Stage success remains the image-fidelity half of the gate; `Judge Eval` covers behavior, scoring the same commit's agent code in-process rather than a deployed revision, so it gates what the promoted digest carries without depending on the stage rollout. A regression reds the merge run after stage has already deployed, blocking the tag rather than reverting stage (#213)

- Trim the root `AGENTS.md` from 55,161 to about 17,000 characters. Mechanics and rationale move to `docs/references/`, after adding any fact no doc stated yet. Directory-scoped rules move to new `tests/AGENTS.md`, `terraform/AGENTS.md`, and `.github/workflows/AGENTS.md`, which load when a session works in that directory; the root file lists them and keeps every rule a session can break without opening a file there. The Terraform and workflow files are template internals that sync with their directories (#271)
- Set only the live-log format in `[tool.pytest.ini_options]`, matching the scaffold-python baseline. `--log-cli-level` alone now streams timestamped logs for any lane, with nothing on by default; the commented `log_cli` block is gone. CI adds no live-log level, since `-s` already streams eval progress (#263)

### Removed
- **BREAKING:** The `service.version` resource attribute. On Cloud Run the GCP resource detector's `faas.version` carries the revision name instead: point trace and log queries keyed on `service.version` at `faas.version` (#224)
- **BREAKING:** The callback's token span attributes (`gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.reasoning_tokens`, `gen_ai.usage.tool_use.input_tokens`) and its `Token usage` log line. ADK records cache-read and reasoning tokens on the same span itself, reasoning under the semconv name `gen_ai.usage.reasoning.output_tokens`, and counts tool-use tokens in `gen_ai.usage.input_tokens` and its `adk.experimental.*.tool.input_tokens` metrics. Point dashboards keyed on the removed attributes at ADK's names, and take usage analysis from ADK's metrics (#224)
- The runtime service account's `roles/cloudtrace.agent`: `roles/telemetry.tracesWriter` grants the same `telemetry.traces.write` the Telemetry API checks (#224)
- `CloudLoggingExporter` (deprecated upstream), the `EventLoggerProvider`, the explicit `GoogleGenAiSdkInstrumentor` call, and the `google-cloud-logging`, `opentelemetry-exporter-gcp-logging` and `opentelemetry-instrumentation-google-genai` direct dependencies. ADK records the model call span and GenAI events itself, and the instrumentor, when ADK hands it the span, fails to serialize Pydantic tool responses (#224)
- The `CLAUDE.md` adapter that only imported `AGENTS.md`. Claude Code reads `AGENTS.md` natively, including the `claude.yml` PR review on Vertex AI, so forks keep one instruction file for every coding agent. A contributor's own `CLAUDE.local.md` or an older Claude Code version stops native reading; `docs/development.md` points to the upstream caveats (#271)
- The `terraform fmt -check` step and its PR-comment row from `terraform-plan-apply.yml`. The pre-commit suite in `ci.yml` now checks formatting for every Terraform root, a superset of that step's `terraform/main` coverage (#259)
- The App-aware eval monkey-patch (`_eval_app_aware_patch.py`), its import-time trigger in the package `__init__.py`, and its unit tests, now that ADK ships the same behavior (#262)
- The pytest `filterwarnings` entry for the `BaseAgentConfig` deprecation warning, which ADK 2.13.0 no longer emits at import (#262)

### Fixed
- Tag merge and promotion images with the full commit SHA instead of `git rev-parse --short`. The short form picks its length from the clone's object count, so a promotion run could compute a longer abbreviation than the merge run that tagged stage and fail to find the stage image, and any fixed-length abbreviation can collide with another commit's, which would let a later merge overwrite the stage image a promotion resolves. Merge runs also stop adding a version tag to dev and stage images, which no job read (#319)
- Keep local files out of Docker images: `.dockerignore` patterns matched only at the build-context root, so a local build copied `src/<package>/.adk/session.db` (local web UI sessions) and `__pycache__` into the image, and would have copied a `.env`, editor swap files, logs or `.DS_Store` under `src/`. Match those patterns at any depth. CI builds from a clean checkout and was not affected (#258)
- Deliver application logs and GenAI events to Cloud Logging when the ADK web UI is on. ADK set the global logger provider first, so the template's provider was refused with `Overriding of current LoggerProvider is not allowed` and nothing exported (#285)
- Keep a consumer's `OTEL_RESOURCE_ATTRIBUTES`: they were overwritten at startup, and now win over the template's values on a shared key (#224)
- Cap the `terraform` job in `terraform-plan-apply.yml` at 60 minutes and `resolve-env` at 5, instead of GitHub's 360-minute default. The Terraform limit covers the 30-minute `-lock-timeout` wait plus a first apply that creates Cloud SQL. `docs/references/cicd.md` listed build and deploy timeouts of 30 and 20 minutes that no workflow set; it now points to each workflow's `timeout-minutes` (#312)
- Stop concurrent pull requests cancelling each other's Terraform plans, and a PR plan displacing a merge's pending apply. The concurrency group moves from `terraform-plan-apply.yml`'s workflow level to its `terraform` job: applies still queue per environment without cancellation, each plan gets its own group, and plan and apply pass `-lock-timeout=30m` so the GCS state lock serializes them instead of failing (#303)
- Rewrite the template names `init_template.py` missed: `APP_NAME` and `ROOT_AGENT_NAME` in the package sources, `app_name` in `tests/eval/data/*.json`, `AGENT_NAME` in `.env.example`, and the owner in the `mkdocs.yml` `repo_url`, whose URL rule required a trailing slash (#305)
- Skip the Claude auto-review (`claude.yml`) on pull requests opened by Dependabot, which GitHub runs like fork PRs with a read-only token and no Actions secrets, so the review could not authenticate. The condition matches the PR author, so a later human push keeps the skip; comment `@claude` to review a dependency bump (#302)
- Correct stale infrastructure docs: bootstrap roots use GCS remote state and pre-bootstrap creates the state buckets (`docs/infrastructure.md`, `docs/references/deployment.md`), and deployed `TELEMETRY_NAMESPACE` is the environment name (`docs/observability.md`) (#271)
- Drop `[tool.ruff] fix = true`. The setting made CI's bare `ruff check` rewrite files inside the runner and exit 0, so the lint gate could never fail on an auto-fixable rule (I, F401, UP, SIM, C4, RET, most RUF). Every call site that should fix now passes `--fix`; a bare `ruff check` only reports (#259)
- Fail both eval gates through `EVAL_ERROR_EXIT_CODE` when any run goes unscored, instead of letting the surviving runs decide the verdict. ADK records no score for a run whose metric evaluation raised and averages only the scores that exist, and it reports a run whose inference failed through the same `AssertionError` as a low score, which `judge-eval.yml`'s `gating: false` absorbed as a behavioral regression. The gates capture every run's results through `AgentEvaluator`'s public `eval_set_results_manager` parameter and treat a run as unscored when it produced no metric results, when a gating metric's score is missing or NaN (including a metric that found nothing to score), or when a rubric metric left a configured rubric unjudged. Which metrics gate follows ADK's own rule, so the efficiency metrics ADK adds to every run never count. Exit 1 now means only a sub-threshold verdict over fully scored runs. The gate fails its test normally with the cause chained, so pytest's report carries the traceback, ADK's logs, and the captured results tables, and a hook in the new `tests/eval/conftest.py` sets the exit code. Both CI eval steps pass `-s`, so job logs stream ADK's output as each run happens. Both gates load their config explicitly and call `evaluate_eval_set` the same way, and the configs and eval set load at collection, so malformed eval data fails the preflight instead of reading as a score. `tests/unit/test_eval_gate.py` covers the classification and every exit path offline, and `docs/references/agent-evals.md` gains a "What each gate proves" section (#240)
- Integration lane runs against any Docker daemon the `docker` CLI reaches through its active context, including one whose socket is not `/var/run/docker.sock`, with no setup. A new `tests/integration/conftest.py` runs `docker info` to fail fast when the daemon is unreachable, exports the active docker context's endpoint as `DOCKER_HOST`, and disables testcontainers' Ryuk container, which cannot mount a host-only socket path. A `DOCKER_HOST` you set yourself still wins, and `INTEGRATION_DATABASE_URI` skips the Docker check entirely (#268)
- Close a script-injection path in `metadata-extract.yml`'s job summary. The branch name reached the step through `${{ github.head_ref || github.ref_name }}` inside an unquoted heredoc, and GitHub substitutes expressions into the script text before the shell parses it, so a fork PR from a branch named with backticks or `$(...)` would execute in the runner. The value now arrives through a `BRANCH_NAME` environment variable. Found by the actionlint gate this change adds (#215)
- Judge gate now runs on a merge that changes only eval data. `ci-cd.yml`'s trigger allowlisted deployable content and excluded `tests/**`, so a commit editing the eval set, the judge config, or a threshold produced no judge run at all, which is exactly the commit that changes what the gate asserts. Path handling is now two layers with opposite polarity, matched to what each one risks getting wrong. The trigger is a `paths-ignore` denylist covering documentation and local-developer scaffolding, so it answers just "should a run start"; a path missing from it starts a run whose jobs all skip. A new `changes` job holds the allowlists that decide what actually runs: `build` gates on `deploy`, and `judge-eval` gates on `eval`, which is `deploy` plus `tests/eval/**`. An eval-data merge therefore scores the change and builds no image, which `judge-eval` was always able to do, since it scores the checked-out agent in-process and never depended on the build chain. Because every deploy job reaches `build` through `needs`, one condition skips the whole build-and-deploy chain. The path list that does something now exists in exactly one place, with `eval` reusing `deploy` through a YAML anchor that the action's own parser resolves. `require-stage-success` is unchanged: a merge that builds no image has no `Apply Stage` or `Smoke Stage` conclusion, so tagging it still fails closed, which is correct rather than a hole to patch and is now documented alongside the gate (#238)
- Remove the dead `num_samples` from `hallucinations_v1` in `tests/eval/data/full_eval_config.json`. `HallucinationsV1Evaluator` overrides `evaluate_invocations` and never enters the sampling loop, so the field bought nothing; the metric makes exactly two judge calls per response, a segmenter and a validator. Confirmed against the pinned ADK, upstream `main`, and ADK's criteria docs, which list only `judge_model` for this metric (#242)
- Correct the judge-threshold explanation in `docs/references/agent-evals.md` and AGENTS.md, which claimed resolution comes from `num_runs` alone. It comes from `rubrics x num_runs x invocations`, since ADK means every run's per-invocation scores in one flat list; sampling is a majority vote that buys reliability and no resolution; one judge call carries every rubric in a metric, so rubric count does not multiply LLM calls; `hallucinations_v1` has no fixed set of achievable scores at all, because it scores supported over total sentences and the agent does not write the same number of sentences each run; and ROUGE-1 is finely spaced rather than continuous, since its f-measure denominator counts the response's own tokens and so shifts run to run by the same mechanism, only at token scale instead of sentence scale. A new "How a judge score is built" section carries the aggregation funnel, the effective-threshold arithmetic, the rubric-subsidy floor, and the per-run call counts (#242)
- Fail the eval lane in seconds when a model endpoint is unreachable, before the paid gates run. Preflight liveness probes make one minimal live call per model role, the agent's inference model and each judge autorater, and report the exact endpoint reply or error. In CI they run as their own always-blocking step, so `gating: false` never absorbs a dead endpoint. Each probe reads its role's model from source (`ROOT_AGENT_MODEL`, `full_eval_config.json`), so swapping a model re-points its probe automatically (#229)

### Security
- **BREAKING:** Scope each environment's Workload Identity Federation provider to its repository ID and GitHub Environments. The provider's `attribute_condition` checked only the repository name, so any job in the repository with `id-token: write`, on any branch and with or without an `environment:`, could authenticate to the stage or prod project with the full CI/CD role set, outside the promotion tag ruleset and `require-stage-success`. Each provider now requires the immutable `attribute.repository_id`, so another repository that later takes this name is rejected, and `attribute.environment` in the root's new `github_environments` list (dev: `dev`; stage: `stage`; prod: `prod`, `prod-apply`). The `stage` environment now accepts only the `main` branch and `prod-v*.*.*` tags, the refs on which its jobs run, so a branch workflow cannot get the stage claim; `prod` and `prod-apply` already accept only admin-pushed `prod-v*.*.*` tags. The `github` bootstrap module takes `deployment_branch_patterns` and `deployment_tag_patterns` lists, and the `gcp` module requires `github_environments`. Custom workflows whose jobs authenticate to GCP must declare a matching `environment:`. To migrate, in order: (1) delete hand-made deployment branch or tag rules on `stage` (list and `DELETE` commands in `docs/references/protection-strategies.md` Environment Protection), since a rule bootstrap also creates makes the apply fail; (2) re-apply `terraform/bootstrap/dev`, `terraform/bootstrap/stage` and `terraform/bootstrap/prod` (#323)

## [0.19.1] - 2026-07-12

### Fixed
- CI: make the `code-quality` job the sole writer of the shared uv cache in `ci.yml`. The `integration` and `agent-eval` jobs set `save-cache: false` on `astral-sh/setup-uv` so they restore the same key but no longer save it, removing the concurrent cache-reserve race that produced "Failed to save cache" warning annotations on a cold cache. All three jobs keep `enable-cache: true`, so cache reuse is unchanged (#227)

## [0.19.0] - 2026-07-12

### Added
- Require-stage-success prod gate (`.github/workflows/require-stage-success.yml`): a tag-time, agent-agnostic gate that runs before `prod-promote` (and so before the `prod-apply` approval), so a failure halts the tag run before any reviewer is prompted. It finds the tagged commit's merge run and requires `Apply Stage` and `Smoke Stage` to have both concluded success, failing closed otherwise. Stage success is the whole gate: the promotion workflow copies the image digest-for-digest and prod deploys by digest, so prod runs exactly the digest stage validated. No digest comparison is needed: stage `{sha7}` is written only by that commit's own merge-run attempts and the tag run never rebuilds, so a green `Smoke Stage` (latest attempt) already means `{sha7}` resolves to the digest that was smoked (#211)
- Post-deploy smoke test lane (`tests/smoke/`): after each `terraform apply`, drives the live Cloud Run URL over the real network to confirm the new revision serves end to end. Layered cheapest-first so a failure localizes the broken subsystem (L0 `/health`, L1 session create + read-back, L2 a thin `/run_sse` turn asserting only that a text part streamed, L3 delete + 404), with a readiness wait that absorbs cold-start latency. Authenticates by impersonating a dedicated invoker SA in-process to mint a Cloud Run ID token, so the same code runs locally and in CI. Runs by explicit path only (`uv run pytest tests/smoke`); `ci-cd.yml` runs it after each environment apply (`dev-smoke`/`stage-smoke`/`prod-smoke`), not in the PR gate (#101)
- Dedicated smoke invoker service account (`terraform/main/smoke.tf`): a least-privilege identity with resource-scoped `roles/run.invoker`, plus `roles/iam.serviceAccountOpenIdTokenCreator` for the WIF principal so CI can mint the Cloud Run ID token by impersonation. `terraform-plan-apply.yml` exposes the service URL and invoker SA email as outputs for the smoke job (#101)
- App-aware agent eval: eval inference now runs the full `App` with its plugins applied (the global instruction, logging, and any fork-added plugins), so evals score the same agent `adk web` chat and the deployed server run, and LLM-judge metrics that read `app_details` (developer instructions + tool declarations) get real in-process context instead of empty context. A documented, prod-safe monkey-patch (`src/<pkg>/_eval_app_aware_patch.py`, applied at package import, an `except ModuleNotFoundError` no-op in the runtime image where eval deps are absent) restores App-awareness across all four dev eval surfaces (`uv run pytest tests/eval`, the `adk eval` CLI, the `adk web` eval tab, and `adk web` chat); removed once an equivalent fix lands upstream (adk-python#5503) (#212)
- Judge eval gate (`test_template_agent_judge_eval`): scores the agent against `full_eval_config.json` (rubric, hallucination, and safety metrics) via `AgentEvaluator.evaluate_eval_set`, App-aware in-process. Gated by a new `judge` pytest marker, separate from the deterministic PR gate; runs locally today (its own CI job is future work). Like every eval case it runs the agent with live inference (real Vertex creds); the judge metrics additionally call the paid Gen AI evaluation service (#212)
- `deterministic` and `judge` pytest markers on the eval lane, so the PR gate selects the deterministic cases by explicit opt-in (`-m "deterministic"`, so an unmarked live-model case can't leak into the fast gate) and the LLM-judged cases run on demand (#212)

### Changed
- Test-lane credential mocking is now per-lane instead of shared: the root `tests/conftest.py` moved to `tests/unit/conftest.py`, so its auth/dotenv `pytest_configure()` mocking scopes to the unit lane only. A smoke lane can run against real credentials without the shared conftest suppressing them
- Integration lane collapsed into a single module: the lane-level `tests/integration/conftest.py` is removed, with its fixtures, the `MockLlm` stub, and an autouse session fixture that blocks real credentials now inlined in `test_server_integration.py`
- Unit, integration, and eval lanes resolve the agent package name from `src/` at import time instead of hard-coding it, so a downstream fork that renames the package reuses every lane (and the eval gate) with no edits. The unit `conftest.py` builds its mock patch targets from the discovered name, so `init_template.py` no longer rewrites it and template syncs diff it clean
- Restructured `docs/references/testing.md` into the lane taxonomy plus the unit-test guide, splitting the integration lane into its own `docs/references/integration-tests.md` (added to the docs indexes and MkDocs nav); non-unit lanes now point to their own reference docs
- Integration test lane now provisions Postgres with `testcontainers`: `uv run pytest tests/integration` starts a throwaway `postgres:18` via the Docker daemon and tears it down at session end, so a running Docker daemon is the only prerequisite (no manual `docker run`). The `ci.yml` `integration` job drops its service container and uses the same path, so local and CI runs are identical and the image version lives in one place. Set `INTEGRATION_DATABASE_URI` to point the lane at an already-running Postgres. The `postgres:18` major still matches the deployed `POSTGRES_18` Cloud SQL version (previously a `postgres:17` service container)
- pytest now runs with `--import-mode=importlib` (pytest's recommended import mode for new projects), which keeps test directories free of `__init__.py` and avoids same-named modules colliding across lanes. Lane selection stays by explicit path; the registered `integration`/`smoke` markers are kept for ad-hoc `-m` selection (e.g. `-m "not integration"`)
- Move the agent eval lane from the top-level `eval/` directory to `tests/eval/`, grouping it with the other test lanes (it stays live-model-distinct by loading the real `.env` itself). The deterministic PR gate now runs `uv run pytest tests/eval -m "deterministic"` (was `uv run pytest eval`) (#212)
- Upgrade `google-adk` to 2.4.0 and the OpenTelemetry stack (API/SDK 1.42.1, instrumentation 0.63b1). Migrate the logging bridge to `LoggingInstrumentor().instrument(log_code_attributes=True)`, which now owns root-logger handler attachment: drop the manual SDK `LoggingHandler` (deprecated upstream; keeping it alongside the upgraded instrumentor would double-export every log record) while retaining the `code.file.path`/`function.name`/`line.number` attributes. Cap the fastapi and logging instrumentors at `<0.64`: ADK pins `opentelemetry-api<=1.42.1`, and the 0.64b0 line requires api 1.43.0 (via `semantic-conventions`), so it cannot resolve in an ADK project. Remove the obsolete `LogDeprecatedInitWarning` filter (the symbol was removed upstream) (#225)

### Fixed
- `docs/references/agent-evals.md` is now listed in the MkDocs site nav (previously reachable only through the docs index pages)

## [0.18.0] - 2026-06-15

### Added
- Integration test lane (`tests/integration/`): exercises the real FastAPI app against a real Postgres session service with no mocks, covering session create/list/get/delete, an agent run that persists and reads session state, and FK cascade-on-delete (a raw `DELETE` on `sessions` removes the session's events through the Postgres `ON DELETE CASCADE`, the database-level path the `pg_cron` retention job relies on). Builds the production app via ADK `get_fast_api_app()` with a `postgresql+asyncpg://` URI and drives it in-process with httpx `ASGITransport`; the LLM is stubbed so the lane is deterministic and free. Includes a Postgres-dialect strictness test (asyncpg rejects ISO strings for `timestamptz` where sqlite tolerates them). Runs in the `ci.yml` required check via a `postgres:17` service container, gated on `changes` and folded into the `CI / status` sentinel, without `--cov` (#102)
- Agent eval harness in a top-level `eval/` lane (separate from `tests/` because it calls the live model): `eval/data/template_agent.evalset.json` (ADK `EvalSet` schema) with a deterministic `get_current_time` tool-trajectory case, and `test_config.json` deterministic PR-gate criteria (`tool_trajectory_avg_score` IN_ORDER 1.0 + `response_match_score` ROUGE-1 0.4) (#104)
- Gate-fidelity pytest eval runner (`uv run pytest eval`) calling `AgentEvaluator.evaluate()`, which raises on sub-threshold metrics — unlike the `adk eval` CLI, which exits 0 even when cases fail (verified against google-adk 2.2.0) and remains the interactive authoring loop only (#104)
- `agent-eval` CI job: deterministic agent eval gate on every code PR, authenticating to Vertex AI with the dev environment's WIF principal; the always-run `status` sentinel now requires it, so the existing `CI / status` required check blocks merges on eval failures (#104)
- `google-adk[eval]` dev extra for the agent eval lane, providing `AgentEvaluator` and its deterministic-metric dependencies (dev-only; no runtime or image impact) (#104)
- Full ADK eval-surface coverage as thin, runnable examples: a scripted multi-turn case (`multi_turn.evalset.json`), the `.test.json` single-file format (`simple_time_query.test.json`), dynamic user simulation (`conversation_scenarios.json` with a pre-built and a custom persona, `session_input.json`, `user_sim_config.json`), and an expanded `full_eval_config.json` covering judge, rubric, hallucination, and safety metrics (`final_response_match_v2`, `rubric_based_final_response_quality_v1`, `rubric_based_tool_use_quality_v1`, `hallucinations_v1`, `safety_v1`) for local deep evaluation (#104)
- `tests/unit/test_eval_artifacts.py`: schema-validates every eval data file (eval sets, criteria configs, conversation scenarios, session input) against the installed ADK schemas and metric registry on each PR, so malformed eval data fails in the fast unit lane with no LLM cost (#104)
- `docs/references/agent-evals.md`: the complete agent-evaluation map — data formats, every run path (`uv run server` dev UI, `uv run pytest eval`, `adk eval`/`adk test`/`adk eval_set`/`adk optimize`/`adk migrate`), a metrics table, the deterministic CI gate, dynamic user simulation, a Limits-and-gotchas section (cross-session memory is integration-tested not eval-tested, the deterministic-gate rationale, thinking-mode tool bypass, app-name match, eval-service region), and a Relationship-to-the-Agent-Platform-Eval-SDK section that records why the template stays ADK-native and where regression-diff/failure-clustering live instead — with ADK's docs as the source of truth for mechanics (#104)

### Changed
- Upgrade `google-adk` to 2.2.0 and declare its `[gcp,otel-gcp]` extras. ADK 2.x no longer pulls the Vertex/Agent Engine (`aiplatform`), GCS, and GCP OpenTelemetry dependencies by default; the extras restore them for the Agent Engine memory service, the GCS artifact service, and Cloud Trace/Logging export. Raise the `opentelemetry-instrumentation-google-genai` floor to `>=0.7b1` (earlier builds capped `google-genai<2` and silently skipped GenAI instrumentation under ADK 2.x)

### Removed
- Drop the preventive `litellm<=1.82.6` constraint-dependency. The supply-chain compromise that prompted it is contained: the two malicious versions (1.82.7, 1.82.8) are deleted from PyPI and all current releases are verified clean ([BerriAI/litellm#24518](https://github.com/BerriAI/litellm/issues/24518)). The `exclude-newer` dependency cooldown remains the general guard against newly-compromised packages, so no version-specific litellm pin is needed. Unblocks the `google-adk[eval]` extra

### Fixed
- Drop the per-turn microsecond timestamp from the global instruction; use day-precision date so the cached system-instruction prefix holds across a session, fixing Gemini/Anthropic prompt-cache misses every turn (#199)

## [0.17.0] - 2026-06-08

### Added
- `docs/references/image-digest-resolution.md`: how one build surfaces as different digests across Artifact Registry tags (OCI index), Cloud Run revisions (platform manifest), and the provenance attestation — with resolution commands, console paths, and digest-based debugging recipes. Restores and modernizes content dropped in the February docs refactor
- `verify-image-provenance` project skill: operationalizes the digest-resolution doc as a deterministic procedure (`resolve_chain.sh` with service/compare/revision/tag/classify/find-commit modes) answering image-identity questions with digest evidence — same-image checks across revisions, running-image-to-commit/PR attribution, artifact classification, and deploy-chain verification. Eval-validated across models

### Changed
- `sync-foundation` skill: add a doc-reuse principle to Phase 8 (Documentation) mirroring the Phase 1 fixture-reuse principle — prefer verbatim reuse of upstream docs and isolate unavoidable divergence into bounded blocks, so future syncs evaluate docs as fast verbatim diffs rather than line-by-line reconciliation (#191)

## [0.16.0] - 2026-06-04

### Changed
- Flatten `src/<pkg>/utils/` into the package root: `utils/config.py` → `config.py`, `utils/observability.py` → `observability.py`; the `utils/__init__.py` re-export facade is removed and `server.py` imports from the modules directly. Forks syncing past this release: apply the same moves, update imports (`from .utils import X` → `from .config import X` / `from .observability import X`), test patch targets (`<pkg>.utils.config.load_dotenv` → `<pkg>.config.load_dotenv` in `conftest.py`), and the coverage omit path in `pyproject.toml` (#186)
- Reorganize `tests/` into explicit `unit/`, `integration/`, `smoke/`, and `eval/` lane directories; existing test modules move to `tests/unit/`. A lane is decided by runtime requirements and determinism; non-unit lanes run by explicit path and `testpaths = ["tests/unit"]` scopes a bare `pytest` to the fast, free, deterministic lane with the 100% coverage gate. Lane markers registered in `pyproject.toml` (#177)
- Establish the mirror-source test naming convention: test module path mirrors source path (`src/<pkg>/config.py` → `tests/unit/test_config.py`); nested source paths flatten with underscores (#177, #186)

### Removed
- `tests/test_integration.py`: in-process structural assertions on coverage-omitted modules, not integration tests. App/agent wiring will be validated by the real integration lane, freeing the name for the Postgres + FastAPI suite (#177)

## [0.15.0] - 2026-06-04

### Added
- Scheduled session-data cleanup via `pg_cron`: a daily job deletes `sessions` older than 90 days (`events` cascade via the FK), closing the `DatabaseSessionService` no-server-side-TTL storage gap. Provisioned with no application code, via the `cloudsql.enable_pg_cron` flag and an idempotent bootstrap in the bastion cloud-init. Runs and failures are observable by default through `cron.job_run_details` and the instance Postgres logs in Cloud Logging (#182)
- Local Cloud SQL access from the host: `docker-compose.yml` publishes `127.0.0.1:5432:5432`, so a laptop DB client reaches Cloud SQL through the existing IAP tunnel and bastion Auth Proxy as the app SA (#181)
- Design rationale in `docs/references/cloud-sql.md` for DELETE-based session cleanup over pg_partman partition expiry: ADK owns the schema, idle-based retention keys on the mutable `update_time`, and the bounded sweep keeps the zero-application-code property (#184)

## [0.14.1] - 2026-05-21

### Changed
- Consolidate Test Suite Typing Strategy in `docs/references/code-quality.md` as the single source of truth (mypy scoped to src/, conftest by convention) and catalog expected mypy error categories from `uv run mypy src tests`. `docs/references/testing.md` and `AGENTS.md` now point at it (#173)

### Removed
- Dead `[[tool.mypy.overrides]] module = "tests.*"` block from `pyproject.toml`. mypy was already scoped to `packages = ["agent_foundation"]`, so the override never fired — its presence misled readers about what was actually being checked (#173)

## [0.14.0] - 2026-05-13

### Added
- Optional `image_name` and `context` overrides on `.github/workflows/docker-build.yml` to support building subproject images alongside the primary app
- Optional `image_name` override on `.github/workflows/pull-and-promote.yml` (applies to both source and target by design — image name stays static across environments)
- Optional `image_name` override on `.github/workflows/resolve-image-digest.yml`
- Subproject Builds section in `docs/references/cicd.md` covering the override pattern, the per-context `.dockerignore` gotcha, the per-subproject CI lane recipe, and the rationale for not exposing a `registry` override
- Consumer Extension Points entries in `AGENTS.md` for adding a CI lane and adding a subproject Docker image to the deploy pipeline
- Migration bullet in `docs/references/protection-strategies.md` Prerequisites for renamed required-status checks (do the swap on the PR before merging to avoid an unprotected window)
- Local `pre-commit` hooks via `.pre-commit-config.yaml` covering trailing whitespace, end-of-file, YAML, TOML, large-file checks, `uv-lock` sync, and `language: system` hooks for ruff format, ruff check, and mypy (#168)
- Pre-commit Hooks subsection in `docs/development.md` covering install, manual invocation patterns, and the `language: system` autoupdate caveat (#170)
- Consumer Extension Points row in `AGENTS.md` pointing at ADK model selection for swapping the LLM (Gemini string, Model Garden endpoint, LiteLlm/MaaS connectors) (#143)

### Changed
- **BREAKING:** Required status check renamed from `Required Checks / required-status` to `CI / status`. Consumers with branch protection configured must update the required check name (see `docs/references/protection-strategies.md` Prerequisites for the migration path)
- **BREAKING:** Rename `terraform/main` outputs for consistent `app_*` / `bastion_*` prefixes:
  `deployed_image` → `app_deployed_image`, `service_account_email` → `app_service_account_email`,
  `service_account_roles` → `app_service_account_roles`, `cloud_run_services` → `app_cloud_run_services`,
  `configured_environment_variables` → `app_environment_variables`
- `app_environment_variables` now reflects the deployed Cloud Run service env, not the configured input
- **BREAKING:** Replace `uri` (string) with `urls` (list) in `app_cloud_run_services.<location>` to surface all
  configured service URLs (deterministic and random) for auditability
- Consolidated `code-quality.yml` and `required-checks.yml` into a single self-contained `ci.yml` workflow with three jobs (`changes`, `code-quality`, `status`)
- Use the official Claude GitHub Action app for PR automation; remove explicit GitHub token from job step inputs (#156)
- Upgrade `google-adk` pin `1.30.0` → `1.33.0` (#171)

### Removed
- `.github/workflows/code-quality.yml` (consolidated into `ci.yml`)
- `.github/workflows/required-checks.yml` (consolidated into `ci.yml`)
- `workflow_dispatch` and `workflow_call` triggers from the code-quality pipeline (intentional — neither was invoked, and `ci.yml` is now self-contained)

### Fixed
- Replace `instanceAdmin.v1` with `compute.admin` in bootstrap WIF roles to unblock first-time VPC creation (#167)

## [0.13.0] - 2026-04-21

### Added
- Opt-in FastAPI HTTP-layer instrumentation via `setup_opentelemetry(app=...)` — emits server spans as parents to ADK `invocation` spans; disabled by default (#153)
- `gen_ai.usage.reasoning_tokens` span attribute and `reasoning_tokens` log entry, sourced from Gemini's `thoughts_token_count` (#153)
- `gen_ai.usage.tool_use.input_tokens` span attribute and `tool_use_tokens` log entry, sourced from `tool_use_prompt_token_count` (#153)
- Cloud Run Concurrency Tuning reference doc — runtime model, memory math, GIL / multi-process tradeoffs, and starting-point profile for async Python agents (#153)
- Test Double Naming convention in testing reference (`Mock` / `mock_` / `create_mock_` prefixes) and AGENTS.md (#153)
- `asyncpg` type strictness note in AGENTS.md (bind typed columns as native Python objects, not ISO strings) (#153)
- Session state security posture section in security reference — encryption at rest, user isolation, value-safe logging, ADK OAuth2 credential refresher (#152)

### Changed
- **BREAKING:** Rename `gen_ai.usage.experimental.cached_tokens` span attribute to canonical `gen_ai.usage.cache_read.input_tokens` per OTel semantic conventions — update any dashboards or alerts keyed on the old name (#153)
- Upgrade `google-adk` pin `1.28.0` → `1.30.0` (#154)
- Filter ADK `PLUGGABLE_AUTH` experimental `UserWarning` by source module in `[tool.pytest.ini_options]` (#154)

### Removed
- **BREAKING:** `total_tokens` entry from `after_model` token usage log line and `gen_ai.usage.experimental.total_tokens` span attribute — derive from component counts instead (no semconv equivalent exists); update any dashboards or alerts that referenced the old attribute (#153)

## [0.12.5] - 2026-04-08

### Changed
- Replace `PreloadMemoryTool` with the `load_memory` function tool in `agent.py` — memory is now retrieved on-demand when the LLM decides it is needed, rather than eager-preloaded into context on every turn (#150)
- Add explicit empty-password colon to `SESSION_SERVICE_URI` in `terraform/main/main.tf` (`user@` → `user:@`) to align with the documented example in `docs/environment-variables.md` and self-document intentional empty password under IAM database auth (#150)
- Document memory read/write paths in AGENTS.md Architecture Overview (`load_memory` tool with auto-appended ADK instruction; `add_session_to_memory` after-agent callback) (#150)

### Removed
- Stale `PydanticDeprecatedSince212` warning filter from `pyproject.toml` — no longer triggered by current dependencies (#150)

## [0.12.4] - 2026-04-07

### Added
- "How to Maintain This File" meta-instructions in AGENTS.md with pointer-over-enumeration principle, template internals framing, and intentional global-rule duplication note (#148)
- Consumer Extension Points table in AGENTS.md mapping "I want to add X" intent to file locations (#148)
- Pointer-over-enumeration guidance in memorizer agent instructions with template/scaffold exception for intentional global-rule duplication (#148)

### Changed
- Restructure AGENTS.md to optimize default token consumption for AI sessions — replace stale-prone enumerations with source-of-truth pointers, convert dense prose to scannable bullets, mark template internals with soft framing (#148)
- Wrap `get_current_time` with `FunctionTool` in `agent.py` to match documented custom-tool pattern (#148)
- Use Python basename convention in AGENTS.md to reduce package-path substitution sites in downstream forks after `init_template.py` runs (#148)

## [0.12.3] - 2026-04-06

### Added
- Explicit `time` provider block in Terraform main module (#146)
- `DOWNSTREAM_PKG` variable in template management guide for copy-paste commands (#146)
- Template notice in code quality reference guide with `{your_agent}` placeholders (#146)

### Changed
- Restructure sync skill: fixtures first (Phase 1), code+tests together (Phase 2), bulk test sync (Phase 3) (#146)
- Unify template management guide with sync skill phase ordering and commands (#146)
- Use `git diff` refspec pattern for cross-package `src/` comparisons (#146)
- Make `memory_service_uri` Terraform output optional with `try(null)` (#146)
- Use realistic URI formats in config tests (#146)
- Upgrade google provider 7.21.0 → 7.26.0 in all bootstrap lockfiles (#145)

### Fixed
- Remove stale "multi-platform" language from CI/CD reference guide (#145)
- Add `-backend=false` to lockfile upgrade documentation (#145)

## [0.12.2] - 2026-04-05

### Changed
- Remove unnecessary env var assignments from `pytest_configure()` — no module in the test import graph reads env vars at collection time (#141)
- Update testing guide and AGENTS.md to document when `pytest_configure()` env vars are needed (#141)

## [0.12.1] - 2026-04-04

### Added
- `/sync-foundation` skill for interactive template sync workflow with 9-phase review order, IDE-agnostic diffs, per-file HITL checkpoints, and conftest fixture reuse strategy (#139)
- `_log_state_debug` private method in `LoggingCallbacks` for active/all state key logging at DEBUG level (#139)
- `test_callbacks_omit_falsy_state_keys` test for state key filtering behavior (#139)

### Changed
- Split docker-compose restart policies: app `no` (clean crash output), IAP tunnel `unless-stopped` (auto-reconnect) (#139)
- Remove trailing punctuation from docstring list items in config module (#139)

### Fixed
- Update test assertions from stale `State keys: dict_keys([...])` to `Active state keys: [...]` format (#139)

## [0.12.0] - 2026-04-03

### Added
- Security Posture reference doc — defense-in-depth rationale across 7 layers with GCP source links and CMEK consumer guidance (#136)
- Cloud SQL automated backups (daily 03:00 UTC, 7-day retention, point-in-time recovery) (#136)
- Cloud SQL maintenance window (Sunday 06:00 UTC, stable track, offset from backup window) (#136)
- Cloud SQL deletion protection for stage/prod environments (#136)
- COS automatic OS updates on bastion (`cos-update-strategy = "update_enabled"`) (#136)
- "Try It Locally" section in README linking to Development Quick Start (#137)

### Changed
- Organize reference navigation into Infrastructure/Security/Operations/Development groupings (#136)
- Rename mkdocs nav "Quick Start" to "First Deployment" (#136)
- Update cloud-sql.md baseline to reflect new backup and maintenance defaults (#136)

### Fixed
- Add missing reference docs to mkdocs nav (#135)

## [0.11.0] - 2026-04-03

### Added
- Cloud SQL Postgres with private IP and IAM database auth for session persistence via ADK `DatabaseSessionService`
- VPC network with Private Services Access peering for Cloud SQL private IP connectivity
- Bastion host (e2-micro, COS) running Auth Proxy via cloud-init for local dev IAP tunnel access
- Cloud Run direct VPC egress (`PRIVATE_RANGES_ONLY`) for Auth Proxy sidecar → Cloud SQL
- IAP tunnel container in docker-compose (`network_mode: "service:app"`) for automatic Cloud SQL connectivity
- DRY proxy config via `local.cloud_sql_proxy_args` shared between bastion and Cloud Run sidecar
- `sqlalchemy[postgresql-asyncpg]` runtime dependency (async Postgres driver + greenlet)
- `zone` Terraform variable threaded through bootstrap, CI/CD, and main module
- `BASTION_INSTANCE` and `BASTION_ZONE` environment variables for docker-compose IAP tunnel
- `bastion_instance` and `bastion_zone` Terraform outputs
- `google_cloud_location` Terraform variable — decouples Vertex AI model endpoint routing from infrastructure region (#118)
- `SESSION_SERVICE_URI` and `MEMORY_SERVICE_URI` environment variables — separate session and memory service configuration (#116)
- Cloud Backend Options reference doc (`docs/references/cloud-backend-options.md`) — manual IAP tunnel, Agent Engine sessions, selective service URIs
- COS iptables rule in cloud-init for bastion port 5432 (default INPUT policy is DROP)
- Bastion SA impersonation of app SA (`--impersonate-service-account`, `roles/iam.serviceAccountTokenCreator`)
- Cloud SQL hardening: `connector_enforcement=REQUIRED`, `ssl_mode=TRUSTED_CLIENT_CERTIFICATE_REQUIRED`, `data_api_access=ALLOW_DATA_API`, password validation policy
- Locked postgres built-in user with random 30-char password
- IAP firewall rules (SSH + SQL proxy port) targeting bastion service account
- Cloud NAT router for bastion outbound connectivity
- Timezone-aware `get_current_time` tool replacing placeholder `example_tool` (#105)
- Per-call LLM token usage tracking in `LoggingCallbacks` with structured logging and trace span attributes (#108)
- OpenTelemetry Architecture reference doc — ADK coexistence, instrumentation strategy, dependency management
- ADK Origin Check Middleware reference doc — origin validation, CORS interaction, ALLOW_ORIGINS configuration
- Cloud SQL Scaling and Reliability reference doc — instance tiers, backups, HA, connection pooling, monitoring (#124)
- uv dependency cooldown (5 days `exclude-newer`) and litellm supply chain constraint

### Changed
- **BREAKING**: Replace Agent Engine session service with Cloud SQL Postgres (`SESSION_SERVICE_URI` now `postgresql+asyncpg://` instead of `agentengine://`)
- **BREAKING**: Rename GitHub Environment Variables: `GCP_PROJECT_ID` → `GOOGLE_CLOUD_PROJECT`, `GCP_LOCATION` → `REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER` → `WORKLOAD_IDENTITY_PROVIDER`
- **BREAKING**: Rename Terraform variable `location` → `region` across all modules
- **BREAKING**: Replace `AGENT_ENGINE` env var with `SESSION_SERVICE_URI` and `MEMORY_SERVICE_URI` (full URIs with protocol prefix)
- Split `terraform/main/main.tf` into `network.tf`, `database.tf`, `bastion.tf` (main.tf remains composition root)
- Replace docker-compose Auth Proxy sidecar with IAP tunnel container (`gcr.io/google.com/cloudsdktool/google-cloud-cli:stable`)
- Docker-compose IAP tunnel uses `CLOUDSDK_CONFIG` with writable mount (gcloud CLI requires token cache writes)
- Remove Auth Proxy sidecar startup probe on Cloud Run (unreliable — Cloud Run restarts on crash)
- Replace `asyncpg` + `greenlet` deps with single `sqlalchemy[postgresql-asyncpg]` extra
- Rename agent.py constants to `ROOT_AGENT_*` prefix (`ROOT_AGENT_NAME`, `ROOT_AGENT_MODEL`, `ROOT_AGENT_DESCRIPTION`, `ROOT_AGENT_INSTRUCTION`)
- Add `roles/cloudsql.client` and `roles/cloudsql.instanceUser` to app service account
- Add `roles/cloudsql.admin`, `roles/compute.instanceAdmin.v1`, `roles/servicenetworking.networksAdmin` for WIF principal in bootstrap
- Enable `compute.googleapis.com`, `servicenetworking.googleapis.com`, `iap.googleapis.com` APIs in bootstrap
- Unify two-tier dev workflow: `uv run server` (local SQLite) and `docker compose` (cloud resources)
- Emphasize `TELEMETRY_NAMESPACE` for collaborative team trace filtering
- Upgrade google-adk from 1.25.1 to 1.28.0 (#130)
- Upgrade opentelemetry-instrumentation-google-genai from 0.4b0 to 0.7b0 (#130)
- Unpin opentelemetry-exporter-otlp-proto-grpc (`==1.37.0` → `>=1.37.0,<2.0.0`) (#130)
- Bump uv from 0.9.6 to 0.10.11 in Dockerfile (#122)
- Upgrade GitHub Actions versions and fix TF summary injection (#121)
- Update `ALLOW_ORIGINS` default to include both `127.0.0.1:8000` and `localhost:8000` with explicit ports (#131)

### Fixed
- Cloud Run sidecar startup probe timing: increase budget from ~20s to ~60s (#126)
- Add `time_sleep` for Cloud SQL IAM user creation race condition on initial provisioning (#126)
- Add explicit `edition = "ENTERPRISE"` to Cloud SQL to prevent provider default drift (#125)
- `ALLOW_ORIGINS` missing `localhost:8000` — required by ADK >=1.27.3 `_OriginCheckMiddleware` exact string matching (#131)

### Removed
- `ROOT_AGENT_MODEL` environment variable — model selection is now a module constant in `agent.py` (#114)
- `agent_engine_uri` property from `ServerEnv` — URI construction moved to Terraform
- `root_agent_model` Terraform variable and CI/CD mapping
- `CLOUD_SQL_INSTANCE_CONNECTION_NAME` environment variable (replaced by `BASTION_INSTANCE`/`BASTION_ZONE`)
- `data/` volume mount from docker-compose (unused)
- Auth Proxy sidecar from docker-compose (bastion runs proxy, IAP tunnel provides connectivity)

## [0.10.1] - 2026-03-19

### Added
- Editable install build argument (`ARG editable=false`) in Dockerfile for Docker Compose file sync with auto-restart (~2-5s feedback vs 20-120s rebuild)
- Factory fixtures in conftest.py (`create_mock_*`) for flexible mock creation
- Promotion source outputs to bootstrap environments (dev/stage/prod)
- Cross-path file sync instructions in template-management guide
- `RET` ruff rule for consistent return statement style
- OpenTelemetry background task context propagation pattern in observability docs

### Changed
- Docker Compose watch uses `sync+restart` for source files instead of full rebuild
- Replace "hot reload" language with "file sync with auto-restart" across all documentation
- Refactor agent.py and prompt.py to use constants instead of wrapper functions
- Enforce strict mock fixture usage in tests (no direct mock class imports)
- Generalize coverage omit patterns in pyproject.toml for downstream portability
- Upgrade WIF role to `serviceUsageAdmin` for main module API enablement
- Upgrade main module providers (google 7.12.0 → 7.21.0, random 3.7.2 → 3.8.1)
- Update bootstrap docs with deployment branch and tag protection rules
- Update job summaries pattern and project structure descriptions

## [0.10.0] - 2026-03-01

### Added
- `terraform/bootstrap/pre/` module creates GCS state buckets (one per environment) before bootstrap — supports incremental provisioning
- `terraform/main/services.tf` — consumer extension point for additional GCP API enablement; `time_sleep.service_enablement_propagation` (120s, `for_each` per service) guards against async backend initialization after API enablement
- `terraform/main/iam.tf` — consumer extension point for additional WIF principal IAM roles; `time_sleep.wif_iam_propagation` (120s, `for_each` per role) sequences role grants before dependent resource creation
- Bootstrap exports `WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER` as a GitHub Environment Variable, enabling `iam.tf` to bind additional roles to the WIF principal in CI/CD

### Changed
- Bootstrap environments now use GCS remote state with `bootstrap/` prefix; `terraform_state_bucket` is now a required input in all bootstrap roots
- `terraform/main/.terraform.lock.hcl` committed with multi-platform hashes (`linux_amd64`, `darwin_arm64`); locks provider versions for CI/CD stability

## [0.9.4] - 2026-02-25

### Changed
- Refine developer journey across README, getting-started, infrastructure, and reference docs

## [0.9.3] - 2026-02-23

### Changed
- Use AGENTS.md for portable AI assistant project memory
- Refactor package initialization to use PEP 562 lazy loading pattern for improved ADK compatibility
- Clarify Terraform resource configuration with explicit region parameter and cleaner naming

### Fixed
- Support ADK eval command with PEP 562 lazy loading pattern

## [0.9.2] - 2026-02-20

### Changed
- Restructure template management guide with semantic workflow phases (Prepare/Sync/Review/Test & Merge)
- Add Quick Reference section with copy-paste sync commands organized by file type
- Introduce VERSION shell variable pattern for streamlined workflow
- Add roadmap tip directing first-time users to essential sections
- Enhance Common Patterns and Troubleshooting sections with proper alert styling

### Fixed
- Correct git checkout behavior warning (does not delete untracked local files)
- Add .adk/ directory to .dockerignore for ADK v1.20.0+ compatibility
- Clarify RELOAD_AGENTS comment in .env.example

## [0.9.1] - 2026-02-19

### Changed
- Upgrade google-adk from 1.21.0 to 1.25.1 with transitive deps
- Update .gitignore for google-adk v1.20.0+ storage (.adk/)

### Fixed
- Restore OpenAPI spec endpoint (GET /docs) via google-adk upgrade
- Add type narrowing for credentials (google-auth 2.48.0 compat)

## [0.9.0] - 2026-02-18

### Added
- MkDocs documentation site with Material theme and GitHub Pages deployment
- Documentation badge in README linking to GitHub Pages site
- GitHub Pages URL replacement pattern in init_template.py
- Multi-environment deployment with dual-mode operation (toggle via `production_mode` in ci-cd.yml)
  - Dev-only mode (default): Deploy to dev on merge to main
  - Production mode: Deploy dev+stage on merge, prod on git tag with approval gate
- Environment-specific bootstrap with separate Terraform roots (dev, stage, prod)
  - Each environment provisions WIF, Artifact Registry, state bucket, GitHub Environment and Variables
  - Cross-project IAM grants for secure image promotion (stage reads dev registry, prod reads stage)
- Image promotion workflow for production mode (pull-and-promote.yml)
  - Promotes images by digest between registries without rebuilding
  - Conditional deployment strategy: PR builds and plans, main deploys based on mode, tags trigger prod
- Real-time Terraform output streaming in CI/CD with `tee` and secure temp files
- Environment display in Terraform job summaries for visibility
- Optional PR deployment support with single-line workflow change for downstream repos needing immediate feedback

### Changed
- **BREAKING**: Remove app export from __init__.py to enable lazy loading pattern
  - Forces ADK to use fallback discovery pattern for improved developer experience
  - Ensures .env loads before module-level code executes
  - Integration tests updated to import from agent_foundation.agent
- **BREAKING**: Update callback signatures for ADK 1.21.0 API compatibility
- **BREAKING**: Resource naming switched from workspace-based to variable-based suffixes
  - Previous behavior used Terraform workspace (was "default") → `{agent_name}-default` resources
  - New behavior uses `environment` input variable (dev/stage/prod) → `{agent_name}-{environment}` resources
  - Existing deployments must recreate resources or manually rename to match new convention
  - Enables multi-environment deployment with production mode (dev → stage → prod workflows)
  - Dev-only mode continues single-environment deployment with `environment=dev` → `-dev` suffix
- Standardize workflow concurrency groups across CI/CD workflows
- Update terminology from "Reasoning Engine" to "Agent Engine" throughout documentation
- Reorganize documentation with task-based core guides (docs/*.md) and detailed references (docs/references/*.md)
- Adopt modern pytest patterns with class-based test organization

### Fixed
- Exclude release PRs from automated code review workflow
- Cloud Run output inconsistency from GCP API eventual consistency
- Exit code capture in Terraform plan and apply steps for proper error propagation in CI/CD workflow
- Terraform output logging to runner logs for complete visibility of plan and apply operations

## [0.8.0] - 2025-12-12

### Changed
- **BREAKING**: Move GitHub repository configuration from `.env` to `terraform/bootstrap/terraform.tfvars` for cleaner separation of infrastructure config from application runtime config
  - `GITHUB_REPO_OWNER` → `repository_owner` in terraform.tfvars
  - `GITHUB_REPO_NAME` → `repository_name` in terraform.tfvars
  - Bootstrap Terraform module now requires explicit tfvars (no .env fallback)
- **BREAKING**: Enforce deploy-first workflow by making `AGENT_ENGINE` and `ARTIFACT_SERVICE_URI` required for local development
  - Moved from optional to required deployment-created resources
  - Local development now requires completed deployment to cloud
  - Ensures users test full deployment pipeline early
- Restructure documentation to emphasize deploy-first workflow before local development
- Standardize prerequisite messaging with GitHub-style alerts across all user-facing documentation

## [0.7.0] - 2025-12-11

### Changed
- **BREAKING**: Upgrade to google-adk 1.20.0 and migrate to App and plugin pattern for improved modularity and ADK best practices
  - Agent now wrapped in `App` container with `GlobalInstructionPlugin` for dynamic instruction generation and `LoggingPlugin` for agent lifecycle logging
  - Package exports `app` instead of `root_agent` (breaking change for direct agent imports)
  - `global_instruction` moved from `LlmAgent` to `GlobalInstructionPlugin`
  - Integration tests simplified to pattern-based validation for better template customization (test app/agent wiring, not specific implementations)
- Display terraform apply results in CI/CD job summaries alongside plan results for better deployment visibility

## [0.6.0] - 2025-12-07

### Fixed
- Use PR head SHA instead of GitHub's temporary merge commit SHA for Docker image tags, improving traceability to actual commits in repository history
- Move OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT to required section in Terraform variables
- Prevent workload identity federation resource ID collisions by using GitHub repository ID instead of repository name, ensuring unique identifiers even for repositories with similar names
- Add `shell: bash {0}` to terraform plan for error output capture
- Truncate service account IDs to enforce GCP 30-character limit

### Added
- Dedicated bootstrap setup guide (`docs/bootstrap-setup.md`) with minimal commands and troubleshooting
- Comprehensive environment variables reference (`docs/environment-variables.md`) with WHEN/WHY/HOW context for each variable

### Changed
- Rename Terraform dotenv data source from `adk` to `config` in bootstrap module for clarity after project rename
- Update documentation naming consistency: replace "ADK agent" with "LLM agent", update example project IDs from `my-adk-*` to `my-agent-*`
- **BREAKING**: Rename project from `adk-docker-uv` to `agent-foundation` to better reflect production-grade infrastructure focus
  - Repository: `doughayden/adk-docker-uv` → `doughayden/agent-foundation`
  - Package: `adk_docker_uv` → `agent_foundation`
  - Docker images: `adk-docker-uv` → `agent-foundation`
  - All imports, configuration, and documentation updated
- Streamline developer onboarding: condense README from 170 to 106 lines (38% reduction), integrate template initialization into Getting Started Phase 1, remove duplication between Quickstart and Getting Started sections
- Condense development guide from 315 to 164 lines (48% reduction) with even density throughout, remove verbose code examples, combine related workflow sections
- Reorganize README Documentation section with logical grouping: Getting Started, Infrastructure and Deployment, Production Features
- Use generic placeholders (your-agent-name, your_agent_name) in documentation examples
- Update project structure tree in development.md to reflect current files and directories
- Optimize CLAUDE.md for AI consumption: 36% size reduction (440→279 lines), replace verbose prose with dense technical summaries, update outdated utils references (env_parser.py → config.py/observability.py), add branch protection warning
- Add explicit project parameters to all GCP resources in bootstrap Terraform module for clarity and reduced misconfiguration risk
- Exclude main Terraform module lockfile from version control to prevent platform-specific conflicts from local testing (CI/CD-only execution)

## [0.5.0] - 2025-11-27

### Added
- OpenTelemetry observability with trace export to Google Cloud Trace via OTLP and log export to Cloud Logging with automatic trace correlation
- Pydantic-based environment configuration (`ServerEnv` model) with type-safe validation and required field enforcement
- Comprehensive observability documentation (`docs/observability.md`) covering setup, resource attributes, and usage
- OpenTelemetry resource attributes for service identification: `service.name`, `service.namespace`, `service.version`, `service.instance.id`, and `gcp.project_id`
- Workspace-based resource naming in Terraform using `local.resource_name = "${var.agent_name}-${terraform.workspace}"` for environment-specific resources
- Automatic trace grouping by environment via `TELEMETRY_NAMESPACE` environment variable (set to workspace name in deployments)
- Billing labels (`application`, `environment`) on all GCP resources for cost tracking and organization
- UUID-based instance ID (`service.instance.id=worker-{PID}-{UUID}`) for collision-free process tracking
- Cloud Run revision tracking via `service.version` resource attribute

### Changed
- Required environment variables now include `AGENT_NAME` (service identifier) and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` (LLM content capture control)
- Terraform resources now use workspace-based naming for environment isolation (e.g., `my-agent-dev`, `my-agent-prod`)
- Cloud Run services automatically receive `TELEMETRY_NAMESPACE = terraform.workspace` environment variable for trace grouping
- Server startup now configures OpenTelemetry before ADK initialization for proper resource attribute propagation
- Environment configuration now uses Pydantic models with factory pattern (`initialize_environment`) for validation and error handling

### Fixed
- Add `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to Terraform bootstrap and main modules for proper deployment configuration

### Removed
- File logging system with rotating handlers (replaced with cloud-native OpenTelemetry logging)
- `src/agent_foundation/utils/env_parser.py` module (replaced with Pydantic-based configuration)
- `src/agent_foundation/utils/log_config.py` module (replaced with `observability.py`)
- `tests/test_env_parser.py` and `tests/test_logging.py` (replaced with `tests/test_config.py`)
- Log volume mount from `docker-compose.yml` (no longer needed without file logging)

## [0.4.1] - 2025-11-26

### Changed
- CI/CD workflows now use image digest (instead of tag) for Cloud Run deployments to ensure every Docker rebuild triggers a new revision deployment, even when tags are reused (e.g., base image security updates, manual rebuilds)

### Added
- "Image Digest Deployment" section in CLAUDE.md explaining digest-based deployment rationale and workflow
- "Tracing Deployed Image to Git Commit" troubleshooting section in docs/cicd-setup.md with gcloud commands to lookup digest → tags → commit SHA

## [0.4.0] - 2025-11-25

### Added
- Reusable CI/CD workflow pattern with three workflows: `ci-cd.yml` (orchestrator), `docker-build.yml` (multi-arch builds), `terraform-plan-apply.yml` (infrastructure deployment)
- Automatic CI/CD workflow trigger on version tag push (builds Docker images for `v*` tags)
- Smart image tagging strategy: PRs tagged as `pr-{number}-{sha}`, main branch tagged as `{sha}`, `latest`, and `{version}` (if git tag exists)
- PR automation with Terraform plan posted as comment on pull requests
- Workspace-based Terraform deployment supporting environment isolation (default/dev/stage/prod)
- GCS bucket for main module's remote state created by bootstrap module
- Vertex AI Reasoning Engine provisioning in main Terraform module for session/memory persistence
- GCS bucket for artifact storage in main Terraform module
- Docker image recycling pattern with nullable `docker_image` variable for infrastructure-only updates
- `docs/cicd-setup.md` documenting complete CI/CD workflow automation
- `docs/terraform-infrastructure.md` documenting bootstrap and main module architecture
- `docs/IMPLEMENTATION_PLAN.md` providing detailed implementation guide
- `docs/production-environment-strategy.md` for future multi-environment planning

### Changed
- Changed default Terraform workspace from `sandbox` to `default` in CI/CD workflows to use Terraform's built-in default workspace while maintaining extensibility for multi-environment deployments (dev/stage/prod)
- Reorganized `.env.example` with purpose-based grouping (Required, GitHub CI/CD, Optional) and corrected variable names
- Bootstrap module now creates GCS bucket for main module's remote state and adds storage.objectUser role for state bucket access
- Main module now uses remote state in GCS (bucket created by bootstrap) with workspace isolation
- Cloud Run deployment now integrates with Vertex AI Reasoning Engine via `AGENT_ENGINE` environment variable

### Removed
- `docs/github-docker-setup.md` (replaced by comprehensive cicd-setup.md)
- `.github/workflows/docker-build-push.yml` (superseded by reusable workflow pattern)
- `docs/IMPLEMENTATION_PLAN.md` (historical planning document, core implementation complete, architecture decisions preserved in terraform-infrastructure.md and cicd-setup.md)

### Fixed
- Documented IAM bucket access limitation in artifact storage bucket variable (project-level storage roles only work within same GCP project, cross-project access requires additional configuration)
- Cloud Run startup probe configuration now uses HTTP health checks with resilient retry strategy (5 attempts over 120 seconds) to handle container initialization delays
- Inline comment justifying `roles/iam.serviceAccountUser` role requirement for Cloud Run service account attachment during deployment
- Documentation of `coalesce()` usage for empty string vs null handling in Terraform variables
- "Terraform Variable Overrides" section in terraform-infrastructure.md documenting GitHub Actions Variables pattern
- "IAM and Permissions Model" section in terraform-infrastructure.md documenting project-level IAM assumptions and cross-project limitations

## [0.3.0] - 2025-11-20

### Added
- CODEOWNERS file with fresh template replacement during init
- Init script now updates GitHub Actions badge URLs to point to new repository
- Init script now resets version to 0.1.0 in pyproject.toml
- Terraform infrastructure-as-code for GCP and GitHub configuration
- `terraform/bootstrap/` module for initial infrastructure (Workload Identity Federation, Artifact Registry, Reasoning Engine)
- `terraform/main/` module for Cloud Run deployment
- Automated GitHub Actions Variables creation via Terraform
- Artifact Registry cleanup policies (age-based deletion with version count protection and buildcache exemption)
- Required Terraform configuration entries in `.env.example` (AGENT_NAME, GITHUB_REPO_NAME, GITHUB_REPO_OWNER)

### Changed
- Init script now removes template author from pyproject.toml (developers no longer inherit template author info)
- Refactored GitHub info parsing to use tuples directly (removed dict conversion step)
- Made `github_owner` required in TemplateConfig (parsing is all-or-nothing)
- Improved agent directory discovery in server.py with file-based path resolution (using `.resolve()` for absolute paths and symlink resolution) and environment variable override
- GitHub Actions workflows now use Variables instead of Secrets for non-sensitive identifiers (GCP_PROJECT_ID, GCP_WORKLOAD_IDENTITY_PROVIDER)
- Renamed `ARTIFACT_REGISTRY_URL` to `ARTIFACT_REGISTRY_URI` for accuracy
- Simplified `AGENT_ENGINE_URI` to `AGENT_ENGINE` (URI prefix `agentengine://` now added in code)
- Server now defaults to `127.0.0.1` instead of `localhost` for explicit IPv4 binding
- Dockerfile now explicitly sets `PORT=8000` environment variable for consistency
- `RELOAD_AGENTS` environment variable added for optional agent hot reloading (defaults to false)

## [0.2.0] - 2025-11-17

### Added
- Template initialization script (`init_template.py`) with dry-run mode.
- Init script audit logs (`init_template_results.md`, `init_template_dry_run.md`) for change tracking
- Template setup documentation in README.md and docs/development.md
- InstructionProvider pattern for dynamic instruction generation (enables current dates, session-aware customization)
- MockReadonlyContext fixture in conftest.py for InstructionProvider testing
- Comprehensive prompt function tests (test_prompt.py, 13 tests)
- Integration tests for component wiring (test_integration.py, 5 tests)
- InstructionProvider pattern documentation in CLAUDE.md

### Changed
- Restructured package from nested `agent/` directory to flat structure (`agent.py`, `callbacks.py`, `tools.py`, `prompt.py` at root)
- Updated `global_instruction` to use InstructionProvider callable pattern instead of static string
- Sorted `LlmAgent` parameters in agent.py to match ADK field order
- Updated coverage exclusions in pyproject.toml (removed prompt.py, updated paths to flat structure)
- Updated test imports after package restructure (all existing tests passing)
- Docker Compose container name adds `-local` suffix
- Health endpoint response from `{"status": "healthy"}` to `{"status": "ok"}`
- Simplified development.md with project-specific examples
- Moved project structure documentation from README.md to development.md only

## [0.1.0] - 2025-11-12

### Added
- Google ADK agent with Gemini model integration and FastAPI server
- Dual authentication: Gemini Developer API or Vertex AI
- Agent lifecycle callbacks for logging and memory persistence (no short-circuits, all return None)
- Comprehensive unit tests with 100% coverage
- Environment variable parsing utility for safe JSON list handling with validation and fallback
- Multi-stage Docker build with uv optimization (~200MB runtime image, 5-10s rebuilds)
- Docker Compose with hot reloading (instant sync for code changes)
- Code quality tooling: ruff, mypy (strict), pytest (100% coverage)
- GitHub Actions workflows for quality checks and Docker builds
- Comprehensive documentation (README, development guides, Docker strategy, CLAUDE.md)
- Environment-based configuration with optional Agent Engine and GCS integration
- `.vscode/settings.json` to configure Pylance (excludes tests from type checking)

### Configuration
- Type checking excludes tests (standard pytest pattern): mypy checks only production code
- Ruff excludes notebooks from linting
- Notebooks for Agent Engine creation

[Unreleased]: https://github.com/doughayden/agent-foundation/compare/v0.19.1...HEAD
[0.19.1]: https://github.com/doughayden/agent-foundation/compare/v0.19.0...v0.19.1
[0.19.0]: https://github.com/doughayden/agent-foundation/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/doughayden/agent-foundation/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/doughayden/agent-foundation/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/doughayden/agent-foundation/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/doughayden/agent-foundation/compare/v0.14.1...v0.15.0
[0.14.1]: https://github.com/doughayden/agent-foundation/compare/v0.14.0...v0.14.1
[0.14.0]: https://github.com/doughayden/agent-foundation/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/doughayden/agent-foundation/compare/v0.12.5...v0.13.0
[0.12.5]: https://github.com/doughayden/agent-foundation/compare/v0.12.4...v0.12.5
[0.12.4]: https://github.com/doughayden/agent-foundation/compare/v0.12.3...v0.12.4
[0.12.3]: https://github.com/doughayden/agent-foundation/compare/v0.12.2...v0.12.3
[0.12.2]: https://github.com/doughayden/agent-foundation/compare/v0.12.1...v0.12.2
[0.12.1]: https://github.com/doughayden/agent-foundation/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/doughayden/agent-foundation/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/doughayden/agent-foundation/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/doughayden/agent-foundation/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/doughayden/agent-foundation/compare/v0.9.4...v0.10.0
[0.9.4]: https://github.com/doughayden/agent-foundation/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/doughayden/agent-foundation/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/doughayden/agent-foundation/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/doughayden/agent-foundation/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/doughayden/agent-foundation/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/doughayden/agent-foundation/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/doughayden/agent-foundation/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/doughayden/agent-foundation/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/doughayden/agent-foundation/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/doughayden/agent-foundation/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/doughayden/agent-foundation/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/doughayden/agent-foundation/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/doughayden/agent-foundation/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/doughayden/agent-foundation/releases/tag/v0.1.0
