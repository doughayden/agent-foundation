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
- **Optimized Docker builds**: Multi-stage builds with uv package manager (~200MB images, 5-10s rebuilds)
- **Developer experience**: Hot reloading with Docker Compose watch mode for instant feedback
- **Code quality**: Strict type checking (mypy), comprehensive testing (100% coverage), modern linting (ruff)
- **Template-ready**: One-command initialization script for rapid project setup

### 🏗️ Production Infrastructure
- **Automated CI/CD**: GitHub Actions workflows with Terraform IaC, smart PR automation with plan comments
- **Automated code reviews**: Claude Code integration in CI for quality assurance
- **Cloud Run deployment**: Production-grade hosting with regional redundancy and autoscaling
- **Environment isolation**: Production-grade multi-environment deployments (dev/stage/prod)
- **Global scalability**: Clear path to multi-region deployments via external Application Load Balancer

### 🤖 Agent Capabilities
- **Managed sessions**: Vertex AI Agent Engine for durable conversation state and memory bank
- **Artifact storage**: GCS-backed persistent storage for session artifacts
- **Custom observability**: 🔭 OpenTelemetry instrumentation with full trace-log correlation in Cloud Trace and Cloud Logging

### 🔒 Security & Reliability
- **Workload Identity Federation**: Keyless authentication for CI/CD (no service account keys)
- **Non-root containers**: Security-hardened runtime with least privilege
- **Health checks**: Kubernetes-style probes with startup grace periods

## Getting Started

> [!IMPORTANT]
> You must complete deployment first to create required resources (Agent Engine, GCS buckets, other agent-specific resources) before running locally.

Provision CI/CD infrastructure and deploy cloud resources.

### Bootstrap CI/CD Infrastructure

Set up the foundation for automated deployments:

```bash
# 1. Configure bootstrap for dev environment
cp terraform/bootstrap/dev/terraform.tfvars.example terraform/bootstrap/dev/terraform.tfvars
# Edit terraform/bootstrap/dev/terraform.tfvars REQUIRED variables: project, location, agent_name, repository_owner, repository_name

# 2. Authenticate
gcloud auth application-default login
gh auth login

# 3. Provision CI/CD infrastructure for dev
terraform -chdir=terraform/bootstrap/dev init
terraform -chdir=terraform/bootstrap/dev apply

# 4. Verify
gh variable list  # or view in GitHub repo Settings > Environments > dev
```

**Production Mode Setup:**

To enable full production deployment (dev/stage/prod):
1. Bootstrap all three environments (dev, stage, prod) using steps above
2. Set `production_mode: true` in the `config` job of `.github/workflows/ci-cd.yml`
3. See [Multi-Environment Guide](docs/base-infra/multi-environment-guide.md) for complete setup

Bootstrap creates: Workload Identity Federation, Artifact Registry, GCS state bucket, GitHub Environments, GitHub Variables.

See [Bootstrap Setup](docs/base-infra/bootstrap-setup.md) for details and [Multi-Environment Guide](docs/base-infra/multi-environment-guide.md) for production mode.

---

### Deploy Cloud Resources

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
- Agent Engine for session and memory persistence (`AGENT_ENGINE`)
- GCS bucket for artifact storage (`ARTIFACT_SERVICE_URI`)
- Cloud Run service (automatically configured with `AGENT_ENGINE` and `ARTIFACT_SERVICE_URI`)

See [CI/CD Workflow](docs/base-infra/cicd-setup.md) for automation details.

---

### Configure Local Development Environment

Get resource values from GitHub Actions logs (`gh run view <run-id>` or Actions tab UI) or GCP Console, then add to `.env`:

```bash
AGENT_ENGINE=projects/YOUR_PROJECT_ID/locations/YOUR_LOCATION/reasoningEngines/YOUR_ENGINE_ID
ARTIFACT_SERVICE_URI=gs://YOUR_BUCKET_NAME
```

Run the local server:

```bash
# Run server (http://localhost:8000)
uv run server

# Or with Docker Compose (hot reloading)
docker compose up --build --watch
```

See [Environment Variables](docs/base-infra/environment-variables.md) for where to find each value.
See [Development Guide](docs/base-infra/development.md) for workflow, testing, and code quality standards.

---

### Test the Deployed Service

Test the deployed Cloud Run service via proxy:

```bash
# Local proxy (http://localhost:8000)
gcloud run services proxy <service-name> --project <project-id> --region <region> --port 8000
```

---

## Documentation

See [docs/](docs/) for complete documentation.

### Getting Started
- **[Bootstrap Setup](docs/base-infra/bootstrap-setup.md)** - One-time CI/CD infrastructure provisioning
- **[CI/CD Workflow](docs/base-infra/cicd-setup.md)** - GitHub Actions automation details
- **[Development](docs/base-infra/development.md)** - Development workflow, code quality, testing
- **[Environment Variables](docs/base-infra/environment-variables.md)** - Complete environment variable reference

### Infrastructure and Deployment
- **[Multi-Environment Guide](docs/base-infra/multi-environment-guide.md)** - Complete multi-environment deployment guide
- **[Docker Compose Workflow](docs/base-infra/docker-compose-workflow.md)** - Local development with hot reloading
- **[Dockerfile Strategy](docs/base-infra/dockerfile-strategy.md)** - Multi-stage build architecture
- **[Terraform Infrastructure](docs/base-infra/terraform-infrastructure.md)** - Bootstrap and main module setup

### Production Features
- **[Observability](docs/base-infra/observability.md)** - OpenTelemetry traces and logs
