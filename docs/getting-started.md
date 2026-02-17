# Getting Started

First-time setup: from zero to deployed.

> [!NOTE]
> This is a one-time setup. After successful bootstrap and first deployment, use the feature branch workflow described in [Development](development.md).

## Prerequisites

**Required:**
- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.14.0
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (gcloud CLI)
- [GitHub CLI](https://cli.github.com/) (gh)
- Python 3.13+
- `uv` package manager

**GCP Project:**
- Create a new GCP project (or use existing)
- Enable billing
- Owner or Editor role

**GitHub Repository:**
- Create a new repository from this template
- Admin access (for GitHub Variables and Environments)

## Bootstrap CI/CD

Bootstrap creates the infrastructure for automated deployments.

**What gets created:**
1. **Workload Identity Federation** - Keyless GitHub Actions authentication
2. **Artifact Registry** - Docker image storage with cleanup policies
3. **Terraform State Bucket** - Remote state for main module (GCS)
4. **GitHub Variables** - Auto-configured repository variables for CI/CD

### 1. Authenticate

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gh auth login
```

### 2. Configure Runtime Environment

```bash
cp .env.example .env
# Edit .env with your values (see inline comments)
```

Required variables in `.env`:
- `GOOGLE_CLOUD_PROJECT` - Your GCP project ID
- `GOOGLE_CLOUD_LOCATION` - GCP region (e.g., `us-central1`)
- `AGENT_NAME` - Unique identifier (e.g., `my-agent`)
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` - `TRUE` or `FALSE`

See [Environment Variables](environment-variables.md) for complete reference.

### 3. Configure Bootstrap

Dev-only mode (default): bootstrap only the dev environment.

```bash
cp terraform/bootstrap/dev/terraform.tfvars.example terraform/bootstrap/dev/terraform.tfvars
# Edit terraform.tfvars with your values
```

Required variables in `terraform/bootstrap/dev/terraform.tfvars`:
- `project` - GCP project ID for dev environment
- `location` - GCP region (e.g., `us-central1`)
- `agent_name` - Unique identifier (same value from `.env`)
- `repository_owner` - GitHub username or organization
- `repository_name` - GitHub repository name

**Note:** For production mode (dev → stage → prod), see [Deployment](deployment.md).

### 4. Run Bootstrap

```bash
# Initialize Terraform
terraform -chdir=terraform/bootstrap/dev init

# Preview changes
terraform -chdir=terraform/bootstrap/dev plan

# Apply (typically completes in 2-3 minutes)
terraform -chdir=terraform/bootstrap/dev apply
```

### 5. Verify Bootstrap

```bash
# Check GitHub Variables
gh variable list
```

Expected output:
- `ARTIFACT_REGISTRY_LOCATION`
- `ARTIFACT_REGISTRY_URI`
- `GCP_LOCATION`
- `GCP_PROJECT_ID`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `IMAGE_NAME`
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`
- `TERRAFORM_STATE_BUCKET`

## First Deployment

Deploy the agent to Cloud Run using GitHub Actions.

### 1. Push to Main

```bash
# Commit any initial customizations
git add .
git commit -m "feat: initial setup"

# Push to main (triggers deployment)
git push origin main
```

### 2. Monitor Deployment

```bash
# View workflow runs
gh run list --workflow=ci-cd.yml --limit 5

# Watch logs (use run ID from list)
gh run view <run-id> --log

# Or: view in browser
gh run view <run-id> --web
```

Deployment flow:
1. Build Docker image
2. Run Terraform plan (infrastructure changes)
3. Deploy to Cloud Run (default environment)
4. Report outputs in job summary

### 3. Get Deployment Info

```bash
# View job summary (includes Cloud Run URL, resource URIs)
gh run view <run-id>
```

Save these values from the job summary:
- **AGENT_ENGINE** - Agent Engine resource name (for local `.env`)
- **ARTIFACT_SERVICE_URI** - GCS bucket URI (for local `.env`)

## Verify Deployment

Test the deployed agent using Cloud Run proxy (handles authentication automatically).

```bash
# Service name format: ${agent_name}-dev (or ${agent_name}-default for single env)
# Get service name, project, and region from deployment summary
gcloud run services proxy <service-name> \
  --project <project-id> \
  --region <region> \
  --port 8000

# In another terminal, test the health endpoint
curl http://localhost:8000/health

# Expected response: {"status": "ok"}

# Stop proxy: Ctrl+C
```

**Why use proxy?** Cloud Run services enforce authentication. The proxy handles auth automatically using your gcloud credentials.

See [Cloud Run proxy documentation](https://cloud.google.com/run/docs/authenticating/developers#proxy) for details.

## Next Steps

**Local Development:**
1. Update `.env` with AGENT_ENGINE and ARTIFACT_SERVICE_URI from deployment
2. See [Development](development.md) for feature branch workflow

**Multi-Environment:**
- Default: Dev-only mode (deploys to default environment on merge to main)
- Optional: Enable production mode for dev → stage → prod workflow
- See [Deployment](deployment.md) for multi-environment strategy

**Observability:**
- View traces in [Cloud Trace](https://console.cloud.google.com/traces)
- View logs in [Logs Explorer](https://console.cloud.google.com/logs)
- See [Observability](observability.md) for query examples

**CI/CD:**
- Understand GitHub Actions workflows
- Customize deployment triggers
- See [CI/CD](cicd.md) for workflow reference
