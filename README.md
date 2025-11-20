# adk-docker-uv

![Build](https://github.com/doughayden/adk-docker-uv/actions/workflows/docker-build-push.yml/badge.svg)
![CI](https://github.com/doughayden/adk-docker-uv/actions/workflows/code-quality.yml/badge.svg)

ADK on Docker, optimized with uv

## Template Setup

**If you created this repository from the template**, run the initialization script once:

```bash
uv run init_template.py
# Or preview changes first: uv run init_template.py --dry-run
```

This renames the package, updates configuration files, resets the changelog, and creates a fresh CODEOWNERS file. Review changes with `git status`, then commit.

## Quickstart

**1. Authentication** (one-time setup):
```bash
cp .env.example .env
# Edit .env and choose ONE authentication method:
#   - GOOGLE_API_KEY for Gemini Developer API
#   - GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION for Vertex AI

# If using Vertex AI, authenticate with gcloud:
gcloud auth application-default login
```

See [ADK docs](https://google.github.io/adk-docs/get-started/quickstart/#set-up-the-model) for authentication details.

**2. Run the server**:

**Option A: Direct (uv)**
```bash
uv run server
# Server runs on http://127.0.0.1:8000 (API-only by default)
# Set SERVE_WEB_INTERFACE=true in .env to enable the web UI
```

**Option B: Docker Compose (recommended for local development)**
```bash
# Sync first to create uv.lock if it does not exist
uv sync
docker compose up --build --watch
# Includes hot reloading - changes sync instantly
# See docs/docker-compose-workflow.md for details
```

## What is this?

A production-ready template for deploying Google ADK (Agent Development Kit) agents using containerization best practices. This project demonstrates how to build efficient, type-safe ADK agents with modern Python tooling.

**Key features:**
- **Optimized Docker builds**: Multi-stage builds with uv package manager (~200MB images, 5-10s rebuilds)
- **Developer experience**: Hot reloading with Docker Compose watch mode for instant feedback
- **Code quality**: Strict type checking (mypy), comprehensive testing (100% coverage), modern linting (ruff)
- **Production ready**: Non-root containers, health checks, environment-based configuration

## Documentation

- **[Development](docs/development.md)** - Code quality, testing, dependencies, and project structure
- **[Docker Compose Workflow](docs/docker-compose-workflow.md)** - Local development with hot reloading
- **[Dockerfile Strategy](docs/dockerfile-strategy.md)** - Multi-stage build architecture and rationale
- **[GitHub Docker Workflow](docs/github-docker-setup.md)** - CI/CD setup for automated Docker builds
