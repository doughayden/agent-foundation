# Public Contract

What a template consumer can rely on staying stable within a major version, and what changes in any release.

The template manages an agent's lifecycle: build, test, evaluate, deploy, promote and observe it. The agent in `src/` is a working example of those strategies, and every consumer replaces it. The contract covers the lifecycle surfaces, not the example.

## How Versions Map to the Contract

The template follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html), with this page as its public API:

- **Major:** removes, renames or changes the meaning of a covered surface
- **Minor:** adds to a covered surface (a new optional setting, a new Terraform variable with a default, a new reusable workflow input with a default), or changes anything not covered
- **Patch:** fixes a covered surface so it behaves as documented

Releases before 1.0.0 bumped the minor version for a breaking change. Every breaking change carries its migration steps in the release notes ([Release a Version: Changelog and Commit Types](releasing.md#changelog-and-commit-types)).

## Covered

A change that removes, renames or changes the meaning of anything in this section is breaking.

**Settings:**
- Environment variable names, defaults and meanings read by `ServerEnv` in `config.py`, as documented in [Environment Variables](environment-variables.md)

**Runtime guarantees:**
- **Content capture by environment:** by default, stage and prod record no user content in traces, log records or stdout. The deployed dev service also keeps user content off stdout, and records message content in traces for debugging. `build_plugins()` in `plugins.py` and the capture settings in Terraform implement this strategy; the strategy is the contract, not the code ([Observability: Message Content Capture](observability.md#message-content-capture))
- **Stored state stays readable:** a release never orphans existing sessions, memories or artifacts. The app name they are stored under and the stateful resources that hold them stay the same (the name itself is yours, set by `init_template.py`)
- **Health endpoint:** `/health` keeps its meaning, since the Cloud Run probes and the smoke lane read it

**Telemetry** (what `telemetry.py` provides, not its function signatures; [OpenTelemetry Architecture](references/opentelemetry-architecture.md)):
- The application owns the tracer, logger and meter providers, configured before ADK builds the app
- Every signal exports to the Google Cloud Telemetry API with Application Default Credentials; the standard `OTEL_SDK_DISABLED` and `OTEL_TRACES_SAMPLER` variables work as the OpenTelemetry SDK documents them
- Every agent turn is recorded, even when Cloud Run marks the incoming request unsampled
- Resource attributes and the `cloud_run_revision` log labels keep their keys, so saved log queries, dashboards and alerts keep working
- Health-check requests stay out of the logs
- ADK's built-in tracing stays intact: the template never renames, drops or reshapes ADK's spans, and the `adk web` trace view keeps showing them

**Terraform** (`terraform/main/` and the bootstrap roots):
- Input variables and outputs
- Resource addresses, so an existing deployment plans without replacing a stateful resource like Cloud SQL or a bucket
- The documented landing spots for consumer additions: `services.tf` and `iam.tf` with their `time_sleep` propagation keys, the `alert_thresholds` and `alert_notification_channels` locals in `monitoring.tf`, and the `run_app_env_config` local in `env.tf`

**GitHub configuration:**
- Repository and environment variables, secrets, environments and their protection rules that a consumer provides or bootstrap writes
- The `CI / status` required check and the `<Name> / status` pattern for subproject lanes
- Deployment modes (`production_mode`) and the tag scheme: `vX.Y.Z` releases, `prod-vX.Y.Z` promotions
- Inputs and outputs of the reusable workflows a consumer calls from its own jobs: `docker-build.yml`, `pull-and-promote.yml` and `resolve-image-digest.yml`

**Eval gate:**
- Eval sets in `tests/eval/data/*.evalset.json`, the `deterministic` and `judge` markers, and which config file gates which marker (`test_config.json`, `full_eval_config.json`, `user_sim_config.json`)
- The lane's exit codes: 1 for a score below threshold, `EVAL_ERROR_EXIT_CODE` for an unscored run ([Agent Evals: The CI gates](references/agent-evals.md#the-ci-gates))

**Commands and prerequisites:**
- Commands documented in `docs/` (`uv run server`, the test lane commands, bootstrap steps) and the local tools they need

## Not Covered

These change in any release, including a patch:

- **Agent code:** `agent.py`, `tools.py`, `callbacks.py`, `prompt.py`, `plugins.py`, and the shipped eval cases written against them. Constants like `ROOT_AGENT_MODEL` and function names like `build_plugins()` illustrate the strategies above
- **Workflow internals:** job graphs, names of jobs that are not required checks, and reusable workflow internals beyond their inputs and outputs
- **Dependency majors** (ADK, Terraform providers, OpenTelemetry), unless one changes a covered surface. Upstream changes to ADK's own spans, eval formats or CLI follow ADK's release notes
- **Repository tooling:** `.claude/skills/` and other developer assistant files
- **Documentation wording and structure**, apart from the commands it documents

## When an Upstream Sync Breaks Something

Within a major version, syncing a newer release changes no covered surface, so a consumer's settings, deployments, required checks and saved telemetry queries keep working. Conflicts land in files the consumer has edited, mostly agent code. A major version lists each break and its migration steps in the release notes; read them before the sync ([Template Management](template-management.md)).

---

← [Back to Documentation](README.md)
