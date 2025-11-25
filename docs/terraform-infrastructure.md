# Terraform Infrastructure Guide

This guide explains the Terraform infrastructure setup for deploying the ADK agent to Google Cloud Platform.

## Overview

The project uses **two Terraform modules** with distinct responsibilities:

- **`terraform/bootstrap/`** - One-time CI/CD infrastructure setup
  - Workload Identity Federation for GitHub Actions
  - Artifact Registry for Docker images
  - GCS bucket for main module's Terraform state
  - GitHub Actions Variables (auto-configured)
  - **State management:** Local state (default)

- **`terraform/main/`** - Application deployment (runs in CI/CD)
  - Cloud Run service configuration
  - Service account and IAM bindings
  - Vertex AI Reasoning Engine for session/memory persistence
  - GCS bucket for artifacts
  - **State management:** Remote state in GCS (bucket created by bootstrap)
  - **Execution:** Designed for GitHub Actions (local execution optional, see Advanced Usage)

## Prerequisites

### 1. Required Tools

- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.14.0
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (gcloud CLI)
- [GitHub CLI](https://cli.github.com/) (gh) - for GitHub Variables setup

### 2. GCP Authentication

Authenticate with Google Cloud:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 3. GitHub Authentication

Authenticate with GitHub (for bootstrap module to create Variables):

```bash
gh auth login
```

### 4. Environment Configuration

Create `.env` from `.env.example` and configure required variables:

```bash
cp .env.example .env
# Edit .env with your values
```

**Required variables:**
- `AGENT_NAME` - Your agent name (e.g., `adk-docker-uv`)
- `GOOGLE_CLOUD_PROJECT` - GCP project ID
- `GOOGLE_CLOUD_LOCATION` - GCP region (e.g., `us-central1`)
- `GITHUB_REPO_NAME` - Repository name
- `GITHUB_REPO_OWNER` - GitHub username or organization

## State Management

### Bootstrap Module - Local State

The bootstrap module uses **local state by default** because:
- Bootstrap is a one-time operation that creates CI/CD infrastructure
- Simpler setup (no chicken-egg problem with state buckets)
- Local state file can be committed to version control if desired
- Team collaboration can configure remote state if needed (see Advanced Usage)

**State location:** `terraform/bootstrap/terraform.tfstate` (gitignored by default)

### Main Module - Remote State in GCS

The main module uses **remote state in GCS** because:
- CI/CD requires shared state between workflow runs
- State locking prevents concurrent modification conflicts
- Versioning enables recovery from state corruption
- GitHub Actions has automatic access via WIF

**State bucket:** Created by bootstrap module, name follows pattern `terraform-state-{agent-name}-{random-suffix}`

**State location:** `gs://terraform-state-{agent-name}-{random-suffix}/main/`

## Bootstrap Module

### Purpose

Creates one-time infrastructure that supports automated CI/CD deployment. Run this module **once** from your local machine to set up the deployment pipeline.

### Resources Created

1. **Workload Identity Federation**
   - Pool: `{agent-name}-github`
   - Provider: GitHub OIDC with repository attribute condition
   - Direct principal binding (no service account impersonation)
   - IAM roles:
     - `roles/aiplatform.user` - Access Vertex AI models
     - `roles/artifactregistry.writer` - Push Docker images

2. **Artifact Registry**
   - Docker repository for container images
   - Cleanup policies:
     - Delete untagged images (intermediate layers)
     - Delete tagged images older than 30 days
     - **EXCEPT** keep 5 most recent versions (regardless of age)
     - **EXCEPT** keep `buildcache` tag indefinitely (critical for fast builds)

3. **GCS Bucket for Main Module State**
   - Name: `terraform-state-{agent-name}-{random-suffix}`
   - Location: `US`
   - Versioning enabled for state recovery
   - GitHub Actions granted `roles/storage.objectUser` access

4. **GitHub Actions Variables** (auto-configured)
   - `GCP_PROJECT_ID` - GCP project ID
   - `GCP_LOCATION` - GCP region
   - `IMAGE_NAME` - Docker image name (same as agent_name)
   - `GCP_WORKLOAD_IDENTITY_PROVIDER` - WIF provider name
   - `ARTIFACT_REGISTRY_URI` - Registry URI
   - `ARTIFACT_REGISTRY_LOCATION` - Registry location
   - `TERRAFORM_STATE_BUCKET` - GCS bucket name for main module

### Configuration

Bootstrap reads configuration from `.env` using the `dotenv` provider:

```hcl
# terraform/bootstrap uses dotenv provider
data "dotenv" "adk" {
  filename = "${path.cwd}/.env"
}
```

**Security:** Dotenv provider version `1.2.9` is pinned. See [Security: Dotenv Provider](#security-dotenv-provider) section below.

### Usage

#### Initialize

```bash
# Run from repository root using -chdir flag
terraform -chdir=terraform/bootstrap init
```

#### Plan and Apply

```bash
# Preview changes
terraform -chdir=terraform/bootstrap plan

# Apply changes (creates all CI/CD infrastructure)
terraform -chdir=terraform/bootstrap apply
```

Bootstrap typically completes in 2-3 minutes and outputs:
- Terraform state bucket name
- WIF provider name
- Registry URI
- List of GitHub Variables created

#### Verify GitHub Variables

```bash
# List all repository variables
gh variable list

# Expected output:
# ARTIFACT_REGISTRY_LOCATION     us-central1
# ARTIFACT_REGISTRY_URI          us-central1-docker.pkg.dev/...
# GCP_LOCATION                   us-central1
# GCP_PROJECT_ID                 your-project-id
# GCP_WORKLOAD_IDENTITY_PROVIDER projects/.../locations/global/...
# IMAGE_NAME                     adk-docker-uv
# TERRAFORM_STATE_BUCKET         terraform-state-adk-docker-uv-a1b2c3d4
```

### Security: Dotenv Provider

Bootstrap uses the `germanbrew/dotenv` provider for convenient `.env` file reading.

**Current version:** 1.2.9 (pinned)
**Registry:** https://registry.terraform.io/providers/germanbrew/dotenv/latest/docs
**Review date:** 2025-11-21

**Security assessment:**
- Provider source: `germanbrew/dotenv` from Terraform Registry
- Version 1.2.9 (exact pin, not range)
- Code review: Read-only file operations, no network calls
- Provenance: Official Terraform Registry
- Risk level: LOW (read-only local file access)
- Scope: Only bootstrap module (not main)

**Upgrade process:**
1. Review new version documentation on Terraform Registry
2. Check for security issues or unexpected changes
3. Update version pin in `terraform/bootstrap/terraform.tf`
4. Document review with date and findings
5. Test with sample .env file

**Why dotenv in bootstrap?**
- Convenience for one-time setup (no need to pass CLI variables)
- Local execution only (not in CI/CD)
- Alternative: Remove dotenv and use `TF_VAR_*` environment variables

## Main Module

### Purpose

Deploys the ADK agent application to Cloud Run. Designed to run in **GitHub Actions CI/CD** as part of the automated deployment pipeline.

**Execution model:**
- **Primary:** GitHub Actions (automated on merge to main)
- **Secondary:** Local execution possible for infrastructure-only changes (see Advanced Usage)

### Resources Created

1. **Service Account**
   - Attached to Cloud Run service
   - IAM roles:
     - `roles/aiplatform.user` - Access Vertex AI models
     - `roles/logging.logWriter` - Write logs
     - `roles/cloudtrace.agent` - Write traces
     - `roles/telemetry.tracesWriter` - Write telemetry
     - `roles/serviceusage.serviceUsageConsumer` - API usage
     - `roles/storage.bucketViewer` - List buckets in project
     - `roles/storage.objectUser` - Read/write objects in project buckets

2. **Vertex AI Reasoning Engine**
   - Session and memory persistence service
   - Display name: `Session and Memory: {agent-name}`
   - Resource ID passed to Cloud Run via `AGENT_ENGINE` env var

3. **GCS Bucket for Artifacts**
   - Name: `artifact-service-{agent-name}-{random-suffix}`
   - Location: `US`
   - Versioning enabled
   - Service account granted `roles/storage.objectUser` access

4. **Cloud Run Service**
   - HTTP/2 service on port 8000
   - Auto-scaling (0-100 instances)
   - Minimum instances: 0 (request-based billing)
   - Environment variables from Terraform variables (see Configuration below)
   - **Production safety:** `RELOAD_AGENTS` hardcoded to `FALSE`

### IAM and Permissions Model

**Project-level IAM assumption:**
This Terraform configuration assumes a dedicated GCP project per deployment. The app service account is granted project-level IAM roles that provide access to all resources within the project.

**App service account roles:**
- `roles/aiplatform.user` - Vertex AI API access
- `roles/cloudtrace.agent` - Cloud Trace write access
- `roles/logging.logWriter` - Cloud Logging write access
- `roles/serviceusage.serviceUsageConsumer` - Service usage tracking
- `roles/storage.bucketViewer` - List buckets in project
- `roles/storage.objectUser` - Read/write objects in project buckets
- `roles/telemetry.tracesWriter` - Telemetry traces write access

**Storage access:**
Project-level `storage.bucketViewer` and `storage.objectUser` roles grant access to all buckets **within the same project**. If you override `artifact_service_uri` to use an external bucket in a different project, you must configure cross-project IAM bindings separately.

**GitHub Actions WIF roles:**
See `terraform/bootstrap/main.tf` for the complete list of roles granted to GitHub Actions via Workload Identity Federation. Notable roles:
- `roles/iam.serviceAccountUser` - Required for Cloud Run to attach service accounts during deployment
- `roles/run.admin` - Create and update Cloud Run services
- `roles/storage.admin` - Manage GCS buckets and Terraform state

### Configuration

Main module receives **all inputs via Terraform variables**. No `.env` file reading.

**In GitHub Actions** (via `terraform-plan-apply.yml` workflow):
```yaml
env:
  TF_VAR_project: ${{ vars.GCP_PROJECT_ID }}
  TF_VAR_location: ${{ vars.GCP_LOCATION }}
  TF_VAR_agent_name: ${{ vars.IMAGE_NAME }}
  TF_VAR_terraform_state_bucket: ${{ vars.TERRAFORM_STATE_BUCKET }}
  TF_VAR_docker_image: ${{ inputs.docker_image }}
```

**Backend configuration** (bucket name):
```bash
# In GitHub Actions
terraform init -backend-config="bucket=${{ vars.TERRAFORM_STATE_BUCKET }}"
```

**Variable details:**
- **Required:** `project`, `location`, `agent_name`, `terraform_state_bucket`, `docker_image`
- **Optional with defaults:** `log_level` (INFO), `serve_web_interface` (false), `root_agent_model` (gemini-2.5-flash)
- **Nullable with defaults:** `agent_engine` (uses created resource), `artifact_service_uri` (uses created bucket)

### Terraform Variable Overrides

The main module accepts optional runtime configuration variables that can be set via GitHub Actions Variables.

**How it works:**
1. GitHub Actions Variables are set in the repository (e.g., `LOG_LEVEL=DEBUG`)
2. CI/CD workflow maps them to `TF_VAR_*` environment variables
3. Terraform uses `coalesce()` to fall back to defaults if null or empty

**Empty string handling:**
- GitHub Actions defaults unset Variables to empty strings (`""`)
- `coalesce(var.x, "default")` applies defaults when null or empty

**Available overrides:**
- `ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS` (default: TRUE)
- `AGENT_ENGINE` (default: auto-created Reasoning Engine)
- `ALLOW_ORIGINS` (default: `["http://127.0.0.1", "http://127.0.0.1:8000"]`)
- `ARTIFACT_SERVICE_URI` (default: auto-created GCS bucket)
- `LOG_LEVEL` (default: INFO)
- `ROOT_AGENT_MODEL` (default: gemini-2.5-flash)
- `SERVE_WEB_INTERFACE` (default: FALSE)

See `.github/workflows/terraform-plan-apply.yml` for the complete mapping.

### Usage in CI/CD

The main module runs automatically in GitHub Actions. See `.github/workflows/ci-cd.yml` and `.github/workflows/terraform-plan-apply.yml` for the complete workflow.

**On Pull Request:**
1. Build Docker image (tagged `pr-{number}-{sha}`)
2. Run `terraform plan` (no apply)
3. Post plan output as PR comment

**On Merge to Main:**
1. Build Docker image (tagged `{sha}`, `latest`, `{version}`)
2. Run `terraform apply` with auto-approval
3. Cloud Run service updated with new image
4. Service URL output in workflow logs

### Local Execution (Not Recommended)

The main module is designed for GitHub Actions execution. Local execution is possible but not supported. All Terraform inputs must be provided via `TF_VAR_*` environment variables, and the backend bucket must be configured via `-backend-config` flag.

**Note:** The `docker_image` variable is nullable and defaults to the previous deployment's image from remote state, allowing infrastructure-only updates without specifying an image URI.

## Workspace Management

Workspaces provide environment isolation (default, dev, stage, prod).

### Workspaces

**Bootstrap:** Uses `default` workspace (workspaces not recommended for local state).

**Main:** Uses workspaces for environment isolation in CI/CD (default/dev/stage/prod). Workspace selection happens automatically via the `--or-create` flag in workflows.

```bash
# List workspaces
terraform -chdir=terraform/main workspace list

# Create workspace (manual)
terraform -chdir=terraform/main workspace new stage
```

## Common Operations

### View Outputs

```bash
# Bootstrap outputs
terraform -chdir=terraform/bootstrap output
terraform -chdir=terraform/bootstrap output -raw terraform_state_bucket

# Main outputs
terraform -chdir=terraform/main output
terraform -chdir=terraform/main output -json cloud_run_services
```

### Update Bootstrap

```bash
# After modifying .env or bootstrap/*.tf
terraform -chdir=terraform/bootstrap plan
terraform -chdir=terraform/bootstrap apply
```

### Inspect State

```bash
# List resources in state
terraform -chdir=terraform/main state list

# Show specific resource
terraform -chdir=terraform/main state show google_vertex_ai_reasoning_engine.session_and_memory
```

## Troubleshooting

### Backend Initialization Fails

**Error:** `Backend configuration changed`

**Solution:** Reinitialize with `-reconfigure`:

```bash
terraform -chdir=terraform/main init -reconfigure \
  -backend-config="bucket=${STATE_BUCKET}"
```

### State Locking Errors

**Error:** `Error acquiring the state lock`

**Cause:** Previous Terraform operation didn't complete cleanly.

**Solution:** Force unlock (use with caution):

```bash
# Get lock ID from error message
terraform -chdir=terraform/main force-unlock LOCK_ID
```

### GitHub Variables Not Created

**Error:** Bootstrap completes but GitHub Variables missing.

**Cause:** GitHub CLI not authenticated or insufficient permissions.

**Solution:**

```bash
# Re-authenticate with full permissions
gh auth login

# Verify access
gh repo view OWNER/REPO

# Re-run bootstrap
terraform -chdir=terraform/bootstrap apply
```

### Wrong Variable Names in Workflows

**Error:** Workflow fails with "variable not found" or similar.

**Expected variable names** (set by bootstrap):
- `GCP_PROJECT_ID` (not `GOOGLE_CLOUD_PROJECT`)
- `GCP_LOCATION` (not `GOOGLE_CLOUD_LOCATION`)
- `IMAGE_NAME` (not `AGENT_NAME` - serves dual purpose)
- `TERRAFORM_STATE_BUCKET`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `ARTIFACT_REGISTRY_URI`
- `ARTIFACT_REGISTRY_LOCATION`

**Solution:** Verify variable names match bootstrap outputs:

```bash
gh variable list
```

### Workflow Fails with Missing Variables

**Error:** `var.terraform_state_bucket` not set (or similar).

**Cause:** Bootstrap didn't complete successfully or GitHub Variables weren't created.

**Solution:** Verify bootstrap completed and re-run if needed:

```bash
terraform -chdir=terraform/bootstrap apply
gh variable list
```

## CI/CD Integration

The Terraform modules are designed for GitHub Actions automation:

**Bootstrap → GitHub Variables → Workflows**

```
terraform/bootstrap
  ↓ (creates)
GitHub Variables (GCP_PROJECT_ID, TERRAFORM_STATE_BUCKET, etc.)
  ↓ (used by)
.github/workflows/terraform-plan-apply.yml
  ↓ (runs)
terraform/main (with TF_VAR_* from Variables)
```

**Key points:**
- GitHub Actions has WIF access (no service account keys)
- All Terraform inputs via `TF_VAR_*` environment variables
- Docker image passed directly from build workflow output
- State bucket access granted via bootstrap IAM bindings
- Workspace selection via `--or-create` flag (idempotent)

## Advanced Configuration

### Bootstrap with Remote State

The bootstrap module uses local state by default. Remote state via GCS backend is possible by creating a `backend.tf` file, but this is not the recommended or supported configuration for this template.

## Next Steps

1. ✅ Configure `.env` file
2. ✅ Run bootstrap module (creates CI/CD infrastructure)
3. ✅ Verify GitHub Variables created
4. 📖 See [CI/CD Workflow Guide](./cicd-setup.md) for automated deployment
5. 📖 See [Development Guide](./development.md) for local development

## Design Rationale

**Local state for bootstrap:**
- One-time operation that creates CI/CD infrastructure
- No chicken-egg problem (no state bucket needed to create state bucket)
- Simpler setup for template users

**TF_VAR_* in main module (no dotenv):**
- Standard Terraform pattern for CI/CD
- No `.env` file exposure in workflows
- Single execution environment to support

**Agent Engine in main (not bootstrap):**
- Lifecycle coupling with application deployment
- Environment isolation via workspaces
- No cross-module remote state dependencies

**Local development:** Optionally copy Agent Engine resource name to `.env` after first deployment for persistent sessions in local development.
