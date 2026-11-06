# Dockerfile Strategy Explained

This document explains our multi-stage Docker build strategy and why we chose this approach for containerizing the agent.

## Table of Contents

- [Overview](#overview)
- [Dockerfile Breakdown](#dockerfile-breakdown)
- [Why Not Use UV Image Directly](#why-not-use-uv-image-directly)
- [Why We COPY Instead of Using Bind Mounts](#why-we-copy-instead-of-using-bind-mounts)
- [Performance Comparison](#performance-comparison)
- [Summary](#summary)
- [Local Development](#local-development)
- [References](#references)

## Overview

Our Dockerfile uses a **multi-stage build** with the following architecture:

1. **Builder Stage**: `python:X.Y-slim` + uv binary (copied from Astral's distroless image)
2. **Runtime Stage**: Clean `python:X.Y-slim` + the virtual environment and the source, as separate layers

`X.Y` is the Python version pinned in `.python-version`.

This approach gives us:
- ✅ Official uv binary (pinned for reproducible builds)
- ✅ Full build capabilities (shell, Python, package manager)
- ✅ No uv, uv cache or build metadata in the runtime image
- ✅ Small pushes: a source edit changes only the source layer (kilobytes); the dependency layer stays cached
- ✅ Runs as a non-root user

---

## Dockerfile Breakdown

### Syntax Directive
```dockerfile
# syntax=docker/dockerfile:1
```
**What:** Selects the Dockerfile frontend: the latest stable 1.x syntax
**Why:** Builds get current Dockerfile features without upgrading Docker. BuildKit itself is already Docker's default builder, so `docker build` needs no flag or `DOCKER_BUILDKIT=1` ([Dockerfile reference](https://docs.docker.com/reference/dockerfile/#syntax))

---

### Builder Stage Base Image
```dockerfile
FROM python:X.Y-slim AS builder
```
**What:** Start builder stage with official Python slim image (Debian-based), tagged with the version in `.python-version`
**Why:** We need:
- Python runtime for `uv sync` to work
- Shell and basic utilities (cp, mkdir, etc.) for build commands

**Why not `ghcr.io/astral-sh/uv:latest` as base?**
- Astral's uv image is **distroless**: it contains only the `uv` and `uvx` binaries, so there is no shell to run `RUN` commands
- It's designed to copy the binary FROM, not build FROM

---

### Copy UV Binary
```dockerfile
# Exact uv: equal to every setup-uv version, inside [tool.uv] required-version
COPY --from=ghcr.io/astral-sh/uv:X.Y.Z /uv /uvx /bin/
```
**What:** Extract just the `uv` and `uvx` binaries from Astral's image
**Why:**
- Pinned to an exact version for reproducible, deterministic builds (bump procedure: `docs/development.md` uv Version)
- Copies two binaries, not a whole base image
- Puts them in `/bin/` so they're in PATH

**Key insight:** We get official uv without the distroless constraints.

---

### Working Directory (Builder Stage)
```dockerfile
WORKDIR /app
```
**What:** Set working directory to `/app`
**Why:**
- All subsequent commands run from this directory
- Creates the directory if it doesn't exist
- Standard convention for application code

---

### UV Environment Variables
```dockerfile
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
```
**What:** Configure uv behavior
**Why:**

| Variable | Value | Reason |
|----------|-------|--------|
| `UV_LINK_MODE=copy` | Copy files instead of hardlinking | The cache mount and `.venv` are on separate filesystems, so uv can't hardlink and would warn |
| `UV_COMPILE_BYTECODE=1` | Pre-compile .py → .pyc files | Tends to improve startup time, at the cost of install time and image size ([uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/)) |
| `UV_PYTHON_DOWNLOADS=never` | Don't download Python | Use system Python from base image |

---

### Install Dependencies
```dockerfile
# A change to either file re-runs the dependency sync
COPY pyproject.toml uv.lock ./

# The cache mount reuses downloaded packages across builds
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev
```
**What:** Install dependencies WITHOUT installing the project itself
**Why:** This is the only install step. The project is never installed, so `.venv` holds dependencies only and changes only when `pyproject.toml` or `uv.lock` does.

| Flag | Meaning | Benefit |
|------|---------|---------|
| `--mount=type=cache` | Persist `/root/.cache/uv` across builds | Don't re-download packages already cached |
| `--locked` | Validate lockfile matches pyproject.toml | Catches mistakes, prevents silent failures (our standard) |
| `--no-install-project` | Skip installing the project package | `.venv` stays independent of source edits |
| `--no-dev` | Skip dev dependencies | Smaller image |

**Why COPY both files?**
- ✅ **Explicit cache invalidation** - When dependencies change, this layer rebuilds (as it should)
- ✅ **Predictable** - Standard Docker caching behavior, no surprises
- ✅ **Simple** - Easy to understand and maintain

**Why `--locked` (not `--frozen`)?**

We **standardize on `--locked`** for all builds. Here's why:

| Flag | Behavior | When to Use |
|------|----------|-------------|
| `--locked` | **Validates lockfile matches pyproject.toml** | ✅ **Always** (our standard) |
| `--frozen` | Skips validation, silently uses stale lockfile | ❌ **Avoid** |

**Why avoid `--frozen`:**
- ❌ Silently installs wrong dependencies if lockfile is stale
- ❌ uv's own GitHub Actions example uses `--locked`
- ❌ Hides developer mistakes instead of catching them

**Why use `--locked` everywhere:**
- ✅ Catches developer mistakes (forgot to run `uv lock`)
- ✅ Ensures lockfile and pyproject.toml stay synchronized
- ✅ Fails fast with clear error message
- ✅ Validation is cheap (`uv lock --check` takes tens of milliseconds)
- ✅ Enforces correct workflow: change deps → `uv lock` → commit both files

**Example of `--locked` preventing bugs:**
```bash
# Developer adds pandas to pyproject.toml but forgets to run uv lock
$ docker build .
error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
# Developer: "Oh right, I need to run uv lock first!"
$ uv lock
$ docker build .  # Now succeeds with correct dependencies
```

**Bottom line:** The Dockerfile and every CI `uv sync` use `--locked`. We'll only consider `--frozen` if we encounter a very specific use case that requires skipping validation (none identified yet).

**What the cache mount buys:** packages already downloaded are not fetched again. The gain is modest: most of a dependency install goes to unpacking and byte-compiling, not downloading. It also persists only on the same builder: `cache-to` exports layers, not cache mounts, so each CI run on a fresh runner starts with an empty uv cache ([Docker GitHub Actions cache](https://docs.docker.com/build/ci/github-actions/cache/)). Registry layer cache still skips the whole sync when `pyproject.toml` and `uv.lock` are unchanged.

---

### Copy Source Code
```dockerfile
# Source runs from /app/src; the project is never installed, so .venv changes only with dependencies
COPY src ./src
```
**What:** Copy only the application source code
**Why:**
- Done AFTER dependencies, so a source edit never invalidates the dependency layer
- Only `src/` is copied: documentation, tests and config changes don't invalidate it
- The runtime stage copies this directory as its own layer and imports the package from it via `PYTHONPATH`

---

### Runtime Stage Base
```dockerfile
FROM python:X.Y-slim AS runtime
```
**What:** Start fresh with clean Python image for runtime
**Why:** Multi-stage build benefits:
- uv, its cache and the dependency files stay in the builder stage
- Runtime stage only has Python, `.venv` and `src/`

---

### Non-Root User
```dockerfile
RUN groupadd -r app && useradd -r -s /usr/sbin/nologin -g app app
```
**What:** Create a non-root system user named `app`
**Why:** The server doesn't need root, so it doesn't run as root

**Command breakdown:**
- `groupadd -r app`: Create a system group (system range, below 1000)
- `useradd -r -s /usr/sbin/nologin -g app app`: Create a system user in that group (system range, below 1000; no home directory is created)
- `-s /usr/sbin/nologin`: The account has no login shell, so `su app` or any login as `app` is refused. `docker exec` and the `CMD` start their own process and never read the account's shell, so the server and debugging sessions are unaffected

**Explicit UIDs:** some Dockerfiles pin a UID (like `useradd -u 1001`) so files on shared volumes keep consistent ownership. The image mounts no volumes, so a system-assigned ID is enough. Pin one if you add a volume that needs POSIX ownership.

---

### Working Directory (Runtime Stage)
```dockerfile
WORKDIR /app
```
**What:** Set working directory again (new stage = new filesystem)
**Why:** Container starts in `/app` when it runs

---

### Copy Virtual Environment and Source from Builder
```dockerfile
# Separate layers: a source edit invalidates only the small src layer
COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/src ./src
```
**What:** Copy the dependencies and the source as two layers
**Why:**
- Each `COPY` produces one layer, and any change to its content invalidates the whole layer. The `.venv` layer is hundreds of MB; the `src` layer is tens of kB
- A source edit rebuilds and re-pushes only the `src` layer; the `.venv` layer stays cached locally and in the registry. Copying `/app` in one layer would re-export and re-push the whole venv on every source edit
- `--chown=app:app`: Make the `app` user own both
- **uv, `pyproject.toml` and `uv.lock` are NOT copied** (needed only to build)

---

### Runtime Environment
```dockerfile
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    PORT=8000
```
**What:** Configure runtime environment
**Why:**

| Variable | Purpose |
|----------|---------|
| `VIRTUAL_ENV=/app/.venv` | Tell Python which venv to use |
| `PATH="/app/.venv/bin:$PATH"` | Make venv binaries available (python, uvicorn) |
| `PYTHONUNBUFFERED=1` | Don't buffer stdout/stderr (better logs in Docker) |
| `PYTHONPATH=/app/src` | Import the agent package from source, since the project is not installed |
| `HOST=0.0.0.0` | Explicitly bind all interfaces for containers (server.py defaults to 127.0.0.1) |
| `PORT=8000` | Explicitly set default port (matches EXPOSE and server.py default) |

---

### Agent Directory

ADK's `get_fast_api_app(agents_dir=...)` lists every package in a directory as an agent, so it needs a directory holding only the agent source. `server.py` derives it from its own location:

```python
AGENT_DIR = os.getenv("AGENT_DIR", str(Path(__file__).resolve().parent.parent))
```

Because the image runs the package from `/app/src` instead of installing it, `__file__` is `/app/src/your_agent_name/server.py` and the default resolves to `/app/src`, the same as a local checkout resolves to `src/`. The Dockerfile sets no override.

Installing the project would move `__file__` into `.venv/lib/pythonX.Y/site-packages/`, and the default would then point at every installed package. Running from source avoids that, and keeps `.venv` independent of source edits. `AGENT_DIR` remains available as an override for other layouts.

Without the install, the container venv has no `server` console script and no project metadata (`importlib.metadata` cannot find the project). The `CMD` runs `python -m`, so neither is needed; locally, `uv run server` still works because `uv sync` installs the project. Release tooling reads the version from `pyproject.toml`, not from the image.

---

### Switch to Non-Root
```dockerfile
USER app
```
**What:** All subsequent commands, and the container process at runtime, run as `app`

---

### Expose Port
```dockerfile
EXPOSE 8000
```
**What:** Document the port the server listens on (the `PORT` default above)
**Why:**
- Documentation only: it publishes nothing. Compose publishes through `ports:` in `compose.yml`, Cloud Run through the service's container port
- `docker run -P` publishes exposed ports to random host ports

---

### Startup Command
```dockerfile
# Run server.main(), the same entry point as `uv run server`
CMD ["python", "-m", "your_agent_name.server"]
```
**What:** Default command when container starts
**Why:**
- Importing `server` loads settings and configures telemetry; `main()` then runs uvicorn on `HOST` and `PORT` from `ServerEnv`
  - `HOST` defaults to 127.0.0.1 (only local connections); the Dockerfile sets `0.0.0.0` so the container accepts outside connections
- Exec form (JSON array): Python runs as PID 1 and receives `SIGTERM` directly; the shell form would wrap it in `/bin/sh -c`, which does not pass signals ([Dockerfile reference](https://docs.docker.com/reference/dockerfile/#cmd))
- Can be overridden at runtime

---

## Why Not Use UV Image Directly?

Let's compare the approaches:

### ❌ Using UV Image Directly (Won't Work)
```dockerfile
FROM ghcr.io/astral-sh/uv:X.Y.Z

# ERROR: No shell to run these commands!
RUN uv sync  # FAILS - distroless has no /bin/sh
COPY src ./src  # Works, but then what?
```

**Problems:**
- The image holds only `uv` and `uvx`: no shell for `RUN`, no Python, no package manager
- Designed for copying FROM, not building FROM

### ✅ Our Approach (Multi-Stage)
```dockerfile
# Builder: Use python:X.Y-slim + uv binary
FROM python:X.Y-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:X.Y.Z /uv /uvx /bin/
# ... build with full shell/utilities ...

# Runtime: Clean python:X.Y-slim + .venv and src
FROM python:X.Y-slim AS runtime
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/src ./src
```

**Benefits:**
- Builder has shell + Python + uv → can build anything
- Runtime carries no uv and no dependency manifests
- Gets official uv binary → pinned for reproducibility

---

## Why We COPY Instead of Using Bind Mounts

uv's Docker guide also shows bind-mounting `pyproject.toml` and `uv.lock` into the sync step instead of copying them:

```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project
```

Both invalidate the same way: BuildKit tracks bind-mounted files, so changing one re-runs the step. The only difference is that `COPY` leaves the two files (about 435 kB) in a builder layer. The builder stage never ships, so that costs nothing in the runtime image. We keep `COPY` because it is the plainer pattern.

## Performance Comparison

Once images build in CI and push to a registry, the cost of a change is the bytes it re-pushes, not local build time. Each change invalidates only its own layer:

| Change | Layers rebuilt and re-pushed | Order of magnitude (compressed) |
|--------|------------------------------|---------------------------------|
| Source edit in `src/` | `src` only | kilobytes |
| `pyproject.toml` or `uv.lock` | dependency sync, `.venv`, `src` | tens of MB |
| Anything outside `pyproject.toml`, `uv.lock` and `src/` | none (never copied into the image) | none |

Measure the current numbers with `docker history <image>` after a rebuild; layer sizes move with the dependency tree.

**Alternatives considered:**

| Approach | Why we don't use it |
|----------|---------------------|
| Single stage | Ships uv, its cache and build metadata in the runtime image |
| One `COPY /app .` in the runtime stage | A source edit re-pushes the whole venv layer |
| Installing the project into `.venv` | Writes source into `.venv`, so every source edit invalidates the venv layer |
| Bind mounts for dependency files | Same caching; saves only builder-stage bytes that never ship |
| uv distroless image as base | No shell for build commands |

---

## Summary

**Why our multi-stage COPY approach?**

1. **We can't use distroless uv image as base** → no shell to run build commands
2. **We still want official uv binary** → copy it from distroless image into python:slim
3. **We separate build from runtime** → no build tooling in the final image
4. **Dependencies and source in separate layers** → a source edit re-pushes kilobytes, not the venv
5. **COPY over bind mounts** → same caching, plainer pattern

**Key architectural decisions:**

| Component | Approach | Why |
|-----------|----------|-----|
| `uv` binary | Copy from distroless (pinned) | Reproducible builds, bump manually |
| Base image | `python:X.Y-slim` | Need shell + Python for build, minimal for runtime |
| Build pattern | Multi-stage | Discard uv, its cache and build metadata |
| Dependency caching | Cache mount | Skip re-downloading cached packages |
| Dependency files | **COPY both** | A change to either re-runs the sync |
| Project install | **None** (`--no-install-project`, run from `src/`) | `.venv` changes only with dependencies |
| Runtime copy | **`.venv` and `src` as separate layers** | A source edit invalidates only the `src` layer |
| Import path | **`PYTHONPATH=/app/src`** | Package importable without an install; `AGENT_DIR` default resolves to `/app/src` |

This gives us:
- ✅ Official uv binary (pinned for reproducible builds)
- ✅ Full build capabilities (shell, Python, package manager)
- ✅ Source edits re-push only the source layer
- ✅ Documentation updates don't trigger any layer rebuild
- ✅ Dependency changes always re-run the sync
- ✅ Runs as a non-root user

## Local Development

For local development workflow using Docker Compose (recommended), see [Docker Compose Workflow Guide](./docker-compose-workflow.md).

For direct Docker builds without Compose:
```bash
docker build -t your-agent-name:latest .
```

---

## References

### UV Documentation
- [UV Docker Integration Guide](https://docs.astral.sh/uv/guides/integration/docker/)
- [UV Docker Intermediate Layers (Bind Mounts)](https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers)
- [UV Documentation](https://docs.astral.sh/uv/)

### Docker Documentation
- [Docker Best Practices](https://docs.docker.com/build/building/best-practices/)
- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker RUN Command Reference](https://docs.docker.com/reference/dockerfile/#run)
- [BuildKit Cache Mounts](https://docs.docker.com/build/cache/optimize/)
- [Docker Best Practices: ADD or COPY (bind mounts)](https://docs.docker.com/build/building/best-practices/#add-or-copy)

### Docker Compose
- [Docker Compose Workflow Guide](./docker-compose-workflow.md) - Local development workflow
- [Docker Compose Watch Mode](https://docs.docker.com/compose/file-watch/)

---

← [Back to References](README.md) | [Documentation](../README.md)
