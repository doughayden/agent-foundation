# CI/CD Workflows Reference

GitHub Actions workflow architecture, mechanics, and customization.

## Workflow Architecture

**Orchestrator:**
- **`ci-cd.yml`** - Main workflow coordinating all jobs based on trigger event

**Reusable Workflows:**
- **`config-summary.yml`** - Configuration and production mode detection
- **`metadata-extract.yml`** - Build metadata extraction
- **`docker-build.yml`** - Docker image build and push
- **`pull-and-promote.yml`** - Image promotion between registries (production mode)
- **`resolve-image-digest.yml`** - Digest lookup by tag (production mode)
- **`smoke.yml`** - Post-deploy smoke tests against the live deployed revision
- **`judge-eval.yml`** - LLM-as-judge behavioral gate, run in-process against the checked-out agent
- **`require-stage-success.yml`** - Tag-time gate requiring the tagged SHA's stage run to have passed before prod promotion (production mode)
- **`terraform-plan-apply.yml`** - Terraform deployment

**Standalone CI Workflow:**
- **`ci.yml`** - Code quality (ruff, mypy, pytest with coverage), Postgres integration lane, and deterministic agent eval gate

**Key principle:** Infrastructure as code + GitOps = reproducible deployments.

## GitHub Variables (Auto-Created by Bootstrap)

**Dev-only mode:**
- Variables scoped to repository (no environments)

**Production mode:**
- Variables scoped to environments (dev/stage/prod)

| Variable Name | Description |
|---------------|-------------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `REGION` | GCP Compute region |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI model endpoint routing |
| `IMAGE_NAME` | Docker image name (also agent_name) |
| `WORKLOAD_IDENTITY_PROVIDER` | WIF provider resource name |
| `ARTIFACT_REGISTRY_URI` | Registry URI |
| `ARTIFACT_REGISTRY_LOCATION` | Registry location |
| `TERRAFORM_STATE_BUCKET` | GCS bucket for main module state |
| `WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER` | WIF principal identifier for main module IAM bindings |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Capture LLM content in traces |

**Note:** These are Variables (not Secrets) because they're resource identifiers, not credentials. Security comes from WIF IAM policies.

## ci-cd.yml (Orchestrator)

**Triggers:**
- Pull request to main (docs and local development changes excluded)
- Push to main (docs and local development changes excluded)
- Tag push matching `v*`

**Key jobs:**
- `changes` - dorny/paths-filter resolving the `deploy` and `eval` filters that gate `build` and `judge-eval` (branch events only)
- `meta` - Extract metadata (tags, SHA, context)
- `config` - Determine production mode
- `build` - Build Docker image (branch events only, not tags; gated on `changes.outputs.deploy == 'true'`)
- `resolve-digest` - Look up image in stage by tag (tag events in production mode)
- `dev-plan` / `dev-apply` - Dev environment (branch events)
- `dev-smoke` - Post-deploy smoke against the live dev revision (after `dev-apply`)
- `judge-eval` - LLM-judge behavioral gate on merge (blocking in production mode, signal only in dev-only mode; gated on `changes.outputs.eval == 'true'`)
- `stage-promote` / `stage-plan` / `stage-apply` - Stage environment (merge in production mode)
- `stage-smoke` - Post-deploy smoke against the live stage revision (after `stage-apply`, production mode only)
- `require-stage-success` - Tag-time gate: requires the tagged SHA's merge run to have passed `Apply Stage`, `Smoke Stage`, and `Judge Eval` before promotion (production mode, upstream of `prod-promote`)
- `prod-promote` / `prod-plan` / `prod-apply` - Prod environment (tags in production mode)
- `prod-smoke` - Post-deploy smoke against the live prod revision (after `prod-apply`, production mode only)

**Concurrency:**
- PR builds: Cancel in-progress on new push (`cancel-in-progress: true`)
- Main builds: Run sequentially (no cancellation, `cancel-in-progress: false`)
- Terraform applies queue per environment and plans never queue; the Terraform state lock serializes their state access (see [terraform-plan-apply.yml](#terraform-plan-applyyml))

**Path filtering:** the trigger `paths-ignore` exclusions prevent the workflow from running on docs or local development changes; the `changes` job selects which jobs run when the change set passes the trigger exclusions.

The trigger is a denylist, because the only thing it needs to answer is "could this possibly affect a deployment or a gate?" GitHub does not allow `paths` and `paths-ignore` on the same event, and a denylist is the correct polarity here: the list is short, provably non-deployable, and its failure direction is harmless. A path missing from it starts a run whose jobs all skip, costing seconds of runner time.

```yaml
paths-ignore:
  - '*.md'
  - 'docs/**'
  - 'init_template.py'
  - 'mkdocs.yml'
  - 'LICENSE'
  - 'notebooks/**'
  - '.claude/**'
  - '.env.example'
  - '.pre-commit-config.yaml'
```

The Markdown pattern is shallow `'*.md'` and not recursive `'**.md'` to cover only the root files (`README.md`, `AGENTS.md`, `CHANGELOG.md`) and nothing else, while `docs/**` and `.claude/**` cover the Markdown that lives in those trees. A recursive `'**.md'` would also swallow Markdown a fork adds inside the package, like a prompt fragment or a skill definition under `src/`, and that file would silently stop triggering runs. Keeping the pattern shallow makes the safe behavior structural instead of something a fork has to remember.

The rest of the list is local-developer and template scaffolding with no CI or image role: `init_template.py` is the one-time bootstrap script, `.pre-commit-config.yaml` drives local hooks that no workflow invokes, and `.env.example` is a template for local `.env`. The Dockerfile copies only `pyproject.toml`, `uv.lock`, and `src`, so none of them can reach an image.

The `changes` job is the allowlist, and the only place that enumerates paths that *do* something. Allowlist is the correct polarity here for the opposite reason: a forgotten path means "no build", which is visible and safe, where a denylist controlling a deploy decision would fail open and roll out unchanged source. The action parses its `filters` input as YAML itself, so a YAML anchor removes the duplication that the workflow-level parser cannot (GitHub Actions rejects anchors in workflow syntax).

```yaml
filters: |
  deploy: &deploy
    - 'src/**'
    # ...everything that lands in an image or the infrastructure running it
  eval:
    - *deploy
    - 'tests/eval/**'
    - '.github/workflows/judge-eval.yml'
```

`build` gates on `deploy`, `judge-eval` gates on `eval`. `deploy` lists every reusable workflow `ci-cd.yml` calls, tag-only ones included, so the rule stays uniform and a workflow-only edit lands on a commit that built an image and can be tagged. `eval` is a superset: a source or dependency change alters agent behavior, so the judge should score it too. `tests/eval/**` sits only in `eval`, which makes an eval-data merge score the change that altered what the gate asserts while building nothing. `judge-eval` scores the checked-out source in-process, so it depends on no image and no deploy job.

One condition on `build` is enough to skip the whole deploy chain: every deploy job reaches `build` through `needs`, and a skipped dependency skips its dependents.

**The invariant between the layers:** every `paths-ignore` entry must be absent from both filters. A path in both can never reach the allowlist, because the run never starts, and the allowlist entry is silently dead.

Tag pushes always run: GitHub does not evaluate path filters for them. The `changes` job is branch-only for the same reason, plus a tag push has no base to diff against.

## Workflow Flows

Job-level dependency graphs showing how GitHub Actions jobs chain together. For the higher-level deployment strategy view, see [Deployment Modes: Deployment Flow](deployment.md#deployment-flow).

### PR Flow

**Trigger:** Push to feature branch with open PR

**What happens (both modes):**
```
config (parallel root: selects mode, gates via if-conditions)
changes, metadata-extract ─→ docker-build → dev-plan
```

**Result:** Plan preview in PR comment, no actual deployment. A PR touching only `tests/eval/**` runs `changes`, `meta`, and `config` and skips the rest: there is no image to build and no plan to preview, and the judge gate is a merge-time job. The deterministic eval gate in `ci.yml` covers that PR.

### Merge Flow

**Dev-only mode:**
```
changes, config ─→ judge-eval
changes, metadata-extract ─→ docker-build → dev-plan → dev-apply → dev-smoke
```

**Production mode:**
```
changes, config ─→ judge-eval
changes, metadata-extract ─→ docker-build ┬─→ dev-plan → dev-apply → dev-smoke
                                          │
config ───────────────────────────────────┴─→ stage-promote → stage-plan → stage-apply → stage-smoke
```

**Result:** Dev deployed and smoked (always), stage deployed and smoked (production mode only), and the judge eval scored on every merge that touches the agent or its eval data. `judge-eval` runs from source rather than against a revision, so it starts as soon as `changes` and `config` resolve and never waits on a deploy. It blocks the merge run in production mode and is signal only in dev-only mode. The smoke lane detail lives in [Smoke Tests](smoke-tests.md); the eval lane's in [Agent Evals](agent-evals.md).

**Eval-data-only merge (both modes):**
```
changes, config ─→ judge-eval
changes ─→ (docker-build and every deploy job skipped)
```

`eval` matches and `deploy` does not, so the judge gate scores the change that altered what it asserts and nothing is rebuilt or redeployed. In production mode this merge run has no `Apply Stage` or `Smoke Stage` conclusion, so tagging that commit fails `require-stage-success` closed. That is correct, not a defect; see [Require Stage Success](#require-stage-successyml).

### Tag Flow

**Dev-only mode:**
```
config, metadata-extract → (no deploy)
```
Tags are a no-op in dev-only mode: `build` skips on tag events and `dev-plan`/`dev-apply` are branch-only, so only `meta` and `config` run. Dev-only mode deploys on merge to main, not on tags.

**Production mode:**
```
metadata-extract ─┐
                  ├─→ resolve-digest ──────┐
config ──┬────────┘                        │
         │                                 │
         └─→ require-stage-success ────────┤
                                           ↓
                                 prod-promote → prod-plan → prod-apply → prod-smoke
```

`require-stage-success` gates the prod pipeline tag run. No eval runs at tag time; the gate reads the merge run's `Judge Eval` conclusion. See [Require Stage Success](#require-stage-successyml) for details.

**Result:** Version-tagged deployment, gated on stage success plus the behavioral judge gate, and smoked after apply. Prod requires manual approval in `prod-apply` environment.

## Image Tagging Strategy

Tags name images for people and for the tag-time digest lookup. Every deploy consumes an immutable digest, never a tag.

### Tags by Event

`metadata-extract.yml` derives the tag list. `{sha7}` is the commit's `git rev-parse --short` SHA and always comes first, because `resolve-image-digest.yml` and the promotion digest check read the first tag.

| Event | Registry | Tags | Written by |
|---|---|---|---|
| Pull request | dev | `pr-{number}-{sha7}` (PR head commit, not the merge commit) | `build` |
| Merge to main | dev | `{sha7}`, `latest` | `build` |
| Merge to main (production mode) | stage | `{sha7}`, `latest` (same digest, copied) | `stage-promote` |
| Release tag (production mode) | prod | `{sha7}`, `latest`, `{version}` (the git tag, like `v1.0.0`) | `prod-promote` |
| Every build | dev | `buildcache` (BuildKit layer cache, never deployed) | `build` |

`latest` is a convenience pointer that moves on every merge (and on every release in prod). No workflow reads it. `buildcache` is overwritten on every build; [Image Digest Resolution](image-digest-resolution.md#the-registry-cache-artifact) describes the artifact.

### Build Once, Promote by Digest

1. **Build (merge):** `build` builds the image once, in dev, and pushes it with its tags. `{sha7}` is applied at push time, before any smoke test has run against that digest.
2. **Promote to stage (merge, production mode):** `stage-promote` copies the dev digest into the stage registry under the same tags with `crane cp`, then fails unless the target digest equals the source digest.
3. **Deploy:** Terraform receives a digest URI (`registry/image@sha256:...`), so every Cloud Run revision pins a digest and every new digest creates a new revision. The deployed digest is the OCI index; revisions record the platform image digest inside it ([Image Digest Resolution](image-digest-resolution.md)).
4. **Release (tag, production mode):** nothing rebuilds. `resolve-digest` reads the digest behind stage `{sha7}`, `require-stage-success` confirms the tagged commit's merge run passed `Apply Stage`, `Smoke Stage`, and `Judge Eval`, and `prod-promote` copies that digest into prod with the `{version}` tag added. Prod then deploys the digest after the `prod-apply` approval.

Prod therefore runs a digest that stage deployed and smoked: the tag run promotes only what stage `{sha7}` resolves to, `require-stage-success` ties that digest to a green stage smoke ([Require Stage Success](#require-stage-successyml)), and the copy and deploy steps preserve it byte for byte.

### Registry Tags Stay Mutable

The Artifact Registry repositories do not enable [immutable tags](https://docs.cloud.google.com/artifact-registry/docs/docker/immutable-image-tags). Deployment already consumes only immutable digests, `{sha7}` is unique per commit, and `require-stage-success` proves the promoted digest is the one stage smoked, so registry-level immutability would guarantee nothing the pipeline does not already guarantee.

The setting is repository-wide, so enabling it would also reject the re-push of `latest` and `buildcache` on every build. Keeping it off preserves the registry build cache and the `latest` pointer at no correctness cost. The remaining way to repoint `{sha7}` is a manual push to the registry, which Artifact Registry IAM governs.

### Re-running a Merge Run

`require-stage-success` reads the conclusions of the merge run's latest attempt, and stage `{sha7}` is written only by that commit's own merge-run attempts. Any re-run is therefore safe for prod: a re-run that leaves stage on an unsmoked digest also leaves `Smoke Stage` not green, and the tag fails closed.

- **To re-validate the same image:** use "Re-run failed jobs" on the merge run. Jobs that succeeded keep their results, and the re-run jobs work on the digest already built.
- **To rebuild:** "Re-run all jobs" rebuilds from the same commit. With a warm `buildcache` every layer is cached and the digest is byte-identical; a cache miss produces a new digest, which moves `{sha7}` in dev and stage, and that attempt's own stage smoke must pass before the commit can be released.
- **To ship a different image:** land a new commit. A new image belongs to a new `{sha7}`; never retag a digest by hand.

Tag a release only on a commit whose merge run's latest attempt is green.

### Registry Cleanup

The cleanup policies in `terraform/bootstrap/module/gcp/main.tf` decide how long a tagged image stays available. Retention values are set per environment in each bootstrap root's `terraform.tfvars`.

- **Untagged images are deleted.** A digest that loses its last tag, like the previous image when a rebuild moves `{sha7}`, is removed.
- **Tagged images age out too.** The general retention policy deletes images older than `registry_cleanup_general_retention_days`, tagged or not, unless a KEEP policy (`registry_cleanup_keep_count`, or the `buildcache` keep) protects them. Artifact Registry applies a KEEP policy over a DELETE policy when both match ([cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)).
- **PR images expire separately** when `registry_cleanup_pr_retention_days` is set (dev only).

Two consequences follow. Stage `{sha7}` must still exist when you tag, or `resolve-digest` fails and the release stops before promotion. And re-deploying an older prod digest from the registry works only while that digest is retained, so size prod retention to your rollback window.

## Reusable Workflows

**Caller constraints:** a job that calls a reusable workflow may not set `continue-on-error`, `env`, `steps`, or `timeout-minutes`. Non-blocking behavior therefore has to be an input the called workflow honors by exiting 0 itself; `judge-eval.yml`'s `gating` input is the instance.

**Optional overrides:** a workflow that takes an optional override resolves `inputs.X || vars.X` once in the job-level `env:` block and references `${{ env.X }}` in its steps, like `IMAGE_NAME: ${{ inputs.image_name || vars.IMAGE_NAME }}` in `docker-build.yml`. The fallback is stated once and the steps never repeat it.

### config-summary.yml

**Purpose:** Determine deployment mode and create configuration summary.

**Inputs:**
- `production_mode` (boolean) - Enable multi-environment deployment

**Outputs:**
- `production_mode` - Pass-through for downstream jobs
- Job summary with deployment mode explanation

**When it runs:** First job in every ci-cd.yml run

### metadata-extract.yml

**Purpose:** Extract build metadata (tags, SHA, context).

**Outputs:**
- Image tags (PR, SHA, latest, version)
- Build context (pull_request, push, tag)
- Metadata summary

**When it runs:** After config job in ci-cd.yml

### docker-build.yml

**Purpose:** Build and push Docker images.

**Inputs:**
- Image tags from metadata-extract.yml
- Registry URI and location
- Environment (dev/stage/prod)

**Optional overrides (for subproject builds):**
- `image_name` - override `vars.IMAGE_NAME`
- `context` - Docker build context path (defaults to `.`)

**Features:**
- Builds for `linux/amd64` (Cloud Run target platform)
- Registry cache with protected `buildcache` tag
- Build provenance and SBOM generation

**Outputs:**
- Image digest (immutable identifier)
- Digest URI (registry/image@sha256:...)

**When it runs:** After metadata extraction (branch events only, not tags)

### pull-and-promote.yml

**Purpose:** Promote images between registries (production mode only).

**Inputs:**
- Source environment (dev or stage)
- Target environment (stage or prod)
- Source digest
- Target tags

**Optional overrides (for subproject promotion):**
- `image_name` - override `vars.IMAGE_NAME` for both source and target (image name is intended to remain static across environments)

**How it works:**
1. Authenticate to source and target registries via WIF
2. Pull image from source registry by digest
3. Re-tag image with all target tags
4. Push to target registry

**Outputs:**
- Image digest (same as source)
- Digest URI in target registry

**When it runs:** Production mode deployments (dev → stage, stage → prod)

### resolve-image-digest.yml

**Purpose:** Resolve image digest from tag (production mode only).

**Inputs:**
- Environment (stage)
- Tags to resolve

**Optional overrides (for subproject digest lookup):**
- `image_name` - override `vars.IMAGE_NAME` for the resolved environment

**How it works:**
1. Authenticate to registry via WIF
2. Query Artifact Registry for image by tag
3. Extract digest (sha256:...)

**Outputs:**
- Image digest
- All tags associated with the image

**When it runs:** Production mode tag deployments (lookup stage image for prod)

### terraform-plan-apply.yml

**Purpose:** Plan and apply Terraform changes.

**Inputs:**
- Environment (dev/stage/prod)
- Action (plan/apply)
- Docker image digest
- WIF and state bucket details
- `save_plan` (boolean) - Save plan artifact
- `use_saved_plan` (boolean) - Use saved plan artifact

**Features:**
- Plan artifacts saved between jobs (ensures plan matches apply)
- PR comment with plan output (plan-only runs)
- Job summary with deployment details
- Terraform init, validate, plan, apply steps (formatting is checked by the pre-commit suite in `ci.yml`)

**When it runs:** After build (or promote) for each environment

**Key behavior:**
- `plan` job on PR: Comment plan, don't save artifact
- `plan` job on merge: Save plan artifact (no comment)
- `apply` job: Use saved plan artifact

**Concurrency and state locking:** the `terraform` job sets its own concurrency group. An apply joins `terraform-apply-<environment>` with `cancel-in-progress: false`, so applies to one environment run one at a time and a running apply is never cancelled. Each plan gets a group unique to its run, so plans never queue behind each other or behind an apply.

GitHub keeps one running and one pending job per concurrency group, and a newly queued job cancels the pending one. A shared group for plans would let three PRs pushing together (a Dependabot batch, for example) cancel the middle plan, and would let a PR plan displace a merge's pending apply.

The GCS backend's state lock serializes the state access instead. Plan and apply both pass `-lock-timeout=30m`, so a run that finds the lock held waits for it rather than failing. Thirty minutes covers a plan waiting behind a full apply, including a first apply that creates the Cloud SQL instance, one of the slowest resources the main module creates. An apply waiting behind a few PR plans needs far less. A wait that runs past it fails with the lock holder's details in the log, which points at a stuck lock rather than ordinary contention. The job's 60-minute `timeout-minutes` sits above that worst case: the full lock wait followed by a first apply. An apply queued in its concurrency group has not started, so queue time does not count toward it. Keep the limit generous: a timeout that stops an apply partway can leave the state lock held and the apply half-done.

### smoke.yml

**Purpose:** Run the post-deploy smoke lane against the live deployed Cloud Run revision.

**Inputs:**
- `environment` (dev/stage/prod) - selects the GitHub Environment vars and secrets
- `service_url` - deployed Cloud Run URL, from the apply job's `smoke_target_url` output
- `invoker_service_account` - invoker SA email to impersonate, from the apply job's `smoke_invoker_service_account_email` output

**How it works:**
1. Authenticate to GCP via WIF
2. Run `uv run pytest tests/smoke` with `SMOKE_BASE_URL` and `SMOKE_INVOKER_SA` set from the inputs, surfacing pass/fail in the job summary

The service deploys `--no-allow-unauthenticated`, so requests need a Cloud Run ID token. The lane mints one in-process by impersonating a dedicated invoker SA (the runner's WIF principal holds `serviceAccountOpenIdTokenCreator` on it), so no token crosses the environment. The service URL and SA email come from `terraform-plan-apply.yml` outputs. See [Security Posture](security-posture.md) for the identity model. The lane layering and assertions live in [Smoke Tests](smoke-tests.md).

**When it runs:** Called by `ci-cd.yml` after each environment apply — `dev-smoke` after `dev-apply` on merge, and in production mode `stage-smoke` after `stage-apply` on merge and `prod-smoke` after `prod-apply` on tag. Not part of the PR gate.

### judge-eval.yml

**Purpose:** Run the LLM-as-judge behavioral gate (the `judge` marker in `tests/eval`) against the checked-out agent.

**Inputs:**
- `environment` (dev/stage/prod) - selects the GitHub Environment vars and secrets, which supply the WIF principal and the Vertex AI project
- `gating` (optional, default `true`) - whether a sub-threshold score fails the job

What gets scored is not an input. The eval set, the judge criteria, and the per-gate run counts are constants in `tests/eval/test_agent_eval.py`, so CI and a local run score the same thing and changing either is a reviewable code diff.

**How it works:**
1. Authenticate to GCP via WIF
2. Probe model liveness (`-m "judge and liveness"`) under the default shell, so a dead endpoint fails the job in either mode
3. Run the scored eval (`-m "judge and not liveness"`), surfacing pass/fail in the job summary alongside the environment and whether the run was blocking

The eval runs in-process and App-aware, so it scores the same agent the built image carries without a deployed revision, a service URL, or invoker auth. `ci-cd.yml` passes `environment: dev` in both deployment modes: the job needs Vertex AI credentials rather than a deployed target, and dev keeps it clear of stage's deployment protection rules. The judge gate scores `JUDGE_NUM_RUNS` passes per case, set to 5 in the eval module because judge metrics return a binary verdict per run and 2 would quantize the average to 0, 0.5, or 1 — see [Agent Evals](agent-evals.md). ADK runs those passes serially (`num_runs` is a `for` loop in `AgentEvaluator`; its `parallelism` semaphore fans out across eval cases, not runs), so wall clock scales linearly with the run count and sublinearly with case count.

`gating` exists because a job that calls a reusable workflow may not use `continue-on-error`. With `gating: false` the workflow reports the regression in the summary, emits a warning annotation, and exits 0, so the job conclusion stays `success` — which is what the dev-only mode wants, since nothing reads that conclusion there.

`gating` absorbs a sub-threshold score and nothing else. The preflight is a separate step, and the eval test leaves through `EVAL_ERROR_EXIT_CODE` (6) when the eval could not run or any run went unscored, so the scored step's exit 1 can only be a sub-threshold verdict over fully scored runs. Every other non-zero exit (2 interrupted, 3 internal error, 4 usage error, 5 nothing collected, 6 eval error or unscored run) fails the job in both modes, and the summary names the code. Malformed eval config or data fails at collection, inside the preflight step. Both steps pass `-s`, so the job log streams ADK's output as each run happens. Without that split, a dead judge endpoint would abort the lane with the same exit 1 as a regression and report green forever in dev-only mode, which is the vacuous pass the preflight was added to prevent.

**When it runs:** Called by `ci-cd.yml` as `judge-eval` on merge to main, blocking in production mode and signal only in dev-only mode. Not on PRs (the deterministic gate in `ci.yml` covers those) and not on tags.

**Swapping the eval body:** A consumer changes what is scored by editing `tests/eval/data/` (the eval set and `full_eval_config.json`) and, for the file paths or run counts, the constants in `tests/eval/test_agent_eval.py`. The workflow takes no eval inputs, so there is nothing to override from the caller. Replacing the eval framework entirely (deepeval, ragas, or other) means pointing the `judge-eval` job at a different reusable workflow; the gate interface is just the job's name and conclusion, so `require-stage-success` needs no change as long as the job is still named `Judge Eval`.

### require-stage-success.yml

**Purpose:** Tag-time gate that requires the tagged SHA's stage release candidate to have passed before prod promotion.

**Inputs:**
- `head_sha` - the tagged commit whose stage run is required to have passed (`github.sha` on the tag event)
- `stage_run_workflow` (optional, default `ci-cd.yml`) - the workflow whose merge-to-main run deployed stage

**How it works:**
1. Find the merge run for `head_sha` on the default branch (the tag run is excluded because its head branch is the tag ref)
2. Require that run's `Apply Stage`, `Smoke Stage`, and `Judge Eval` jobs all concluded `success` (matching the reusable-workflow `X / <inner>` job-naming; anything but success, including `skipped`, fails closed)

`Judge Eval` covers the behavioral dimension: it scores the same commit's agent code in-process, so requiring its conclusion gates the behavior the promoted digest carries without depending on the stage rollout. A behavioral regression reds the merge run after stage has already deployed, which blocks the prod tag rather than reverting stage.

Stage success is the whole prod gate for image fidelity. The promotion workflow copies the image digest-for-digest and prod deploys by digest, so prod runs exactly the digest `resolve-digest` reads from stage `{sha7}` — the fidelity guarantee lives there, not in this gate. So the gate only has to confirm that digest was validated, and a green `Smoke Stage` does: stage `{sha7}` is written only by that commit's own merge-run attempts, the tag run never rebuilds (it only re-reads `{sha7}` and promotes it), and the jobs API reports the latest attempt, so a green smoke means `{sha7}` resolves to the digest that was smoked. No separate digest comparison is needed (and conclusions, not outputs, are what the REST API exposes after a run). The only way to break that equivalence is an out-of-band registry repoint of `{sha7}`, governed by Artifact Registry IAM. Because `prod-promote` declares `needs: require-stage-success`, a failure halts the tag run upstream of the `prod-apply` approval.

**Tagging a commit that built no image.** Not every merge produces an image. A merge touching only `tests/eval/**` runs the judge gate and skips `build`, so `Apply Stage` and `Smoke Stage` are skipped in that run and this gate fails closed on them. It's intentional behavior: no image exists for that commit, so stage `{sha7}` resolves to nothing and prod's deploy-by-digest has nothing to promote. Relaxing the gate to accept a skipped stage job would trade a clear failure for an unsound pass.

Practically, a release tag belongs on a commit whose merge deployed and smoked stage. If the last merge before a tag changed only eval data, tag the commit before it, or land a deployable change first.

**Permissions:** `actions: read` (read the merge run's job conclusions), `contents: read`. No GCP credentials.

**When it runs:** Called by `ci-cd.yml` on tag events in production mode, before `prod-promote`. Generic and agent-agnostic, so every fork inherits it.

## Standalone CI Workflow

### ci.yml

**Purpose:** Run the pre-commit hook suite and pytest with coverage, the Postgres integration lane, and the deterministic agent eval gate.

**Pipeline (five jobs):**
1. `changes` - dorny/paths-filter detects whether relevant files changed
2. `code-quality` - runs every pre-commit hook on all files (`uv run pre-commit run --all-files --show-diff-on-failure`: ruff, mypy, actionlint, `terraform fmt`, config-file checks), then pytest with coverage even when a hook fails. Installs Terraform from `.terraform-version` for the fmt hook and caches hook environments. Restores `.mypy_cache` on every run so mypy re-checks only what changed, and saves it only on pushes to main: pull requests read main's cache without adding entries to the repository's Actions cache quota. Runs on every push and pull request, since the hooks cover every file type. Checks out with `persist-credentials: false`, since the hooks run third-party code.
3. `integration` - runs `pytest tests/integration`, which starts a throwaway `postgres:18` via `testcontainers` on the runner's Docker daemon (no coverage gate; the 100% gate is unit-lane-only). The `postgres:18` image matches the deployed Cloud SQL `POSTGRES_18` major. Gated on `changes.outputs.code == 'true'`.
4. `agent-eval` - runs the deterministic agent eval (`uv run pytest tests/eval -m "deterministic"`) against Vertex AI, authenticating with the dev environment's WIF principal (no coverage gate). Gated on `changes.outputs.code == 'true'`.
5. `status` - always-runs sentinel that aggregates results for branch protection

**Timeout:** 10 minutes each for the `code-quality`, `integration`, and `agent-eval` jobs (typical: 2-3 minutes)

**When it runs:** Every push to main and every pull request. `code-quality` always runs; `integration` and `agent-eval` are skipped when no code paths changed; the `status` sentinel always reports.

**Branch protection:** Require `CI / status` (the `status` job). The sentinel requires `code-quality` to pass, and `integration` and `agent-eval` to pass or be skipped because no code paths changed.

## Workflow Behavior

**Build cache:**
- Registry cache with protected `buildcache` tag
- Significant speedup on cache hits
- Never expires (protected by cleanup policy in bootstrap)

**Timeouts:** see each workflow's `timeout-minutes`; a job without one gets GitHub's 360-minute default. The Terraform job's limit is sized against the state-lock wait (see Concurrency and state locking above).

## Job Summaries

Workflows generate formatted summaries in GitHub Actions UI:

**Config summary:**
- Deployment mode (dev-only vs production)
- Environment deployment plan
- Mode switching instructions

**Metadata extraction:**
- Build context (PR, main, tag, manual)
- Branch/tag name and commit SHA
- All image tags (bulleted list)

**Terraform deployment:**
- Environment and action (plan/apply)
- Docker image being deployed
- Step outcomes (init, validate, plan, apply)
- Deployed resources (Cloud Run URL, Cloud SQL, Agent Engine, GCS bucket, bastion instance/zone)
- Collapsible plan output

Job summaries provide quick insight without log analysis.

**Writing a summary step:** stream command output to the log and capture it in one pass with `FILE=$(mktemp)`, `cmd | tee "$FILE"`, and `${PIPESTATUS[0]}` for the command's own exit code (`tee`'s would always be 0). Export GitHub context to shell variables first, capture each value once, and check for empty outputs before rendering. `smoke.yml` and `judge-eval.yml` follow this pattern.

## PR Comments

Terraform plan workflow posts formatted comments on PRs:

**Comment includes:**
- Plan summary (resources to add/change/destroy)
- Collapsible sections for detailed output
- Init and validation results
- Full plan output

**Permissions:** Requires `pull-requests: write` in ci-cd.yml (configured).

## Authentication

**Workload Identity Federation (WIF):**
- Keyless authentication (no service account keys)
- GitHub Actions requests OIDC token
- GCP validates against WIF provider
- Grants temporary credentials scoped to repository

**IAM roles:** See `terraform/bootstrap/module/gcp/main.tf` for complete role list.

**Security:**
- Repository-scoped IAM bindings (attribute condition on repository name)
- Minimal permissions (only required roles)
- Environment isolation (production mode, separate projects)
- Cross-project IAM is registry-scoped (not project-level)

## Action and Hook Pinning

Every external action in `.github/workflows/` is pinned to a full 40-character commit SHA, with the release it resolves to in a trailing comment:

```yaml
- uses: actions/checkout@<40-char-sha>  # vX.Y.Z
```

Remote pre-commit hooks follow the same rule. Each `rev` in `.pre-commit-config.yaml` is a commit SHA with a `# frozen:` comment, the format `pre-commit autoupdate --freeze` writes, and CI runs these hooks too:

```yaml
- repo: https://github.com/<owner>/<repo>
  rev: <40-char-sha>  # frozen: vX.Y.Z
```

**Why pin by SHA:** a tag like `@v6` is mutable. Its owner, or anyone who compromises the owner's account, can repoint it, and these workflows hold `id-token: write` and federate to GCP, so an action running in them can mint cloud credentials. A SHA pin also stops a new release from changing what CI runs with no diff in this repository. GitHub's [security hardening guide](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions) recommends SHA pinning for this reason.

**Scope:** every action from another repository, `actions/*` and `google-github-actions/*` included. Local reusable-workflow calls (`uses: ./.github/workflows/*.yml`) stay unpinned because they resolve to the caller's own commit.

**Updates:** Dependabot (`.github/dependabot.yml`) opens weekly PRs through two ecosystems: `github-actions` bumps each action SHA and its version comment together, and `pre-commit` reads each hook's `# frozen:` comment to pick the next release tag, then rewrites the SHA and the comment. Both use the same cooldown, the `exclude-newer` window in `pyproject.toml` plus one day, so actions, hooks and Python packages wait out the same release age before adoption (Dependabot counts whole days, so the same number could admit a release up to a day younger). Dependabot does not touch a `with:` input, so a `setup-uv` step's `version:` input stays put, held to `[tool.uv] required-version`.

**Adding an action or hook:** resolve the release tag to its commit and pin that, never a branch or a floating major tag. For a hook, `uv run pre-commit autoupdate --freeze --repo <url>` resolves and writes both. For an action, or to check a hook by hand, dereference an annotated tag object to its commit:

```bash
gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.type + " " + .object.sha'
# If the type is "tag", resolve the tag object to its commit
gh api repos/<owner>/<repo>/git/tags/<sha> --jq '.object.sha'
```

## Customization

### Change Deployment Mode

Edit `production_mode` in `.github/workflows/ci-cd.yml`:

```yaml
jobs:
  config:
    uses: ./.github/workflows/config-summary.yml
    with:
      production_mode: true  # or false for dev-only
```

See [Deployment Modes](deployment.md) for complete instructions.

### Add Environment Variables

**Runtime config** (LOG_LEVEL, SERVE_WEB_INTERFACE, etc.):
1. Settings → Environments → {environment} → Environment variables
2. Add or edit variable
3. Re-run deployment or push new commit

**Infrastructure config** (CORS origins, etc.):
1. Edit `terraform/main/main.tf`
2. Create PR
3. Merge PR → deploys via CI/CD

See [Deployment Modes](deployment.md) for runtime vs infrastructure distinction.

### Add Build Steps

Edit `.github/workflows/ci-cd.yml` or reusable workflows:
- Code quality checks → Edit `ci.yml`
- Integration tests → Add job after `docker-build` in `ci-cd.yml`
- Custom notifications → Add to orchestrator

### Subproject Builds

The reusable workflows (`docker-build.yml`, `pull-and-promote.yml`, `resolve-image-digest.yml`) accept optional `image_name` and (for `docker-build.yml`) `context` overrides. This lets a single `ci-cd.yml` orchestrate multiple images, like a primary app plus a sidecar/relay subproject under `relay/`.

**Pattern:** add a parallel `build-<name>` job per subproject in `ci-cd.yml`, calling `docker-build.yml` with the subproject's `image_name` and `context`. Mirror with parallel promote/resolve jobs (same `image_name` override) and pass each resulting `digest_uri` through to `terraform-plan-apply.yml` as a new `TF_VAR_*` input.

**Path filters:** add the subproject's context path to the `changes` job's `deploy` filter and gate the new job on `needs.changes.outputs.deploy == 'true'` like `build`, or give the subproject its own filter output if it should build independently of the main app. Nothing to add at the trigger, which ignores documentation rather than allowlisting code, but confirm the new path is not swallowed by an existing `paths-ignore` entry.

**Sub-context `.dockerignore` gotcha:** Docker reads `.dockerignore` from the *context root*, not the repo root. When `context: relay`, the build sees `relay/.dockerignore` (if it exists) and ignores the project-root `.dockerignore`. Add a `<context>/.dockerignore` per subproject if you need exclusions.

**CI lane per subproject:** for code-quality coverage of a subproject, copy `ci.yml` to `ci-<name>.yml`, scope its `paths-filter` and step `working-directory` to the subdir, give the workflow a unique `name:` so its `status` check is uniquely addressable, and add the new `<Name> / status` to branch protection (bootstrap path: [Protection Strategies](protection-strategies.md#prerequisites) Prerequisites).

**No `registry` override:** the parameterization deliberately stops at `image_name` (and `context` for builds). `vars.ARTIFACT_REGISTRY_URI` embeds the per-env GCP project, and GitHub Environment vars resolve in the callee's env context (not the caller's), so a static input override would defeat per-env isolation and break cross-project promotion. Subprojects therefore land in the same per-env Artifact Registry as the main app, distinguished only by `image_name`. If a subproject genuinely needs a different per-env registry, define a new env-scoped GitHub var in bootstrap and consume it directly in a per-subproject reusable workflow rather than threading it through the existing inputs.

### Modify Triggers

Edit `.github/workflows/ci-cd.yml` triggers:

```yaml
on:
  pull_request:
    branches: [main]
    paths-ignore:
      - '*.md'
      # Add more non-deployable paths (keep both lists identical)
  push:
    branches:
      - main
      # Add more branches
    paths-ignore:
      - '*.md'
    tags:
      - 'v*'
      # Add more tag patterns
```

Adding a path here only stops runs from starting. To change what a run *does*, edit the `changes` job's `deploy` or `eval` filter; see [Path filtering](#ci-cdyml-orchestrator). Never put a path in both, or the allowlist entry becomes unreachable.

---

← [Back to References](README.md) | [Documentation](../README.md)
