# 🤖 Agent Foundation Documentation

**Opinionated, production-ready LLM Agent deployment with enterprise-grade infrastructure.**

This template provides a complete foundation for building and deploying LLM Agents to production. Get automated CI/CD, managed state persistence, custom observability, and proven cloud infrastructure out of the box.

Built for teams who need to move beyond prototypes and ship production AI agents with confidence.

## Key Features

- 🐳 **Optimized Docker builds** - Multi-stage builds with uv (~200MB images, 5-10s rebuilds)
- 🏗️ **Automated CI/CD** - GitHub Actions + Terraform with smart PR automation
- 🌎 **Multi-environment deployments** - Production-grade dev/stage/prod isolation
- 💾 **Managed sessions** - Vertex AI Agent Engine for durable conversation state
- 🔭 **Custom observability** - OpenTelemetry with full trace-log correlation
- 🔐 **Security** - Workload Identity Federation (no service account keys)

---

## Documentation Guide

## First Time Setup

- [Getting Started](getting-started.md) - Bootstrap CI/CD, first deployment
- [Environment Variables](environment-variables.md) - Complete configuration reference

## Development

- [Development](development.md) - Docker, testing, code quality
- [Infrastructure](infrastructure.md) - Deployment, CI/CD, multi-environment

## Operations

- [Observability](observability.md) - Traces and logs
- [Troubleshooting](troubleshooting.md) - Common issues

## Template Management

- [Syncing Upstream Changes](template-management.md) - Pull updates from template

## References

Deep dives for optional follow-up:

- [Bootstrap](references/bootstrap.md) - Complete bootstrap setup for both modes
- [Protection Strategies](references/protection-strategies.md) - Branch, tag, environment protection
- [Deployment Modes](references/deployment.md) - Multi-environment strategy and infrastructure
- [CI/CD Workflows](references/cicd.md) - Workflow architecture and mechanics
- [Testing Strategy](references/testing.md) - Detailed testing patterns and organization
- [Code Quality](references/code-quality.md) - Tool usage and exclusion strategies
- [Docker Compose Workflow](references/docker-compose-workflow.md) - Watch mode, volumes, and configuration
- [Dockerfile Strategy](references/dockerfile-strategy.md) - Multi-stage builds and optimization
- [MkDocs Setup](references/mkdocs-setup.md) - Documentation site setup and customization
