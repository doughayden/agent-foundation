# Bootstrap Setup Reference

Complete bootstrap instructions for dev-only and production modes, including cross-project IAM for image promotion.

## Overview

Bootstrap creates one-time CI/CD infrastructure per environment:

**Resources created:**
1. Workload Identity Federation - Keyless GitHub Actions authentication
2. Artifact Registry - Docker image storage with cleanup policies
3. GitHub Environments - dev/stage/prod/prod-apply (production mode)
4. GitHub Environment Variables - Auto-configured per environment
5. Tag Protection - Production tag ruleset (prod bootstrap only)
6. Cross-Project IAM - Artifact Registry reader for image promotion (stage/prod)

**State management:** Remote state in GCS per environment project using `bootstrap/` prefix (bucket created by pre-bootstrap)

**Location:** `terraform/bootstrap/{dev,stage,prod}/`

## Pre-Bootstrap

Pre-bootstrap creates GCS state buckets used by both bootstrap and the main module.

### State Bucket Options

**Option A — Use `terraform/bootstrap/pre` (recommended):** Creates buckets automatically and outputs their names. Enables the `jq`-based `terraform init` commands throughout this guide.

**Option B — Bring your own bucket:** Skip `terraform/bootstrap/pre` entirely. Pass an existing GCS bucket name directly to `-backend-config` when initializing each bootstrap environment:

```bash
# Replace the jq subshell with a literal bucket name
terraform -chdir=terraform/bootstrap/dev init -backend-config="bucket=your-existing-bucket-name"
```

Pre-bootstrap uses local state only (`terraform/bootstrap/pre/terraform.tfstate` — gitignored).

### Configure (Option A)

Define only the environments you plan to bootstrap — you can always add more later.

```bash
cp terraform/bootstrap/pre/terraform.tfvars.example terraform/bootstrap/pre/terraform.tfvars
```

`terraform/bootstrap/pre/terraform.tfvars`:

```hcl
agent_name = "your-agent-name"  # Must match agent_name in bootstrap tfvars

projects = {
  ### Always required
  dev = "your-project-dev"

  ### Optional, but must use stage + prod together (not one or the other)
  # stage = "your-project-stage"
  # prod  = "your-project-prod"
}
```

**Scope options:**
- **Dev-only:** Define only `dev` to start
- **Full production:** Define all three (`dev`, `stage`, `prod`) up front
- **Incremental:** Start with `dev` only; add `stage` and `prod` to `terraform.tfvars` and re-run `apply` before bootstrapping those environments — no impact on existing dev bucket

### Apply (Option A)

```bash
terraform -chdir=terraform/bootstrap/pre init
terraform -chdir=terraform/bootstrap/pre apply
```

### Note Outputs

```bash
terraform -chdir=terraform/bootstrap/pre output
```

The `terraform_state_buckets` output provides bucket names for:
- The `terraform_state_bucket` variable in each bootstrap environment's `terraform.tfvars`
- The `-backend-config` flag when running `terraform init` for each bootstrap environment

## Dev-Only Mode

Bootstrap only the dev environment.

### 1. Create Environment Config

```bash
cp terraform/bootstrap/dev/terraform.tfvars.example \
   terraform/bootstrap/dev/terraform.tfvars
```

### 2. Edit Configuration

`terraform/bootstrap/dev/terraform.tfvars`:

```hcl
# GCP Configuration
project                = "your-dev-project-id"
location               = "us-central1"
agent_name             = "your-agent-name"                      # MUST match pre-bootstrap agent_name
terraform_state_bucket = "terraform-state-your-agent-name-dev"  # From pre-bootstrap output

# Cross-project IAM (null for dev - no promotion source)
promotion_source_project                = null
promotion_source_artifact_registry_name = null

# GitHub Configuration
repository_owner = "your-github-username-or-org"
repository_name  = "your-agent-repository"

# Optional: adjust cleanup policies (defaults shown in .example file)
```

### 3. Bootstrap

**Option A - Using the bucket name created in pre-bootstrap:**
```bash
terraform -chdir=terraform/bootstrap/dev init \
  -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.dev')"
terraform -chdir=terraform/bootstrap/dev apply
```

**Option B - Using an existing bucket (skip pre-bootstrap):**
```bash
terraform -chdir=terraform/bootstrap/dev init \
  -backend-config="bucket=your-existing-bucket-name"
terraform -chdir=terraform/bootstrap/dev apply
```

> [!NOTE]
> Later examples only show `init` commands using `jq` parsing from pre-bootstrap but the same existing bucket option applies

### 4. Verify

**Check GitHub Variables:**
```bash
gh variable list --env dev
```

Expected variables: `GCP_PROJECT_ID`, `IMAGE_NAME`, `ARTIFACT_REGISTRY_URI`, `TERRAFORM_STATE_BUCKET`, `WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER`, etc.

**Check GitHub Environment:**
1. Go to Settings → Environments
2. Confirm `dev` environment exists
3. Click `dev` → check Environment variables populated

## Production Mode

Bootstrap all three environments sequentially (dev → stage → prod).

**Important:** Stage and prod require promotion source values from previous environment bootstrap outputs.

### 1. Create Config Files

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

### 2. Bootstrap Dev

**Edit `terraform/bootstrap/dev/terraform.tfvars`:**

```hcl
# GCP Configuration
project                = "your-dev-project-id"
location               = "us-central1"
agent_name             = "your-agent-name"                      # MUST match pre-bootstrap agent_name
terraform_state_bucket = "terraform-state-your-agent-name-dev"  # From pre-bootstrap output

# Cross-project IAM (null for dev - images built in dev, no promotion source)
promotion_source_project                = null
promotion_source_artifact_registry_name = null

# GitHub Configuration
repository_owner = "your-github-username-or-org"
repository_name  = "your-agent-repository"
```

**Bootstrap:**

```bash
terraform -chdir=terraform/bootstrap/dev init \
  -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.dev')"
terraform -chdir=terraform/bootstrap/dev apply
```

### 3. Get Dev Outputs for Stage

```bash
# Get dev project ID
DEV_PROJECT=$(terraform -chdir=terraform/bootstrap/dev output -raw project)

# Get dev registry name (format: {agent_name}-dev)
DEV_REGISTRY=$(terraform -chdir=terraform/bootstrap/dev output -raw artifact_registry_name)

echo "Dev project: $DEV_PROJECT"
echo "Dev registry: $DEV_REGISTRY"
```

### 4. Bootstrap Stage

**Edit `terraform/bootstrap/stage/terraform.tfvars`:**

```hcl
# GCP Configuration
project                = "your-stage-project-id"
location               = "us-central1"
agent_name             = "your-agent-name"                        # MUST match dev agent_name
terraform_state_bucket = "terraform-state-your-agent-name-stage"  # From pre-bootstrap output

# Cross-project IAM (use dev outputs from step 3)
promotion_source_project                = "your-dev-project-id"
promotion_source_artifact_registry_name = "your-agent-name-dev"

# GitHub Configuration
repository_owner = "your-github-username-or-org"
repository_name  = "your-agent-repository"
```

**Bootstrap:**

```bash
terraform -chdir=terraform/bootstrap/stage init \
  -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.stage')"
terraform -chdir=terraform/bootstrap/stage apply
```

### 5. Get Stage Outputs for Prod

```bash
# Get stage project ID
STAGE_PROJECT=$(terraform -chdir=terraform/bootstrap/stage output -raw project)

# Get stage registry name (format: {agent_name}-stage)
STAGE_REGISTRY=$(terraform -chdir=terraform/bootstrap/stage output -raw artifact_registry_name)

echo "Stage project: $STAGE_PROJECT"
echo "Stage registry: $STAGE_REGISTRY"
```

### 6. Bootstrap Prod

**Edit `terraform/bootstrap/prod/terraform.tfvars`:**

```hcl
# GCP Configuration
project                = "your-prod-project-id"
location               = "us-central1"
agent_name             = "your-agent-name"                       # MUST match dev/stage agent_name
terraform_state_bucket = "terraform-state-your-agent-name-prod"  # From pre-bootstrap output

# Cross-project IAM (use stage outputs from step 5)
promotion_source_project                = "your-stage-project-id"
promotion_source_artifact_registry_name = "your-agent-name-stage"

# GitHub Configuration
repository_owner = "your-github-username-or-org"
repository_name  = "your-agent-repository"
```

**Bootstrap:**

```bash
terraform -chdir=terraform/bootstrap/prod init \
  -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.prod')"
terraform -chdir=terraform/bootstrap/prod apply
```

### 7. Verify All Environments

**Check GitHub Environments:**
1. Settings → Environments
2. Confirm environments: `dev`, `stage`, `prod`, `prod-apply`

**Check Tag Protection:**
1. Settings → Rules → Rulesets
2. Confirm ruleset: **Production Release Tag Protection**
3. Check: Enforcement=Active, Target=Tags, Patterns=`refs/tags/v*`

**Check Environment Variables:**
1. Settings → Environments → click each (`dev`, `stage`, `prod`)
2. Environment variables tab → verify values populated

**Verify with CLI:**
```bash
# Check environments
gh api repos/:owner/:repo/environments | jq -r '.environments[].name'

# Check tag protection ruleset
gh api repos/:owner/:repo/rulesets | jq '.[] | {name, enforcement, target}'
```

### 8. Configure prod-apply Reviewers (REQUIRED)

1. Settings → Environments → prod-apply
2. Under **Environment protection rules**, check **Required reviewers**
3. Click **Add reviewers**
4. Search for and add users or teams who can approve production deployments
5. Click **Save protection rules**

See [Protection Strategies](protection-strategies.md) for detailed setup instructions.

## Important Notes

**Migrating Existing Local Bootstrap State:**
- If you bootstrapped before remote state was introduced, your existing state is local (`terraform/bootstrap/{env}/terraform.tfstate`)
- Pass `-migrate-state` to copy it to GCS during init (example shown for the `dev` environment):
  ```bash
  terraform -chdir=terraform/bootstrap/dev init \
    -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/pre output -json terraform_state_buckets | jq -r '.dev')" \
    -migrate-state
  ```
- Delete the local state file after successful migration

**Terraform State Bucket Names:**
- Each bootstrap environment requires its GCS bucket name in two places: `terraform.tfvars` (`terraform_state_bucket`) and the `-backend-config` flag on `terraform init`
- Record the `terraform_state_buckets` output after running pre-bootstrap — you need these names when bootstrapping each environment, including when adding environments incrementally later. If you've lost track, re-run `terraform -chdir=terraform/bootstrap/pre output` to retrieve them
- Bringing your own bucket: set it in `terraform.tfvars` and pass it directly to `-backend-config`; skip pre-bootstrap entirely

**Sequential Bootstrap:**
- Production mode requires bootstrapping in order: dev → stage → prod
- Stage needs dev outputs (promotion_source_project, promotion_source_artifact_registry_name)
- Prod needs stage outputs

**Agent Name Consistency:**
- `agent_name` MUST be identical across pre-bootstrap and all bootstrap environments
- Used in resource naming: `{agent_name}-{environment}`
- Example: `my-agent-dev`, `my-agent-stage`, `my-agent-prod`

**Different GCP Projects:**
- Use separate GCP projects for each environment (security and cost isolation)
- Example: `my-company-dev`, `my-company-stage`, `my-company-prod`

**Cross-Project IAM:**
- Grants read-only access for image promotion
- Registry-scoped (not project-level)
- Stage WIF principal → read dev registry
- Prod WIF principal → read stage registry

**GitHub Environments (Production Mode):**
- `dev`, `stage`, `prod` - Standard deployment environments
- `prod-apply` - Separate environment for approval gate (manual reviewers)

## Extending the Main Module

> [!WARNING]
> Bootstrap is frozen after initial setup. The services and IAM roles in `terraform/bootstrap/module/gcp/main.tf` are the minimum required to setup the CI/CD pipeline and are **NOT MANAGED** by any automation. Changes there will not be provisioned by GitHub Actions. Use `terraform/main/services.tf` and `terraform/main/iam.tf` instead.

Two extension points in `terraform/main/` exist for post-bootstrap customization. Only grant roles and enable services your agent strictly requires — prefer narrow, least-privilege, resource-scoped roles over broad project-level grants.

- **`services.tf`** — Enable additional GCP APIs
- **`iam.tf`** — Grant additional IAM roles to the GitHub Actions WIF principal so CI/CD can provision your agent's custom resources

Both use the same `for_each` + `triggers` pattern: one `time_sleep` instance per entry, created only when that entry is added. When the sets are empty (the default), no sleep resources are created and no delay occurs on apply.

> [!WARNING]
> Any resource that requires a newly-enabled service or role MUST declare `depends_on` on the corresponding `time_sleep` instance(s), or it may fail on the first apply before the service or binding has propagated.

### Adding GCP APIs (`services.tf`)

`google_project_service` is synchronous with respect to the Service Usage API, but some GCP services have async backend initialization after that confirmation (Artifact Registry is a known example). The `time_sleep.service_enablement_propagation` (120s) guards against this.

```hcl
# terraform/main/services.tf
locals {
  services = toset([
    "bigquery.googleapis.com",
    "pubsub.googleapis.com",
  ])
}
```

Then in any resource that requires the enabled API:

```hcl
resource "google_bigquery_dataset" "example" {
  # ...
  depends_on = [time_sleep.service_enablement_propagation["bigquery.googleapis.com"]]
}
```

If a resource requires multiple newly-enabled services:

```hcl
resource "google_pubsub_subscription" "example" {
  # ...
  depends_on = [
    time_sleep.service_enablement_propagation["bigquery.googleapis.com"],
    time_sleep.service_enablement_propagation["pubsub.googleapis.com"],
  ]
}
```

### Adding WIF Principal IAM Roles (`iam.tf`)

Adding a role to `wif_additional_roles` grants that role to the GitHub Actions WIF principal. Because GCP IAM propagation is eventually consistent, the template includes `time_sleep.wif_iam_propagation` (120s) to sequence role grants before dependent resource creation. One sleep instance is created per role — when `wif_additional_roles` is empty (the default), no sleep instances are created and no delay occurs.

```hcl
# terraform/main/iam.tf
locals {
  wif_additional_roles = toset([
    "roles/bigquery.admin",
  ])
}
```

Then in any resource that requires the new role:

```hcl
resource "google_bigquery_dataset" "example" {
  # ...
  depends_on = [time_sleep.wif_iam_propagation["roles/bigquery.admin"]]
}
```

If a resource requires multiple new roles, list each sleep instance explicitly — the resource will wait until all specified roles have propagated:

```hcl
resource "google_pubsub_subscription" "example" {
  # ...
  depends_on = [
    time_sleep.wif_iam_propagation["roles/bigquery.admin"],
    time_sleep.wif_iam_propagation["roles/pubsub.editor"],
  ]
}
```

### How the WIF Principal Identifier Flows

Bootstrap creates the WIF principal and exports it as a GitHub Environment Variable (`WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER`). The CI/CD workflow passes it to Terraform as `TF_VAR_workload_identity_pool_principal_identifier`, making it available in `iam.tf` as `var.workload_identity_pool_principal_identifier` — no hardcoding or bootstrap output look-up needed.

### Why Not Re-Run Bootstrap Instead?

An admin re-running bootstrap to add services and IAM roles reintroduces a human dependency into the CI/CD pipeline: every future customization requires admin availability and coordination. The extension point pattern scales — any developer can add services and roles through a normal PR, and CI/CD applies them automatically on merge.

## Bootstrap Outputs

**Key outputs (use for downstream configuration):**

```bash
# View all outputs
terraform -chdir=terraform/bootstrap/{env} output

# Specific outputs
terraform -chdir=terraform/bootstrap/dev output -raw project
terraform -chdir=terraform/bootstrap/dev output -raw artifact_registry_name
terraform -chdir=terraform/bootstrap/dev output -raw terraform_state_bucket
```

**Note:** `terraform_state_bucket` is an input to bootstrap (sourced from pre-bootstrap outputs via `terraform.tfvars`) that bootstrap passes through to GitHub Environment Variables. Bootstrap does not create this bucket — pre-bootstrap does.

**Use cases:**
- Promotion variables for next environment bootstrap
- Troubleshooting WIF authentication
- Verifying resource names

---

← [Back to References](README.md) | [Documentation](../README.md)
