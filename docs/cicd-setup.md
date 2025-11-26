# CI/CD Workflow Guide

This guide explains the GitHub Actions workflows that automate building and deploying the ADK agent to Cloud Run.

## Overview

The project uses **automated CI/CD** via GitHub Actions with three reusable workflows:

1. **`ci-cd.yml`** - Orchestrator (meta → build → deploy)
2. **`docker-build.yml`** - Reusable Docker image build
3. **`terraform-plan-apply.yml`** - Reusable Terraform deployment

**Key principle:** Zero manual intervention after initial setup. Merge to main = automatic deployment.

## Prerequisites

Before workflows can run, you must complete the one-time bootstrap setup:

1. ✅ Run `terraform -chdir=terraform/bootstrap apply` (see [Terraform Infrastructure Guide](./terraform-infrastructure.md))
2. ✅ Verify GitHub Variables created: `gh variable list`

Bootstrap automatically creates all required GitHub Variables. **No manual configuration needed.**

## GitHub Variables (Auto-Created)

The bootstrap module creates these Variables in your repository:

| Variable Name | Description | Created By |
|---------------|-------------|------------|
| `GCP_PROJECT_ID` | GCP project ID | Bootstrap |
| `GCP_LOCATION` | GCP region | Bootstrap |
| `IMAGE_NAME` | Docker image name (also used as agent_name) | Bootstrap |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | WIF provider resource name | Bootstrap |
| `ARTIFACT_REGISTRY_URI` | Registry URI | Bootstrap |
| `ARTIFACT_REGISTRY_LOCATION` | Registry location | Bootstrap |
| `TERRAFORM_STATE_BUCKET` | GCS bucket for main module state | Bootstrap |

**Note:** These are Variables (not Secrets) because they're resource identifiers, not credentials. Security comes from WIF IAM policies, not obscurity.

## Workflow Architecture

### Three-Workflow Pattern

```
ci-cd.yml (orchestrator)
├── meta (job) - Extract metadata and determine tags
├── build (calls docker-build.yml) - Build multi-platform image
└── deploy (calls terraform-plan-apply.yml) - Deploy to Cloud Run
```

**Benefits:**
- Clean separation of concerns
- Reusable workflows can be triggered independently
- Direct output passing (no tag reconstruction)
- Single orchestrator controls the full pipeline

### Workflow Flow

**On Pull Request:**
```
1. meta job extracts: pr-{number}-{sha}
2. docker-build.yml pushes: registry/image:pr-123-abc123
3. terraform-plan-apply.yml runs: plan (no apply)
4. Plan output posted as PR comment
```

**On Merge to Main:**
```
1. meta job extracts: {sha}, latest, {version}
2. docker-build.yml pushes: registry/image:abc123 (+ latest + v1.0.0)
3. terraform-plan-apply.yml runs: apply (auto-approved)
4. Cloud Run service updated with SHA-tagged image
```

**On Manual Dispatch:**
```
1. meta job runs (uses current commit SHA)
2. docker-build.yml builds image
3. terraform-plan-apply.yml runs plan or apply (user choice)
4. Workspace selection: default/dev/stage/prod
```

## Image Tagging Strategy

### Pull Request Builds

**Tag format:** `pr-{number}-{sha}`

**Example:** `pr-123-abc1234`

**Purpose:**
- Unique per commit within PR
- Clearly indicates origin
- Isolated from main builds
- Can be used for preview environments

### Main Branch Builds

**Tags created:**
1. **`{sha-short}`** - Primary tag (immutable, traceable)
2. **`latest`** - Always points to most recent main build
3. **`{version}`** - Semantic version (if commit is tagged)

**Example:** Commit `abc1234` tagged `v0.9.0`
```
registry/image:abc1234
registry/image:latest
registry/image:v0.9.0
```

**Deployment uses SHA tag** for immutability and traceability.

**Deployment uses image digest** (not tags) to ensure every build triggers a Cloud Run revision deployment. When the same tag is rebuilt (e.g., base image security update, manual rebuild), the new digest ensures Terraform detects a change and deploys the updated image.

### Version Tag Builds

**Trigger:** Pushing a git tag matching `v*` pattern (e.g., `v0.4.0`)

**When this happens:**
1. Release PR merged to main (code already reviewed)
2. Tag created via `git tag v0.4.0 && git push origin v0.4.0`
3. **CI/CD workflow automatically triggers** on tag push
4. Builds Docker image with version tag: `registry/image:v0.4.0`

**Why automatic tag trigger is safe:**
- Tag creation happens AFTER release PR is merged (code already vetted through PR review)
- Tag is immutable pointer to already-reviewed code on main
- Standard industry practice for automated release workflows
- Security: Only authorized users can push tags (optional: enable GitHub tag protection rules)

**Workflow outputs:**
```
registry/image:abc1234     # SHA tag
registry/image:latest      # Latest tag
registry/image:v0.4.0      # Version tag
```

**Note:** The version-tagged image is built automatically when the tag is pushed. No manual workflow trigger needed.

## Workflow Behavior

### Concurrency Control

**ci-cd.yml:**
```yaml
concurrency:
  group: ci-cd-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

**Behavior:**
- **PRs:** New commits cancel in-progress builds (saves CI minutes)
- **Main branch:** Builds run sequentially to completion
- **Manual dispatch:** Runs to completion

**terraform-plan-apply.yml:**
```yaml
concurrency:
  group: terraform-deploy-${{ inputs.workspace }}
  cancel-in-progress: false
```

**Behavior:**
- Per-workspace locking prevents concurrent Terraform runs
- Multiple workspaces can run in parallel
- Prevents state corruption

### Path Filtering

Workflows trigger only on relevant changes:

```yaml
paths:
  - 'src/**'
  - 'pyproject.toml'
  - 'uv.lock'
  - 'Dockerfile'
  - '.dockerignore'
  - 'terraform/main/**'
  - '.github/workflows/ci-cd.yml'
  - '.github/workflows/docker-build.yml'
  - '.github/workflows/terraform-plan-apply.yml'
```

**Won't trigger on:**
- Documentation changes (*.md)
- Code quality workflow changes
- Bootstrap Terraform changes (one-time setup)

**Note:** Tag triggers (`tags: - 'v*'`) ignore path filters and always run the full workflow.

### Multi-Platform Builds

All images built for:
- **linux/amd64** - Standard x86_64 servers
- **linux/arm64** - ARM-based systems (Apple Silicon, ARM cloud)

Buildx creates a multi-platform manifest, so pulling `registry/image:tag` automatically selects the correct architecture.

### Build Cache Strategy

**Registry cache** with dedicated `buildcache` tag:

```yaml
cache-from: type=registry,ref=registry/image:buildcache
cache-to: type=registry,ref=registry/image:buildcache,mode=max
```

**Benefits:**
- Persists across workflow runs
- Shared between PR and main builds
- ~80% speedup on cache hits (5-10s vs 3-5 minutes)
- Protected by Artifact Registry cleanup policy (never deleted)

## Pull Request Comments

terraform-plan-apply.yml posts a comment on PRs with collapsible sections:

```
#### Terraform Format and Style 🖌 `success`
#### Terraform Initialization ⚙️ `success`
#### Terraform Validation 🤖 `success`
<details><summary>Validation Output</summary>
...
</details>

#### Terraform Plan 📖 `success`
<details><summary>Show Plan</summary>
```terraform
...
```
</details>

*Pushed by: @username, Action: `pull_request`*
```

**Success indicators:**
- ✅ `success` - Step passed
- ❌ `failure` - Step failed (workflow fails)

## Workload Identity Federation

Workflows use **keyless authentication** via WIF (no service account keys):

1. GitHub Actions requests OIDC token from GitHub
2. Token includes repository metadata (owner, repo, ref)
3. Google Cloud validates token against WIF provider
4. WIF provider grants permissions based on repository attribute condition
5. Workflow runs with temporary credentials

**IAM roles granted to GitHub Actions:**
- `roles/aiplatform.user` - Access Vertex AI models
- `roles/artifactregistry.writer` - Push Docker images
- `roles/storage.objectUser` - Access Terraform state bucket

## Testing Workflows

### Manual Trigger: Build Only

Test the build workflow independently:

```bash
# Via GitHub UI
Actions > Docker Build > Run workflow

# Via GitHub CLI
gh workflow run docker-build.yml \
  -f push=true \
  -f tags="us-central1-docker.pkg.dev/project/repo/image:test"
```

### Manual Trigger: Full Pipeline

Test the complete pipeline:

```bash
# Via GitHub UI
Actions > CI/CD Pipeline > Run workflow
  - Workspace: default
  - Terraform action: plan (or apply)

# Via GitHub CLI
gh workflow run ci-cd.yml \
  -f workspace=default \
  -f terraform_action=plan
```

### Manual Trigger: Terraform Only

Test deployment with existing image:

```bash
# Via GitHub UI
Actions > Terraform Plan and Apply > Run workflow
  - Docker image: us-central1-docker.pkg.dev/project/repo/image:abc1234
  - Workspace: default
  - Terraform action: plan

# Via GitHub CLI
gh workflow run terraform-plan-apply.yml \
  -f docker_image="us-central1-docker.pkg.dev/project/repo/image:abc1234" \
  -f workspace=default \
  -f terraform_action=plan
```

### Verify Deployment

After workflow completes:

```bash
# Check workflow run status
gh run list --workflow=ci-cd.yml --limit 5

# View specific run
gh run view RUN_ID

# Check deployed image in registry
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/PROJECT/REPO

# Check Cloud Run service
gcloud run services describe IMAGE_NAME \
  --region=us-central1 \
  --format="value(status.url)"
```

## Troubleshooting

### Tracing Deployed Image to Git Commit

Cloud Run deployments use image digests for reliability. To trace a deployed image back to its git commit:

**Step-by-step process:**

```bash
# 1. Get deployed digest from Cloud Run service
gcloud run services describe SERVICE_NAME \
  --region REGION \
  --format="value(spec.template.spec.containers[0].image)"

# Output: us-central1-docker.pkg.dev/.../adk-docker-uv@sha256:abc123...

# 2. Lookup tags in Artifact Registry using the digest
gcloud artifacts docker images describe "DIGEST_FROM_STEP_1" \
  --format="value(tags)"

# Output: d1dda49,latest,v0.4.0

# 3. Extract commit SHA (first tag is always the commit SHA)
```

**One-liner command:**

```bash
gcloud artifacts docker images describe \
  "$(gcloud run services describe adk-docker-uv --region us-central1 \
     --format='value(spec.template.spec.containers[0].image)')" \
  --format="value(tags)" | cut -d',' -f1
```

**How it works:**

1. Inner command gets the deployed image digest from Cloud Run
2. `gcloud artifacts docker images describe` looks up all tags for that digest
3. `cut -d',' -f1` extracts the first tag (always the commit SHA short hash)

**Example output:**

```
d1dda49
```

The commit SHA can then be used with `git show d1dda49` to view the deployed code.

### Workflow Fails: Missing Variables

**Error:** `var.GCP_PROJECT_ID` not found (or similar)

**Cause:** Bootstrap didn't complete successfully or Variables weren't created

**Solution:**
```bash
# Verify Variables exist
gh variable list

# If missing, re-run bootstrap
terraform -chdir=terraform/bootstrap apply
```

### Workflow Fails: WIF Authentication

**Error:** `Failed to authenticate to Google Cloud`

**Cause:** WIF provider not configured or IAM bindings incorrect

**Solution:**
```bash
# Check WIF provider exists
terraform -chdir=terraform/bootstrap output -raw workload_identity_provider

# Verify IAM bindings
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:principalSet*"
```

### Workflow Fails: Image Push

**Error:** `denied: Permission denied for resource`

**Cause:** GitHub Actions doesn't have `artifactregistry.writer` role

**Solution:**
```bash
# Check IAM binding on project
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.role:roles/artifactregistry.writer"

# Should show principalSet binding for your repository
```

### PR Comment Not Posted

**Error:** Plan runs but no PR comment appears

**Cause:** Insufficient permissions or workflow misconfiguration

**Solution:**
```yaml
# Verify workflow has PR write permission
permissions:
  pull-requests: write  # Required for PR comments
```

### Build Cache Miss

**Symptom:** Builds take 3-5 minutes instead of 5-10 seconds

**Cause:** Cache invalidated or buildcache tag deleted

**Solution:**
- Check Artifact Registry cleanup policies don't delete buildcache tag
- Verify `keep-buildcache` policy exists in bootstrap module
- First build after cache miss will repopulate cache

### Terraform State Lock

**Error:** `Error acquiring the state lock`

**Cause:** Previous workflow didn't complete cleanly

**Solution:**
```bash
# View recent workflow runs
gh run list --workflow=ci-cd.yml --limit 10

# Cancel stuck runs
gh run cancel RUN_ID

# Force unlock (last resort, use with caution)
# Get lock ID from workflow error logs, then:
terraform -chdir=terraform/main force-unlock LOCK_ID
```

## Workflow Timeouts

All workflows include timeouts to prevent runaway processes:

- **docker-build.yml:** 15 minutes (typical: 5-10 minutes)
- **terraform-plan-apply.yml:** Default (60 minutes)
- **ci-cd.yml:** No job-level timeout (controlled by child workflows)

If timeouts occur frequently, investigate:
- Network issues with Artifact Registry
- Large context being sent to Docker daemon
- Terraform state locking issues

## Security Best Practices

**Authentication:**
- ✅ Use WIF (keyless) - no service account keys
- ✅ Attribute conditions limit to specific repository
- ✅ Direct IAM bindings (no service account impersonation)

**Permissions:**
- ✅ Minimal IAM roles (only what's needed)
- ✅ Repository-scoped Variables (not organization-wide)
- ✅ Separate workspaces for environments (default/dev/stage/prod)

**State Management:**
- ✅ Remote state in GCS (encrypted at rest)
- ✅ Versioning enabled (state recovery)
- ✅ State locking prevents concurrent modifications

**Image Security:**
- ✅ Multi-platform manifests (no separate per-arch images)
- ✅ SHA tags for immutability and traceability
- ✅ Cleanup policies prevent unbounded storage growth

## Next Steps

1. ✅ Complete bootstrap setup (see [Terraform Infrastructure Guide](./terraform-infrastructure.md))
2. ✅ Verify GitHub Variables: `gh variable list`
3. ✅ Test workflow: Create PR, verify plan posted as comment
4. ✅ Merge PR, verify automatic deployment to Cloud Run
5. 📖 Monitor deployments: `gh run list --workflow=ci-cd.yml`

## Related Documentation

- [Terraform Infrastructure Guide](./terraform-infrastructure.md) - Bootstrap and main module setup
- [Development Guide](./development.md) - Local development workflow
