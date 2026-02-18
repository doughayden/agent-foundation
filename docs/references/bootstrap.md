# Bootstrap Setup Reference

Complete bootstrap instructions for dev-only and production modes, including cross-project IAM for image promotion.

## Overview

Bootstrap creates one-time CI/CD infrastructure per environment:

**Resources created:**
1. Workload Identity Federation - Keyless GitHub Actions authentication
2. Artifact Registry - Docker image storage with cleanup policies
3. Terraform State Bucket - Remote state for main module (GCS)
4. GitHub Environments - dev/stage/prod/prod-apply (production mode)
5. GitHub Environment Variables - Auto-configured per environment
6. Tag Protection - Production tag ruleset (prod bootstrap only)
7. Cross-Project IAM - Artifact Registry reader for image promotion (stage/prod)

**State management:** Local state (per environment)

**Location:** `terraform/bootstrap/{dev,stage,prod}/`

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
project     = "your-dev-project-id"
location    = "us-central1"
agent_name  = "your-agent-name"

# Cross-project IAM (null for dev - no promotion source)
promotion_source_project                = null
promotion_source_artifact_registry_name = null

# GitHub Configuration
repository_owner = "your-github-org"
repository_name  = "your-repo"

# Optional: adjust cleanup policies (defaults shown in .example file)
```

### 3. Bootstrap

```bash
terraform -chdir=terraform/bootstrap/dev init
terraform -chdir=terraform/bootstrap/dev apply
```

### 4. Verify

**Check GitHub Variables:**
```bash
gh variable list
```

Expected variables: `GCP_PROJECT_ID`, `IMAGE_NAME`, `ARTIFACT_REGISTRY_URI`, `TERRAFORM_STATE_BUCKET`, etc.

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
project     = "your-dev-project-id"
location    = "us-central1"
agent_name  = "your-agent-name"

# Cross-project IAM (null for dev - images built in dev, no promotion source)
promotion_source_project                = null
promotion_source_artifact_registry_name = null

# GitHub Configuration
repository_owner = "your-github-org"
repository_name  = "your-repo"
```

**Bootstrap:**

```bash
terraform -chdir=terraform/bootstrap/dev init
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
project     = "your-stage-project-id"
location    = "us-central1"
agent_name  = "your-agent-name"  # MUST match dev agent_name

# Cross-project IAM (use dev outputs from step 3)
promotion_source_project                = "your-dev-project-id"
promotion_source_artifact_registry_name = "your-agent-name-dev"

# GitHub Configuration
repository_owner = "your-github-org"
repository_name  = "your-repo"
```

**Bootstrap:**

```bash
terraform -chdir=terraform/bootstrap/stage init
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
project     = "your-prod-project-id"
location    = "us-central1"
agent_name  = "your-agent-name"  # MUST match dev/stage agent_name

# Cross-project IAM (use stage outputs from step 5)
promotion_source_project                = "your-stage-project-id"
promotion_source_artifact_registry_name = "your-agent-name-stage"

# GitHub Configuration
repository_owner = "your-github-org"
repository_name  = "your-repo"
```

**Bootstrap:**

```bash
terraform -chdir=terraform/bootstrap/prod init
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

**Sequential Bootstrap:**
- Production mode requires bootstrapping in order: dev → stage → prod
- Stage needs dev outputs (promotion_source_project, promotion_source_artifact_registry_name)
- Prod needs stage outputs

**Agent Name Consistency:**
- `agent_name` MUST be identical across all environments
- Used in resource naming: `{agent_name}-{environment}`
- Example: `my-agent-dev`, `my-agent-stage`, `my-agent-prod`

**Different GCP Projects:**
- Use separate GCP projects for each environment (security isolation)
- Example: `my-company-dev`, `my-company-stage`, `my-company-prod`

**Cross-Project IAM:**
- Grants read-only access for image promotion
- Registry-scoped (not project-level)
- Stage WIF principal → read dev registry
- Prod WIF principal → read stage registry

**GitHub Environments (Production Mode):**
- `dev`, `stage`, `prod` - Standard deployment environments
- `prod-apply` - Separate environment for approval gate (manual reviewers)

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

**Use cases:**
- Promotion variables for next environment bootstrap
- Troubleshooting WIF authentication
- Verifying resource names

---

← [Back to References](README.md) | [Documentation](../README.md)
