# Docker Compose Local Development Workflow

This guide covers the recommended workflow for local development using Docker Compose.

## Quick Start

### Daily Development (Recommended)

```bash
docker compose up --build --watch
```

**Why both flags?**
- `--build`: Ensures you have the latest code and dependencies
- `--watch`: Enables file sync with auto-restart for fast feedback

**What happens:**
- Container starts with your latest code
- Watch mode monitors your files for changes
- Edits to `src/` files are **synced instantly** (no rebuild needed)
- Changes to `pyproject.toml` or `uv.lock` **trigger automatic rebuild**

**Leave it running** while you develop - changes are applied automatically!

---

## Common Commands

### Start with file sync and auto-restart (default workflow)
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
    # Sync + restart: Instant file copy, editable install resolves imports
    - action: sync+restart
      path: ./src
      target: /app/src

    # Rebuild: Triggers full image rebuild
    - action: rebuild
      path: ./pyproject.toml

    - action: rebuild
      path: ./uv.lock
```

### Sync + Restart Action
- **Triggers when:** You edit files in `src/`
- **What happens:** Files are synced into running container, then container restarts
- **Speed:** ~2-5 seconds (no rebuild)
- **Use case:** Code changes during development

### Rebuild Action
- **Triggers when:** You edit `pyproject.toml` or `uv.lock`
- **What happens:** Full image rebuild, container recreated
- **Speed:** ~5-10 seconds (with cache)
- **Use case:** Dependency changes

---

## Cloud SQL Auth Proxy Sidecar

Docker Compose runs a Cloud SQL Auth Proxy sidecar alongside the app container, matching the Cloud Run deployment architecture 1:1. The proxy provides IAM-authenticated connectivity to Cloud SQL without database passwords.

**Proxy flags:**
- `--auto-iam-authn` — IAM database auth via Application Default Credentials
- `--health-check` + `--http-port=9090` — enables `/startup`, `/liveness`, `/readiness` endpoints
- `--structured-logs` — JSON logging (matches Cloud Logging format)
- `--exit-zero-on-sigterm` — clean shutdown (exit code 0 on SIGTERM)
- `--credentials-file` — mounted ADC file (Cloud Run uses SA identity natively instead)

**Healthcheck:** Uses the proxy's built-in `wait` subcommand (`cloud-sql-proxy wait --max=5s`), which checks the `/startup` endpoint. Works in distroless images (no `wget`/`curl` needed). App container starts only after the proxy confirms connectivity to Cloud SQL.

**Port:** `5432` on localhost (mapped to host for optional direct database access via `psql`).

**Startup timing:** `start_period=5s`, `interval=5s`, `timeout=5s`, `retries=3` (~20s total). The proxy typically connects within 2-5s (TLS handshake + IAM token exchange). The 5s start period allows for initial startup, and 3 retries at 5s intervals provide headroom for slow networks or cold Cloud SQL instances. Values match the Cloud Run sidecar probe (`initial_delay_seconds=5`, `period_seconds=5`, `failure_threshold=3`) for dev/prod parity.

**Requires:** `CLOUD_SQL_INSTANCE_CONNECTION_NAME` set in `.env` (get from deployment job summary or `terraform output cloud_sql_instance_connection_name`).

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
