# Getting Started

First-time setup: from a fresh repository to a deployed agent you can run.

> [!NOTE]
> Bootstrap is a one-time setup per GitHub Environment. After the first deployment, use the feature branch workflow described in [Development](development.md).

## Prerequisites

**Required:**
- [tenv](https://github.com/tofuutils/tenv) to install Terraform at the version pinned in `.terraform-version` (run `tenv terraform install` from the repo root)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (gcloud CLI)
- [GitHub CLI](https://cli.github.com/) (gh)
- [uv](https://docs.astral.sh/uv/) (it installs the Python version in `.python-version`)
- `jq` command-line JSON processor (for parsing Terraform output)

> [!WARNING]
> Install Terraform through tenv, not on its own. CI installs exactly the version in `.terraform-version`, and a standalone `terraform` ignores that file, so your local version drifts from CI's and `terraform fmt` and plans can differ from what CI produces.

**GCP Project:**
- Create a new GCP project (or use existing)
- Enable billing
- Owner role

**GitHub Repository:**
- Create a new repository from this template
- Admin access (for GitHub Environments and Variables)

## Bootstrap CI/CD

Bootstrap creates the one-time CI/CD infrastructure for the dev environment: keyless GitHub Actions authentication, the image registry, and the GitHub Environment and its variables. [Bootstrap Reference](references/bootstrap.md) lists every resource and covers production mode.

### 1. Authenticate

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID  # Optional
gh auth login
```

### 2. Create State Buckets (Pre-Bootstrap)

Pre-bootstrap creates the GCS state buckets used by bootstrap and the main module.

```bash
cp terraform/bootstrap/pre/terraform.tfvars.example terraform/bootstrap/pre/terraform.tfvars
# Edit terraform.tfvars: set agent_name and GCP project IDs

terraform -chdir=terraform/bootstrap/pre init
terraform -chdir=terraform/bootstrap/pre apply
```

See [Bootstrap Reference: Pre-Bootstrap](references/bootstrap.md#pre-bootstrap) for scope options (dev-only, full production, incremental) and how to skip pre-bootstrap if you already have a GCS bucket.

### 3. Configure

Dev-only mode (default): bootstrap only the dev environment.

```bash
cp terraform/bootstrap/dev/terraform.tfvars.example terraform/bootstrap/dev/terraform.tfvars
```

Fill in every value under the `REQUIRED` header in `terraform.tfvars`; the comments in the file describe each one. `agent_name` must match pre-bootstrap, and `terraform_state_bucket` comes from the pre-bootstrap `terraform_state_buckets` output.

> [!NOTE]
> For production mode (dev → stage → prod), see [Infrastructure](infrastructure.md).

### 4. Bootstrap

```bash
terraform -chdir=terraform/bootstrap/dev init \
  -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.dev')"
terraform -chdir=terraform/bootstrap/dev apply
```

Confirm the GitHub Environment variables exist:

```bash
gh variable list --env dev  # or GitHub repo Settings > Environments > dev
```

### 5. Set Up Claude PR Review

Opening a pull request triggers an automated Claude code review. It needs a one-time setup before the first PR: install the Claude GitHub App, then pick a model auth path, either Vertex AI in the dev project or a direct Anthropic credential. See [Claude PR Review](references/claude-pr-review.md).

## Deploy

Merging to `main` deploys the agent's infrastructure and Cloud Run service to dev. [Infrastructure: Terraform Structure](infrastructure.md#terraform-structure) lists what the main module creates.

### 1. Create Pull Request

```bash
# Install the git hooks (one time; runs the CI quality checks on each commit)
uv run pre-commit install

git checkout -b feat/initial-setup
git add .
git commit -m "feat: initial setup"
git push origin feat/initial-setup
gh pr create --title "feat: initial setup" --body "Initial agent deployment"
```

### 2. Review and Merge

1. Review the Terraform plan in the PR comments
2. Merge the PR (triggers deployment to dev)

### 3. Monitor Deployment

```bash
gh run list --workflow=ci-cd.yml --limit 5
gh run view <run-id>         # Job summary: Cloud Run URL and resource URIs
gh run view <run-id> --log   # Full logs
```

Save the cloud resource values from the job summary for the next step.

## Run the Agent

### 1. Configure .env

```bash
cp .env.example .env
```

Add the values from the deployment job summary to `.env`, and enable the development web interface:

```bash
BASTION_INSTANCE=agent-name-dev-bastion
BASTION_ZONE=YOUR_ZONE
SESSION_SERVICE_URI=postgresql+asyncpg://YOUR_SERVICE_ACCOUNT@project.iam:@localhost:5432/agent_sessions
MEMORY_SERVICE_URI=agentengine://projects/YOUR_PROJECT_ID/locations/YOUR_LOCATION/reasoningEngines/YOUR_ENGINE_ID
ARTIFACT_SERVICE_URI=gs://YOUR_BUCKET_NAME
SERVE_WEB_INTERFACE=TRUE
# Add values for resources you customized for your agent
```

See [Environment Variables: Cloud Resources](environment-variables.md#cloud-resources) for where to find each value.

### 2. Run the Local Agent

Docker Compose mirrors production and connects to the deployed cloud resources:

```bash
docker compose up --build --watch
```

> [!IMPORTANT]
> Docker Compose requires `roles/iap.tunnelResourceAccessor` on your Google account for the IAP tunnel to the bastion host. Grant via GCP Console (IAM) or `gcloud projects add-iam-policy-binding`.

The web interface is at `http://localhost:8000`. To run without cloud resources (`uv run server`), see [Development](development.md).

### 3. Run the Remote Agent

Proxy the deployed Cloud Run service to your machine:

```bash
# Service name format: ${AGENT_NAME}-${environment} (like your-agent-dev)
gcloud run services proxy <service-name> --project <project-id> --region <region> --port 8000

# In another terminal
curl http://localhost:8000/health  # Expected: {"status": "ok"}
```

The deployed service serves the web interface only when enabled; see `TF_VAR_serve_web_interface` in [Environment Variables](environment-variables.md#runtime-configuration-overrides).

## Next Steps

- [Development](development.md): feature branch workflow, testing, and code quality
- [Infrastructure](infrastructure.md): deployment modes, pipeline behavior, and operations
- [Observability](observability.md): traces and logs in Cloud Trace and Cloud Logging, with query examples

---

← [Back to Documentation](README.md)
