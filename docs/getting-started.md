# Getting Started

First-time setup: from zero to deployed.

> [!NOTE]
> Bootstrap is a one-time setup per GitHub Environment. After successful bootstrap and first deployment, use the feature branch workflow described in [Development](development.md).

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
- Owner role

**GitHub Repository:**
- Create a new repository from this template
- Admin access (for GitHub Environments and Variables)

## Bootstrap CI/CD

Bootstrap creates the infrastructure for automated deployments:
- Workload Identity Federation for keyless GitHub Actions authentication
- Artifact Registry for Docker image storage with cleanup policies
- Terraform State Bucket for main module remote state (GCS)
- GitHub Environment and Variables for CI/CD

### 1. Configure

Dev-only mode (default): bootstrap only the dev environment.

```bash
cp terraform/bootstrap/dev/terraform.tfvars.example terraform/bootstrap/dev/terraform.tfvars
# Edit terraform.tfvars with your values
```

Required variables in `terraform/bootstrap/dev/terraform.tfvars`:
- `project` - GCP project ID for dev environment
- `location` - GCP region (e.g., `us-central1`)
- `agent_name` - Unique identifier (e.g., `my-agent`)
- `repository_owner` - GitHub username or organization
- `repository_name` - GitHub repository name

**Refer to `terraform.tfvars.example` for required variables you customized for your agent**

> [!NOTE]
> For production mode (dev → stage → prod), see [Infrastructure](infrastructure.md).

### 2. Authenticate

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID  # Optional
gh auth login
```

### 3. Bootstrap

```bash
# Initialize Terraform
terraform -chdir=terraform/bootstrap/dev init

# Preview and Approve to Apply
terraform -chdir=terraform/bootstrap/dev apply
```

### 4. Verify

```bash
# Check GitHub Variables
gh variable list --env dev  # or GitHub repo Settings > Environments > dev
```

See [Bootstrap Reference](references/bootstrap.md) for complete bootstrap setup instructions.

## Deploy

GitHub Actions deploy the agent resources:
- Agent Engine for session and memory persistence (`AGENT_ENGINE`)
- GCS bucket for artifact storage (`ARTIFACT_SERVICE_URI`)
- Cloud Run service (auto-configured with all resources)
- Service account with least-privilege IAM bindings
- Additional cloud resources you customized for your agent

### 1. Create Pull Request

```bash
# Create feature branch
git checkout -b feat/initial-setup

# Commit any initial customizations
git add .
git commit -m "feat: initial setup"

# Push branch
git push origin feat/initial-setup

# Create PR
gh pr create --title "feat: initial setup" --body "Initial agent deployment"
```

### 2. Review and Merge

1. Review the Terraform plan in the PR comments
2. Verify the planned infrastructure changes
3. Merge the PR (triggers deployment to dev environment)

### 3. Monitor Deployment

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

### 4. Get Deployment Info

```bash
# View job summary (includes Cloud Run URL, resource URIs)
gh run view <run-id>
```

Save cloud resource values from the job summary to use in the next step.

## Run the Agent

Configure your local `.env` with cloud resource values from the deployment, then run the agent.

### 1. Create .env File

```bash
cp .env.example .env
```

### 2. Add Cloud Resource Values for the Local Agent

Add the values from the deployment job summary to `.env`:

```bash
AGENT_ENGINE=projects/YOUR_PROJECT_ID/locations/YOUR_LOCATION/reasoningEngines/YOUR_ENGINE_ID
ARTIFACT_SERVICE_URI=gs://YOUR_BUCKET_NAME
# Add values for resources you customized for your agent
```

Enable the development web interface in your `.env`:

```bash
SERVE_WEB_INTERFACE=TRUE
```

See [Environment Variables: Cloud Resources](environment-variables.md#cloud-resources) for where to find each value and a complete configuration reference.

### 3. Run the Local Agent

```bash
# Authenticate with GCP (if not already done)
gcloud auth application-default login

# Run server (http://localhost:8000)
uv run server

# Or with Docker Compose (hot reloading, matches production)
docker compose up --build --watch
```

See [Development](development.md) for the full local development workflow including testing and code quality.

### 4. Run the Remote Agent

Authenticate to the deployed agent service using the Cloud Run proxy.

```bash
# Service name format: ${AGENT_NAME}-${environment} (e.g., agent-foundation-dev)
gcloud run services proxy <service-name> --project <project-id> --region <region> --port 8000

# In another terminal, test the health endpoint
curl http://localhost:8000/health

# Expected response: {"status": "ok"}

# Stop proxy: Ctrl+C
```

> [!TIP]
> ### Enable the deployed remote agent web interface (optional)
> 
> To access the same dev UI available locally, set `SERVE_WEB_INTERFACE=TRUE` in the `dev` GitHub Environment variables and re-deploy:
> 
> ```bash
> gh variable set SERVE_WEB_INTERFACE --env dev --body "TRUE"  # Or change in GitHub on the web
> ```
> 
> Then re-run the latest CI/CD workflow (Actions tab → CI/CD Pipeline → Re-run jobs).
>
> Once deployed, the web UI is available at `http://localhost:8000` via the proxy.

See [Cloud Run proxy documentation](https://cloud.google.com/run/docs/authenticating/developers#proxy) for details.

## Next Steps

**Local Development:**
- See [Development](development.md) for feature branch workflow, testing, and code quality

**Infrastructure & CI/CD:**
- See [Infrastructure](infrastructure.md) for deployment modes, pipeline behavior, and operations

**Observability:**
- View traces in [Cloud Trace](https://console.cloud.google.com/traces)
- View logs in [Logs Explorer](https://console.cloud.google.com/logs)
- See [Observability](observability.md) for query examples

---

← [Back to Documentation](README.md)
