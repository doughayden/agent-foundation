# agent-foundation

![CI](https://github.com/doughayden/agent-foundation/actions/workflows/ci.yml/badge.svg)
![CI/CD](https://github.com/doughayden/agent-foundation/actions/workflows/ci-cd.yml/badge.svg)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://doughayden.github.io/agent-foundation/)

Opinionated, production-ready LLM Agent deployment with enterprise-grade infrastructure

## What is this?

A comprehensive template for building and deploying LLM Agents, including those built using Google Agent Development Kit (ADK) to production. This is a complete, battle-tested foundation with automated CI/CD, managed state persistence, custom observability, and proven cloud infrastructure.

Built for teams who need to move beyond prototypes and ship production AI agents with confidence.

## Design priorities
- **Opinionated foundation**: Single optimized path (GitHub Actions + Terraform) built for extension
- **Low-level control**: Direct infrastructure management for teams who need flexibility and performance without the CLI abstraction

## Features

### ⚙️ Development & Build Optimization
- **Optimized Docker builds**: Multi-stage uv builds; a code change rebuilds and pushes only a kilobyte-sized source layer
- **Developer experience**: Local persistent sessions with no infrastructure; Docker Compose to connect to deployed resources
- **Code quality**: Strict type checking (mypy), 100% test coverage, modern linting (ruff)
- **Template-ready**: One-command initialization script for rapid project setup

### 🏗️ Production Infrastructure
- **Automated CI/CD**: GitHub Actions with Terraform IaC, smart PR automation with plan comments
- **Automated code reviews**: Claude Code integration in CI
- **Cloud Run deployment**: Production-grade hosting with regional redundancy and autoscaling
- **Environment isolation**: Multi-environment deployments (dev/stage/prod)
- **Global scalability**: Create multi-region deployments by adding External Application Load Balancer

### 🤖 Agent Capabilities
- **Database sessions**: Cloud SQL Postgres for durable conversation state
- **Artifact storage**: GCS-backed persistent storage for session artifacts
- **Custom observability**: OpenTelemetry instrumentation with full trace-log correlation

### 🔒 Security & Reliability
- **Hardened Cloud SQL**: Private IP only, IAM database auth (no passwords), enforced TLS, enforced Auth Proxy (no direct connections)
- **Workload Identity Federation**: Keyless CI/CD authentication (no service account keys)
- **Non-root containers**: Security-hardened runtime with least-privilege IAM
- **Health checks**: Kubernetes-style probes with startup grace periods

## Getting Started

> [!NOTE]
> The project starts in **dev-only mode** (single environment) by default. To enable production mode with staged deployments (dev → stage → prod), see [Infrastructure: Deployment Modes](docs/infrastructure.md#deployment-modes).

1. **Set up and run the local agent** — install, test, and run the agent with local storage; needs only a GCP project for Vertex AI
2. **Bootstrap CI/CD** — provision WIF, Artifact Registry, GCS state bucket, and GitHub Environments
3. **Deploy** — merge a PR to trigger deployment to Cloud Run with Cloud SQL sessions, Agent Engine memory, and artifact storage
4. **Run the deployed agent** — test it through the Cloud Run proxy

See [Getting Started](docs/getting-started.md) for the complete walkthrough.

## Documentation

See [docs/](docs/) for complete documentation.

### Core
- **[Getting Started](docs/getting-started.md)** - Prerequisites, local run, bootstrap, deploy
- **[Development](docs/development.md)** - Local workflow, testing, code quality, deployed resources
- **[Infrastructure](docs/infrastructure.md)** - Deployment modes, CI/CD, protection strategies, IaC
- **[Environment Variables](docs/environment-variables.md)** - Complete configuration reference

### Operations
- **[Observability](docs/observability.md)** - OpenTelemetry traces and logs
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

### Syncing Upstream Changes
- **[Template Management](docs/template-management.md)** - Syncing upstream agent-foundation changes
