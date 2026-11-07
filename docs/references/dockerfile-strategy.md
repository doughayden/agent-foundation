# Dockerfile Strategy Explained

How and why to build a multi-stage uv Dockerfile.

## Table of Contents

- [Overview](#overview)
- [Dockerfile Breakdown](#dockerfile-breakdown)
- [Why We COPY Instead of Using Bind Mounts](#why-we-copy-instead-of-using-bind-mounts)
- [Rebuild and Push Cost](#rebuild-and-push-cost)
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

**Why not `ghcr.io/astral-sh/uv` as base?**
- Astral's uv image is **distroless**: it contains only the `uv` and `uvx` binaries, so there is no shell to run `RUN` commands
- It's designed to copy the binary FROM, not build FROM

---

### Copy UV Binary
```dockerfile
COPY --from=ghcr.io/astral-sh/uv:X.Y.Z /uv /uvx /bin/
```
**What:** Extract just the `uv` and `uvx` binaries from Astral's image
**Why:**
- Pinned to an exact version for reproducible, deterministic builds (bump procedure: `docs/development.md` uv Version)
- Copies two binaries, not a whole base image
- Puts them in `/bin/` so they're in PATH

---

### Working Directory
```dockerfile
WORKDIR /app
```
**What:** Both stages work in `/app`. Each `FROM` starts a fresh filesystem, so the runtime stage sets it again.

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
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev
```
**What:** Install dependencies WITHOUT installing the project itself
**Why:** This is the only install step. The project is never installed, so `.venv` holds dependencies only and changes only when `pyproject.toml` or `uv.lock` does.

| Flag | Meaning | Benefit |
|------|---------|---------|
| `--mount=type=cache` | Persist `/root/.cache/uv` across builds | Don't re-download packages already cached |
| `--locked` | Validate lockfile matches pyproject.toml | Fails the build on a stale lockfile |
| `--no-install-project` | Skip installing the project package | `.venv` stays independent of source edits |
| `--no-dev` | Skip dev dependencies | Smaller image |

**Why `--locked`, not `--frozen`:** a `uv.lock` that no longer matches `pyproject.toml` is a broken config. `--locked` fails the build loudly so it gets fixed; `--frozen` trusts the lockfile blindly, stale or not, so a mismatch ships undetected. The Dockerfile and every CI `uv sync` use `--locked`, as does uv's own GitHub Actions example.

```bash
# A dependency was added to pyproject.toml without re-running uv lock
$ docker build .
error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
$ uv lock && docker build .  # succeeds
```

**What the cache mount buys:** packages already downloaded are not fetched again. The gain is modest: most of a dependency install goes to unpacking and byte-compiling, not downloading. It also persists only on the same builder: `cache-to` exports layers, not cache mounts, so each CI run on a fresh runner starts with an empty uv cache ([Docker GitHub Actions cache](https://docs.docker.com/build/ci/github-actions/cache/)). Registry layer cache still skips the whole sync when `pyproject.toml` and `uv.lock` are unchanged.

---

### Runtime Stage Base
```dockerfile
FROM python:X.Y-slim AS runtime
```
**What:** Start fresh with clean Python image for runtime
**Why:**
- uv, its cache and the dependency files stay in the builder stage
- Runtime has only Python, `.venv` (from the builder) and `src/` (from the build context)

---

### Non-Root User
```dockerfile
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
```
**What:** Create a non-root user named `app` with a fixed UID and GID of 10001
**Why:** The server doesn't need root, so it doesn't run as root

**Command breakdown:**
- `groupadd -g 10001 app`: Create the `app` group with GID 10001
- `useradd -u 10001 -g app -M -s /usr/sbin/nologin app`: Create the `app` user with UID 10001 in that group
- `-M`: Create no home directory; the server writes nothing to `~/`
- `-s /usr/sbin/nologin`: The account has no login shell, so `su app` or any login as `app` is refused. `docker exec` and the `CMD` start their own process and never read the account's shell, so the server and debugging sessions are unaffected

**Why a fixed ID:** volume mounts and file ownership on shared storage key on the numeric UID and GID, so a pinned value gives them a stable target that doesn't shift with the base image's user list. 10001 sits outside the range Linux hosts assign to people (the first user is usually 1000), so the container process never shares an ID with a host account. On native Linux Docker, a bind-mounted host file readable only by your host user (like a `0600` credentials file) may be unreadable to UID 10001.

---

### Copy Virtual Environment and Source
```dockerfile
COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --chown=app:app src ./src
```
**What:** Copy the dependencies from the builder and the source straight from the build context, as two layers
**Why:**
- Each `COPY` produces one layer, and any change to its content invalidates the whole layer. The `.venv` layer is hundreds of MB; the `src` layer is tens of kB
- A source edit rebuilds and re-pushes only the `src` layer; the `.venv` layer stays cached locally and in the registry. Copying `/app` in one layer would re-export and re-push the whole venv on every source edit
- `--chown=app:app`: Make the `app` user own both
- Only `src/` comes from the build context: documentation, tests and config changes never invalidate a layer
- **uv, `pyproject.toml` and `uv.lock` are NOT copied** (needed only to build)

**Running from source:** the package is imported from `/app/src` (see `PYTHONPATH` below), so code that locates files relative to `__file__` sees the same `src/<package>/` layout as a local checkout. Without a project install, the container venv has no `[project.scripts]` console scripts and no package metadata for the project (`importlib.metadata` cannot find it): start the app with `python -m`, and don't read the project's version from installed metadata at runtime.

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
| `PYTHONPATH=/app/src` | Import the package from source, since the project is not installed |
| `HOST=0.0.0.0` | Bind all interfaces so the server accepts connections from outside the container |
| `PORT=8000` | Default port, matching `EXPOSE` |

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
**What:** Document the server's listening port (the `PORT` default above)
**Why:**
- Documentation only: it publishes nothing. Compose publishes through `ports:` in `compose.yml`, Cloud Run through the service's container port
- `docker run -P` publishes exposed ports to random host ports

---

### Startup Command
```dockerfile
CMD ["python", "-m", "<package>.server"]
```
**What:** Default command when container starts
**Why:**
- `python -m` runs the module directly, so no console script is needed (the project isn't installed)
- Exec form (JSON array): Python runs as PID 1 and receives `SIGTERM` directly; the shell form would wrap it in `/bin/sh -c`, which does not pass signals ([Dockerfile reference](https://docs.docker.com/reference/dockerfile/#cmd))

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

---

## Rebuild and Push Cost

Once images build in CI and push to a registry, the cost of a change is the bytes it re-pushes, not local build time. Each change invalidates only its own layer and those after it:

| Change | Layers rebuilt and re-pushed | Order of magnitude (compressed) |
|--------|------------------------------|---------------------------------|
| Source edit in `src/` | `src` only | kilobytes |
| `pyproject.toml` or `uv.lock` | dependency sync, `.venv`, `src` | tens of MB |
| Anything outside `pyproject.toml`, `uv.lock` and `src/` | none (never copied into the image) | none |

Compressed sizes are the `size` of each layer in the image's platform manifest in the registry; `docker history` shows uncompressed sizes. Layer sizes move with the dependency tree.

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

| Component | Approach | Why |
|-----------|----------|-----|
| `uv` binary | Copy from distroless (pinned) | Reproducible builds, bump manually |
| Base image | `python:X.Y-slim` | Need shell + Python for build, minimal for runtime |
| Build pattern | Multi-stage | Discard uv, its cache and build metadata |
| Dependency caching | Cache mount | Skip re-downloading cached packages |
| Dependency files | **COPY both** | A change to either re-runs the sync |
| Project install | **None** (`--no-install-project`, run from `src/`) | `.venv` changes only with dependencies |
| Runtime copy | **`.venv` and `src` as separate layers** | A source edit invalidates only the `src` layer |
| Import path | **`PYTHONPATH=/app/src`** | Package importable without an install |
| Runtime user | **Fixed UID/GID 10001, no login shell** | Non-root, stable ownership, matches no host account |

## Local Development

To run the image locally against deployed resources with Docker Compose, see [Docker Compose Workflow](docker-compose-workflow.md).

---

## References

### UV Documentation
- [UV Docker Integration Guide](https://docs.astral.sh/uv/guides/integration/docker/)
- [UV Docker Intermediate Layers (Bind Mounts)](https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers)

### Docker Documentation
- [Docker Best Practices](https://docs.docker.com/build/building/best-practices/)
- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker RUN Command Reference](https://docs.docker.com/reference/dockerfile/#run)
- [BuildKit Cache Mounts](https://docs.docker.com/build/cache/optimize/)
- [Docker Best Practices: ADD or COPY (bind mounts)](https://docs.docker.com/build/building/best-practices/#add-or-copy)

### Docker Compose
- [Docker Compose Workflow](docker-compose-workflow.md) - Run a local agent against deployed resources
- [Docker Compose Watch Mode](https://docs.docker.com/compose/file-watch/)

---

← [Back to References](README.md) | [Documentation](../README.md)
