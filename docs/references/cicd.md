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
- **`terraform-plan-apply.yml`** - Terraform deployment
- **`smoke.yml`** - Post-deploy smoke tests against the live deployed revision

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
- Pull request to main (paths filtered)
- Push to main (paths filtered)
- Tag push matching `v*`

**Key jobs:**
- `meta` - Extract metadata (tags, SHA, context)
- `config` - Determine production mode
- `build` - Build Docker image (branch events only, not tags)
- `resolve-digest` - Look up image in stage by tag (tag events in production mode)
- `dev-plan` / `dev-apply` - Dev environment (branch events)
- `smoke-dev` - Post-deploy smoke against the live dev revision (after `dev-apply`)
- `stage-promote` / `stage-plan` / `stage-apply` - Stage environment (merge in production mode)
- `smoke-stage` - Post-deploy smoke against the live stage revision (after `stage-apply`, production mode only)
- `prod-promote` / `prod-plan` / `prod-apply` - Prod environment (tags in production mode)

**Concurrency:**
- PR builds: Cancel in-progress on new push (`cancel-in-progress: true`)
- Main builds: Run sequentially (no cancellation, `cancel-in-progress: false`)
- Per-environment Terraform locking prevents state corruption

**Path filtering:**
```yaml
paths:
  - 'src/**'
  - 'pyproject.toml'
  - 'uv.lock'
  - 'Dockerfile'
  - '.dockerignore'
  - 'terraform/main/**'
  - '.github/workflows/ci-cd.yml'
  - '.github/workflows/config-summary.yml'
  - '.github/workflows/docker-build.yml'
  - '.github/workflows/metadata-extract.yml'
  - '.github/workflows/pull-and-promote.yml'
  - '.github/workflows/resolve-image-digest.yml'
  - '.github/workflows/terraform-plan-apply.yml'
```

Tag triggers (`v*`) always run regardless of paths.

## Workflow Flows

Job-level dependency graphs showing how GitHub Actions jobs chain together. For the higher-level deployment strategy view, see [Deployment Modes: Deployment Flow](deployment.md#deployment-flow).

### PR Flow

**Trigger:** Push to feature branch with open PR

**What happens (both modes):**
```
config → metadata-extract → docker-build → dev-plan
                              ↓
                           Push to dev registry: pr-{number}-{sha}
                              ↓
                           Terraform plan (no apply)
                              ↓
                           Comment plan on PR
```

**Result:** Plan preview in PR comment, no actual deployment.

### Merge Flow

**Dev-only mode:**
```
config → metadata-extract → docker-build → dev-plan → dev-apply → smoke-dev
                              ↓
                           Push to dev registry: {sha}, latest
                              ↓
                           Deploy to dev Cloud Run
                              ↓
                           Smoke the live dev revision
```

**Production mode:**
```
config → metadata-extract → docker-build
           ↓                    ↓
           └────────────────────┴─→ dev-plan → dev-apply → smoke-dev
                                    (parallel)
                                ↓
                              stage-promote → stage-plan → stage-apply → smoke-stage
                                ↓
                           Pull from dev, push to stage
                                ↓
                           Deploy to stage Cloud Run
                                ↓
                           Smoke the live stage revision
```

**Result:** Dev deployed and smoked (always), stage deployed and smoked (production mode only). The smoke lane detail lives in [Testing Strategy](testing.md).

### Tag Flow

**Dev-only mode:**
```
config → metadata-extract → docker-build → dev-plan → dev-apply
                              ↓
                           Push to dev registry: {sha}, latest, {version}
                              ↓
                           Deploy to dev Cloud Run
```

**Production mode:**
```
config → metadata-extract → resolve-digest → prod-promote → prod-plan → prod-apply
                              ↓                  ↓                          ↑
                           Look up image in     Pull from stage         (requires
                           stage by tag         Push to prod             approval)
                              ↓
                           Deploy to prod Cloud Run (after approval)
```

**Result:** Version-tagged deployment. Prod requires manual approval in `prod-apply` environment.

## Image Tagging Strategy

**Pull Request builds:**
- Format: `pr-{number}-{sha}` (e.g., `pr-123-abc1234`)
- Isolated from main builds
- Tagged for dev registry only

**Main branch builds:**
- Tags: `{sha}` (primary), `latest`
- Example: `abc1234`, `latest`

**Version tag builds:**
- Tags: `{sha}`, `latest`, `{version}`
- Example: `abc1234`, `latest`, `v1.0.0`

**Deployment uses image digest** (not tags) to ensure every rebuild triggers a new Cloud Run revision. The deployed digest is the OCI index; Cloud Run revisions record the resolved platform image digest — see [Image Digest Resolution](image-digest-resolution.md) for the taxonomy and verification commands.

## Reusable Workflows

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
- Terraform format, init, validate, plan, apply steps

**When it runs:** After build (or promote) for each environment

**Key behavior:**
- `plan` job on PR: Comment plan, don't save artifact
- `plan` job on merge: Save plan artifact (no comment)
- `apply` job: Use saved plan artifact

### smoke.yml

**Purpose:** Run the post-deploy smoke lane against the live deployed Cloud Run revision.

**Inputs:**
- `environment` (dev/stage) - selects the GitHub Environment vars and the deployed target

**How it works:**
1. Authenticate to GCP via WIF
2. Resolve the service URL with `gcloud run services describe`
3. Resolve the dedicated invoker SA by display name and mint a Cloud Run ID token by impersonating it (`gcloud auth print-identity-token --impersonate-service-account --audiences`)
4. Run `uv run pytest tests/smoke` with `SMOKE_BASE_URL` and `SMOKE_ID_TOKEN` set, surfacing pass/fail in the job summary

The service deploys `--no-allow-unauthenticated`, so requests need a Cloud Run identity token. The invoker SA is a least-privilege identity distinct from the runtime app SA. See [Security Posture](security-posture.md) for the identity model. The lane layering and assertions live in [Testing Strategy](testing.md).

**When it runs:** Called by `ci-cd.yml` as `smoke-dev` after `dev-apply` (and `smoke-stage` after `stage-apply` in production mode), on branch push events only. Not part of the PR gate.

## Standalone CI Workflow

### ci.yml

**Purpose:** Run code quality checks (ruff, mypy, pytest with coverage), the Postgres integration lane, and the deterministic agent eval gate.

**Pipeline (five jobs):**
1. `changes` - dorny/paths-filter detects whether relevant files changed
2. `code-quality` - runs ruff format check, ruff linting, mypy, pytest with coverage. Gated on `changes.outputs.code == 'true'`.
3. `integration` - runs `pytest tests/integration` against a `postgres:17` service container (no coverage gate; the 100% gate is unit-lane-only). Gated on `changes.outputs.code == 'true'`.
4. `agent-eval` - runs the deterministic agent eval (`uv run pytest eval`) against Vertex AI, authenticating with the dev environment's WIF principal (no coverage gate). Gated on `changes.outputs.code == 'true'`.
5. `status` - always-runs sentinel that aggregates results for branch protection

**Timeout:** 10 minutes each for the `code-quality`, `integration`, and `agent-eval` jobs (typical: 2-3 minutes)

**When it runs:** Every push to main and every pull request. The inner `code-quality`, `integration`, and `agent-eval` jobs are skipped when no relevant paths changed; the `status` sentinel always reports.

**Branch protection:** Require `CI / status` (the `status` job). The sentinel passes either with "skipped — no relevant files changed" or with the actual quality-check result.

## Workflow Behavior

**Build cache:**
- Registry cache with protected `buildcache` tag
- Significant speedup on cache hits
- Never expires (protected by cleanup policy in bootstrap)

**Timeouts:**
- Build: 30 minutes
- Deploy: 20 minutes per environment
- Code quality: 10 minutes

See workflow files for specific timeout values.

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
- Step outcomes (format, init, validate, plan, apply)
- Deployed resources (Cloud Run URL, Cloud SQL, Agent Engine, GCS bucket, bastion instance/zone)
- Collapsible plan output

Job summaries provide quick insight without log analysis.

## PR Comments

Terraform plan workflow posts formatted comments on PRs:

**Comment includes:**
- Plan summary (resources to add/change/destroy)
- Collapsible sections for detailed output
- Format, init, validation results
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

**Sub-context `.dockerignore` gotcha:** Docker reads `.dockerignore` from the *context root*, not the repo root. When `context: relay`, the build sees `relay/.dockerignore` (if it exists) and ignores the project-root `.dockerignore`. Add a `<context>/.dockerignore` per subproject if you need exclusions.

**CI lane per subproject:** for code-quality coverage of a subproject, copy `ci.yml` to `ci-<name>.yml`, scope its `paths-filter` and step `working-directory` to the subdir, give the workflow a unique `name:` so its `status` check is uniquely addressable, and add the new `<Name> / status` to branch protection.

**No `registry` override:** the parameterization deliberately stops at `image_name` (and `context` for builds). `vars.ARTIFACT_REGISTRY_URI` embeds the per-env GCP project, and GitHub Environment vars resolve in the callee's env context (not the caller's), so a static input override would defeat per-env isolation and break cross-project promotion. Subprojects therefore land in the same per-env Artifact Registry as the main app, distinguished only by `image_name`. If a subproject genuinely needs a different per-env registry, define a new env-scoped GitHub var in bootstrap and consume it directly in a per-subproject reusable workflow rather than threading it through the existing inputs.

### Modify Triggers

Edit `.github/workflows/ci-cd.yml` triggers:

```yaml
on:
  pull_request:
    paths:
      - 'src/**'
      # Add more paths
  push:
    branches:
      - main
      # Add more branches
  push:
    tags:
      - 'v*'
      # Add more tag patterns
```

---

← [Back to References](README.md) | [Documentation](../README.md)
