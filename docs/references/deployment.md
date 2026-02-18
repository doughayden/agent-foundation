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
- Tag → dev deploy (version labeled)

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
- Tag protection ruleset (v*)

**Workflow:**
- PR → dev plan (comment on PR)
- Merge → dev + stage deploy (parallel)
- Tag → prod deploy (manual approval required)

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
- Runtime app config (GitHub Environment variables: LOG_LEVEL, etc.)
- Cleanup policies (configured per environment in bootstrap)

**Infrastructure config is hard-coded** in Terraform and identical across environments. This ensures infrastructure changes (for example, the Cloud Run service minimum instance count) require explicit file edits and PR review, not hidden variable overrides.

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

**Tag push:**
No effect on deployment in dev-only mode

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
prod-apply (gated: requires manual approval, uses saved plan)
```

**Key principles:**
- Dev deployment never waits for stage or prod
- Stage validates every merge (continuous feedback)
- Prod deploys only on explicit git tags (release discipline)
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

**Trigger:** Git tag push (e.g., `v1.0.0`)

**Process:**
1. resolve-digest job:
   - Queries stage registry for image by tag: `v1.0.0`
   - Extracts digest: `sha256:abc123`
2. prod-promote job:
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

**Runtime app config** (configurable via GitHub Environment variables):
- `LOG_LEVEL` - Logging verbosity
- `ROOT_AGENT_MODEL` - Gemini model selection
- `SERVE_WEB_INTERFACE` - Enable web UI
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` - Capture LLM content in traces

GitHub Environment Variables pass overrides to Terraform as `TF_VAR_*` inputs. Default values managed in Terraform.

**Infrastructure config** (managed exclusively in Terraform files):
- `AGENT_ENGINE` - Vertex AI Agent Engine ID (auto-created)
- `ARTIFACT_SERVICE_URI` - GCS bucket URL (auto-created)
- `ALLOW_ORIGINS` - CORS origins for Cloud Run
- Terraform-managed values only (no variable overrides)

**Why separate them:**
- Runtime config changes don't require Terraform rebuilds (fast iteration)
- Infrastructure changes require explicit code review and PR (security)
- CORS origins not overridable by GitHub variables (prevent bypass)

### Changing Runtime Config

Update GitHub Environment variables (no code changes):

1. Settings → Environments → {environment} → Environment variables
2. Edit variable (e.g., `LOG_LEVEL=DEBUG`)
3. Re-run latest workflow or push new commit

Changes apply on next deployment.

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
- Terraform State Bucket (remote state for main module)
- GitHub Environments (dev/stage/prod/prod-apply in production mode)
- GitHub Environment Variables (auto-configured per environment)
- Tag Protection (production tag ruleset, prod bootstrap only)
- Cross-Project IAM (Artifact Registry reader for promotion, stage/prod)

**State management:** Local state (per environment)

**Runs:** Manually by infrastructure owners (one-time setup)

### Main Module

**Purpose:** Application deployment (runs in CI/CD)

**Location:** `terraform/main/`

**Resources created:**
- Cloud Run Service (containerized agent deployment)
- Service Account (IAM identity for Cloud Run)
- Vertex AI Agent Engine (session/memory persistence)
- GCS Bucket (artifact storage)

**State management:** Remote state in GCS (bucket created by bootstrap)

**Runs:** Automatically in GitHub Actions on merge/tag

**Inputs:** All via `TF_VAR_*` environment variables from GitHub

### Resource Naming

All resources named: `${var.agent_name}-${var.environment}`

**Examples:**
- Cloud Run service: `my-agent-dev`, `my-agent-stage`, `my-agent-prod`
- Artifact Registry: `my-agent-dev`, `my-agent-stage`, `my-agent-prod`
- Service account: `my-agent-dev@project.iam.gserviceaccount.com`

**Note:** Service account IDs truncate agent_name to 30 chars (GCP limit).

---

← [Back to References](README.md) | [Documentation](../README.md)
