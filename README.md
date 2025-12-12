# agent-foundation

![CI/CD](https://github.com/doughayden/agent-foundation/actions/workflows/ci-cd.yml/badge.svg)
![Code Quality](https://github.com/doughayden/agent-foundation/actions/workflows/code-quality.yml/badge.svg)

Opinionated, production-ready LLM Agent deployment with enterprise-grade infrastructure

## What is this?

A comprehensive template for building and deploying LLM Agents, including those built using Google Agent Development Kit (ADK) to production. This is a complete, battle-tested foundation with automated CI/CD, managed state persistence, custom observability, and proven cloud infrastructure.

Built for teams who need to move beyond prototypes and ship production AI agents with confidence.

### How does this compare to Google's Agent Starter Pack?

Google's [Agent Starter Pack](https://googlecloudplatform.github.io/agent-starter-pack/) is a feature-rich framework with extensive tooling and multi-platform CI/CD options. `agent-foundation` takes a different approach:

- **Opinionated foundation**: Single optimized path (GitHub Actions + Terraform) vs choose-your-adventure configuration
- **Build optimization**: Multi-stage Docker purpose-built for `uv` with aggressive layer caching (~200MB, 5-10s rebuilds) vs generic catch-all patterns
- **Cloud Run deployment**: Production-grade container hosting with autoscaling vs preference for Agent Engine runtime
- **Low-level control**: Direct infrastructure management for teams who need flexibility and performance without the CLI abstraction

This project distills proven patterns from the Starter Pack while prioritizing build efficiency, deployment simplicity, and infrastructure transparency. Use the Starter Pack for rapid prototyping with Agent Engine; use `agent-foundation` for thoughtfully-curated developer experience and production deployments requiring optimization and control.

## Features

### ⚙️ Development & Build Optimization
- **Multi-platform builds**: AMD64 and ARM64 support for local testing consistency with production
- **Optimized Docker builds**: Multi-stage builds with uv package manager (~200MB images, 5-10s rebuilds)
- **Developer experience**: Hot reloading with Docker Compose watch mode for instant feedback
- **Code quality**: Strict type checking (mypy), comprehensive testing (100% coverage), modern linting (ruff)
- **Template-ready**: One-command initialization script for rapid project setup

### 🏗️ Production Infrastructure
- **Automated CI/CD**: GitHub Actions workflows with Terraform IaC, smart PR automation with plan comments
- **Automated code reviews**: Claude Code integration in CI for quality assurance
- **Cloud Run deployment**: Production-grade hosting with regional redundancy and autoscaling
- **Environment isolation**: Architecture supports workspace-based deployments (dev/stage/prod) - planned enhancement
- **Global scalability**: Clear path to multi-region deployments via external Application Load Balancer

### 🤖 Agent Capabilities
- **Managed sessions**: Vertex AI Reasoning Engine for durable conversation state and memory bank
- **Artifact storage**: GCS-backed persistent storage for session artifacts
- **Custom observability**: 🔭 OpenTelemetry instrumentation with full trace-log correlation in Cloud Trace and Cloud Logging

### 🔒 Security & Reliability
- **Workload Identity Federation**: Keyless authentication for CI/CD (no service account keys)
- **Non-root containers**: Security-hardened runtime with least privilege
- **Health checks**: Kubernetes-style probes with startup grace periods

## Getting Started

### Phase 1: Bootstrap CI/CD Infrastructure (One-Time)

Set up the foundation for automated deployments:

```bash
# 0. Initialize from template (if using as template)
uv run init_template.py  # Only if using as GitHub template; --dry-run to preview
git add -A && git commit -m "chore: initialize from template"

# 1. Configure app runtime environment
cp .env.example .env
# Edit .env: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, AGENT_NAME,
#       OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT

# 2. Configure bootstrap for GitHub
cp terraform/bootstrap/terraform.tfvars.example terraform/bootstrap/terraform.tfvars
# Edit terraform/bootstrap/terraform.tfvars: repository_owner, repository_name

# 3. Authenticate
gcloud auth application-default login
gh auth login

# 4. Provision CI/CD infrastructure
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap apply

# 5. Verify
gh variable list  # or view in GitHub repo Settings > Variables
```

Bootstrap creates: Workload Identity Federation, Artifact Registry, GCS state bucket, GitHub Variables.

See [Bootstrap Setup](docs/bootstrap-setup.md) for details and troubleshooting.

---

### Phase 2: Deploy Cloud Resources

> [!IMPORTANT]
> You must complete deployment first to create required resources (Reasoning Engine, GCS buckets) before running locally.

```bash
# 1. Create feature branch
git checkout -b feat/initial-setup

# 2. Commit and push
git add . && git commit -m "feat: initial agent setup"
git push origin feat/initial-setup

# 3. Create pull request
gh pr create  # or use GitHub UI

# 4. Review terraform plan in PR comments, then merge PR

# 5. Monitor deployment (merging to main triggers automatic deployment)
gh run list --workflow=ci-cd.yml --limit 5
gh run view --log
```

Deployment creates:
- Reasoning Engine for session persistence (`AGENT_ENGINE`)
- GCS bucket for artifact storage (`ARTIFACT_SERVICE_URI`)
- Cloud Run service

See [CI/CD Workflow](docs/cicd-setup.md) for automation details.

---

### Phase 3: Capture Deployed Resources

Get resource values from GitHub Actions logs (`gh run view <run-id>` or Actions tab UI) or GCP Console, then add to `.env`:

```bash
AGENT_ENGINE=projects/.../reasoningEngines/...
ARTIFACT_SERVICE_URI=gs://...
```

See [Environment Variables](docs/environment-variables.md) for where to find each value.

---

### Phase 4: Develop Locally

With deployment complete (from Phase 2) and resources captured (from Phase 3):

**Optional runtime configuration:** Set `SERVE_WEB_INTERFACE`, `LOG_LEVEL`, or other runtime variables in `.env` as needed.

Run the server:

```bash
# Run server (http://127.0.0.1:8000)
uv run server

# Or with Docker Compose (hot reloading)
docker compose up --build --watch
```

See [Development Guide](docs/development.md) for workflow, testing, and code quality standards.

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
