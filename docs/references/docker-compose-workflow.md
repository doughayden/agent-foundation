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

## IAP Tunnel to Bastion

Docker Compose uses an IAP tunnel container to reach the bastion host, which runs Cloud SQL Auth Proxy. This mirrors the production architecture where Cloud Run connects to Cloud SQL via private IP, but substitutes IAP tunneling for direct VPC egress.

**Architecture:**
```
App container (localhost:5432) ──► IAP tunnel container ──► IAP ──► Bastion VM (Auth Proxy) ──► Cloud SQL private IP
```

The bastion Auth Proxy binds to `0.0.0.0` (not loopback) to accept IAP tunnel connections arriving from outside the loopback interface. It also uses `--impersonate-service-account=<app-sa-email>` to authenticate to Cloud SQL as the app SA, since the bastion runs under its own dedicated SA. These flags are bastion-specific — the Cloud Run sidecar uses the defaults (loopback binding, runs as app SA directly).

**IAP tunnel container** (`gcr.io/google.com/cloudsdktool/google-cloud-cli:stable`):
- Uses `network_mode: "service:app"` to share the app container's network namespace — the tunnel binds to `0.0.0.0:5432` which appears as `localhost:5432` from the app's perspective
- Runs `gcloud compute start-iap-tunnel` targeting the bastion host on port 5432
- Requires `BASTION_INSTANCE`, `BASTION_ZONE`, and `GOOGLE_CLOUD_PROJECT` in `.env`

**Credentials:** Mounts `~/.config/gcloud` to `/gcloud-config` with `CLOUDSDK_CONFIG=/gcloud-config` (decouples from container home directory). IAP tunnel requires full gcloud CLI config, not just Application Default Credentials.

**Developer IAM prerequisite:** `roles/iap.tunnelResourceAccessor` on your Google account. Without this role, the IAP tunnel fails with a permission denied error.

**Port:** `5432` on the app container's localhost. The app connects to `localhost:5432` identically to Cloud Run, where the Auth Proxy sidecar also listens on the same address.

**Requires:** `BASTION_INSTANCE` and `BASTION_ZONE` set in `.env` (get from deployment job summary or `terraform output bastion_instance` / `terraform output bastion_zone`).

---

## File Locations

### Source Code
- **Host:** `./src/`
- **Container:** `/app/src`
- **Sync:** Automatic via watch mode

### Credentials
- **App container:** `~/.config/gcloud/application_default_credentials.json` mounted read-only at `/gcloud/application_default_credentials.json` — for Vertex AI and Cloud SQL IAM auth via `GOOGLE_APPLICATION_CREDENTIALS`
- **IAP tunnel container:** Full `~/.config/gcloud/` directory mounted (writable) at `/gcloud-config/` with `CLOUDSDK_CONFIG=/gcloud-config` — decouples from container home directory, writable because gcloud CLI writes token cache and logs at runtime, IAP tunnel requires full gcloud CLI config beyond ADC

---

## Environment Variables

Docker Compose loads `.env` automatically. See [Environment Variables Guide](../environment-variables.md) for details on required and optional variables.

**Note:** The container uses `HOST=0.0.0.0` to allow connections from the host machine.

---

## Troubleshooting

See [Troubleshooting: Docker Compose](../troubleshooting.md#docker-compose) for container restart issues, IAP tunnel failures, permission errors, port conflicts, and Windows path compatibility.

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
