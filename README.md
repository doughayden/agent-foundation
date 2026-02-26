# agent-foundation

![CI/CD](https://github.com/doughayden/agent-foundation/actions/workflows/ci-cd.yml/badge.svg)
![Code Quality](https://github.com/doughayden/agent-foundation/actions/workflows/code-quality.yml/badge.svg)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://doughayden.github.io/agent-foundation/)

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
- **Optimized Docker builds**: Multi-stage builds with uv (~200MB images, fast rebuilds with layer caching)
- **Developer experience**: Hot reloading with Docker Compose watch mode for instant feedback
- **Code quality**: Strict type checking (mypy), 100% test coverage, modern linting (ruff)
- **Template-ready**: One-command initialization script for rapid project setup

### 🏗️ Production Infrastructure
- **Automated CI/CD**: GitHub Actions with Terraform IaC, smart PR automation with plan comments
- **Automated code reviews**: Claude Code integration in CI
- **Cloud Run deployment**: Production-grade hosting with regional redundancy and autoscaling
- **Environment isolation**: Multi-environment deployments (dev/stage/prod)
- **Global scalability**: Create multi-region deployments by adding External Application Load Balancer

### 🤖 Agent Capabilities
- **Managed sessions**: Vertex AI Agent Engine for durable conversation state and memory
- **Artifact storage**: GCS-backed persistent storage for session artifacts
- **Custom observability**: OpenTelemetry instrumentation with full trace-log correlation

### 🔒 Security & Reliability
- **Workload Identity Federation**: Keyless CI/CD authentication (no service account keys)
- **Non-root containers**: Security-hardened runtime with least-privilege IAM
- **Health checks**: Kubernetes-style probes with startup grace periods

## Getting Started

> [!IMPORTANT]
> Complete deployment first to create required resources (Agent Engine, GCS buckets, other agent-specific resources) before running locally with cloud persistence.

> [!NOTE]
> The project starts in **dev-only mode** (single environment) by default. To enable production mode with staged deployments (dev → stage → prod), see [Infrastructure: Deployment Modes](docs/infrastructure.md#deployment-modes).

Follow three steps to get started:
1. **Bootstrap CI/CD** — provision WIF, Artifact Registry, GCS state bucket, and GitHub Environments
2. **Deploy** — merge a PR to trigger deployment to Cloud Run with Agent Engine session and memory persistence
3. **Run the Agent** — start a local agent or test the remote agent via the Cloud Run proxy

See [Getting Started](docs/getting-started.md) for the complete walkthrough.

## Documentation

See [docs/](docs/) for complete documentation.

### Core
- **[Getting Started](docs/getting-started.md)** - Prerequisites, bootstrap, deploy, run
- **[Development](docs/development.md)** - Local workflow, Docker, testing, code quality
- **[Infrastructure](docs/infrastructure.md)** - Deployment modes, CI/CD, protection strategies, IaC
- **[Environment Variables](docs/environment-variables.md)** - Complete configuration reference

### Operations
- **[Observability](docs/observability.md)** - OpenTelemetry traces and logs
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

### Syncing Upstream Changes
- **[Template Management](docs/template-management.md)** - Syncing upstream agent-foundation changes
