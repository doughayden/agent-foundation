# Getting Started

First-time setup: from a fresh repository to an agent running locally, then deployed.

> [!NOTE]
> Bootstrap is a one-time setup per GitHub Environment. After the first deployment, use the feature branch workflow described in [Development](development.md).

## Prerequisites

**Required:**
- [tenv](https://github.com/tofuutils/tenv) to install Terraform at the version pinned in `.terraform-version` (run `tenv terraform install` from the repo root)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (gcloud CLI)
- [GitHub CLI](https://cli.github.com/) (gh)
- [uv](https://docs.astral.sh/uv/), within the `required-version` range in `pyproject.toml` (it installs the Python version in `.python-version`)
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

## Set Up the Project

### 1. Authenticate

Choose your dev project ID now. Use the same ID for `GOOGLE_CLOUD_PROJECT` in `.env` below, and for `projects.dev` in pre-bootstrap and `project` in the dev bootstrap configuration later.

```bash
gcloud auth login
gcloud config set project YOUR_DEV_PROJECT_ID
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_DEV_PROJECT_ID
gh auth login
```

ADC login can set the quota project automatically; the explicit command confirms the intended project. For quota and billing errors, see [Troubleshooting](troubleshooting.md#adc-quota-project-and-billing-errors).

### 2. Enable the APIs for a Local Run

The local agent calls Gemini through Vertex AI and exports traces and logs through the Telemetry API.

```bash
gcloud services enable aiplatform.googleapis.com telemetry.googleapis.com
```

### 3. Install and Test

```bash
uv sync                      # Create .venv with runtime and dev dependencies
uv run pre-commit install    # Run the CI quality checks on each commit
uv run pytest --cov          # Unit tests, 100% coverage required
```

### 4. Configure .env

```bash
cp .env.example .env
```

Set `GOOGLE_CLOUD_PROJECT` to your dev project ID. Leave the deployed-resource block commented out: with those URIs unset, the agent stores sessions and artifacts locally.

## Run the Agent Locally

```bash
SERVE_WEB_INTERFACE=TRUE uv run server
```

The web interface is at `http://localhost:8000`. Sessions persist in SQLite under `src/<package>/.adk/` (gitignored), so you can stop the server and return to a previous conversation, like with `adk web`. Memory is in-process only and resets on restart.

> [!TIP]
> Add `RELOAD_AGENTS=TRUE` to reload the agent when you edit files under `src/`, with no restart.

Local options and connecting to deployed resources: [Development](development.md).

## Bootstrap CI/CD

Bootstrap creates the one-time CI/CD infrastructure for the dev environment: keyless GitHub Actions authentication, the image registry, and the GitHub Environment and its variables. [Bootstrap Reference](references/bootstrap.md) lists every resource and covers production mode.

### 1. Create State Buckets (Pre-Bootstrap)

Pre-bootstrap creates the GCS state buckets used by bootstrap and the main module.

```bash
cp terraform/bootstrap/pre/terraform.tfvars.example terraform/bootstrap/pre/terraform.tfvars
# Edit terraform.tfvars: set agent_name and GCP project IDs

terraform -chdir=terraform/bootstrap/pre init
terraform -chdir=terraform/bootstrap/pre apply
```

See [Bootstrap Reference: Pre-Bootstrap](references/bootstrap.md#pre-bootstrap) for scope options (dev-only, full production, incremental) and how to skip pre-bootstrap if you already have a GCS bucket.

### 2. Configure

Dev-only mode (default): bootstrap only the dev environment.

```bash
cp terraform/bootstrap/dev/terraform.tfvars.example terraform/bootstrap/dev/terraform.tfvars
```

Fill in every value under the `REQUIRED` header in `terraform.tfvars`; the comments in the file describe each one. `agent_name` must match pre-bootstrap, and `terraform_state_bucket` comes from the pre-bootstrap `terraform_state_buckets` output.

> [!NOTE]
> For production mode (dev → stage → prod), see [Infrastructure](infrastructure.md).

### 3. Bootstrap

```bash
terraform -chdir=terraform/bootstrap/dev init \
  -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.dev')"
terraform -chdir=terraform/bootstrap/dev apply
```

Confirm the GitHub Environment variables exist:

```bash
gh variable list --env dev  # or GitHub repo Settings > Environments > dev
```

### 4. Set Up Claude PR Review

Opening a pull request triggers an automated Claude code review. It needs a one-time setup before the first PR: install the Claude GitHub App, then pick a model auth path, either Vertex AI in the dev project or a direct Anthropic credential. See [Claude PR Review](references/claude-pr-review.md).

## Deploy

Merging to `main` deploys the agent's infrastructure and Cloud Run service to dev. [Infrastructure: Terraform Structure](infrastructure.md#terraform-structure) lists what the main module creates.

### 1. Create Pull Request

```bash
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

The job summary lists the deployed resource values. You need them only to run a local agent against deployed resources ([Development: Connect to Deployed Resources](development.md#connect-to-deployed-resources)).

## Run the Deployed Agent

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
