# Docker Compose Local Development Workflow

This guide covers the recommended workflow for local development using Docker Compose.

## Quick Start

### Daily Development (Recommended)

```bash
docker compose up --build --watch
```

**Why both flags?**
- `--build`: Ensures you have the latest code and dependencies
- `--watch`: Enables hot reloading for instant feedback

**What happens:**
- Container starts with your latest code
- Watch mode monitors your files for changes
- Edits to `src/` files are **synced instantly** (no rebuild needed)
- Changes to `pyproject.toml` or `uv.lock` **trigger automatic rebuild**

**Leave it running** while you develop - changes are applied automatically!

---

## Common Commands

### Start with hot reloading (default workflow)
```bash
docker compose up --build --watch
```

### Stop the service
```bash
# Press Ctrl+C to gracefully stop
# Or in another terminal:
docker compose down
```

### View logs
```bash
# If running in detached mode
docker compose logs -f

# View just the app logs
docker compose logs -f app
```

### Rebuild without starting
```bash
docker compose build
```

### Run without watch mode
```bash
docker compose up --build
```

---

## How Watch Mode Works

Watch mode uses the configuration in `docker-compose.yml`:

```yaml
develop:
  watch:
    # Sync: Instant file copy, no rebuild
    - action: sync
      path: ./src
      target: /app/src

    # Rebuild: Triggers full image rebuild
    - action: rebuild
      path: ./pyproject.toml

    - action: rebuild
      path: ./uv.lock
```

### Sync Action
- **Triggers when:** You edit files in `src/`
- **What happens:** Files are copied into running container instantly
- **Speed:** Immediate (no rebuild)
- **Use case:** Code changes during development

### Rebuild Action
- **Triggers when:** You edit `pyproject.toml` or `uv.lock`
- **What happens:** Full image rebuild, container recreated
- **Speed:** ~5-10 seconds (with cache)
- **Use case:** Dependency changes

---

## File Locations

### Source Code
- **Host:** `./src/`
- **Container:** `/app/src`
- **Sync:** Automatic via watch mode

### Credentials
- **Host:** `~/.config/gcloud/`
- **Container:** `/gcloud/`
- **Mount:** Read-only volume
- **Purpose:** Secure access for the local development to Application Default Credentials for Google authentication

### Data Directory
- **Host:** `./data/`
- **Container:** `/app/data` (read-only)
- **Purpose:** Optional data files for agent

---

## Environment Variables

Docker Compose loads `.env` automatically. See [Environment Variables Guide](../environment-variables.md) for details on required and optional variables.

**Note:** The container uses `HOST=0.0.0.0` to allow connections from the host machine.

---

## Troubleshooting

### Container keeps restarting
- Check logs: `docker compose logs -f`
- Verify `.env` file exists and has required variables
- Ensure Application Default Credentials are configured: `gcloud auth application-default login`

### Changes not appearing
- **For code changes:** Should sync instantly via watch mode
- **For dependency changes:** Watch should auto-rebuild
- **If stuck:** Stop and restart with `docker compose up --build --watch`

### Permission errors
- Data directory: Mounted read-only, should not need write access
- Credentials: Ensure `~/.config/gcloud/application_default_credentials.json` exists and is readable

### Port already in use
```bash
# Check what's using port 8000
lsof -i :8000

# Stop the conflicting process or change PORT in .env
PORT=8001
```

### Windows path compatibility
- The `docker-compose.yml` uses `${HOME}` which is Unix/Mac specific
- Windows users need to update the volume path in `docker-compose.yml`:
  - Replace `${HOME}/.config/gcloud/application_default_credentials.json`
  - With your Windows path: `C:\Users\YourUsername\AppData\Roaming\gcloud\application_default_credentials.json`
- Alternative: Use `%USERPROFILE%` environment variable in PowerShell
- See the comment in `docker-compose.yml` for the exact syntax

---

## Testing Registry Images

For rare cases when you need to test the exact image from CI/CD:

```bash
# Authenticate once
gcloud auth configure-docker us-central1-docker.pkg.dev

# Set your image
export REGISTRY_IMAGE="us-central1-docker.pkg.dev/project/repo/app:sha123"

# Pull and run with docker-compose
docker pull $REGISTRY_IMAGE
docker compose run -e IMAGE=$REGISTRY_IMAGE app
```

**Alternative - direct run:**
```bash
docker run --rm \
  -v ./data:/app/data:ro \
  -v ~/.config/gcloud/application_default_credentials.json:/gcloud/application_default_credentials.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/gcloud/application_default_credentials.json \
  -p 127.0.0.1:8000:8000 \
  --env-file .env \
  $REGISTRY_IMAGE
```

---

## Direct Docker Commands (Without Compose)

If you need to build and run without docker-compose:

```bash
# Build the image with BuildKit
DOCKER_BUILDKIT=1 docker build -t your-agent-name:latest .

# Run directly
docker run \
  -v ./data:/app/data:ro \
  -p 127.0.0.1:8000:8000 \
  --env-file .env \
  your-agent-name:latest
```

**Note:** Docker Compose is recommended - it handles volumes, environment, and networking automatically.

---

## References

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Docker Compose Watch Mode](https://docs.docker.com/compose/file-watch/)
- [Dockerfile Strategy Guide](./dockerfile-strategy.md) - Architecture decisions and design rationale

---

← [Back to References](README.md) | [Documentation](../README.md)
