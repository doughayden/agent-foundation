# Development

Day-to-day development workflow, code quality, testing, and Docker.

> [!IMPORTANT]
> Configure `AGENT_ENGINE` and `ARTIFACT_SERVICE_URI` in `.env` after first deployment for production-ready persistence (sessions, memory, artifacts). See [Environment Variables](environment-variables.md) and [Getting Started](getting-started.md).

## Quick Start

```bash
# Run directly (fast iteration)
uv run server  # API-only
LOG_LEVEL=DEBUG uv run server  # Debug mode
SERVE_WEB_INTERFACE=TRUE uv run server  # With web UI

# Docker Compose (recommended - matches production)
docker compose up --build --watch
```

**Prerequisites:**
- `.env` file configured (copy from `.env.example`)
- `gcloud auth application-default login` (for Vertex AI)

See [Getting Started](getting-started.md) for initial setup.

## Environment Setup

Configure your local `.env` file after completing your first deployment. The deployed resources provide production-ready persistence for sessions, memory, and artifacts.

### 1. Create .env File

```bash
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env` and configure required values. The `.env.example` file includes inline comments for each variable.

**Required configuration:**
- Google Cloud Vertex AI credentials
- Agent identification
- OpenTelemetry settings

**Recommended (after first deployment):**
- `AGENT_ENGINE` - Session and memory persistence
- `ARTIFACT_SERVICE_URI` - Artifact storage

See [Environment Variables](environment-variables.md) for complete reference.

### 3. Verify Configuration

Test your setup:

```bash
# Check auth
gcloud auth application-default login

# Start server
uv run server

# Or with Docker Compose
docker compose up --build --watch
```

**Note:** Without cloud resource configuration, the agent falls back to in-memory persistence (not recommended for development).

See [Environment Variables](environment-variables.md) for complete reference.

## Feature Branch Workflow

```bash
# Create branch (feat/, fix/, docs/, refactor/, test/)
git checkout -b feat/your-feature-name

# Develop locally (choose one)
docker compose up --build --watch  # Docker (recommended - matches production)
uv run server  # Direct execution (if Docker unavailable)

# Quality checks before commit (100% coverage required)
uv run ruff format && uv run ruff check && uv run mypy
uv run pytest --cov --cov-report=term-missing

# Commit (Conventional Commits: 50 char title, list body)
git add . && git commit -m "feat: add new tool"

# Push and create PR
git push origin feat/your-feature-name
gh pr create  # Follow PR format: What, Why, How, Tests

# After merge to main, monitor deployment
gh run list --workflow=ci-cd.yml --limit 5
gh run view --log
```

GitHub Actions automatically builds, tests, and deploys to Cloud Run. Check job summary for deployment details.

## Code Quality & Testing

Run format, lint, type check, and unit tests (100% coverage required) **before every commit**

**Standards:**
- **Type Hints:** Strict mypy, modern Python 3.13+ syntax (`|` unions, lowercase generics)
- **Code Style:** Ruff enforced (88-char lines, `Path` objects, security checks)
- **Docstrings:** Google-style format (args, returns, exceptions)
- **Testing:** 100% coverage on production code, exclusions for configuration modules, fixtures in `conftest.py`, test behaviors and errors

See [Testing Strategy](references/testing.md) and [Code Quality](references/code-quality.md) references for detailed patterns, tool usage, and exclusion strategies.

## Docker Development

**Recommended:** Docker Compose matches production environment and enables hot reloading.

**Alternative:** Use `uv run server` if Docker is unavailable (device policies, etc.). You'll need to manually restart the server when making changes.

```bash
# Start with watch mode (leave running)
docker compose up --build --watch

# Changes in src/ sync instantly
# Changes in pyproject.toml or uv.lock trigger rebuild

# Stop: Ctrl+C or docker compose down
```

**Key details:**
- Source files sync to container without rebuild (instant feedback)
- Loads `.env` automatically for configuration
- Multi-stage Dockerfile optimized with uv cache mounts (~80% faster rebuilds)
- Non-root container (~200MB final image)

See [Docker Compose Workflow](references/docker-compose-workflow.md) and [Dockerfile Strategy](references/dockerfile-strategy.md) for details on watch mode, volumes, layer optimization, and security.

## Common Tasks

### Dependencies

```bash
# Add runtime dependency
uv add package-name

# Add dev dependency
uv add --group dev package-name

# Update all dependencies
uv lock --upgrade

# Update specific package
uv lock --upgrade-package package-name

# After updating pyproject.toml or uv.lock:
# - Locally: Restart server or Docker Compose (auto-rebuild with watch)
# - CI/CD: Commit both files together (required for --locked to pass)
```

### Version Bump

When bumping version in `pyproject.toml`:

```bash
# Edit version in pyproject.toml
# Then update lockfile
uv lock

# Commit both together
git add pyproject.toml uv.lock
git commit -m "chore: bump version to X.Y.Z"
```

**Why:** CI uses `uv sync --locked` which will fail if lockfile is out of sync.

### Test Deployed Service

Proxy Cloud Run service to test locally:

```bash
# Service name format: ${agent_name}-${environment}
gcloud run services proxy <service-name> \
  --project <project-id> \
  --region <region> \
  --port 8000

# Test
curl http://localhost:8000/health

# With web UI (if SERVE_WEB_INTERFACE=TRUE)
open http://localhost:8000

# Stop proxy: Ctrl+C
```

See [Cloud Run proxy documentation](https://cloud.google.com/run/docs/authenticating/developers#proxy).

### Observability

**Server Logs:**
- Print to stdout (via LoggingPlugin callbacks)
- Basic request/response logging for immediate feedback

**Opentelemetry Traces and Logs:**
- Detailed traces → Cloud Trace
- Structured logs → Cloud Logging
- Full correlation between traces and logs

See [Observability](observability.md) for querying, filtering, and trace analysis.

## Project Structure

```
your-agent-name/
  src/your_agent_name/
    agent.py              # LlmAgent configuration
    callbacks.py          # Agent callbacks
    prompt.py             # Agent prompts
    tools.py              # Custom tools
    server.py             # FastAPI development server
    utils/
      config.py           # Configuration and environment parsing
      observability.py    # OpenTelemetry setup
  tests/                  # Test suite
    conftest.py           # Shared fixtures
    test_*.py             # Unit and integration tests
  terraform/              # Infrastructure as code
    bootstrap/{env}       # One-time CI/CD setup (per environment)
    main/                 # Cloud Run deployment
  docs/                   # Documentation
  .env.example            # Environment template
  pyproject.toml          # Project configuration
  docker-compose.yml      # Local development
  Dockerfile              # Container image
  CLAUDE.md               # LLM Agent instructions
  README.md               # Main documentation
```

---

← [Back to Documentation](README.md)
