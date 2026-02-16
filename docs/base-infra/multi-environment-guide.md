# Multi-Environment Deployment Guide

This guide provides complete documentation for the multi-environment CI/CD system supporting staged deployments across dev, stage, and prod environments.

## Overview

This project supports two deployment modes:

**Dev-Only Mode (default):**
- Single GCP project
- Single environment (dev)
- Workflow: PR → dev, Merge → dev
- Use case: Experiments, prototypes, internal tools

**Production Mode (opt-in):**
- Three GCP projects (dev/stage/prod)
- Four GitHub Environments (dev/stage/prod/prod-apply)
- Workflow: PR → dev, Merge → dev + stage, Git tag → prod (manual approval)
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

## Architecture

### Infrastructure Parity

All environments use **identical infrastructure configuration**. Stage validates the exact infrastructure that will deploy to prod.

**Only differences between environments:**
- Resource names (via `environment` variable: dev/stage/prod)
- Runtime app config (GitHub Environment variables: LOG_LEVEL, etc.)
- Cleanup policies (configured per environment in bootstrap)

**Infrastructure config is hard-coded** in Terraform and identical across environments. This ensures infrastructure changes require explicit file edits and PR review, not hidden variable overrides.

### Job Dependency Graphs

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

**Why use config job parameter instead of workflow-level env?**

GitHub Actions doesn't allow accessing workflow-level `env` variables in jobs that call reusable workflows. The config job output pattern works around this limitation by exposing `production_mode` as a job output that downstream jobs can access via `needs.config.outputs.production_mode`.

**Important:** Changing modes requires:
1. Bootstrap infrastructure for target mode (see Bootstrap Setup section)
2. PR with mode change in ci-cd.yml
3. Merge PR to apply new workflow behavior

## Bootstrap Setup

Bootstrap uses a shared module with per-environment root configurations.

### Module Structure

```
terraform/bootstrap/
├── module/          # Shared module
│   ├── gcp/        # GCP infrastructure submodule
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── github/     # GitHub automation submodule
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── dev/            # Dev environment root config
│   ├── terraform.tf
│   ├── providers.tf
│   ├── variables.tf
│   ├── main.tf
│   ├── outputs.tf
│   └── terraform.tfvars  (not committed)
├── stage/          # Stage environment root config
│   └── (same structure as dev/)
└── prod/           # Prod environment root config
    └── (same structure as dev/)
```

### Dev-Only Mode Setup

1. Create environment config:
```bash
cp terraform/bootstrap/dev/terraform.tfvars.example \
   terraform/bootstrap/dev/terraform.tfvars
```

2. Edit `terraform/bootstrap/dev/terraform.tfvars`:
```hcl
gcp_project_id  = "your-dev-project-id"
gcp_location    = "us-central1"
image_name      = "your-app"
repository_owner = "your-github-org"
repository_name  = "your-repo"
```

3. Authenticate:
```bash
gcloud auth application-default login
gh auth login
```

4. Bootstrap dev environment:
```bash
terraform -chdir=terraform/bootstrap/dev init
terraform -chdir=terraform/bootstrap/dev apply
```

5. Verify GitHub Environment and Variables:
```bash
gh variable list
```

### Production Mode Setup

Repeat the dev-only setup for all three environments:

**Stage:**
```bash
cp terraform/bootstrap/stage/terraform.tfvars.example \
   terraform/bootstrap/stage/terraform.tfvars
# Edit with stage project details
terraform -chdir=terraform/bootstrap/stage init
terraform -chdir=terraform/bootstrap/stage apply
```

**Prod:**
```bash
cp terraform/bootstrap/prod/terraform.tfvars.example \
   terraform/bootstrap/prod/terraform.tfvars
# Edit with prod project details
terraform -chdir=terraform/bootstrap/prod init
terraform -chdir=terraform/bootstrap/prod apply
```

### State Isolation

Each environment uses local state (no backend configuration needed):
- Dev state: `terraform/bootstrap/dev/terraform.tfstate`
- Stage state: `terraform/bootstrap/stage/terraform.tfstate`
- Prod state: `terraform/bootstrap/prod/terraform.tfstate`

State files are environment-specific and isolated. No shared state or workspace switching.

## Image Promotion

The project uses a **hybrid pull-and-promote** strategy to distribute images across environments.

### How It Works

1. **Build** pushes image to dev registry only
2. **Stage promotion** (on merge): Pull from dev by digest → create ephemeral artifact → push to stage
3. **Prod promotion** (on tag): Pull from stage by digest → create ephemeral artifact → push to prod

### Key Benefits

**Minimal cross-project IAM:**
- Narrow grants: read-only (`roles/artifactregistry.reader`) members on specific registry resources
- Resource-level, not project-level: stage WIF → dev registry only, prod WIF → stage registry only
- Uses WIF principals, not service accounts: not impacted by cross-project service account org policies
- Each promotion job authenticates with its own environment's WIF

**Extended retention window:**
- Dev registry: 90-day retention (source of truth for rollbacks)
- Ephemeral artifacts: 1-day retention (used only during promotion)
- Can promote any image in dev registry within 90 days

**On-demand artifacts:**
- Promotion artifacts created only when needed
- Not created during build (saves storage costs)
- Short retention (1 day) since they can be recreated from dev registry

**Immutability:**
- Same image digest guaranteed across all environments
- Pull by digest ensures exact image (no tag manipulation)
- Digest verification in deployment

### Source Selection

**Stage promotion:** Always pulls from dev (validates latest commit)

**Prod promotion:** Always pulls from stage (promotes validated release candidate)

## Deployment Workflows

### Pull Request Workflow

**Triggers:** Opening PR, pushing new commits to PR branch

**Jobs (both modes):**
1. Build → pushes `pr-{number}-{sha}` to dev registry
2. Dev-plan → validates Terraform, posts plan to PR comment

**No apply or promotion jobs run.** PR builds are isolated and never promoted to stage/prod.

### Merge Workflow

**Triggers:** Merging PR to main branch

**Jobs (dev-only mode):**
1. Build → pushes `{sha}` and `latest` to dev registry
2. Dev-plan → saves tfplan-dev artifact
3. Dev-apply → uses saved plan, deploys to dev

**Jobs (production mode):**
1. Build → pushes `{sha}` and `latest` to dev registry
2. Dev-plan → saves tfplan-dev artifact
3. Dev-apply → uses saved plan, deploys to dev
4. Stage-promote → pulls from dev, pushes to stage
5. Stage-plan → saves tfplan-stage artifact
6. Stage-apply → uses saved plan, deploys to stage

**No prod jobs run on merge.** Production waits for explicit git tag.

### Tag Workflow

**Triggers:** Pushing git tag matching `v*` pattern (e.g., `git push origin v0.5.0`)

**Jobs (production mode only):**
1. Resolve-digest → looks up image in stage registry by SHA tag
2. Prod-promote → pulls from stage, pushes to prod with version tag
3. Prod-plan → saves tfplan-prod artifact, displays output
4. Prod-apply → waits for manual approval, uses saved plan, deploys to prod

**No dev or stage jobs run on tag.** Only prod deploys.

**Tag workflow is production-mode only.** Dev-only mode ignores tag events (no prod environment exists).

## Rollback Procedures

Two rollback strategies depending on the scenario:

### Strategy 1: Cloud Run Traffic Split

**When to use:**
- Production app issue (code bug or bad container)
- Need immediate relief (< 1 minute)
- Have direct GCP project access
- Old revision still exists in Cloud Run

**How:**
```bash
# List revisions
gcloud run revisions list \
  --service=your-service-prod \
  --project=your-prod-project \
  --region=us-central1

# Route 100% traffic to old revision
gcloud run services update-traffic your-service-prod \
  --to-revisions=REVISION_NAME=100 \
  --project=your-prod-project \
  --region=us-central1
```

**Limitations:**
- Requires direct prod GCP access (blocked in some orgs)
- Only works if old revision exists (Cloud Run retention limits)
- App-only (cannot rollback infrastructure changes)
- Manual operation (no CI/CD involved)

**Reference:** [Cloud Run Rollbacks and Traffic Migration](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)

### Strategy 2: Hotfix + Tag

**When to use:**
- Infrastructure needs rollback (Terraform changes)
- Configuration in code needs rollback
- Beyond 90-day registry retention
- Need coordinated rollback of multiple changes
- Want stage validation before prod deployment

**Approach A: Revert specific commits (preserves history):**
```bash
# Create hotfix branch
git checkout -b hotfix/rollback-v0.5.0 main

# Revert the bad commit(s)
git revert BAD_COMMIT_SHA

# Push and create PR
git push origin hotfix/rollback-v0.5.0
gh pr create

# After merge (deploys to dev + stage)
# Create tag for prod
git checkout main
git pull
git tag v0.4.10
git push origin v0.4.10
```

**Approach B: Reset to known-good state (clean slate):**
```bash
# Create hotfix branch from known-good tag
git checkout -b hotfix/reset-to-v0.4.9 v0.4.9

# Cherry-pick any commits to keep (optional)
git cherry-pick COMMIT_SHA

# Push and create PR
git push origin hotfix/reset-to-v0.4.9
gh pr create

# After merge, create tag
git checkout main
git pull
git tag v0.4.10
git push origin v0.4.10
```

**Timing:**
- 10-20 minutes end-to-end
- PR review and merge: variable
- Dev + stage deployment: ~5 minutes
- Prod deployment (after tag): ~3 minutes

**Limitations:**
- Slowest option
- Requires PR approval (branch protection enforced)
- Goes through full validation pipeline

**Benefits:**
- Can rollback infrastructure (Terraform changes)
- Stage validates changes before prod
- Full audit trail in git history
- Supports complex rollbacks

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
   └─→ Strategy 2: Hotfix + Tag (only option)
```

## Environment Variables

### Runtime vs Infrastructure Config

**Runtime app config** (configurable via GitHub Environment variables):
- `LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `ROOT_AGENT_MODEL` - Gemini model for root agent
- `SERVE_WEB_INTERFACE` - Enable web UI (true/false)
- Pass to Terraform as `TF_VAR_*` inputs

**Infrastructure config** (hard-coded in Terraform):
- `AGENT_ENGINE` - Vertex AI Reasoning Engine ID
- `ARTIFACT_SERVICE_URI` - GCS bucket URL
- `ALLOW_ORIGINS` - CORS origins for Cloud Run
- Terraform-managed values only (no variable overrides)
- Project-specific infrastructure documented in project root

**Why separate them:**
- Runtime config changes don't require Terraform rebuilds
- Infrastructure changes require explicit code review and PR
- Security: CORS origins not overridable by GitHub variables

### How GitHub Environments Load Variables

Setting `environment: dev` at job level automatically loads variables from the `dev` GitHub Environment.

**Example:**
```yaml
jobs:
  deploy:
    environment: dev  # Loads dev environment variables
    env:
      PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}  # Reads from dev environment
```

Each environment has its own scoped variables with different values. Same variable name, different values per environment.

### Overriding Variables

**Runtime app config:** Edit GitHub Environment variables in repository settings

**Infrastructure config:** Edit Terraform files and create PR (requires code review)

## Plan Artifacts

All environments use a uniform plan → apply pattern with saved plan artifacts.

### How Plan Artifacts Work

**PR events:**
- Plan runs and displays output in PR comment
- Artifact not saved (plan only, no apply)

**Merge events:**
- Dev plan saves tfplan-dev artifact
- Stage plan saves tfplan-stage artifact
- Apply jobs download and use saved plans

**Tag events:**
- Prod plan saves tfplan-prod artifact
- Prod apply waits for approval, then uses saved plan

### Benefits

**Gated deployments:**
- Plan artifact saved before approval
- Review plan output before approving
- Apply uses exact same plan (no drift)

**No re-planning:**
- Apply step skips plan (uses saved artifact)
- Format and validate checks skipped (already validated during plan)
- Faster apply execution (~30% time savings)

**Artifact retention:**
- 7-day retention for all plan artifacts
- Sufficient for review and approval cycles
- Auto-cleanup prevents storage bloat

**Uniform pattern:**
- Same workflow across all environments
- Consistent, predictable, reviewable
- Enterprise-grade deployment process

## Troubleshooting

### Environment Variable Not Found

**Symptom:** Workflow fails with "Variable not found" error

**Solution:**
1. Verify environment exists: GitHub repo → Settings → Environments
2. Verify variable exists in environment: Select environment → Variables
3. Re-run bootstrap if missing: `terraform -chdir=terraform/bootstrap/{env} apply`

### Image Not Found in Registry

**Symptom:** Promotion job fails with "image not found" error

**Solution:**
1. Verify image exists in source registry:
```bash
gcloud artifacts docker tags list \
  REGISTRY_URI/IMAGE_NAME \
  --project=SOURCE_PROJECT
```
2. Check SHA tag format (7 characters, no `v` prefix)
3. Verify image within retention window (90 days for dev)

### Plan Artifact Not Found

**Symptom:** Apply job fails with "artifact not found" error

**Solution:**
1. Verify plan job completed successfully
2. Check artifact retention (7 days)
3. Re-run plan job if artifact expired
4. Check workflow concurrency (parallel runs may conflict)

### WIF Authentication Failed

**Symptom:** "Permission denied" or "authentication failed" errors

**Solution:**
1. Verify WIF provider exists:
```bash
terraform -chdir=terraform/bootstrap/{env} output workload_identity_provider
```
2. Verify IAM bindings:
```bash
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:principalSet*"
```
3. Re-run bootstrap if bindings missing

### Terraform State Lock

**Symptom:** "Error acquiring state lock" message

**Solution:**
1. Check for stuck workflow runs:
```bash
gh run list --workflow=ci-cd.yml --limit 10
```
2. Cancel stuck runs:
```bash
gh run cancel RUN_ID
```
3. Force unlock (last resort):
```bash
terraform -chdir=terraform/main force-unlock LOCK_ID
```

## Security Best Practices

**Keyless authentication:**
- WIF provides keyless auth to GCP
- No service account keys stored in GitHub
- Repository-scoped IAM bindings

**Minimal permissions:**
- Each environment uses dedicated service account
- Only required IAM roles granted
- Cross-project grants WIF narrowly scoped (read-only, registry-resource-bound)

**Environment protection:**
- Production requires manual approval
- Required reviewers enforced
- Prevent self-review enabled
- Deployment branch restrictions

**Immutable deployments:**
- All deployments use image digest (not tags)
- Same digest guaranteed across environments
- Tag manipulation cannot affect deployed image

**Audit trail:**
- All deployments logged in workflow runs
- Git history tracks all code changes
- Workflow run logs capture all automation

## Next Steps

1. ✅ Choose deployment mode (dev-only or production)
2. ✅ Bootstrap infrastructure for chosen mode
3. ✅ Verify GitHub Environments and Variables created
4. ✅ Set `production_mode` parameter in config job of ci-cd.yml
5. ✅ Create PR to test workflow
6. ✅ Merge PR to deploy to dev (and stage in production mode)
7. ✅ Create git tag to deploy to prod (production mode only)
8. 📖 Monitor deployments: `gh run list --workflow=ci-cd.yml`

## Related Documentation

- [CI/CD Workflow Guide](./cicd-setup.md) - Detailed workflow reference
- [Bootstrap Setup](./bootstrap-setup.md) - Bootstrap infrastructure setup
- [Terraform Infrastructure Guide](./terraform-infrastructure.md) - Terraform module reference
- [Development Guide](./development.md) - Local development workflow
