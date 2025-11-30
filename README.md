# adk-docker-uv

![CI/CD](https://github.com/doughayden/adk-docker-uv/actions/workflows/ci-cd.yml/badge.svg)
![Code Quality](https://github.com/doughayden/adk-docker-uv/actions/workflows/code-quality.yml/badge.svg)

ADK on Docker, optimized with uv

## What is this?

A production-ready template for deploying Google ADK (Agent Development Kit) agents using containerization best practices. This project demonstrates how to build efficient, type-safe ADK agents with modern Python tooling.

**Key features:**
- **Optimized Docker builds**: Multi-stage builds with uv package manager (~200MB images, 5-10s rebuilds)
- **Developer experience**: Hot reloading with Docker Compose watch mode for instant feedback
- **Code quality**: Strict type checking (mypy), comprehensive testing (100% coverage), modern linting (ruff)
- **Production ready**: Non-root containers, health checks, environment-based configuration

## Getting Started

### Phase 1: Setup (One-Time)

```bash
# 1. Initialize from template (if using as template)
uv run init_template.py  # Only if using as GitHub template; --dry-run to preview
git add -A && git commit -m "chore: initialize from template"

# 2. Configure environment
cp .env.example .env
# Edit: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, AGENT_NAME,
#       OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
#       GITHUB_REPO_NAME, GITHUB_REPO_OWNER

# 3. Authenticate
gcloud auth application-default login
gh auth login

# 4. Provision CI/CD infrastructure
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap apply

# 5. Verify
gh variable list  # or view in GitHub repo Settings > Variables
```

See [Bootstrap Setup](docs/bootstrap-setup.md) for details and troubleshooting.

### Phase 2: Develop Locally

```bash
uv run server
# Or: docker compose up --build --watch
```

See [Development Guide](docs/development.md) for workflow, testing, and code quality.

### Phase 3: Deploy to Cloud Run

```bash
git checkout -b feat/initial-setup
git add . && git commit -m "feat: initial agent setup"
git push origin feat/initial-setup
```

Open PR on GitHub. Merge to `main` triggers automatic deployment. Monitor:
```bash
gh run list --workflow=ci-cd.yml --limit 5
```

### Phase 4: Capture Deployed Resources (Optional)

For local development with persistent sessions, add to `.env`:
```bash
# Get values from: terraform -chdir=terraform/main output
AGENT_ENGINE=projects/PROJECT_ID/locations/LOCATION/reasoningEngines/ID
ARTIFACT_SERVICE_URI=gs://BUCKET_NAME
```

See [Environment Variables](docs/environment-variables.md) for details.

## Documentation

### Getting Started
- **[Bootstrap Setup](docs/bootstrap-setup.md)** - One-time CI/CD infrastructure provisioning
- **[CI/CD Workflow](docs/cicd-setup.md)** - GitHub Actions automation details
- **[Development](docs/development.md)** - Development workflow, code quality, testing
- **[Environment Variables](docs/environment-variables.md)** - Complete environment variable reference

### Infrastructure and Deployment
- **[Docker Compose Workflow](docs/docker-compose-workflow.md)** - Local development with hot reloading
- **[Dockerfile Strategy](docs/dockerfile-strategy.md)** - Multi-stage build architecture
- **[Terraform Infrastructure](docs/terraform-infrastructure.md)** - Bootstrap and main module setup

### Production Features
- **[Observability](docs/observability.md)** - OpenTelemetry traces and logs
- **[Validating Multi-Platform Builds](docs/validating-multiplatform-builds.md)** - Digest verification
