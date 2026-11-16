# AGENTS.md: CI/CD workflows

Rules for editing `.github/workflows/`. **Template Internals:** this whole file describes upstream-owned workflows; customizing them raises upstream-sync cost. Cross-cutting rules live in the root `AGENTS.md`.

## Orchestration

`ci-cd.yml` orchestrates the reusable workflows in this directory; per-event job graphs in `docs/references/cicd.md` Workflow Flows.

- **Deploy by immutable digest** (not tag) so every deploy creates a new Cloud Run revision
- **A reusable-workflow caller job may not use `continue-on-error`** (nor `env`/`steps`/`timeout-minutes`): non-blocking behavior is an input the callee honors by exiting 0 (`judge-eval.yml` `gating`)
- **Path filtering is two layers with opposite polarity:** trigger `paths-ignore` DENYLIST (does a run start) + `changes` job ALLOWLIST (`deploy`, `eval`: which jobs run). **Never invert the allowlist** (a denylist on the deploy decision fails open). **Every `paths-ignore` entry MUST be absent from both filters** (else the allowlist entry is unreachable). Markdown pattern is root-only `'*.md'`; **do not make it recursive** (it would swallow markdown under `src/`). `deploy` lists every reusable workflow `ci-cd.yml` calls, tag-only ones included. Rationale: `docs/references/cicd.md` ci-cd.yml (Orchestrator)
- An eval-data-only merge builds nothing, so promoting it fails `require-stage-success` closed. Correct; do not relax. Release a commit whose merge deployed stage

## Require Stage Success

Tag-time gate upstream of `prod-promote` (halts before the `prod-apply` approval). Requires the tagged SHA's merge run to show `Apply Stage` + `Smoke Stage` + `Judge Eval` success; anything else, `skipped` included, fails closed. No digest comparison: fidelity comes from digest-for-digest promotion plus deploy-by-digest. Reasoning: `docs/references/cicd.md` require-stage-success.yml.

## Promotion Summary

`promotion-summary` (`ci-cd.yml`, merge runs, production mode) runs `scripts/promotion-summary.sh` on the same green jobs `require-stage-success` checks, so it appears exactly when a commit is promotable. **Whenever it runs, prints one of three messages**, never a silent exit: tagged release (the block plus links), untagged release (warning naming `docs/releasing.md` Promote to Production, no link), non-release. **The block's only source is `docs/releasing.md`** (the one fenced block that pushes `prod-${VERSION}`; rule in root `AGENTS.md` Documentation Strategy): never copy it into the script. Release commit = changes `.release-please-manifest.json`; version from the manifest; tag lookup is one `commits/vX.Y.Z` read. **Exits 0 on every path**, GitHub API errors included (a warning summary), so the job never reds a deploy run. The job declares `permissions: contents: read`. Links build from `github.server_url`/`github.repository`, never a literal owner/repo. Keep the job's `needs` in sync with the gate's required jobs.

## Workflow Scripts

- **Extracted logic lives in `scripts/<name>.sh`**, run as `bash .github/workflows/scripts/<name>.sh` (no executable bit), inputs via the step's `env:`, `set -euo pipefail`, usage in the header comment. The step stays one line; the job checks out only what the script reads (sparse checkout)
- **Every script ships unit tests** in `tests/unit/test_<name>.py` that run the real script: fake binaries first on `PATH` (factory fixtures in `tests/unit/conftest.py`, like `create_mock_gh`), assert on its outputs (summary file, stdout annotations), one test per outcome
- **Lint:** the `shellcheck` hook covers `.sh` files (actionlint only sees inline `run:`). `scripts/**` is in the `deploy` filter

## Release

Standalone `release.yml` (not called by the orchestrator): release-please only, `permissions: {}`, every write through the App token. **Never switch it to `GITHUB_TOKEN`**: release PRs it opens start no workflows, so required checks never report. `claude.yml` skips PRs authored by bots (the review action refuses bot actors). `uv.lock` follows the version through `extra-files`, not a relock job; drop the entry once release-please ships googleapis/release-please#2693.

## Required Checks

Standalone `ci.yml` (not called by the orchestrator). Branch protection requires `CI / status`, an always-run sentinel over `code-quality` (unfiltered, `persist-credentials: false` since hooks run third-party code) and the path-gated `integration` and `agent-eval` jobs. **Release-please PRs** (`release_pr`: bot author AND bot sender AND `release-please--` branch; never the branch alone, so a human push runs every check) skip `integration`, `agent-eval` and `ci-cd.yml`'s `build` (so `dev-plan`); the merge run is unchanged. Job detail: `docs/references/cicd.md` ci.yml.

## Workflow Patterns

- Optional overrides resolve `inputs.X || vars.X` once in job-level `env:` (`docs/references/cicd.md` Reusable Workflows)
- **Terraform concurrency lives on the `terraform` job, never the workflow:** applies share `terraform-apply-<env>` (`cancel-in-progress: false`), plans get a per-run group, and `-lock-timeout` on plan and apply makes the state lock serialize them. A shared plan group lets a new job cancel the pending one, merge applies included (`docs/references/cicd.md` terraform-plan-apply.yml)
- Summary steps stream and capture via `tee` + `PIPESTATUS` (`docs/references/cicd.md` Job Summaries)
- **No `registry` input override** (it breaks per-env isolation and promotion; `docs/references/cicd.md` Subproject Builds)
- **Auth:** WIF, no SA keys. Bootstrap creates the GitHub Variables (`docs/references/cicd.md` GitHub Variables). **Every job that authenticates to GCP MUST declare `environment:`**: each provider accepts only its own environments' tokens (`github_environments` in each bootstrap root), and the environment's deployment policy MUST allow the job's ref (patterns in `terraform/bootstrap/{stage,prod}/main.tf`), or the job fails before it runs
- **Pin every external action to a full commit SHA** with a `  # vX.Y.Z` comment (`actions/*` and `google-github-actions/*` included; local `./.github/workflows/` calls stay unpinned). **Never a floating tag**; remote pre-commit hook revs likewise (`# frozen: vX.Y.Z`). Dependabot bumps both (`docs/references/cicd.md` Action and Hook Pinning)

## Workflow Lint

actionlint runs ONLY as a pre-commit hook (its `rev` is the single pin), no separate CI job. The hook includes the shellcheck pass over inline `run:` blocks, using the `shellcheck-py` dev dependency's binary on `PATH` under `uv run pre-commit`. The separate `shellcheck` hook (also `shellcheck-py`, pinned by `uv.lock`) lints `.sh` files. **Every `run:` edit MUST stay actionlint-clean with shellcheck installed**: quote expansions, group consecutive appends; a `# shellcheck disable=` goes on one command with its reason, never file-wide. `zizmor` is a separate surface — do NOT bolt it onto the actionlint hook. Rationale: `docs/references/code-quality.md` Workflow Lint and Version Pins.

**NEVER set a Terraform or Python version literal in a workflow** (pins and parity tests: root `AGENTS.md` Code Quality and Dependencies).
