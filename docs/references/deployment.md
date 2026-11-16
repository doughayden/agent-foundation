# Deployment Modes Reference

Multi-environment deployment strategy, infrastructure parity, and image promotion.

## Deployment Mode Comparison

### Dev-Only Mode (Default)

**Infrastructure:**
- Single GCP project
- Single Terraform deployment environment (dev)
- One GitHub Environment variable scope
- No tag protection

**Workflow:**
- PR → dev plan (comment on PR)
- Merge → dev deploy
- Tags start no deployment

**Use cases:**
- Experiments and prototypes
- Internal tools with limited user base
- Cost optimization (single project)
- Rapid iteration without approval gates

**Configuration:**
```yaml
# .github/workflows/ci-cd.yml
jobs:
  config:
    uses: ./.github/workflows/config-summary.yml
    with:
      production_mode: false
```

### Production Mode (Opt-In)

**Infrastructure:**
- Three GCP projects (dev/stage/prod)
- Four GitHub Environments (dev/stage/prod/prod-apply)
- Environment-scoped variables
- Tag protection ruleset (admin-only `prod-v*` promotion tags)

**Workflow:**
- PR → dev plan (comment on PR)
- Merge → dev + stage deploy (parallel)
- `prod-vX.Y.Z` promotion tag → prod deploy (manual approval required)

**Use cases:**
- Customer-facing production services
- Compliance requiring staged deployment
- Infrastructure validation before production
- Rollback capability critical

**Configuration:**
```yaml
# .github/workflows/ci-cd.yml
jobs:
  config:
    uses: ./.github/workflows/config-summary.yml
    with:
      production_mode: true
```

### Switching Modes

**Requirements:**
1. Bootstrap Github Environment(s) and Google Cloud project(s) for target mode
2. Configure protection rules (if switching to production mode)
3. Create PR with mode change in ci-cd.yml
4. Merge PR to apply new workflow behavior

**Why config job parameter?** GitHub Actions doesn't allow accessing workflow-level `env` variables (like `env.PRODUCTION_MODE: {true/false}`)in jobs that call reusable workflows. The config job output pattern works around this limitation.

## Multi-Environment Strategy

### Infrastructure Parity

All environments use **identical infrastructure configuration**. Stage validates the exact infrastructure that will deploy to prod.

**Differences between environments:**
- Resource names (via `environment` variable: dev/stage/prod)
- Runtime app config (per environment in `terraform/main/env.tf`)
- Cleanup policies (configured per environment in bootstrap)

**Infrastructure config is hard-coded** in Terraform and identical across environments, apart from the per-environment runtime config in `env.tf`. This ensures infrastructure changes (for example, the Cloud Run service minimum instance count) require explicit file edits and PR review, not hidden variable overrides.

### Deployment Flow

For detailed job-level dependency graphs, see [CI/CD Workflows: Workflow Flows](cicd.md#workflow-flows).

#### Dev-Only Mode

**Pull Request:**
- Build Docker image → Plan infrastructure (no apply)
- Comment plan on PR

**Merge to main:**
- Build Docker image → Plan infrastructure → Apply to dev → Smoke test

**Tag push:**
- No effect on deployment in dev-only mode

#### Production Mode

**Pull Request:**
- Build Docker image → Plan infrastructure (no apply)
- Comment plan on PR

**Merge to main:**
- Build Docker image, then in parallel:
  - Deploy to dev → Smoke
  - Deploy to stage → Smoke

**Promotion tag push (`prod-vX.Y.Z`):**
- Verify staged image exists and stage run passed (parallel gates) → Deploy to prod (manual approval) → Smoke

**Key principles:**
- Dev deployment never waits for stage or prod
- Stage validates every merge (continuous feedback)
- Prod deploys only on an explicit `prod-vX.Y.Z` promotion tag, pushed by a repository admin on the commit a `vX.Y.Z` release tag marks (release discipline). Commands: [Release a Version: Promote to Production](../releasing.md#promote-to-production-production-mode)
- Prod promotion is gated on the tagged commit's stage run passing (see [CI/CD Workflows: Require Stage Success](cicd.md#require-stage-successyml))
- Uniform plan → apply pattern across all environments

## Image Promotion

Production mode uses **image promotion** (pull from source, push to target) instead of rebuilding.

### Dev → Stage

**Trigger:** Merge to main

**Process:**
1. Build job pushes image to dev registry: `us-central1-docker.pkg.dev/dev-project/agent-dev/image@sha256:abc123`
2. stage-promote job:
   - Authenticates to dev and stage registries via WIF
   - Pulls image from dev registry by digest
   - Re-tags with all source tags
   - Pushes to stage registry: `us-central1-docker.pkg.dev/stage-project/agent-stage/image@sha256:abc123`

**Cross-project IAM:**
- Stage WIF principal has `roles/artifactregistry.reader` on dev registry
- Configured via `promotion_source_*` variables in stage bootstrap

### Stage → Prod

**Trigger:** Promotion tag push (like `prod-v1.0.0`) on the commit the `v1.0.0` release tag marks

**Process:**
1. resolve-digest job:
   - Queries stage registry for the image by the commit's `{sha}` tag
   - Extracts digest: `sha256:abc123`
2. require-stage-success job (gates prod-promote):
   - Confirms the tagged commit's merge run had `Apply Stage`, `Smoke Stage`, and `Judge Eval` all succeed
   - Fails closed otherwise, halting the tag run before the `prod-apply` approval
3. prod-promote job:
   - Authenticates to stage and prod registries via WIF
   - Pulls image from stage registry by digest
   - Re-tags with all source tags
   - Pushes to prod registry: `us-central1-docker.pkg.dev/prod-project/agent-prod/image@sha256:abc123`

**Cross-project IAM:**
- Prod WIF principal has `roles/artifactregistry.reader` on stage registry
- Configured via `promotion_source_*` variables in prod bootstrap

### Why Promote Instead of Rebuild?

**Guarantees:**
- Deploy the **exact bytes** that were tested in previous environment
- No build-time differences (dependencies, base images, timestamps)
- Immutable artifacts (can't accidentally rebuild with different code)

**Performance:**
- Faster than rebuild (just pull/tag/push)
- No dependency resolution, no layer builds

**Consistency:**
- Same image digest across all environments
- Easy to trace: "prod is running the same image validated in stage"

## Runtime Configuration

### Runtime vs Infrastructure Config

**Runtime app config** (per environment in `terraform/main/env.tf`): the log level, content capture mode, web interface and any variable a consumer adds for one environment. The variables and their values: [Environment Variables: Deployed Values](../environment-variables.md#deployed-values-cloud-run).

Terraform merges the deploying environment's entry over the infrastructure config below; an entry wins over a template key of the same name.

`docker_image` is nullable: a run with no new image (an infrastructure-only apply) reuses the image from the previous deployment's state.

**Infrastructure config** (managed exclusively in Terraform files):
- `SESSION_SERVICE_URI` - Session persistence URI (auto-created, `postgresql+asyncpg://` protocol via Cloud SQL)
- `MEMORY_SERVICE_URI` - Memory persistence URI (auto-created, `agentengine://` protocol)
- `ARTIFACT_SERVICE_URI` - GCS bucket URL (auto-created)
- `ALLOW_ORIGINS` - CORS origins for Cloud Run
- Set in `terraform/main/main.tf`

**Why separate them:**
- Runtime config varies per environment, so it lives in one reviewed map instead of being spread through `main.tf`
- Both go through a PR, so every deployed value is in version control

### Changing Runtime Config

1. Edit the environment's entry in `terraform/main/env.tf` (like `LOG_LEVEL = "DEBUG"` in `dev`)
2. Create a PR; a dev change shows in its plan, stage and prod changes in the merge and promotion plans
3. Merge (prod: promote) to deploy

### Changing Infrastructure Config

Edit Terraform files and create PR:

```bash
git checkout -b fix/update-cors-origins
# Edit terraform/main/main.tf (e.g., update ALLOW_ORIGINS list)
git commit -m "fix: update CORS origins"
git push origin fix/update-cors-origins
gh pr create
# Review plan in PR comment
# Merge PR → deploys to dev (+ stage in production mode)
```

## Terraform Structure

### Bootstrap Module

**Purpose:** One-time CI/CD infrastructure setup (per environment)

**Location:** `terraform/bootstrap/{dev,stage,prod}/`

**Resources created:**
- Workload Identity Federation (keyless GitHub Actions auth)
- Artifact Registry (Docker image storage with cleanup policies)
- GitHub Environments (dev/stage/prod/prod-apply in production mode)
- GitHub Environment Variables (auto-configured per environment)
- Tag Protection (promotion tag ruleset, prod bootstrap only)
- Cross-Project IAM (Artifact Registry reader for promotion, stage/prod)

**State management:** Remote state in GCS (per environment, `bootstrap/` prefix). Pre-bootstrap (`terraform/bootstrap/pre/`, local state) creates the state buckets used by bootstrap and the main module.

**Runs:** Manually by infrastructure owners (one-time setup)

### Main Module

**Purpose:** Application deployment (runs in CI/CD)

**Location:** `terraform/main/`

**Resources created:**
- VPC network + subnet + Private Services Access (Cloud SQL private IP)
- Cloud NAT router (bastion outbound connectivity)
- IAP firewall rules (SSH + SQL proxy port to bastion)
- Bastion host (COS, Auth Proxy impersonating the app SA): [Bastion and IAP Tunnel](bastion.md)
- Cloud Run Service (Auth Proxy sidecar + direct VPC egress)
- Service Account (IAM identity for Cloud Run)
- Cloud SQL instance (private IP only, session persistence via DatabaseSessionService)
- Vertex AI Agent Engine (memory persistence)
- GCS Bucket (artifact storage)
- Cloud Monitoring alert policies (dry-run latency, traffic, errors, saturation and unhealthy instances, `monitoring.tf`)

**State management:** Remote state in GCS (bucket created by pre-bootstrap; bootstrap publishes its name as the `TERRAFORM_STATE_BUCKET` GitHub Variable)

**Runs:** Automatically in GitHub Actions on merge/tag

**Inputs:** All via `TF_VAR_*` environment variables from GitHub

**Auth Proxy flags:** `local.cloud_sql_proxy_args` holds the flags shared by the Cloud Run sidecar and the bastion. The bastion-only flags and the iptables rule live in `templates/bastion-cloud-init.yaml` ([Bastion and IAP Tunnel](bastion.md)).

**IAM layering:** each environment has its own GCP project. Project-level WIF roles are same-project only and live in `terraform/bootstrap/module/gcp/`. Cross-project Artifact Registry reader grants for promotion live in the stage and prod bootstrap roots. App service account roles live in `terraform/main/main.tf`, and consumer-added WIF roles in `terraform/main/iam.tf`.

**Startup probes:** the app container's startup probe polls `/health` for up to ~120s (24 failures x 5s) to cover credential initialization. The Auth Proxy sidecar has no startup probe; Cloud Run restarts it on crash, which is more reliable than probing it. When the app works locally but fails on Cloud Run, suspect credentials or VPC egress first.

### Resource Naming

All resources named: `${var.agent_name}-${var.environment}`

**Examples:**
- Cloud Run service: `my-agent-dev`, `my-agent-stage`, `my-agent-prod`
- Artifact Registry: `my-agent-dev`, `my-agent-stage`, `my-agent-prod`
- Service account: `my-agent-dev@project.iam.gserviceaccount.com`

**Note:** Service account IDs truncate agent_name to 30 chars (GCP limit).

---

← [Back to References](README.md) | [Documentation](../README.md)
