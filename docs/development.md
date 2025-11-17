# Development

This document covers development workflows, code quality standards, and testing.

## Prerequisites

- Python 3.13+
- `uv` package manager
- Google Cloud SDK (optional, for Vertex AI authentication)

## Template Initialization

**If you created this repository from the template**, initialize it once after cloning:

```bash
# Preview changes without making them
uv run init_template.py --dry-run

# Apply changes
uv run init_template.py
```

This script:
- Renames the package to match your repository name
- Updates all configuration, documentation, and test files
- Resets `CHANGELOG.md` with a fresh template
- Regenerates the UV lockfile

After running, review changes with `git status` and commit:

```bash
git add -A
git commit -m "chore: initialize from template"
```

The script creates `init_template_results.md` as an audit log of changes. Dry-run mode creates `init_template_dry_run.md` instead. Both are gitignored.

## Development Commands

### Running the Server

```bash
# Configure authentication first
cp .env.example .env
# Edit .env to set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION

# Run server (default)
uv run server

# Or enable web UI by setting SERVE_WEB_INTERFACE=true in .env
```

**Debug mode** (detailed logging):
```bash
LOG_LEVEL=DEBUG uv run server
```

### Docker Compose (Local Development)

**Recommended workflow** for containerized local development:

```bash
# Start with hot reloading (recommended)
docker compose up --build --watch
```

This provides:
- Automatic file syncing for `src/` changes (instant)
- Automatic rebuilds for dependency changes
- Isolated environment matching production

For complete Docker Compose workflow documentation, see [Docker Compose Workflow Guide](./docker-compose-workflow.md).

### Code Quality

Run all checks before committing:

```bash
# Format code
uv run ruff format

# Lint code
uv run ruff check

# Type check
uv run mypy
```

**One-liner** for all checks:
```bash
uv run ruff format && uv run ruff check && uv run mypy
```

### Testing

```bash
# Run all tests
uv run pytest -v

# Run tests with coverage
uv run pytest --cov --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_integration.py -v

# Run specific test
uv run pytest tests/test_integration.py::test_agent_uses_instruction_provider_callable -v
```

## Code Quality Standards

### Type Hints

- **Strict mypy checking enabled** - all functions must have complete type annotations
- **Modern Python syntax** - uses Python 3.13+ features (PEP 604 union types with `|`, lowercase generics)
- **Type-safe models** - Pydantic for runtime validation

Example:
```python
def example_tool(tool_context: ToolContext) -> dict[str, Any]:
    """Example tool with full type safety."""
    ...
```

### Code Style

**Ruff configuration**:
- Auto-fix enabled with comprehensive linting rules
- Enforces: pycodestyle, pyflakes, isort, flake8-bugbear, pyupgrade, pep8-naming, flake8-bandit, flake8-simplify, flake8-use-pathlib
- Line length: 88 characters (Black-compatible)

**Pathlib usage**:
- Use `Path` objects for all file operations (enforced by ruff PTH rules)
- Never use `os.path` functions

Example:
```python
from pathlib import Path

# Good
log_path = Path(".log/app.log")
if log_path.exists():
    content = log_path.read_text()

# Bad - will be flagged by ruff
import os
if os.path.exists(".log/app.log"):
    with open(".log/app.log") as f:
        content = f.read()
```

### Docstrings

- **Comprehensive module, class, and function docstrings**
- **Include**: arguments, exceptions, return values
- **Google-style docstring format**

Example:
```python
def example_tool(tool_context: ToolContext) -> dict[str, Any]:
    """Example tool that logs a success message.

    This is a placeholder example tool. Replace with actual implementation.

    Args:
        tool_context: ADK ToolContext with access to session state

    Returns:
        A dictionary with status and message about the logging operation.
    """
    ...
```

### Testing

- **100% coverage** on all production code (scripts and server.py excluded)
- **Organized by feature** - tests in separate files, shared fixtures in `conftest.py`
- **pytest fixtures** - reusable fixtures in `conftest.py` to eliminate patching in individual tests
- **Duck-typed mocks** - minimal mock classes that satisfy ADK protocols

Test organization:
```
tests/
  conftest.py              # Shared fixtures
  test_*.py                # Test modules organized by feature
```

## Dependencies

### Core Dependencies

- **Google ADK**: Agent framework for LLM-powered applications
- **pydantic**: Data validation and runtime type checking
- **python-dotenv**: Environment variable management

### Development Dependencies

- **pytest**: Test framework
- **pytest-cov**: Coverage reporting
- **pytest-asyncio**: Async test support
- **ruff**: Fast Python linter and formatter
- **mypy**: Static type checker

### Dependency Groups

The project uses PEP 735 dependency groups (via `uv`):
- `dev` group: Development tools (pytest, ruff, mypy, etc.)
- No `--dev` flag needed - dev dependencies are installed by default with `uv run`

## Project Structure

```
adk-docker-uv/
  src/adk_docker_uv/
    agent.py              # LlmAgent configuration
    callbacks.py          # Agent callbacks
    prompt.py             # Agent prompts
    tools.py              # Custom tools
    server.py             # FastAPI development server
    utils/                # Utilities
      env_parser.py         # Environment variable parsing
      log_config.py         # Logging configuration
  tests/                  # Test suite
    conftest.py             # Shared fixtures
    test_integration.py     # Integration tests
    test_*.py               # Unit tests
  docs/                   # Documentation
  .env.example            # Environment template
  pyproject.toml          # Project configuration
  CLAUDE.md               # Project instructions
  README.md               # Main documentation
```

## CI/CD

The project uses GitHub Actions for continuous integration:
- Code quality checks (ruff format, ruff check, mypy)
- Test suite with coverage reporting
- Runs on every push and pull request

See `.github/workflows/` for workflow definitions.

## Dependency Management

**No manual sync needed**: `uv run` handles dependency installation automatically.

**Adding dependencies**:
```bash
# Add runtime dependency
uv add package-name

# Add dev dependency
uv add --group dev package-name
```

**Updating dependencies**:
```bash
# Update all dependencies
uv lock --upgrade

# Update specific package
uv lock --upgrade-package package-name
```

## Logging

The project uses structured logging with rotating file handler:

**Configuration**:
- Default level: INFO
- File: `.log/app.log`
- Max size: 1 MB
- Backup count: 5 files
- Format: `[{asctime}] [{process}] [{levelname:>8}] [{name}.{funcName}:{lineno:>5}] {message}`

**Custom logger**:
```python
import logging
from adk_docker_uv.utils import setup_file_logging

# Setup logging with custom level
setup_file_logging(log_level="DEBUG")

# Get logger
logger = logging.getLogger(__name__)
logger.debug("Debug message")
```

**Environment control**:
```bash
LOG_LEVEL=DEBUG uv run server
```
