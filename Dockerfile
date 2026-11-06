# syntax=docker/dockerfile:1

# ============================================================================
# Builder Stage: install dependencies into .venv
# ============================================================================
FROM python:3.14-slim AS builder

# Exact uv: equal to every setup-uv version, inside [tool.uv] required-version
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

# Set working directory
WORKDIR /app

# uv settings: copy from the cache mount instead of hardlinking, precompile
# bytecode, use the base image's Python
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# A change to either file re-runs the dependency sync
COPY pyproject.toml uv.lock ./

# The cache mount reuses downloaded packages across builds
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Source runs from /app/src; the project is never installed, so .venv changes only with dependencies
COPY src ./src

# ============================================================================
# Runtime Stage: Python, .venv and src only
# ============================================================================
FROM python:3.14-slim AS runtime

# Create a non-root user to run the server
RUN groupadd -r app && useradd -r -s /usr/sbin/nologin -g app app

# Set working directory
WORKDIR /app

# Separate layers: a source edit invalidates only the small src layer
COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/src ./src

# Use the virtual environment
# PYTHONPATH=/app/src: Import the package from source (not installed)
# HOST=0.0.0.0: Bind to all interfaces for container networking
# PORT=8000: Default port
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    PORT=8000

# Switch to non-root user
USER app

# Document the default port (EXPOSE publishes nothing)
EXPOSE 8000

# Run server.main(), the same entry point as `uv run server`
CMD ["python", "-m", "agent_foundation.server"]
