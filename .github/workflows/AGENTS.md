# AGENTS.md: CI/CD workflows

Rules for editing `.github/workflows/`. **Template Internals:** this whole file describes upstream-owned workflows; customizing them raises upstream-sync cost. Cross-cutting rules live in the root `AGENTS.md`.

## Orchestration

`ci-cd.yml` orchestrates the reusable workflows in this directory; per-event job graphs in `docs/references/cicd.md` Workflow Flows.

- **Deploy by immutable digest** (not tag) so every deploy creates a new Cloud Run revision
- **A reusable-workflow caller job may not use `continue-on-error`** (nor `env`/`steps`/`timeout-minutes`): non-blocking behavior is an input the callee honors by exiting 0 (`judge-eval.yml` `gating`)
- **Path filtering is two layers with opposite polarity:** trigger `paths-ignore` DENYLIST (does a run start) + `changes` job ALLOWLIST (`deploy`, `eval`: which jobs run). **Never invert the allowlist** (a denylist on the deploy decision fails open). **Every `paths-ignore` entry MUST be absent from both filters** (else the allowlist entry is unreachable). Markdown pattern is root-only `'*.md'`; **do not make it recursive** (it would swallow markdown under `src/`). `deploy` lists every reusable workflow `ci-cd.yml` calls, tag-only ones included. Rationale: `docs/references/cicd.md` ci-cd.yml (Orchestrator)
- An eval-data-only merge builds nothing, so tagging it fails `require-stage-success` closed. Correct; do not relax. Tag a commit whose merge deployed stage

## Require Stage Success

Tag-time gate upstream of `prod-promote` (halts before the `prod-apply` approval). Requires the tagged SHA's merge run to show `Apply Stage` + `Smoke Stage` + `Judge Eval` success; anything else, `skipped` included, fails closed. No digest comparison: fidelity comes from digest-for-digest promotion plus deploy-by-digest. Reasoning: `docs/references/cicd.md` require-stage-success.yml.

## Required Checks

Standalone `ci.yml` (not called by the orchestrator). Branch protection requires `CI / status`, an always-run sentinel over `code-quality` (unfiltered, `persist-credentials: false` since hooks run third-party code) and the path-gated `integration` and `agent-eval` jobs. Job detail: `docs/references/cicd.md` ci.yml.

## Workflow Patterns

- Optional overrides resolve `inputs.X || vars.X` once in job-level `env:` (`docs/references/cicd.md` Reusable Workflows)
- Summary steps stream and capture via `tee` + `PIPESTATUS` (`docs/references/cicd.md` Job Summaries)
- **No `registry` input override** (it breaks per-env isolation and promotion; `docs/references/cicd.md` Subproject Builds)
- **Auth:** WIF, no SA keys. Bootstrap creates the GitHub Variables (`docs/references/cicd.md` GitHub Variables)

## Workflow Lint

actionlint runs ONLY as a pre-commit hook (its `rev` is the single pin), no separate CI job. The hook passes `-shellcheck=` until #255 fixes the inline-`run:` findings; remove the flag then. `zizmor` is a separate surface — do NOT bolt it onto the actionlint hook. Rationale: `docs/references/code-quality.md` Workflow Lint and Version Pins.

**NEVER set a Terraform or Python version literal in a workflow** (pins and parity tests: root `AGENTS.md` Code Quality and Dependencies).
