# Deployment

Multi-environment deployment with Terraform and GitHub Actions.

## Overview

Two deployment modes available:

**Dev-Only Mode (default):**
- Single GCP project
- Single environment (dev)
- Workflow: PR → dev plan, Merge → dev deploy
- Use case: Experiments, prototypes, internal tools

**Production Mode (opt-in):**
- Three GCP projects (dev/stage/prod)
- Four GitHub Environments (dev/stage/prod/prod-apply)
- Workflow: PR → dev plan, Merge → dev + stage deploy, Git tag → prod deploy (manual approval)
- Use case: Production services requiring staged deployment

## When to Use Each Mode

### Dev-Only Mode

Choose dev-only mode when:
- Building experimental features or prototypes
- Developing internal tools with limited user base
- Cost optimization is critical (single GCP project)
- Rapid iteration matters more than staged validation

### Production Mode

Choose production mode when:
- Deploying customer-facing services
- Compliance requires staged deployment and approval gates
- Infrastructure changes need validation before production
- Rollback capability is critical

## Multi-Environment Strategy

### Infrastructure Parity

All environments use **identical infrastructure configuration**. Stage validates the exact infrastructure that will deploy to prod.

**Only differences between environments:**
- Resource names (via `environment` variable: dev/stage/prod)
- Runtime app config (GitHub Environment variables: LOG_LEVEL, etc.)
- Cleanup policies (configured per environment in bootstrap)

**Infrastructure config is hard-coded** in Terraform and identical across environments. This ensures infrastructure changes require explicit file edits and PR review, not hidden variable overrides.

### Deployment Flow

#### Dev-Only Mode

**Pull Request:**
```
build (push to dev registry)
  ↓
dev-plan (plan only, PR comment)
```

**Merge to main:**
```
build (push to dev registry)
  ↓
dev-plan (auto, saves tfplan-dev)
  ↓
dev-apply (auto-proceeds, uses saved plan)
```

#### Production Mode

**Pull Request:**
```
build (push to dev registry)
  ↓
dev-plan (plan only, PR comment)
```

**Merge to main:**
```
build (push to dev registry)
  ↓
  ├─→ dev-plan (auto, saves tfplan-dev)
  │     ↓
  │   dev-apply (auto-proceeds, uses saved plan)
  │
  └─→ stage-promote (pull from dev → push to stage)
        ↓
      stage-plan (auto, saves tfplan-stage)
        ↓
      stage-apply (auto-proceeds, uses saved plan)
```

**Git tag push:**
```
resolve-digest (look up image in stage registry by tag)
  ↓
prod-promote (pull from stage → push to prod)
  ↓
prod-plan (auto, saves tfplan-prod)
  ↓
prod-apply (requires manual approval, uses saved plan)
```

**Key principles:**
- Dev deployment never waits for stage or prod
- Stage validates every merge (continuous feedback)
- Prod deploys only on explicit git tags (release discipline)
- Uniform plan → apply pattern across all environments

## Switching Deployment Modes

Edit the `production_mode` parameter in the `config` job of `.github/workflows/ci-cd.yml`:

**Dev-Only Mode:**
```yaml
jobs:
  config:
    uses: ./.github/workflows/config-summary.yml
    with:
      production_mode: false
```

**Production Mode:**
```yaml
jobs:
  config:
    uses: ./.github/workflows/config-summary.yml
    with:
      production_mode: true
```

**Why config job parameter?** GitHub Actions doesn't allow accessing workflow-level `env` variables in jobs that call reusable workflows. The config job output pattern works around this limitation.

**Important:** Changing modes requires:
1. Bootstrap infrastructure for target mode (see Bootstrap Setup)
2. PR with mode change in ci-cd.yml
3. Merge PR to apply new workflow behavior

## Terraform Structure

Two Terraform modules with distinct responsibilities:

### Bootstrap Module

**Purpose:** One-time CI/CD infrastructure setup (per environment)

**Location:** `terraform/bootstrap/{dev,stage,prod}/`

**Resources created:**
1. **Workload Identity Federation** - Keyless GitHub Actions authentication
2. **Artifact Registry** - Docker image storage with cleanup policies
3. **Terraform State Bucket** - Remote state for main module (GCS)
4. **GitHub Variables** - Auto-configured repository variables for CI/CD

**State management:** Local state (per environment)

**Usage:**
```bash
# Dev-only mode (bootstrap dev only)
terraform -chdir=terraform/bootstrap/dev init
terraform -chdir=terraform/bootstrap/dev apply

# Production mode (bootstrap all three environments)
terraform -chdir=terraform/bootstrap/dev init
terraform -chdir=terraform/bootstrap/dev apply

terraform -chdir=terraform/bootstrap/stage init
terraform -chdir=terraform/bootstrap/stage apply

terraform -chdir=terraform/bootstrap/prod init
terraform -chdir=terraform/bootstrap/prod apply
```

See [Getting Started](getting-started.md) for detailed bootstrap instructions.

### Main Module

**Purpose:** Application deployment (runs in CI/CD)

**Location:** `terraform/main/`

**Resources created:**
1. **Cloud Run Service** - Containerized agent deployment
2. **Service Account** - IAM identity for Cloud Run
3. **Vertex AI Reasoning Engine** - Session/memory persistence
4. **GCS Bucket** - Artifact storage

**State management:** Remote state in GCS (bucket created by bootstrap)

**Execution:** Designed for GitHub Actions (local execution possible but not supported)

**Inputs:** All via `TF_VAR_*` environment variables from GitHub

## Deployment Workflows

### PR Flow (Dev Plan)

1. Push to feature branch
2. GitHub Actions triggers:
   - Build Docker image → push to dev registry
   - Run Terraform plan for dev
   - Comment plan on PR

**No actual deployment** - plan only for review.

### Merge Flow

**Dev-Only Mode:**
1. Merge to main
2. GitHub Actions triggers:
   - Build Docker image → push to dev registry
   - Run Terraform plan for dev → save tfplan-dev artifact
   - Run Terraform apply using saved plan → deploy to dev

**Production Mode:**
1. Merge to main
2. GitHub Actions triggers:
   - Build Docker image → push to dev registry
   - **Dev:** plan → apply (as above)
   - **Stage:** promote image from dev → stage registry
   - **Stage:** plan → apply using promoted image

Dev and stage deployments run in parallel after build completes.

### Tag Flow (Production Mode Only)

1. Create and push git tag (e.g., `v1.0.0`)
2. GitHub Actions triggers:
   - Resolve image digest from stage registry by tag
   - Promote image from stage → prod registry
   - Run Terraform plan for prod → save tfplan-prod artifact
   - **Wait for manual approval** (prod-apply environment)
   - Run Terraform apply using saved plan → deploy to prod

**Approval gate:** The `prod-apply` GitHub Environment requires manual approval before deploying to production.

## Image Promotion

Production mode uses **image promotion** (pull from source, push to target) instead of rebuilding:

**Dev → Stage:**
- Trigger: Merge to main
- Source: Dev Artifact Registry
- Target: Stage Artifact Registry
- Tags: Copy all tags from source image

**Stage → Prod:**
- Trigger: Git tag push
- Source: Stage Artifact Registry (by tag)
- Target: Prod Artifact Registry
- Tags: Copy all tags from source image

**Why promote instead of rebuild?**
- Deploy the exact bytes that were tested in previous environment
- Faster (no rebuild)
- Guaranteed consistency across environments

**Cross-Project IAM:** Stage and prod bootstrap grant cross-project Artifact Registry reader access for image promotion (see bootstrap module configuration).

## Runtime Configuration

### Runtime vs Infrastructure Config

**Runtime app config** (configurable via GitHub Environment variables):
- `LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `ROOT_AGENT_MODEL` - Gemini model for root agent
- `SERVE_WEB_INTERFACE` - Enable web UI (true/false)
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` - Capture LLM content in traces

Pass to Terraform as `TF_VAR_*` inputs, override via GitHub Environment Variables.

**Infrastructure config** (hard-coded in Terraform):
- `AGENT_ENGINE` - Vertex AI Reasoning Engine ID (auto-created)
- `ARTIFACT_SERVICE_URI` - GCS bucket URL (auto-created)
- `ALLOW_ORIGINS` - CORS origins for Cloud Run
- Terraform-managed values only (no variable overrides)

**Why separate them:**
- Runtime config changes don't require Terraform rebuilds
- Infrastructure changes require explicit code review and PR
- Security: CORS origins not overridable by GitHub variables

### Overriding Runtime Config

Edit GitHub Environment variables in repository settings:

```
Settings → Environments → {environment} → Environment variables
```

Changes apply on next deployment (no PR required).

### Overriding Infrastructure Config

Edit Terraform files and create PR:

```bash
# Edit terraform/main/main.tf
git checkout -b fix/update-cors-origins
# Make changes
git commit -m "fix: update CORS origins"
git push origin fix/update-cors-origins
gh pr create
# Merge PR → deploys to dev (+ stage in production mode)
```

## Common Operations

### Deploy Runtime Config Change

No code changes needed - just update GitHub Environment variables:

1. Go to `Settings → Environments → dev → Environment variables`
2. Edit variable (e.g., `LOG_LEVEL=DEBUG`)
3. Re-run latest workflow or push new commit

Changes apply on next deployment.

### Deploy Infrastructure Change

Requires PR and code review:

1. Create feature branch
2. Edit Terraform files in `terraform/main/`
3. Push and create PR
4. Review Terraform plan in PR comment
5. Merge PR → deploys to dev (+ stage in production mode)

### Deploy to Production (Production Mode)

1. Ensure dev and stage deployments are successful
2. Create and push git tag:
   ```bash
   git checkout main
   git pull
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. Monitor GitHub Actions run
4. Approve deployment in `prod-apply` environment
5. Verify production deployment

### Rollback Strategies

**Strategy 1: Cloud Run Traffic Split (instant, requires GCP access)**

Revert to previous revision without redeployment:

```bash
# List revisions
gcloud run revisions list --service=<service-name> --region=<region>

# Split traffic (instant rollback to previous revision)
gcloud run services update-traffic <service-name> \
  --to-revisions=<previous-revision>=100 \
  --region=<region>
```

**Strategy 2: Hotfix + Tag (10-20 minutes, works without GCP access)**

Revert via git and redeploy:

```bash
# Revert to previous working commit
git revert <bad-commit>

# Or: cherry-pick fix from another branch
git cherry-pick <fix-commit>

# Push to main
git push origin main

# Tag for production (production mode only)
git tag v1.0.1
git push origin v1.0.1
```

**Strategy 3: Infrastructure Rollback (full validation pipeline)**

Revert Terraform changes via PR:

```bash
# Revert PR that introduced bad infrastructure
git revert <merge-commit>
git push origin main

# Or: create PR with fixed Terraform config
git checkout -b fix/revert-infrastructure
# Make changes
git commit -m "fix: revert infrastructure change"
git push origin fix/revert-infrastructure
gh pr create
# Merge PR → deploys to dev + stage
# Tag for prod deployment
```

### Rollback Decision Tree

```
Production issue detected?
│
├─ App code regression (crashes, errors, bad behavior)
│  │
│  ├─ Have direct GCP prod access?
│  │  └─→ Strategy 1: Cloud Run Traffic Split (instant)
│  │
│  └─ No direct GCP access?
│     └─→ Strategy 2: Hotfix + Tag (10-20 minutes)
│
├─ Bad container image (won't start, missing dependencies)
│  │
│  ├─ Old revision exists + have GCP access?
│  │  └─→ Strategy 1: Cloud Run Traffic Split (instant)
│  │
│  └─ No old revision or no GCP access?
│     └─→ Strategy 2: Hotfix + Tag (10-20 minutes)
│
├─ Configuration regression (wrong env vars, feature flags)
│  │
│  ├─ Config in GitHub Environment variables?
│  │  └─→ Manual GitHub UI edit + re-trigger deployment
│  │
│  └─ Config in application code?
│     └─→ Strategy 2: Hotfix + Tag
│
└─ Infrastructure regression (IAM, GCS, Cloud Run config)
   └─→ Strategy 3: Infrastructure Rollback (full pipeline)
```

## Bootstrap Setup

### Dev-Only Mode

Bootstrap only the dev environment:

1. Create environment config:
   ```bash
   cp terraform/bootstrap/dev/terraform.tfvars.example \
      terraform/bootstrap/dev/terraform.tfvars
   ```

2. Edit `terraform/bootstrap/dev/terraform.tfvars`:
   ```hcl
   project     = "your-dev-project-id"
   location    = "us-central1"
   agent_name  = "your-agent-name"
   repository_owner = "your-github-org"
   repository_name  = "your-repo"
   ```

3. Bootstrap:
   ```bash
   terraform -chdir=terraform/bootstrap/dev init
   terraform -chdir=terraform/bootstrap/dev apply
   ```

### Production Mode

Bootstrap all three environments (dev, stage, prod):

1. Create config for each environment:
   ```bash
   # Dev
   cp terraform/bootstrap/dev/terraform.tfvars.example \
      terraform/bootstrap/dev/terraform.tfvars

   # Stage
   cp terraform/bootstrap/stage/terraform.tfvars.example \
      terraform/bootstrap/stage/terraform.tfvars

   # Prod
   cp terraform/bootstrap/prod/terraform.tfvars.example \
      terraform/bootstrap/prod/terraform.tfvars
   ```

2. Edit each `terraform.tfvars` with environment-specific values:
   - **Different GCP projects** for each environment
   - **Same agent_name** across all environments
   - Same repository_owner and repository_name

3. Bootstrap each environment:
   ```bash
   # Dev
   terraform -chdir=terraform/bootstrap/dev init
   terraform -chdir=terraform/bootstrap/dev apply

   # Stage (includes cross-project IAM for dev → stage promotion)
   terraform -chdir=terraform/bootstrap/stage init
   terraform -chdir=terraform/bootstrap/stage apply

   # Prod (includes cross-project IAM for stage → prod promotion)
   terraform -chdir=terraform/bootstrap/prod init
   terraform -chdir=terraform/bootstrap/prod apply
   ```

4. Verify GitHub Environments created:
   ```bash
   # Should see: dev, stage, prod, prod-apply
   gh api repos/:owner/:repo/environments | jq -r '.environments[].name'
   ```

See [Getting Started](getting-started.md) for detailed first-time setup.

## See Also

- [Getting Started](getting-started.md) - Initial setup and first deployment
- [Environment Variables](environment-variables.md) - Configuration reference
- [CI/CD](cicd.md) - GitHub Actions workflows
- [Development](development.md) - Local development and testing
- [Troubleshooting](troubleshooting.md) - Common issues
