# GitHub Docker Workflow Setup

This document describes the required GitHub secrets and variables for the Docker build and push workflow.

## Required GitHub Secrets

Configure these in your repository settings under **Settings > Secrets and variables > Actions > Secrets**:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `GCP_PROJECT_ID` | Google Cloud project ID | `your-project-id` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity Federation provider resource name | `projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |

## Required GitHub Variables

Configure these in your repository settings under **Settings > Secrets and variables > Actions > Variables**:

| Variable Name | Description | Example Value |
|---------------|-------------|---------------|
| `IMAGE_NAME` | Docker image name (without registry URL or tags) | `adk-docker-uv` |
| `ARTIFACT_REGISTRY_URL` | Full Artifact Registry repository URL (without image name) | `us-central1-docker.pkg.dev/your-project/docker-images` |
| `ARTIFACT_REGISTRY_LOCATION` | Artifact Registry location (region) | `us-central1` |

## Workflow Behavior

### Triggers
- **Automatic**: Runs on every push to `main` branch (after PR merges)
- **Manual**: Can be triggered via GitHub UI (Actions > Build > Run workflow)

### Multi-Platform Builds
The workflow builds images for multiple CPU architectures:
- **linux/amd64**: Standard x86_64 servers and cloud instances
- **linux/arm64**: ARM-based systems (Apple Silicon, ARM cloud instances)

Both platforms are built in a single workflow run and pushed as a multi-platform manifest.

### Image Tags
The workflow creates multiple tags for each build:

1. **`latest`**: Always points to the most recent build from main
2. **Git SHA**: Short commit hash (e.g., `a1b2c3d`) for traceability
3. **Semantic version**: If the commit is tagged (e.g., `v1.0.0`), adds version tag

### Example Output
For a commit tagged `v0.8.1` with SHA `f775f72`:
```
<location>-docker.pkg.dev/<project-id>/<repository>/<image-name>:latest
<location>-docker.pkg.dev/<project-id>/<repository>/<image-name>:f775f72
<location>-docker.pkg.dev/<project-id>/<repository>/<image-name>:v0.8.1
```

### Timeout Configuration
The workflow includes a 15-minute timeout to prevent indefinite hanging:
- **Typical runtime**: 5-10 minutes for multi-platform builds
- **Timeout**: 15 minutes provides buffer for slower builds or network issues
- **Purpose**: Prevents runaway workflows from consuming runner resources

All project workflows follow this pattern with timeouts appropriate to their complexity.

## GCP Prerequisites

Before running the workflow, ensure the following are configured in your GCP project:

1. **Artifact Registry repository** created
2. **Workload Identity Pool** configured for GitHub Actions
3. **Direct IAM binding** between GitHub repository and Artifact Registry with permissions:
   - `roles/artifactregistry.writer` on the Artifact Registry repository
   - Attribute mapping configured in Workload Identity Pool provider

## Testing the Workflow

### Manual Test
1. Go to **Actions** tab in GitHub
2. Select **Build** workflow
3. Click **Run workflow** dropdown
4. Select `main` branch
5. Click **Run workflow** button

### Verify Images
After workflow completes, verify images in GCP Console (replace placeholder values):
```bash
gcloud artifacts docker images list \
  <location>-docker.pkg.dev/<project-id>/<repository-name>
```

## Security Notes

- **GCP secrets** should be treated as highly sensitive
- **Registry URL** and **location** can be variables (not secrets) as they're not sensitive
- IAM bindings should follow principle of least privilege (only Artifact Registry write access)
- GitHub OIDC token provides secure, keyless authentication (no service account keys needed)
- Direct IAM binding is Google's latest recommended approach for GitHub Actions authentication
