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
- **`code-quality.yml`** - Code quality checks (ruff, mypy, pytest)
- **`required-checks.yml`** - Conditional status check wrapper

**Key principle:** Infrastructure as code + GitOps = reproducible deployments.

## GitHub Variables (Auto-Created by Bootstrap)

**Dev-only mode:**
- Variables scoped to repository (no environments)

**Production mode:**
- Variables scoped to environments (dev/stage/prod)

| Variable Name | Description |
|---------------|-------------|
| `GCP_PROJECT_ID` | GCP project ID |
| `GCP_LOCATION` | GCP region |
| `IMAGE_NAME` | Docker image name (also agent_name) |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | WIF provider resource name |
| `ARTIFACT_REGISTRY_URI` | Registry URI |
| `ARTIFACT_REGISTRY_LOCATION` | Registry location |
| `TERRAFORM_STATE_BUCKET` | GCS bucket for main module state |
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
- `stage-promote` / `stage-plan` / `stage-apply` - Stage environment (merge in production mode)
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
config → metadata-extract → docker-build → dev-plan → dev-apply
                              ↓
                           Push to dev registry: {sha}, latest
                              ↓
                           Deploy to dev Cloud Run
```

**Production mode:**
```
config → metadata-extract → docker-build
           ↓                    ↓
           └────────────────────┴─→ dev-plan → dev-apply
                                    (parallel)
                                ↓
                              stage-promote → stage-plan → stage-apply
                                ↓
                           Pull from dev, push to stage
                                ↓
                           Deploy to stage Cloud Run
```

**Result:** Dev deployed (always), stage deployed (production mode only).

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

**Deployment uses image digest** (not tags) to ensure every rebuild triggers a new Cloud Run revision.

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

**Purpose:** Build and push multi-platform Docker images.

**Inputs:**
- Image tags from metadata-extract.yml
- Registry URI and location
- Environment (dev/stage/prod)

**Features:**
- Multi-platform support (linux/amd64)
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

### code-quality.yml

**Purpose:** Run code quality checks (ruff, mypy, pytest).

**Steps:**
1. Install uv and Python 3.13
2. Install dependencies with `uv sync --locked`
3. Run ruff format check
4. Run ruff linting
5. Run mypy type checking
6. Run pytest with coverage

**Timeout:** 10 minutes (typical: 2-3 minutes)

**When it runs:** Push to main (paths filtered) or called by required-checks.yml

### required-checks.yml

**Purpose:** Conditional status check wrapper for branch protection.

**How it works:**
1. `check-changes` job: Use paths-filter to detect code changes
2. `code-quality` job: Run if code changed
3. `required-status` job: Always run (required in branch protection)
   - Pass if no code changes
   - Pass if code changed and quality checks passed
   - Fail if code changed and quality checks failed

**Why this exists:** Branch protection requires a status check that always runs. This wrapper allows skipping quality checks when code hasn't changed while maintaining a consistent required status.

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
- Deployed resources (Cloud Run URL, Agent Engine, GCS bucket)
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

**Runtime config** (LOG_LEVEL, ROOT_AGENT_MODEL, etc.):
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
- Code quality checks → Edit `code-quality.yml`
- Integration tests → Add job after `docker-build` in `ci-cd.yml`
- Custom notifications → Add to orchestrator

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
