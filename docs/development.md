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

### 2. Add Required Variables

Edit `.env` with these required values:

```bash
# Google Cloud Vertex AI (required)
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Agent Identification (required)
AGENT_NAME=your-agent-name

# OpenTelemetry (required)
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=TRUE
```

### 3. Add Cloud Resources

After first deployment, add these values from GitHub Actions job summary (`gh run view <run-id>`):

```bash
# Production-ready persistence (get from deployment outputs)
AGENT_ENGINE=projects/YOUR_PROJECT/locations/YOUR_REGION/reasoningEngines/YOUR_ENGINE_ID
ARTIFACT_SERVICE_URI=gs://YOUR_BUCKET_NAME
```

**Where to find these values:**
- GitHub Actions: `gh run view <run-id>` (look for deployment outputs)
- GCP Console: Vertex AI → Agent Builder → Reasoning Engines
- GCP Console: Cloud Storage → Buckets

### 4. Optional Configuration

Add these for customization (see [Environment Variables](environment-variables.md) for all options):

```bash
# Logging
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Development features
SERVE_WEB_INTERFACE=TRUE  # Enable ADK web UI
TELEMETRY_NAMESPACE=your-name-local  # Isolate your traces

# Model selection
ROOT_AGENT_MODEL=gemini-2.5-flash  # Or gemini-2.5-pro
```

### 5. Verify Configuration

Test your setup:

```bash
# Check auth
gcloud auth application-default login

# Start server
uv run server

# Or with Docker Compose
docker compose up --build --watch
```

**Note:** Without `AGENT_ENGINE` and `ARTIFACT_SERVICE_URI`, the agent falls back to in-memory persistence (not recommended for development).

See [Environment Variables](environment-variables.md) for complete reference.

## Feature Branch Workflow

```bash
# Create branch (feat/, fix/, docs/, refactor/, test/)
git checkout -b feat/your-feature-name

# Develop locally
docker compose up --build --watch  # Leave running, changes sync automatically

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

## Code Quality

Run before every commit:

```bash
# Format, lint, type check
uv run ruff format && uv run ruff check && uv run mypy

# Tests (100% coverage required)
uv run pytest --cov --cov-report=term-missing

# Specific tests
uv run pytest tests/test_integration.py -v
uv run pytest tests/test_file.py::test_name -v
```

### Standards

**Type Hints:**
- Strict mypy
- Complete annotations (args, returns, raises)
- Modern Python 3.13+ syntax (`|` unions, lowercase generics)
- Pydantic validation for config

**Code Style:**
- Ruff (88-char lines, auto-fix)
- Always use `Path` objects (never `os.path`)
- See `pyproject.toml` for rules

**Docstrings:**
- Google-style format
- Document args, returns, exceptions
- See `src/agent_foundation/` for examples

**Testing:**
- 100% coverage (excludes `server.py`, `agent.py`, `prompt.py`, `__init__.py`)
- Shared fixtures in `conftest.py`
- Duck-typed mocks (mirror real interfaces)
- Test behaviors, errors, edge cases

## Testing

### Coverage Requirements

100% coverage on production code:
- Includes: `src/agent_foundation/*.py` (except exclusions), `src/agent_foundation/utils/*.py`
- Excludes: `server.py`, `**/agent.py`, `**/prompt.py`, `**/__init__.py`

```bash
# Full coverage report
uv run pytest --cov --cov-report=term-missing

# HTML report
uv run pytest --cov --cov-report=html
open htmlcov/index.html
```

### Test Organization

- **Location:** `tests/` directory, mirrors source structure
- **Fixtures:** Shared fixtures in `tests/conftest.py`
- **Naming:** `test_<what>_<condition>_<expected>.py`
- **Grouping:** Classes for related tests

### Testing Patterns

**Fixtures:**
- Type hints: `MockerFixture` → `MockType` return
- Factory pattern (not context managers)
- Environment mocking: `mocker.patch.dict(os.environ, env_dict)`

**ADK Mocks:**
- Use fixtures from `conftest.py`: `mock_state`, `mock_session`, `mock_context`
- Mirror real interfaces exactly
- Import mock classes only when fixtures add complexity

**Validation:**
- Pydantic validates at model creation
- Expect `ValidationError` at `model_validate()`, not property access

See `tests/conftest.py` and existing tests for examples.

## Docker Compose Deep Dive

Recommended for local development - matches production environment.

### Daily Workflow

```bash
# Start with hot reloading (leave running)
docker compose up --build --watch

# Changes in src/ sync instantly (no rebuild)
# Changes in pyproject.toml or uv.lock trigger automatic rebuild

# Stop: Ctrl+C or docker compose down
```

### What Watch Mode Does

**Sync Action** (instant):
- Triggers when: You edit files in `src/`
- What happens: Files copied into running container
- Speed: Immediate
- No rebuild needed

**Rebuild Action** (5-10 seconds):
- Triggers when: You edit `pyproject.toml` or `uv.lock`
- What happens: Full image rebuild, container recreated
- Speed: Fast with cache

### File Locations

- **Source:** `./src/` → `/app/src` (synced via watch mode)
- **Data:** `./data/` → `/app/data` (read-only, optional)
- **Credentials:** `~/.config/gcloud/` → `/gcloud/` (Application Default Credentials)

### Environment Variables

Docker Compose loads `.env` automatically. See [Environment Variables](environment-variables.md) for reference.

**Note:** Container uses `HOST=0.0.0.0` to allow connections from host. `docker-compose.yml` maps container port 8000 to host port 8000.

### Common Commands

```bash
# View logs (if running detached)
docker compose logs -f
docker compose logs -f app  # Just app logs

# Rebuild without starting
docker compose build

# Run without watch mode
docker compose up --build
```

## Dockerfile Understanding

Multi-stage build for fast rebuilds and minimal runtime image.

### Architecture

1. **Builder Stage:** `python:3.13-slim` + uv binary
   - Copy uv from Astral's distroless image
   - Install dependencies (cache mount ~80% speedup)
   - Install project code
2. **Runtime Stage:** Clean `python:3.13-slim`
   - Copy only virtual environment from builder
   - Non-root user (`app:app`)
   - ~200MB final image

### Layer Optimization

**Dependency Layer** (rebuilds only when pyproject.toml or uv.lock change):
```dockerfile
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev
```

**Code Layer** (rebuilds on src/ changes):
```dockerfile
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    touch README.md && \
    uv sync --locked --no-editable --no-dev
```

**Why `--locked`?**
- Validates lockfile matches `pyproject.toml`
- Catches developer mistakes (forgot to run `uv lock`)
- Fails fast with clear error
- Standard across dev, CI/CD, production

**Cache mount** is the key optimization - persists across builds, so even "unnecessary" rebuilds are fast.

### Security

- **Non-root:** Runs as user `app:app` (UID 1000)
- **Minimal image:** Only virtual environment, no build tools
- **Slim base:** Debian-based `python:3.13-slim` (~200MB total)

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

View traces and logs:

```bash
# Cloud Console
# Traces: https://console.cloud.google.com/traces
# Logs: https://console.cloud.google.com/logs

# CLI
gcloud logging tail "logName:projects/{PROJECT_ID}/logs/{AGENT_NAME}-otel-logs"
```

See [Observability](observability.md) for query examples and trace filtering.

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
    bootstrap/            # One-time CI/CD setup (per environment)
    main/                 # Cloud Run deployment
  docs/                   # Documentation
  .env.example            # Environment template
  pyproject.toml          # Project configuration
  docker-compose.yml      # Local development
  Dockerfile              # Container image
  CLAUDE.md               # Project instructions
  README.md               # Main documentation
```

## See Also

- [Getting Started](getting-started.md) - Initial setup
- [Environment Variables](environment-variables.md) - Configuration reference
- [Deployment](deployment.md) - Cloud Run and multi-environment
- [CI/CD](cicd.md) - GitHub Actions workflows
- [Observability](observability.md) - Traces and logs
- [Troubleshooting](troubleshooting.md) - Common issues
