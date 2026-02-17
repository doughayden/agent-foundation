# CI/CD

GitHub Actions automation for building and deploying the agent.

## Overview

Zero manual intervention after initial setup. Merge to main = automatic deployment.

**Workflow architecture:**
- **`ci-cd.yml`** - Orchestrator (meta → build → deploy)
- **`config-summary.yml`** - Configuration and production mode detection
- **`metadata-extract.yml`** - Reusable metadata extraction
- **`docker-build.yml`** - Reusable Docker image build
- **`pull-and-promote.yml`** - Reusable image promotion (production mode)
- **`resolve-image-digest.yml`** - Reusable digest lookup (production mode)
- **`terraform-plan-apply.yml`** - Reusable Terraform deployment

**Key principle:** Infrastructure as code + GitOps = reproducible deployments.

## Prerequisites

Complete bootstrap setup before using CI/CD:

1. ✅ Run bootstrap for target environments (see [Getting Started](getting-started.md))
2. ✅ Verify GitHub Variables: `gh variable list`
3. ✅ Verify GitHub Environments created (production mode only)

Bootstrap creates all CI/CD infrastructure: WIF, Artifact Registry, GitHub Variables, Terraform state bucket.

## GitHub Variables (Auto-Created)

Bootstrap creates these Variables per environment:

**Dev-only mode:**
- Variables scoped to repository (no environments)

**Production mode:**
- Variables scoped to environments (dev/stage/prod)

| Variable Name | Description | Created By |
|---------------|-------------|------------|
| `GCP_PROJECT_ID` | GCP project ID | Bootstrap |
| `GCP_LOCATION` | GCP region | Bootstrap |
| `IMAGE_NAME` | Docker image name (also agent_name) | Bootstrap |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | WIF provider resource name | Bootstrap |
| `ARTIFACT_REGISTRY_URI` | Registry URI | Bootstrap |
| `ARTIFACT_REGISTRY_LOCATION` | Registry location | Bootstrap |
| `TERRAFORM_STATE_BUCKET` | GCS bucket for main module state | Bootstrap |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Capture LLM content in traces | Bootstrap |

**Note:** These are Variables (not Secrets) because they're resource identifiers, not credentials. Security comes from WIF IAM policies.

## Workflows Reference

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

**Features:**
- Multi-platform support (linux/amd64)
- Registry cache with protected `buildcache` tag
- Build provenance and SBOM generation

**When it runs:** After metadata extraction

### pull-and-promote.yml

**Purpose:** Promote images between registries (production mode only).

**Inputs:**
- Source and target registry details
- Image digest or tag

**When it runs:** Production mode deployments (dev → stage, stage → prod)

### resolve-image-digest.yml

**Purpose:** Resolve image digest from tag (production mode only).

**Inputs:**
- Registry and image tag

**Outputs:**
- Image digest

**When it runs:** Production mode tag deployments (lookup stage image for prod)

### terraform-plan-apply.yml

**Purpose:** Plan and apply Terraform changes.

**Inputs:**
- Environment (dev/stage/prod)
- Action (plan/apply)
- Docker image digest
- WIF and state bucket details

**Features:**
- Plan artifacts saved between jobs
- PR comment with plan output
- Job summary with deployment details

**When it runs:** After build (or promote) for each environment

## PR Flow

**Trigger:** Push to feature branch with open PR

**What happens:**

**Dev-only mode:**
```
config → metadata-extract → docker-build → dev-plan
                              ↓
                           Push to dev registry: pr-{number}-{sha}
                              ↓
                           Terraform plan (no apply)
                              ↓
                           Comment plan on PR
```

**Production mode:**
```
(Same as dev-only - only builds and plans dev environment)
```

**Result:** Plan preview in PR comment, no actual deployment.

## Merge Flow

**Trigger:** Merge to main

**What happens:**

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

## Tag Flow

**Trigger:** Push git tag matching `v*` (e.g., `git push origin v1.0.0`)

**What happens:**

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

**Main branch builds:**
- Tags: `{sha}` (primary), `latest`
- Example: `abc1234`, `latest`

**Version tag builds:**
- Tags: `{sha}`, `latest`, `{version}`
- Example: `abc1234`, `latest`, `v1.0.0`

**Deployment uses image digest** (not tags) to ensure every rebuild triggers a new Cloud Run revision.

## Image Promotion

Production mode promotes images instead of rebuilding:

**Dev → Stage:**
- Pull image from dev registry by digest
- Push to stage registry with all tags

**Stage → Prod:**
- Resolve digest from stage registry by version tag
- Pull image from stage registry
- Push to prod registry with all tags

**Why?** Deploy the exact bytes tested in previous environment, guaranteed consistency.

See [Deployment](deployment.md) for cross-project IAM configuration.

## Workflow Behavior

**Concurrency:**
- PR builds: Cancel in-progress builds on new push
- Main builds: Run sequentially (no cancellation)
- Per-environment Terraform locking prevents state corruption

**Path filtering:**
- Triggers on code/config changes
- Ignores documentation-only changes
- Tag triggers (`v*`) always run
- See `ci-cd.yml` for complete path list

**Build cache:**
- Registry cache with protected `buildcache` tag
- Significant speedup on cache hits
- Never expires (protected by cleanup policy)

**Timeouts:**
- Build: 30 minutes
- Deploy: 20 minutes per environment
- See workflow files for specific values

## Authentication

**Workload Identity Federation (WIF):**
- Keyless authentication (no service account keys)
- GitHub Actions requests OIDC token
- GCP validates against WIF provider
- Grants temporary credentials scoped to repository

**IAM roles:** See `terraform/bootstrap/module/gcp/main.tf` for complete role list.

**Security:**
- Repository-scoped IAM bindings
- Minimal permissions (only required roles)
- Environment isolation (production mode)

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

**Job summaries provide quick insight without log analysis.**

## PR Comments

Terraform plan workflow posts formatted comments on PRs:

**Comment includes:**
- Plan summary (resources to add/change/destroy)
- Collapsible sections for detailed output
- Format, init, validation results
- Full plan output

**Permissions:** Requires `pull-requests: write` in workflow.

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

See [Deployment](deployment.md) for mode comparison and bootstrap requirements.

### Add Environment Variables

**Runtime config** (LOG_LEVEL, ROOT_AGENT_MODEL, etc.):
1. Go to `Settings → Environments → {environment} → Environment variables`
2. Add or edit variable
3. Re-run deployment or push new commit

**Infrastructure config** (CORS origins, etc.):
1. Edit `terraform/main/main.tf`
2. Create PR
3. Merge PR → deploys via CI/CD

See [Deployment](deployment.md) for runtime vs infrastructure config.

### Add Build Steps

Edit `.github/workflows/ci-cd.yml` or reusable workflows:
- Code quality checks → Add before `docker-build` job
- Integration tests → Add after `docker-build` job
- Custom notifications → Add to orchestrator

### Modify Triggers

Edit `.github/workflows/ci-cd.yml` triggers:

```yaml
on:
  pull_request:
    paths:
      - 'src/**'
      - 'pyproject.toml'
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

## Debugging

### Trace Deployed Image to Git Commit

```bash
# Get deployed image
IMAGE=$(gcloud run services describe <service-name> \
  --region <region> \
  --format='value(spec.template.spec.containers[0].image)')

# Get tags (first tag is commit SHA)
gcloud artifacts docker images describe "$IMAGE" \
  --format="value(tags)" | cut -d',' -f1
```

### View Workflow Runs

```bash
# List recent runs
gh run list --workflow=ci-cd.yml --limit 10

# View specific run
gh run view <run-id>

# View logs
gh run view <run-id> --log

# Open in browser
gh run view <run-id> --web
```

### Manual Trigger

Test workflows manually (also available via GitHub UI: Actions > CI/CD Pipeline > Run workflow):

```bash
# Dev-only mode: deploy to dev
gh workflow run ci-cd.yml

# Production mode: deploy to specific environment
gh workflow run ci-cd.yml \
  -f environment=dev \
  -f terraform_action=plan
```

### Missing Variables

```bash
# Verify Variables exist
gh variable list

# Re-run bootstrap if missing
terraform -chdir=terraform/bootstrap/dev apply
```

### WIF Authentication Failed

```bash
# Check WIF provider
terraform -chdir=terraform/bootstrap/dev output -raw workload_identity_provider

# Verify IAM bindings
gcloud projects get-iam-policy <project-id> \
  --flatten="bindings[].members" \
  --filter="bindings.members:principalSet*"
```

### Image Push Denied

```bash
# Verify artifactregistry.writer role
gcloud projects get-iam-policy <project-id> \
  --flatten="bindings[].members" \
  --filter="bindings.role:roles/artifactregistry.writer"
```

### PR Comment Not Posted

Ensure workflow has `pull-requests: write` permission in `.github/workflows/ci-cd.yml`.

### Build Cache Miss

Verify `buildcache` tag protected by cleanup policy in bootstrap module.

### Terraform State Lock

```bash
# Find stuck runs
gh run list --workflow=ci-cd.yml --limit 10

# Cancel run if needed
gh run cancel <run-id>

# Last resort: force unlock (dangerous)
terraform -chdir=terraform/main force-unlock <lock-id>
```

## Security Best Practices

- **Keyless auth via WIF** - No service account keys, repository-scoped IAM
- **Minimal permissions** - Only required IAM roles
- **Environment isolation** - Separate projects and WIF principals (production mode)
- **Encrypted state** - Remote GCS state with versioning and locking
- **Immutable images** - SHA-tagged with cleanup policies
- **Approval gates** - Manual approval for prod deployments (production mode)

## See Also

- [Getting Started](getting-started.md) - Bootstrap setup and first deployment
- [Deployment](deployment.md) - Multi-environment strategy and rollbacks
- [Environment Variables](environment-variables.md) - Configuration reference
- [Development](development.md) - Local development and testing
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
