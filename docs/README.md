# 🤖 Agent Foundation Documentation

**Opinionated, production-ready LLM Agent deployment with enterprise-grade infrastructure.**

This template provides a complete foundation for building and deploying LLM Agents to production. Get automated CI/CD, managed state persistence, custom observability, and proven cloud infrastructure out of the box.

Built for teams who need to move beyond prototypes and ship production AI agents with confidence.

## Key Features

- 🐳 **Optimized Docker builds** - Multi-stage builds with uv (~200MB images, 5-10s rebuilds)
- 🏗️ **Automated CI/CD** - GitHub Actions + Terraform with smart PR automation
- 🌎 **Multi-environment deployments** - Production-grade dev/stage/prod isolation
- 💾 **Database sessions** - Cloud SQL Postgres for durable conversation state
- 🔭 **Custom observability** - OpenTelemetry with full trace-log correlation
- 🏰 **Hardened Cloud SQL** - Private IP only, IAM database auth, enforced TLS and Auth Proxy
- 🔐 **Workload Identity Federation** - CI/CD authentication (no service account keys)

---

## Documentation Guide

## First Time Setup

- [Getting Started](getting-started.md) - Prerequisites, bootstrap, deploy, run
- [Environment Variables](environment-variables.md) - Complete configuration reference

## Development

- [Development](development.md) - Local workflow, Docker, testing, code quality
- [Infrastructure](infrastructure.md) - Deployment modes, CI/CD, protection strategies, IaC

## Operations

- [Observability](observability.md) - OpenTelemetry traces and logs
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

## Syncing Upstream Changes

- [Template Management](template-management.md) - Syncing upstream agent-foundation changes

## References

Deep dives for optional follow-up:

### Infrastructure
- [Bootstrap](references/bootstrap.md) - Complete bootstrap setup for both deployment modes
- [Protection Strategies](references/protection-strategies.md) - Branch, tag, environment protection
- [Deployment Modes](references/deployment.md) - Multi-environment strategy and infrastructure
- [CI/CD Workflows](references/cicd.md) - Workflow architecture and mechanics
- [Cloud SQL Scaling and Reliability](references/cloud-sql.md) - Instance tiers, backups, HA, connection pooling, monitoring

### Security
- [Security Posture](references/security-posture.md) - Defense-in-depth rationale and architectural security decisions

### Operations
- [ADK Origin Check Middleware](references/adk-origin-check-middleware.md) - Origin validation, CORS interaction, and ALLOW_ORIGINS configuration
- [OpenTelemetry Architecture](references/opentelemetry-architecture.md) - ADK coexistence, instrumentation strategy, dependency management

### Development
- [Testing Strategy](references/testing.md) - Detailed testing patterns and organization
- [Code Quality](references/code-quality.md) - Tool usage and exclusion strategies
- [Cloud Backend Options](references/cloud-backend-options.md) - Advanced options for uv run server with cloud backends
- [Docker Compose Workflow](references/docker-compose-workflow.md) - Watch mode, volumes, and configuration
- [Dockerfile Strategy](references/dockerfile-strategy.md) - Multi-stage builds and optimization
- [MkDocs Setup](references/mkdocs-setup.md) - Documentation site setup and customization
