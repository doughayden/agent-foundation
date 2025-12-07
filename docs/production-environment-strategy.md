# Production Environment Strategy

**Status:** Planning (Not Yet Implemented)

**Goal:** Design a flexible, production-ready multi-environment strategy that supports 2-4 environments (dev, staging, prod, and optional sandbox/qa) with proper isolation using separate GCP projects.

---

## Table of Contents

1. [Requirements & Constraints](#requirements--constraints)
2. [Core Architectural Decisions](#core-architectural-decisions)
3. [Bootstrap Strategy](#bootstrap-strategy)
4. [State Management](#state-management)
5. [Docker Image Strategy](#docker-image-strategy)
6. [GitHub Environments & Workflows](#github-environments--workflows)
7. [Environment Configuration](#environment-configuration)
8. [Deployment Flow](#deployment-flow)
9. [Security & IAM](#security--iam)
10. [Migration Path](#migration-path)
11. [Open Questions](#open-questions)

---

## Requirements & Constraints

### Given
- ✅ GitHub Pro + Enterprise (Environments available)
- ✅ Separate GCP project per environment (true isolation)
- ✅ Flexible environment count: minimum 2 (dev/prod), support 3-4 (dev/staging/prod, +sandbox/qa)
- ✅ Current infrastructure: Bootstrap + Main modules, WIF auth, Artifact Registry

### Desired Behavior
- **Dev environment:** Deploy on every PR (plan + apply) for fast feedback
- **Staging environment:** Deploy on merge to main (auto-apply) for integration testing
- **Prod environment:** Deploy after manual approval from DevOps lead
- **Optional environments:** Configurable (sandbox for experiments, QA for testing)

### Non-Negotiables
- No service account keys (WIF only)
- Terraform state in GCS (not local)
- Same tested artifact flows through all environments (no rebuilds)
- Environment-specific configuration (sizes, logging, features)

---

## Core Architectural Decisions

### Decision 1: Bootstrap Per Environment vs Shared Bootstrap

**Option A: Bootstrap once per environment** (Recommended)

```
terraform/bootstrap/
  ├── environments/
  │   ├── dev.tfvars
  │   ├── staging.tfvars
  │   └── prod.tfvars
  └── [terraform files]

# Run bootstrap for each environment
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap apply -var-file=environments/dev.tfvars
terraform -chdir=terraform/bootstrap apply -var-file=environments/staging.tfvars
terraform -chdir=terraform/bootstrap apply -var-file=environments/prod.tfvars
```

**Pros:**
- ✅ Clean separation (each environment has own WIF pool, registry, state bucket)
- ✅ Easy to add/remove environments
- ✅ No cross-environment dependencies
- ✅ Can use different GCP organizations if needed

**Cons:**
- ❌ More GCP resources (3x registries, 3x state buckets, 3x WIF pools)
- ❌ Need to sync bootstrap code across environments
- ❌ Higher costs (though minimal for bootstrap resources)

**Option B: Shared bootstrap with multi-environment support**

```
# One bootstrap creates resources for all environments
# Uses for_each to create env-specific resources
```

**Pros:**
- ✅ Single bootstrap run
- ✅ Lower resource count

**Cons:**
- ❌ Tight coupling between environments
- ❌ Complex Terraform (nested for_each, complex IAM)
- ❌ Harder to add/remove environments
- ❌ Single point of failure for all environments

**Recommendation:** **Option A** - Bootstrap per environment. Cleaner, safer, more flexible.

---

### Decision 2: Artifact Registry Strategy

**Option A: One registry per environment** (Recommended for isolation)

```
Dev:     us-central1-docker.pkg.dev/project-dev/docker-repo
Staging: us-central1-docker.pkg.dev/project-staging/docker-repo
Prod:    us-central1-docker.pkg.dev/project-prod/docker-repo
```

**Image promotion flow:**
1. Build in dev project → dev registry: `pr-123-abc1234`
2. Copy to staging registry: `abc1234`, `latest-staging`
3. Copy to prod registry: `abc1234`, `v0.3.0`, `latest`

**Pros:**
- ✅ True isolation (dev images can't accidentally reach prod)
- ✅ Each environment controls its own images
- ✅ Audit trail (can see exactly which images are in prod)
- ✅ Supports air-gapped prod environments
- ✅ Cleanup policies per environment (dev aggressive, prod conservative)

**Cons:**
- ❌ Storage duplication (same image stored 3x)
- ❌ Need image copying step in pipeline
- ❌ Slightly slower deployments (copy time)

**Option B: Shared registry with cross-project IAM**

```
Shared:  us-central1-docker.pkg.dev/shared-project/docker-repo

# Grant each environment's Cloud Run SA pull access
```

**Pros:**
- ✅ No duplication (single source of truth)
- ✅ Faster deployments (no copy step)
- ✅ Lower storage costs

**Cons:**
- ❌ Cross-project IAM complexity
- ❌ Shared failure domain (registry down = all envs down)
- ❌ Harder to enforce "prod-approved images only" policy
- ❌ Requires shared GCP project (against "separate projects" requirement)

**Recommendation:** **Option A** - One registry per environment. Aligns with "separate projects" requirement and provides true isolation. Storage costs are minimal compared to operational safety.

---

### Decision 3: State Management

**Option A: One state bucket per environment** (Recommended)

```
Dev:     gs://terraform-state-dev-a1b2c3/main/default.tfstate
Staging: gs://terraform-state-staging-d4e5f6/main/default.tfstate
Prod:    gs://terraform-state-prod-g7h8i9/main/default.tfstate
```

**Pros:**
- ✅ True isolation (dev state can't affect prod)
- ✅ Environment-specific locking (no cross-env conflicts)
- ✅ Easier access control (dev team can't read prod state)
- ✅ Supports separate GCP projects cleanly

**Cons:**
- ❌ Can't reference dev outputs from staging (but should you?)
- ❌ More buckets to manage

**Option B: Shared state bucket with workspaces**

```
Shared: gs://terraform-state-shared/main/env:/dev/default.tfstate
        gs://terraform-state-shared/main/env:/staging/default.tfstate
        gs://terraform-state-shared/main/env:/prod/default.tfstate
```

**Pros:**
- ✅ Single bucket
- ✅ Can use data.terraform_remote_state across environments

**Cons:**
- ❌ Shared failure domain
- ❌ Complex IAM (how to prevent dev from reading prod state?)
- ❌ Requires shared GCP project for state bucket
- ❌ Workspace locking might conflict

**Recommendation:** **Option A** - One state bucket per environment. Each bootstrap creates its own state bucket in the same project as the infrastructure.

**Note:** Current implementation uses data.terraform_remote_state to get previous deployment's image. With separate state buckets, this needs adjustment (see Decision 4).

---

### Decision 4: Handling `docker_image` Defaults

**Current behavior:** Main module uses `data.terraform_remote_state` to get previous deployment's image (main.tf:2-10, 41).

**Problem:** With separate state buckets per environment, can't reference previous state from same bucket.

**Option A: Remove recycling, require explicit image** (Recommended)

```hcl
# Remove data.terraform_remote_state from main.tf
# Always require docker_image input (no default)

variable "docker_image" {
  description = "Docker image URI to deploy"
  type        = string
  nullable    = false  # Changed from nullable = true
}
```

**Pros:**
- ✅ Explicit is better than implicit (know exactly what's deployed)
- ✅ Simpler Terraform (no remote state lookup)
- ✅ Forces CI/CD to pass image (prevents accidents)

**Cons:**
- ❌ Can't run `terraform apply` manually without image
- ❌ Loses "infrastructure-only updates" feature

**Option B: Store previous image in GCS metadata**

```hcl
# Create a separate "deployed_image.txt" file in state bucket
# Read it for default, write it on apply
```

**Pros:**
- ✅ Preserves recycling feature

**Cons:**
- ❌ Complex (need null_resource with local-exec)
- ❌ Race conditions possible
- ❌ Not worth the complexity

**Option C: Use Terraform outputs + workspace-aware remote state**

```hcl
# Even with separate buckets, could reference dev's state from staging
# But this creates coupling we don't want
```

**Recommendation:** **Option A** - Remove docker_image recycling. In production, you should always know exactly which image you're deploying. The current recycling feature is a development convenience that's not needed in proper CI/CD.

**Alternative:** Keep recycling but scope to same environment:
```hcl
# State file is in same bucket, just reference previous deployment in THIS environment
data "terraform_remote_state" "main" {
  backend   = "gcs"
  workspace = terraform.workspace  # Already does this
  config = {
    bucket = var.terraform_state_bucket
    prefix = "main"
  }
}
# This still works! Same bucket, same workspace
```

**Revised recommendation:** Keep current recycling logic. It works fine with separate buckets because each environment's state is self-contained.

---

### Decision 5: Terraform Workspace Usage

**Question:** Do we still need Terraform workspaces if each environment has a separate project and state bucket?

**Option A: Keep workspaces** (for future flexibility)

```
Project: project-dev
Bucket:  gs://terraform-state-dev-xxx/main/env:/dev/default.tfstate
                                           env:/sandbox/default.tfstate

Project: project-prod
Bucket:  gs://terraform-state-prod-yyy/main/env:/prod/default.tfstate
```

**Use case:** Dev project might have both `dev` and `sandbox` workspaces for feature branch testing.

**Option B: Remove workspaces** (simpler)

```
Project: project-dev
Bucket:  gs://terraform-state-dev-xxx/main/default.tfstate

Project: project-prod
Bucket:  gs://terraform-state-prod-yyy/main/default.tfstate
```

**Recommendation:** **Option A** - Keep workspaces. They provide flexibility for experimentation (e.g., `sandbox` workspace in dev project for testing changes) without adding complexity. Just use workspace name as part of resource prefixing.

**Resource naming:**
```hcl
locals {
  env = terraform.workspace
  resource_prefix = "${var.agent_name}-${local.env}"
}

# In dev project with sandbox workspace:
# Service: agent-foundation-sandbox
# In prod project with production workspace:
# Service: agent-foundation-production
```

---

## Bootstrap Strategy

### Bootstrap Module Structure

**Proposed organization:**

```
terraform/bootstrap/
├── main.tf                    # WIF, Artifact Registry, state bucket, GitHub Variables
├── variables.tf               # Parametrized inputs
├── outputs.tf                 # Output values for verification
├── providers.tf               # Google + GitHub providers
├── terraform.tf              # Terraform + provider versions
├── .terraform.lock.hcl       # Version lock file
├── README.md                 # Usage instructions
└── environments/             # Environment-specific configs
    ├── dev.tfvars
    ├── staging.tfvars
    ├── prod.tfvars
    └── sandbox.tfvars        # Optional
```

### Bootstrap Variables (Updated)

```hcl
# Required inputs (no .env, all via tfvars)
variable "environment" {
  description = "Environment name (dev, staging, prod, sandbox)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod", "sandbox"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod, sandbox"
  }
}

variable "project" {
  description = "GCP project ID for this environment"
  type        = string
}

variable "location" {
  description = "GCP location for regional resources"
  type        = string
  default     = "us-central1"
}

variable "agent_name" {
  description = "Agent name (base identifier)"
  type        = string
}

variable "github_repo_owner" {
  description = "GitHub repository owner"
  type        = string
}

variable "github_repo_name" {
  description = "GitHub repository name"
  type        = string
}

# Optional
variable "artifact_registry_location" {
  description = "Artifact Registry location (defaults to location)"
  type        = string
  default     = null
}
```

### Example tfvars Files

**environments/dev.tfvars:**
```hcl
environment        = "dev"
project           = "my-adk-dev"
location          = "us-central1"
agent_name        = "agent-foundation"
github_repo_owner = "my-org"
github_repo_name  = "agent-foundation"
```

**environments/staging.tfvars:**
```hcl
environment        = "staging"
project           = "my-adk-staging"
location          = "us-central1"
agent_name        = "agent-foundation"
github_repo_owner = "my-org"
github_repo_name  = "agent-foundation"
```

**environments/prod.tfvars:**
```hcl
environment        = "prod"
project           = "my-adk-prod"
location          = "us-central1"
agent_name        = "agent-foundation"
github_repo_owner = "my-org"
github_repo_name  = "agent-foundation"
```

### Bootstrap Resources (Per Environment)

Each bootstrap run creates:

1. **Workload Identity Pool** - `github-actions-{environment}` (one per environment)
2. **Workload Identity Provider** - Links to GitHub repo with attribute mapping
3. **Artifact Registry** - `{agent_name}-{environment}` (e.g., `agent-foundation-dev`)
4. **GCS State Bucket** - `terraform-state-{environment}-{random}` (auto-named)
5. **GitHub Environment** - Creates GitHub Environment with protection rules
6. **GitHub Environment Variables** - Scoped to the specific environment:
   - `GCP_PROJECT_ID`: `{project}`
   - `GCP_LOCATION`: `{location}`
   - `IMAGE_NAME`: `{agent_name}`
   - `ARTIFACT_REGISTRY_URI`: `{location}-docker.pkg.dev/{project}/{registry_name}`
   - `GCP_WORKLOAD_IDENTITY_PROVIDER`: `projects/{project_number}/locations/global/...`
   - `TERRAFORM_STATE_BUCKET`: `terraform-state-{environment}-xxx`

**Key change:** GitHub Variables become **environment-scoped** instead of repository-scoped.

### Bootstrap IAM Roles

Grant to GitHub Actions service account (via WIF):

```hcl
locals {
  github_sa_roles = toset([
    "roles/artifactregistry.writer",      # Push images
    "roles/storage.objectUser",          # Access state bucket
    "roles/iam.serviceAccountUser",      # Impersonate Cloud Run SA
    "roles/run.admin",                   # Deploy Cloud Run
    "roles/aiplatform.user",             # Create Agent Engine
  ])
}
```

**Question:** Should dev environment GitHub Actions have access to prod project? **No.** Each environment's WIF provider only grants access to that environment's project.

---

## State Management

### State Bucket Configuration

**Per environment:**

```hcl
resource "google_storage_bucket" "terraform_state" {
  project  = var.project
  name     = "terraform-state-${var.environment}-${random_id.suffix.hex}"
  location = var.location

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }
}
```

### Main Module Backend Configuration

**Updated workflow:** Pass backend config via environment variables:

```yaml
# In terraform-plan-apply.yml
- name: Terraform Init
  env:
    # These come from GitHub Environment variables
    TF_BACKEND_BUCKET: ${{ vars.TERRAFORM_STATE_BUCKET }}
  run: |
    terraform init -backend-config="bucket=${TF_BACKEND_BUCKET}"
```

**No hardcoded backend in main module** - stays flexible for any environment.

---

## Docker Image Strategy

### Image Tagging Convention

**Build tags (per environment registry):**

| Event | Environment | Tags | Example |
|-------|-------------|------|---------|
| PR | dev | `pr-{number}-{sha}` | `pr-123-abc1234` |
| Merge to main | staging | `{sha}`, `latest-staging` | `abc1234`, `latest-staging` |
| Manual approval | prod | `{sha}`, `v{version}`, `latest` | `abc1234`, `v0.3.0`, `latest` |

### Image Promotion Flow

**Option A: Build once, copy cross-registry** (Recommended)

```
1. PR opens → Build in dev registry
   Location: us-central1-docker.pkg.dev/project-dev/agent-foundation-dev:pr-123-abc1234

2. PR merges → Copy to staging registry + deploy
   Source:   project-dev/agent-foundation-dev:pr-123-abc1234
   Dest:     project-staging/agent-foundation-staging:abc1234
   Deploy:   staging Cloud Run ← abc1234

3. DevOps approves → Copy to prod registry + deploy
   Source:   project-staging/agent-foundation-staging:abc1234
   Dest:     project-prod/agent-foundation-prod:abc1234
   Also tag: v0.3.0, latest
   Deploy:   prod Cloud Run ← abc1234
```

**Pros:**
- ✅ Each environment has controlled image catalog
- ✅ Can verify image before promoting
- ✅ Audit trail (can see all prod images in prod registry)

**Cons:**
- ❌ Requires cross-project authentication for copy
- ❌ Copy step adds pipeline complexity

**Implementation:**

```yaml
# In ci-cd.yml (new job after build)
promote-to-staging:
  name: Promote Image to Staging
  needs: [build, deploy-dev]
  runs-on: ubuntu-latest
  steps:
    - name: Authenticate to Dev Project
      uses: google-github-actions/auth@v3
      with:
        project_id: ${{ vars.DEV_GCP_PROJECT_ID }}
        workload_identity_provider: ${{ vars.DEV_GCP_WORKLOAD_IDENTITY_PROVIDER }}

    - name: Copy Image to Staging Registry
      run: |
        gcloud container images add-tag \
          ${{ needs.build.outputs.image_uri }} \
          ${{ vars.STAGING_ARTIFACT_REGISTRY_URI }}/${{ vars.IMAGE_NAME }}:${GITHUB_SHA::7} \
          --quiet
```

**Wait, this won't work** - Need pull access to dev registry from staging workflow.

**Revised approach:**

```yaml
# Use crane (or gcloud) with explicit auth to both registries
- name: Authenticate to Dev (pull)
  uses: google-github-actions/auth@v3
  with:
    project_id: ${{ vars.DEV_GCP_PROJECT_ID }}
    workload_identity_provider: ${{ vars.DEV_WIF_PROVIDER }}

- name: Authenticate to Staging (push)
  uses: google-github-actions/auth@v3
  with:
    project_id: ${{ vars.STAGING_GCP_PROJECT_ID }}
    workload_identity_provider: ${{ vars.STAGING_WIF_PROVIDER }}

- name: Copy Image
  run: |
    # Configure docker for both registries
    gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

    # Pull from dev
    docker pull ${{ needs.build.outputs.image_uri }}

    # Tag for staging
    docker tag ${{ needs.build.outputs.image_uri }} \
      ${{ vars.STAGING_REGISTRY }}/${{ vars.IMAGE_NAME }}:${GITHUB_SHA::7}

    # Push to staging
    docker push ${{ vars.STAGING_REGISTRY }}/${{ vars.IMAGE_NAME }}:${GITHUB_SHA::7}
```

**Problem:** Multiple auth steps in one job might conflict.

**Better solution:** Use `gcloud container images add-tag` with impersonation, or grant staging WIF read access to dev registry.

**Simplest solution:** Grant staging's GitHub Actions WIF provider **read-only** access to dev's Artifact Registry:

```hcl
# In dev bootstrap:
resource "google_artifact_registry_repository_iam_member" "staging_pull" {
  repository = google_artifact_registry_repository.docker.name
  role       = "roles/artifactregistry.reader"
  member     = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/staging"
}
```

This allows staging workflow (running in staging environment) to pull from dev registry.

**Option B: Build in shared registry, reference from all environments**

Against "separate projects" requirement. Skip.

**Option C: Rebuild in each environment**

Against "same artifact" requirement (defeats testing). Skip.

**Recommendation:** **Option A** with cross-registry IAM. Grant staging environment read access to dev registry, prod environment read access to staging registry.

---

## GitHub Environments & Workflows

### GitHub Environments Configuration

**Create environments in GitHub repo settings:**

1. **dev**
   - Protection rules: None
   - Deployment branches: Any branch (for PR testing)
   - Variables: `GCP_PROJECT_ID`, `GCP_LOCATION`, `TERRAFORM_STATE_BUCKET`, etc.

2. **staging**
   - Protection rules: None (auto-deploy)
   - Deployment branches: `main` only
   - Variables: staging-specific values

3. **production**
   - Protection rules:
     - ✅ Required reviewers: DevOps lead
     - ✅ Wait timer: 0 minutes
   - Deployment branches: `main` only
   - Variables: prod-specific values

4. **sandbox** (optional)
   - Protection rules: None
   - Deployment branches: Any
   - Variables: sandbox-specific values

### Environment Variables (Per Environment)

Each GitHub Environment has these variables:

```
GCP_PROJECT_ID                    # e.g., "my-adk-dev"
GCP_LOCATION                      # e.g., "us-central1"
IMAGE_NAME                        # e.g., "agent-foundation"
ARTIFACT_REGISTRY_URI             # e.g., "us-central1-docker.pkg.dev/my-adk-dev/agent-foundation-dev"
GCP_WORKLOAD_IDENTITY_PROVIDER    # e.g., "projects/123/locations/global/..."
TERRAFORM_STATE_BUCKET            # e.g., "terraform-state-dev-a1b2c3"

# Optional environment-specific config
TF_VAR_log_level                  # DEBUG (dev), INFO (staging), WARNING (prod)
TF_VAR_serve_web_interface        # TRUE (dev), FALSE (prod)
TF_VAR_root_agent_model           # gemini-2.5-flash (dev), gemini-2.5-pro (prod)
```

### Workflow Structure

**Proposed:** Single orchestrator with environment-aware deployment jobs.

**ci-cd.yml (updated):**

```yaml
name: CI/CD Pipeline

on:
  pull_request:
    branches: [main]
    paths: [src/**, pyproject.toml, uv.lock, Dockerfile, terraform/main/**, .github/workflows/**]
  push:
    branches: [main]
    paths: [src/**, pyproject.toml, uv.lock, Dockerfile, terraform/main/**, .github/workflows/**]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        type: choice
        options: [dev, staging, production, sandbox]
      terraform_action:
        description: 'Terraform action'
        required: true
        type: choice
        options: [plan, apply]

jobs:
  # 1. Build image in dev registry (always)
  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    environment: dev  # Use dev environment for build
    outputs:
      image_uri: ${{ steps.build.outputs.image_uri }}
      image_digest: ${{ steps.build.outputs.digest }}
    steps:
      # Build and push to dev registry
      # ...

  # 2. Deploy to dev (on PR)
  deploy-dev:
    name: Deploy to Dev
    if: github.event_name == 'pull_request'
    needs: build
    uses: ./.github/workflows/deploy.yml
    with:
      environment: dev
      image_uri: ${{ needs.build.outputs.image_uri }}
      terraform_action: apply  # Auto-apply to dev
    secrets: inherit

  # 3. Promote and deploy to staging (on merge to main)
  deploy-staging:
    name: Deploy to Staging
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: build
    uses: ./.github/workflows/deploy.yml
    with:
      environment: staging
      source_image_uri: ${{ needs.build.outputs.image_uri }}  # Pull from dev
      terraform_action: apply
    secrets: inherit

  # 4. Promote and deploy to prod (manual approval required)
  deploy-production:
    name: Deploy to Production
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: [build, deploy-staging]  # Wait for staging
    uses: ./.github/workflows/deploy.yml
    with:
      environment: production
      source_image_uri: ${{ needs.deploy-staging.outputs.image_uri }}  # Pull from staging
      terraform_action: apply
    secrets: inherit
```

**New reusable workflow: deploy.yml**

```yaml
name: Deploy to Environment

on:
  workflow_call:
    inputs:
      environment:
        description: 'Target environment (dev, staging, production, sandbox)'
        required: true
        type: string
      image_uri:
        description: 'Image URI (if building fresh)'
        required: false
        type: string
      source_image_uri:
        description: 'Source image to promote (if copying)'
        required: false
        type: string
      terraform_action:
        description: 'Terraform action (plan or apply)'
        required: false
        type: string
        default: 'plan'

jobs:
  deploy:
    name: ${{ inputs.environment }}
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}  # References GitHub Environment
    outputs:
      image_uri: ${{ steps.image.outputs.uri }}

    steps:
      # 1. Determine image (use provided, or promote from source)
      - name: Resolve Image
        id: image
        run: |
          if [ -n "${{ inputs.image_uri }}" ]; then
            # Direct image (dev builds)
            IMAGE_URI="${{ inputs.image_uri }}"
          else
            # Promote from source (staging/prod)
            IMAGE_URI="${{ vars.ARTIFACT_REGISTRY_URI }}/${{ vars.IMAGE_NAME }}:${GITHUB_SHA::7}"
          fi
          echo "uri=${IMAGE_URI}" >> $GITHUB_OUTPUT

      # 2. If promoting, copy image from source registry
      - name: Promote Image
        if: inputs.source_image_uri != ''
        uses: google-github-actions/auth@v3
        with:
          project_id: ${{ vars.GCP_PROJECT_ID }}
          workload_identity_provider: ${{ vars.GCP_WORKLOAD_IDENTITY_PROVIDER }}
      - run: |
          gcloud auth configure-docker ${{ vars.GCP_LOCATION }}-docker.pkg.dev
          docker pull ${{ inputs.source_image_uri }}
          docker tag ${{ inputs.source_image_uri }} ${{ steps.image.outputs.uri }}
          docker push ${{ steps.image.outputs.uri }}

      # 3. Run Terraform
      - name: Terraform Deploy
        uses: ./.github/workflows/terraform-plan-apply.yml
        with:
          environment: ${{ inputs.environment }}
          docker_image: ${{ steps.image.outputs.uri }}
          terraform_action: ${{ inputs.terraform_action }}
```

**Key features:**
- ✅ Environment-aware (uses `environment: ${{ inputs.environment }}`)
- ✅ Auto-loads environment-specific variables
- ✅ Respects environment protection rules (prod requires approval)
- ✅ Supports both fresh builds (dev) and promotions (staging/prod)
- ✅ Flexible (can add/remove environments without changing workflow)

---

## Environment Configuration

### Size/Resource Differences

**Via environment-specific TF variables:**

```hcl
# In terraform/main/variables.tf, add environment-aware defaults:

variable "cloud_run_cpu" {
  description = "Cloud Run CPU limit"
  type        = string
  default     = "1"
}

variable "cloud_run_memory" {
  description = "Cloud Run memory limit"
  type        = string
  default     = "2Gi"
}

variable "cloud_run_min_instances" {
  description = "Minimum instance count"
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum instance count"
  type        = number
  default     = 100
}
```

**Set via GitHub Environment variables:**

```yaml
# Dev environment
TF_VAR_cloud_run_cpu: "1"
TF_VAR_cloud_run_memory: "2Gi"
TF_VAR_cloud_run_min_instances: 0
TF_VAR_cloud_run_max_instances: 10

# Prod environment
TF_VAR_cloud_run_cpu: "2"
TF_VAR_cloud_run_memory: "4Gi"
TF_VAR_cloud_run_min_instances: 1  # Avoid cold starts
TF_VAR_cloud_run_max_instances: 100
```

---

## Deployment Flow

### Pull Request Flow

```
1. Developer opens PR
   ↓
2. ci-cd.yml triggers (pull_request event)
   ↓
3. build job (environment: dev)
   - Authenticate to dev project via WIF
   - Build image
   - Push to dev registry: pr-123-abc1234
   ↓
4. deploy-dev job (environment: dev)
   - Run terraform plan + apply
   - Deploy to dev Cloud Run
   ↓
5. Developer tests at dev URL
   ↓
6. Developer merges PR (proceeds to Merge Flow)
```

### Merge to Main Flow

```
1. PR merges to main
   ↓
2. ci-cd.yml triggers (push event, ref = main)
   ↓
3. build job (environment: dev)
   - Build image
   - Push to dev registry: abc1234, latest-dev
   ↓
4. deploy-staging job (environment: staging)
   - Pull dev image: abc1234
   - Tag for staging registry: abc1234, latest-staging
   - Push to staging registry
   - Run terraform apply
   - Deploy to staging Cloud Run
   ↓
5. Automated tests run against staging (future: add test job)
   ↓
6. deploy-production job (environment: production)
   - **PAUSES for manual approval** (DevOps reviews)
   ↓
7. DevOps lead approves
   ↓
8. Continues:
   - Pull staging image: abc1234
   - Tag for prod registry: abc1234, v0.3.0, latest
   - Push to prod registry
   - Run terraform apply
   - Deploy to prod Cloud Run
   ↓
9. Production deployment complete
```

### Manual Dispatch Flow

```
1. DevOps triggers workflow_dispatch
   - Selects environment (dev/staging/production/sandbox)
   - Selects action (plan/apply)
   ↓
2. Workflow runs with selected parameters
   - Can run plan-only against prod for testing
   - Can deploy to sandbox for experiments
```

---

## Security & IAM

### Workload Identity Federation

**Per environment:** Separate WIF pool and provider.

**Dev WIF Provider:**
- Attribute condition: `assertion.repository == 'my-org/agent-foundation' && assertion.environment == 'dev'`
- Grants access to: dev project only
- IAM roles: artifactregistry.writer, run.admin, etc.

**Staging WIF Provider:**
- Attribute condition: `assertion.repository == 'my-org/agent-foundation' && assertion.environment == 'staging'`
- Grants access to: staging project only
- **Additional:** read access to dev Artifact Registry (for image promotion)

**Prod WIF Provider:**
- Attribute condition: `assertion.repository == 'my-org/agent-foundation' && assertion.environment == 'production'`
- Grants access to: prod project only
- **Additional:** read access to staging Artifact Registry (for image promotion)

**Key insight:** GitHub Environment name is included in OIDC token as `assertion.environment`, allowing WIF to verify which environment triggered the workflow.

### Cross-Registry Access

**Grant in dev bootstrap:**
```hcl
# Allow staging environment to pull from dev registry
resource "google_artifact_registry_repository_iam_member" "staging_reader" {
  project    = var.project  # dev project
  location   = var.artifact_registry_location
  repository = google_artifact_registry_repository.docker.name
  role       = "roles/artifactregistry.reader"
  member     = "principalSet://iam.googleapis.com/${var.staging_wif_pool_name}/attribute.environment/staging"
}
```

**Grant in staging bootstrap:**
```hcl
# Allow prod environment to pull from staging registry
resource "google_artifact_registry_repository_iam_member" "prod_reader" {
  project    = var.project  # staging project
  location   = var.artifact_registry_location
  repository = google_artifact_registry_repository.docker.name
  role       = "roles/artifactregistry.reader"
  member     = "principalSet://iam.googleapis.com/${var.prod_wif_pool_name}/attribute.environment/production"
}
```

**Problem:** This creates a dependency chain (dev bootstrap needs to know about staging WIF, staging needs to know about prod WIF).

**Solution:** Pass WIF pool names as variables to bootstrap:

```hcl
# In staging.tfvars
source_wif_pool = "projects/dev-project-number/locations/global/workloadIdentityPools/github-actions-dev"

# In staging bootstrap:
variable "source_wif_pool" {
  description = "Source WIF pool for image promotion (optional)"
  type        = string
  default     = null
}

resource "google_artifact_registry_repository_iam_member" "source_reader" {
  count = var.source_wif_pool != null ? 1 : 0
  # Grant this environment's registry read access to source WIF pool
  member = "principalSet://${var.source_wif_pool}/attribute.environment/${var.previous_environment}"
}
```

**Alternative simpler approach:** Run bootstrap in order (dev → staging → prod), and manually grant cross-registry access after each bootstrap. Not ideal, but works.

---

## Migration Path

### Phase 1: Prepare Bootstrap for Multi-Environment

**Goals:**
- Parametrize bootstrap module
- Remove .env dependency
- Add environment-specific tfvars
- Test with dev environment

**Tasks:**
1. Create `terraform/bootstrap/environments/` directory
2. Create `dev.tfvars`, `staging.tfvars`, `prod.tfvars`
3. Update bootstrap variables.tf (add `environment` variable, remove dotenv)
4. Update bootstrap main.tf (add environment prefixes to resources)
5. Update bootstrap outputs (include environment name)
6. Test: Run bootstrap for dev environment
7. Verify: GitHub Environment created, variables set

### Phase 2: Multi-Environment Bootstrap Execution

**Goals:**
- Bootstrap all environments (dev, staging, prod)
- Verify isolation

**Tasks:**
1. Run bootstrap for staging
2. Run bootstrap for prod
3. Verify separate WIF pools, registries, state buckets
4. Document WIF pool names for cross-registry access
5. Manually grant cross-registry IAM (dev → staging, staging → prod)

### Phase 3: Update Main Module

**Goals:**
- Remove environment assumptions
- Add resource prefixing
- Support environment-specific configuration

**Tasks:**
1. Update main.tf with `local.env` and `local.resource_prefix`
2. Prefix all resource names (SA, Cloud Run, Agent Engine, buckets)
3. Add environment-specific variables (CPU, memory, min instances)
4. Test: Deploy to dev workspace in dev project
5. Verify: Resources prefixed correctly

### Phase 4: Update CI/CD Workflows

**Goals:**
- Add environment-aware deployments
- Implement image promotion
- Add manual approval for prod

**Tasks:**
1. Create GitHub Environments (dev, staging, production)
2. Migrate Variables from repo-level to environment-level
3. Create new `deploy.yml` reusable workflow
4. Update `ci-cd.yml` with environment-aware jobs
5. Update `terraform-plan-apply.yml` to accept environment input
6. Add image promotion logic
7. Test: Open PR, verify dev deployment
8. Test: Merge PR, verify staging deployment (auto)
9. Test: Approve production deployment, verify prod deployment

### Phase 5: Production Hardening

**Goals:**
- Add monitoring and alerting
- Add deployment notifications
- Document runbooks

**Tasks:**
1. Add Slack/email notifications on deployment success/failure
2. Add terraform plan diff in PR comments (per environment)
3. Document rollback procedure
4. Add deployment status badges to README
5. Create runbook for common scenarios

---

## Open Questions

### 1. Image Promotion IAM

**Question:** How to grant cross-registry access cleanly without circular dependencies?

**Options:**
- A) Bootstrap runs in order, manual IAM grant after each
- B) Pass WIF pool names as variables
- C) Post-bootstrap script that grants all cross-registry access
- D) Don't copy images, use Artifact Registry mirroring (if available)

**Recommendation needed:** Which approach is cleanest?

### 2. Terraform Workspace Naming

**Question:** Workspace name = environment name, or allow flexibility?

**Option A:** Enforce workspace = environment
```yaml
with:
  workspace: ${{ inputs.environment }}  # dev, staging, production
```

**Option B:** Allow custom workspaces per environment
```yaml
# Could have "production" environment with "production-canary" workspace
```

**Recommendation:** Start with Option A (simple), allow Option B later if needed.

### 3. Version Tagging

**Question:** When/how to add semantic version tags (v0.3.0)?

**Option A:** Tag on git tag events
```yaml
on:
  push:
    tags: ['v*']
# Use git tag as image tag
```

**Option B:** Manual input during production deployment
```yaml
workflow_dispatch:
  inputs:
    version_tag:
      description: 'Semantic version (e.g., v0.3.0)'
```

**Option C:** Automatic based on CHANGELOG or commit messages

**Recommendation needed:** Which versioning strategy?

### 4. Rollback Strategy

**Question:** How to rollback a bad production deployment?

**Options:**
- A) Re-run workflow with previous image SHA
- B) Terraform state rollback (dangerous)
- C) Keep previous Cloud Run revision, use traffic splitting
- D) Redeploy previous git commit

**Recommendation needed:** Document preferred rollback procedure.

### 5. Cost Optimization

**Question:** With separate registries per environment, storage costs increase. Acceptable?

**Considerations:**
- Image sizes: ~200MB per image
- Dev: High churn (100+ images/month) → Aggressive cleanup (keep 5)
- Prod: Low churn (10 images/month) → Conservative cleanup (keep 50)
- Storage: $0.10/GB/month → Minimal cost impact

**Recommendation:** Accept cost for isolation benefits. Optimize cleanup policies per environment.

### 6. Staging Test Automation

**Question:** Should automated tests run in staging before promoting to prod?

**Ideal flow:**
```
Staging deploys → Automated tests run → If pass, allow prod deployment
```

**Recommendation needed:** What tests to run? How to block prod on test failure?

---

## Detailed Recommendations

This section provides in-depth analysis and rationale for each open question, with concrete implementation guidance.

### 1. Image Promotion IAM (Cross-Registry Access)

**Recommendation:** **Option B - Pass WIF pool names as variables** with bootstrap execution order enforcement.

**Rationale:**
- Maintains infrastructure-as-code principles (all IAM in Terraform)
- Explicit dependencies (clear in tfvars which environments depend on each other)
- Repeatable and auditable (no manual steps)
- Scales to N environments (not hardcoded)

**Implementation Details:**

```hcl
# In terraform/bootstrap/variables.tf
variable "upstream_environment" {
  description = "Upstream environment to pull images from (dev pulls from nowhere, staging from dev, prod from staging)"
  type = object({
    wif_pool_id = string  # Full WIF pool resource ID
    project     = string  # Project ID containing the upstream registry
    environment = string  # Environment name (for IAM member attribute)
  })
  default = null
}

# In terraform/bootstrap/main.tf
resource "google_artifact_registry_repository_iam_member" "upstream_pull" {
  count      = var.upstream_environment != null ? 1 : 0
  project    = var.upstream_environment.project
  location   = var.artifact_registry_location
  repository = "${var.agent_name}-${var.upstream_environment.environment}"
  role       = "roles/artifactregistry.reader"
  member     = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/${var.environment}"
}
```

**Example tfvars:**

```hcl
# environments/dev.tfvars
environment = "dev"
# No upstream_environment (dev is the source)

# environments/staging.tfvars
environment = "staging"
upstream_environment = {
  wif_pool_id = "projects/123456/locations/global/workloadIdentityPools/github-actions-dev"
  project     = "my-adk-dev"
  environment = "dev"
}

# environments/prod.tfvars
environment = "prod"
upstream_environment = {
  wif_pool_id = "projects/789012/locations/global/workloadIdentityPools/github-actions-staging"
  project     = "my-adk-staging"
  environment = "staging"
}
```

**Bootstrap Execution Order:**
1. Run dev bootstrap first (outputs WIF pool ID)
2. Copy dev WIF pool ID to staging.tfvars
3. Run staging bootstrap (grants itself read access to dev registry, outputs staging WIF pool ID)
4. Copy staging WIF pool ID to prod.tfvars
5. Run prod bootstrap (grants itself read access to staging registry)

**Tradeoffs:**
- ✅ Fully automated (no manual IAM grants)
- ✅ Self-documenting (tfvars show dependencies)
- ✅ Version controlled (dependencies tracked in git)
- ❌ Requires strict execution order (can't parallelize bootstraps)
- ❌ Need to manually copy WIF pool IDs between runs (mitigated by scripting)

**Alternative Considered (Option C - Post-Bootstrap Script):**
```bash
# Script: grant_cross_registry_access.sh
# Run once after all bootstraps complete
gcloud artifacts repositories add-iam-policy-binding \
  agent-foundation-dev \
  --project=my-adk-dev \
  --member="principalSet://...staging..." \
  --role=roles/artifactregistry.reader
```
Rejected because: Not infrastructure-as-code, manual, error-prone, not auditable.

---

### 2. Terraform Workspace Naming

**Recommendation:** **Option A - Strict workspace = environment** for initial implementation, with relaxation path documented.

**Rationale:**
- Simplicity: One-to-one mapping reduces cognitive load
- Safety: No confusion about which workspace maps to which environment
- Convention: Follows principle of least surprise
- Escape hatch: Can relax later without breaking anything

**Implementation:**

```yaml
# In deploy.yml
- name: Validate Workspace Matches Environment
  run: |
    EXPECTED="${{ inputs.environment }}"
    CURRENT=$(terraform workspace show)
    if [ "$CURRENT" != "$EXPECTED" ]; then
      echo "❌ ERROR: Workspace/environment mismatch"
      echo "   Environment: $EXPECTED"
      echo "   Workspace:   $CURRENT"
      echo "   For standard deployments, these must match."
      echo "   To use custom workspaces, set ALLOW_CUSTOM_WORKSPACE=true"
      exit 1
    fi
```

**Workspace Selection Logic:**

```yaml
# In terraform-plan-apply.yml
- name: Select Terraform Workspace
  run: |
    # Use environment name as workspace (strict mode)
    WORKSPACE="${{ inputs.environment }}"
    terraform workspace select "$WORKSPACE" || terraform workspace new "$WORKSPACE"
```

**Future Relaxation Path (when needed):**

If you later need blue/green deployments or canary testing:

```yaml
# Add optional workspace override
inputs:
  workspace:
    description: 'Terraform workspace (defaults to environment name)'
    required: false
    type: string
  environment:
    description: 'GitHub Environment (for variables and protection)'
    required: true
    type: string

# Use: environment=production, workspace=production-canary
```

**Tradeoffs:**
- ✅ Eliminates entire class of errors (deploying to wrong workspace)
- ✅ Clear mental model (dev environment → dev workspace → dev resources)
- ✅ Easier debugging (logs clearly show environment = workspace)
- ❌ Can't do blue/green within same environment (can add later)
- ❌ Can't have "staging-canary" workspace in staging environment (probably don't need this)

**Alternative Considered (Option B - Flexible from start):**
Allow custom workspaces from day one. Rejected because: Adds complexity before it's needed, violates YAGNI principle.

---

### 3. Version Tagging Strategy

**Recommendation:** **Option A - Git tag events** integrated with existing release workflow.

**Rationale:**
- Aligns with current release process (git-guru creates tags on main after release PR merge)
- Single source of truth (git tag → image tag → deployment)
- Immutable (git tags can't be moved without force-push)
- Traceable (clear lineage from code → tag → image → deployment)

**Implementation:**

```yaml
# In ci-cd.yml, add new trigger
on:
  push:
    tags: ['v*']
    branches: [main]
  # ... other triggers

jobs:
  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    environment: dev
    outputs:
      image_uri: ${{ steps.build.outputs.image_uri }}
      version_tag: ${{ steps.meta.outputs.version }}
    steps:
      - name: Extract Version
        id: meta
        run: |
          if [[ "${{ github.ref }}" == refs/tags/v* ]]; then
            # Tag push: v0.3.0
            VERSION="${GITHUB_REF#refs/tags/}"
            echo "version=${VERSION}" >> $GITHUB_OUTPUT
          else
            # Regular push: use SHA
            echo "version=" >> $GITHUB_OUTPUT
          fi

      - name: Build and Push
        run: |
          # Always tag with SHA (immutable reference)
          TAGS="${REGISTRY}/${IMAGE_NAME}:${GITHUB_SHA::7}"

          # Add version tag if available
          if [ -n "${{ steps.meta.outputs.version }}" ]; then
            TAGS="${TAGS},${REGISTRY}/${IMAGE_NAME}:${{ steps.meta.outputs.version }}"
          fi

          docker buildx build --push --tag ${TAGS} .

  # Production deployment only runs on tag pushes
  deploy-production:
    if: github.ref_type == 'tag' && startsWith(github.ref, 'refs/tags/v')
    needs: [build, deploy-staging]
    uses: ./.github/workflows/deploy.yml
    with:
      environment: production
      source_image_uri: ${{ needs.deploy-staging.outputs.image_uri }}
      version_tag: ${{ needs.build.outputs.version }}  # Pass version for tagging
```

**Integration with Release Workflow:**

Current process (from release-workflow.md):
1. User requests release → git-guru creates feature branch with version bump
2. PR merged → git-guru creates annotated tag on main (e.g., `v0.3.0`)
3. Tag pushed → **NEW: Triggers production deployment**

Updated flow:
```
1. Release PR merged to main
   ↓
2. git-guru creates and pushes tag: v0.3.0
   ↓
3. Tag push triggers ci-cd.yml
   ↓
4. Build job: Creates image with tags abc1234 + v0.3.0
   ↓
5. Deploy staging: Auto-deploys (no approval needed)
   ↓
6. Deploy production: Pauses for manual approval
   ↓
7. Approval granted: Deploys to prod with v0.3.0 tag
```

**Tradeoffs:**
- ✅ Integrates with existing release workflow (no new process)
- ✅ Semantic versions always correspond to production deployments
- ✅ Can easily find "what version is in prod?" (look at image tags)
- ✅ No manual version input (reduced human error)
- ❌ Can't deploy to prod without creating a git tag (this is a feature, not a bug)
- ❌ Requires discipline: tag only when ready for prod

**Alternative Considered (Option B - Manual Version Input):**
Require version input during production deployment. Rejected because: Adds manual step, prone to errors (typos, wrong version), disconnects git from deployments.

**Alternative Considered (Option C - Automatic from Commits):**
Parse conventional commits to auto-increment version. Rejected because: Complex, opinionated, current workflow already handles versioning.

---

### 4. Rollback Strategy

**Recommendation:** **Layered approach** with multiple rollback options depending on severity and timeline.

**Primary: Re-run Workflow with Previous Image SHA** (Fast, safe)

```yaml
# In GitHub UI: Actions → Deploy to Environment → Run workflow
Inputs:
  environment: production
  terraform_action: apply
  image_override: abc1234  # SHA from previous successful deployment

# Workflow modification to support image override:
- name: Resolve Image
  run: |
    if [ -n "${{ inputs.image_override }}" ]; then
      IMAGE_URI="${{ vars.ARTIFACT_REGISTRY_URI }}/${{ vars.IMAGE_NAME }}:${{ inputs.image_override }}"
    else
      # Normal flow: promote from upstream
      IMAGE_URI="..."
    fi
```

**Process:**
1. Identify issue in production
2. Find previous working deployment SHA (from Cloud Run console or git history)
3. Trigger workflow_dispatch with `image_override: <previous-sha>`
4. Terraform redeploys with previous image
5. Verify rollback successful

**Time to rollback:** 2-3 minutes (terraform apply time)

**Secondary: Cloud Run Traffic Splitting** (Instant, for gradual rollback)

```bash
# If Cloud Run keeps previous revisions (configure in main.tf):
resource "google_cloud_run_v2_service" "app" {
  # ...
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# Manual rollback via gcloud:
gcloud run services update-traffic agent-foundation-production \
  --to-revisions=PREVIOUS-REVISION=100 \
  --region=us-central1

# Or gradual:
gcloud run services update-traffic agent-foundation-production \
  --to-revisions=CURRENT=10,PREVIOUS=90 \
  --region=us-central1
```

**Process:**
1. Identify issue
2. List revisions: `gcloud run revisions list --service=agent-foundation-production`
3. Shift traffic to previous revision
4. Verify rollback
5. Later: Re-run workflow to make rollback permanent in Terraform state

**Time to rollback:** 30 seconds

**Tertiary: Redeploy Previous Git Commit** (Nuclear option)

```bash
# Checkout previous commit
git checkout <previous-working-commit>

# Manually trigger deployment
gh workflow run ci-cd.yml \
  --ref <previous-working-commit> \
  -f environment=production \
  -f terraform_action=apply
```

Only use if: Image is corrupted/deleted, or need to rollback code changes not in image (e.g., Terraform changes).

**Documentation to Add:**

Create `docs/runbook-rollback.md`:

```markdown
# Production Rollback Runbook

## Scenario 1: Bad Deployment (Image Issue)
**Time to resolve:** 2-3 minutes
**Risk level:** Low

1. Identify working version:
   - Check git history: `git log --oneline`
   - Or Cloud Run console: Previous revision SHA
2. Run workflow with override:
   - Actions → Deploy to Environment → Run workflow
   - Environment: production
   - Image override: <previous-sha>
3. Verify at production URL

## Scenario 2: Critical Issue (Need Instant Rollback)
**Time to resolve:** 30 seconds
**Risk level:** Medium (manual, not in Terraform)

1. List Cloud Run revisions:
   ```bash
   gcloud run revisions list --service=agent-foundation-production --region=us-central1
   ```
2. Shift traffic:
   ```bash
   gcloud run services update-traffic agent-foundation-production \
     --to-revisions=<PREVIOUS-REVISION>=100 \
     --region=us-central1
   ```
3. Follow up with workflow run to sync Terraform state

## Prevention
- Always test in staging first (automated)
- Require DevOps approval for production (GitHub Environment)
- Monitor production health checks
- Set up alerts for elevated error rates
```

**Tradeoffs:**
- ✅ Multiple options for different scenarios (flexibility)
- ✅ Primary method uses same CI/CD pipeline (consistent)
- ✅ Fast emergency option available (traffic splitting)
- ✅ All methods preserve audit trail
- ❌ Requires keeping previous Cloud Run revisions (small cost)
- ❌ Emergency rollback creates state drift (must reconcile with Terraform)

---

### 5. Cost Optimization

**Recommendation:** **Accept storage duplication** with environment-specific cleanup policies.

**Cost Analysis:**

```
Assumptions:
- Image size: 200MB
- Dev: 100 images/month, keep 5 recent → 1GB average storage
- Staging: 20 images/month, keep 10 recent → 2GB average storage
- Prod: 10 images/month, keep 50 recent → 10GB average storage
- Total: 13GB across all environments

Cost:
- Artifact Registry storage: $0.10/GB/month
- Monthly cost: 13GB × $0.10 = $1.30/month
- Annual cost: ~$16/year

Comparison:
- Single shared registry: 5GB (no duplication) = $0.50/month
- Savings: $0.80/month = $9.60/year
```

**Value Analysis:**

What you get for $10/year:
- ✅ True isolation (dev can't pollute prod)
- ✅ Separate access control (dev team can't access prod images)
- ✅ Environment-specific cleanup policies
- ✅ Audit trail (know exactly what's deployed where)
- ✅ Simplified RBAC (no cross-project IAM complexity)
- ✅ Blast radius reduction (dev registry issue doesn't affect prod)

**Cleanup Policies (Per Environment):**

```hcl
# In terraform/bootstrap/main.tf

# Dev registry: Aggressive cleanup
resource "google_artifact_registry_repository" "docker" {
  cleanup_policies {
    id     = "keep-recent-builds"
    action = "DELETE"
    condition {
      tag_state             = "TAGGED"
      tag_prefixes          = ["pr-"]
      older_than            = "2592000s"  # 30 days
    }
  }
  cleanup_policies {
    id     = "keep-minimum-images"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
}

# Prod registry: Conservative cleanup
resource "google_artifact_registry_repository" "docker" {
  cleanup_policies {
    id     = "keep-minimum-images"
    action = "KEEP"
    most_recent_versions {
      keep_count = 50
    }
  }
  cleanup_policies {
    id     = "delete-old-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "7776000s"  # 90 days
    }
  }
}
```

**Optimization Opportunities (If Needed Later):**

If costs become significant (unlikely):
1. **Compressed image layers:** Already optimized with multi-stage builds
2. **Shared base images:** Use Google's base image cache
3. **Lifecycle policies:** More aggressive cleanup in non-prod
4. **Image scanning:** Disable in dev, enable in prod only

**Recommendation:** Don't optimize prematurely. Monitor costs for 3 months, reassess if >$5/month.

**Tradeoffs:**
- ✅ Minimal cost ($16/year is negligible)
- ✅ Massive operational benefits
- ✅ Aligns with "separate projects" requirement
- ❌ Slightly higher storage costs (10-15GB vs 5GB)
- ❌ More registries to monitor (mitigated by GCP monitoring)

---

### 6. Staging Test Automation

**Recommendation:** **Phased approach** - Start with manual validation, add automated tests incrementally.

**Phase 1: Manual Validation (Immediate)**

```yaml
# In ci-cd.yml
deploy-staging:
  needs: [build]
  uses: ./.github/workflows/deploy.yml
  with:
    environment: staging
    terraform_action: apply
  # No automated tests yet, rely on DevOps manual testing

deploy-production:
  needs: [build, deploy-staging]
  uses: ./.github/workflows/deploy.yml
  with:
    environment: production
    terraform_action: apply
  # Manual approval gate allows time for staging validation
```

**Process:**
1. Staging deploys automatically on merge to main
2. GitHub Actions posts comment: "Staging deployed: https://staging-url"
3. DevOps validates staging manually (test API, check logs)
4. If good: Approve production deployment
5. If bad: Investigate, fix, redeploy

**Phase 2: Health Check Automation (Next)**

```yaml
# Add after deploy-staging
test-staging:
  name: Staging Health Checks
  needs: deploy-staging
  runs-on: ubuntu-latest
  steps:
    - name: Wait for Service Ready
      run: sleep 30  # Allow service to start

    - name: Health Check
      run: |
        STAGING_URL="${{ needs.deploy-staging.outputs.service_url }}"

        # Basic health endpoint
        curl -f "${STAGING_URL}/health" || exit 1

        # API smoke test
        curl -f "${STAGING_URL}/api/v1/status" || exit 1

    - name: Post Results
      if: always()
      uses: actions/github-script@v8
      with:
        script: |
          const result = '${{ job.status }}' === 'success' ? '✅ PASSED' : '❌ FAILED'
          github.rest.issues.createComment({
            issue_number: context.issue.number,
            owner: context.repo.owner,
            repo: context.repo.repo,
            body: `## Staging Health Checks ${result}\n\nService URL: ${{ needs.deploy-staging.outputs.service_url }}`
          })

# Block production if health checks fail
deploy-production:
  needs: [build, deploy-staging, test-staging]  # Added dependency
```

**Phase 3: Integration Tests (Future)**

```yaml
test-staging:
  name: Staging Integration Tests
  steps:
    - name: Checkout Test Suite
      uses: actions/checkout@v5

    - name: Run Integration Tests
      run: |
        # Example: pytest against staging
        export AGENT_URL="${{ needs.deploy-staging.outputs.service_url }}"
        uv run pytest tests/integration/ -v

    - name: Upload Test Results
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: staging-test-results
        path: test-results/
```

**Test Categories (Priority Order):**

1. **Health checks** (Phase 2)
   - `/health` endpoint returns 200
   - Service responds within 5 seconds
   - Basic dependency checks (DB, external APIs)

2. **Smoke tests** (Phase 2)
   - Critical user flows work end-to-end
   - Example: Send message → Get response
   - Authentication works

3. **Integration tests** (Phase 3)
   - Test interactions with GCP services
   - Verify Agent Engine connectivity
   - Check artifact storage

4. **Performance tests** (Phase 3, optional)
   - Response time < threshold
   - Memory usage within limits
   - No resource leaks

**Blocking vs Non-Blocking:**

```yaml
# Production deployment configuration
deploy-production:
  needs: [build, deploy-staging, test-staging]
  # If test-staging fails, deploy-production won't run (blocked)
  # DevOps can manually override by re-running workflow if false positive
```

**Tradeoffs:**
- ✅ Gradual adoption (add tests as you learn pain points)
- ✅ Fast initial implementation (no test suite required)
- ✅ Reduces production incidents (catches issues in staging)
- ✅ Automated safety net (no human error)
- ❌ Requires maintaining test suite (overhead)
- ❌ Can block legitimate deployments if tests are flaky
- ❌ Adds 2-5 minutes to deployment pipeline

**Recommendation:** Start with Phase 1, implement Phase 2 within first month, evaluate Phase 3 based on production incident rate.

---

## Summary

This strategy provides:
- ✅ True environment isolation (separate GCP projects)
- ✅ Flexibility (2-4 environments, easy to add/remove)
- ✅ Same artifact flows through all environments
- ✅ Manual approval gate for production
- ✅ Environment-specific configuration (sizes, logging, features)
- ✅ No service account keys (WIF only)
- ✅ Terraform state in GCS (per environment)

**Key architectural choices:**
- Separate bootstrap per environment (clean isolation)
- Separate Artifact Registry per environment (controlled catalog)
- Separate state bucket per environment (no cross-env dependencies)
- GitHub Environments for protection rules and variable scoping
- Image promotion via docker pull/tag/push (simple, works everywhere)
- Terraform workspaces for intra-environment flexibility

**Implementation complexity:**
- Medium (more complex than current single-env setup)
- High value (production-ready, scalable, safe)

**Next steps:**
1. Review this document, discuss open questions
2. Make architectural decisions on open items
3. Refine based on feedback
4. Begin Phase 1 implementation

---

## References

- [GitHub Environments Documentation](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Artifact Registry IAM](https://cloud.google.com/artifact-registry/docs/access-control)
- [Terraform Workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces)
- [GCS Backend Configuration](https://developer.hashicorp.com/terraform/language/backend/gcs)
