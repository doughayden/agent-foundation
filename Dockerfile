# syntax=docker/dockerfile:1

# ============================================================================
# Builder: install dependencies into .venv
# ============================================================================
FROM python:3.14-slim AS builder

# Exact uv: equal to every setup-uv version, inside [tool.uv] required-version
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

WORKDIR /app

# Copy from the cache mount (no hardlinks), precompile bytecode, use the image's Python
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# A change to either file re-runs the sync
COPY pyproject.toml uv.lock ./

# Cache mount reuses downloaded packages across builds
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# ============================================================================
# Runtime: Python, .venv and src only
# ============================================================================
FROM python:3.14-slim AS runtime

# Non-root, no login shell, fixed UID/GID that matches no host account
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app

WORKDIR /app

# Project never installed: .venv changes only with dependencies
COPY --from=builder --chown=app:app /app/.venv ./.venv

# Runs from /app/src; a source edit rebuilds only this small layer
COPY --chown=app:app src ./src

# PYTHONPATH: import from source; HOST: accept connections from outside the container
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    PORT=8000

USER app

EXPOSE 8000

CMD ["python", "-m", "agent_foundation.server"]
