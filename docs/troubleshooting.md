# Troubleshooting

Common issues and solutions.

## Local Development

### Docker Compose

**Container keeps restarting:**
```bash
# Check logs
docker compose logs -f

# Verify .env file
cat .env | grep GOOGLE_

# Ensure gcloud auth configured
gcloud auth application-default login
```

**Changes not appearing:**
- Code changes: Should sync instantly via watch mode
- Dependency changes: Watch should auto-rebuild
- If stuck: Stop and restart with `docker compose up --build --watch`

**Permission errors:**
- Data directory: Mounted read-only, should not need write access
- Credentials: Ensure `~/.config/gcloud/application_default_credentials.json` exists and is readable

**Port already in use:**
```bash
# Check what's using port 8000
lsof -i :8000

# Stop the conflicting process or change PORT in .env
# (Update docker-compose.yml if changing port)
```

**Windows path compatibility:**
- `docker-compose.yml` uses `${HOME}` (Unix/Mac specific)
- Windows users need to update volume path:
  - Replace `${HOME}/.config/gcloud/application_default_credentials.json`
  - With Windows path: `C:\Users\YourUsername\AppData\Roaming\gcloud\application_default_credentials.json`
  - Or use `%USERPROFILE%` in PowerShell

### Direct Execution (uv run server)

**Import errors:**
```bash
# Reinstall dependencies
uv sync --locked

# Check virtual environment
uv run python -c "import sys; print(sys.prefix)"
```

**Vertex AI authentication failed:**
```bash
# Verify gcloud auth
gcloud auth application-default login

# Check project set correctly
gcloud config get-value project

# Verify .env variables
cat .env | grep GOOGLE_
```

**Module not found:**
```bash
# Ensure project installed
uv sync --locked

# Verify PYTHONPATH (usually not needed with uv)
uv run python -c "import sys; print(sys.path)"
```

## CI/CD

### Missing Variables

```bash
# Verify Variables exist
gh variable list

# Re-run bootstrap if missing
terraform -chdir=terraform/bootstrap/dev apply
```

### WIF Authentication Failed

```bash
# Check WIF provider
terraform -chdir=terraform/bootstrap/dev output -raw workload_identity_provider

# Verify IAM bindings
gcloud projects get-iam-policy <project-id> \
  --flatten="bindings[].members" \
  --filter="bindings.members:principalSet*"
```

### Image Push Denied

```bash
# Verify artifactregistry.writer role
gcloud projects get-iam-policy <project-id> \
  --flatten="bindings[].members" \
  --filter="bindings.role:roles/artifactregistry.writer"
```

### PR Comment Not Posted

Ensure workflow has `pull-requests: write` permission in `.github/workflows/ci-cd.yml`.

### Build Cache Miss

Verify `buildcache` tag protected by cleanup policy in bootstrap module.

### Terraform State Lock

```bash
# Find stuck runs
gh run list --workflow=ci-cd.yml --limit 10

# Cancel run if needed
gh run cancel <run-id>

# Last resort: force unlock (dangerous)
terraform -chdir=terraform/main force-unlock <lock-id>
```

### Workflow Not Triggering

**Check path filters:**
- Workflows ignore documentation-only changes
- See `ci-cd.yml` for complete path list
- Tag triggers (`v*`) always run regardless of paths

**Verify branch protection:**
```bash
# Check branch protection rules
gh api repos/:owner/:repo/branches/main/protection
```

## Cloud Run

### Health Check Failures

**Symptom:** Cloud Run service won't start, health check timeout

**Common causes:**

1. **Credential initialization taking too long:**
   - Default probe config allows ~120s total (failure_threshold=5, period_seconds=20, initial_delay_seconds=20)
   - Vertex AI credential init can take 30-60s
   - Check logs: `gcloud logging tail "resource.type=cloud_run_revision"`

2. **Wrong port:**
   - Cloud Run always uses port 8000
   - Verify `PORT` env var not overridden in Terraform

3. **Startup error:**
   ```bash
   # Check Cloud Run logs
   gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=<service-name>" --limit 100
   ```

**Solutions:**

```bash
# 1. Check service logs for actual error
gcloud run services logs read <service-name> --region <region> --limit 50

# 2. Test locally with same config
docker compose up --build

# 3. Verify environment variables set correctly
gcloud run services describe <service-name> --region <region> --format="value(spec.template.spec.containers[0].env)"
```

### Permission Errors

**Symptom:** Cloud Run service can't access GCS, Vertex AI, or other GCP services

**Check service account permissions:**
```bash
# Get service account email
SA=$(gcloud run services describe <service-name> --region <region> --format="value(spec.template.spec.serviceAccountName)")

# List IAM roles
gcloud projects get-iam-policy <project-id> \
  --flatten="bindings[].members" \
  --filter="bindings.members:$SA"
```

**Required roles:**
- `roles/aiplatform.user` - Vertex AI access
- `roles/storage.objectUser` - GCS bucket access
- See `terraform/main/main.tf` for complete list

### Image Not Updating

**Symptom:** Deployed new version but old code still running

**Cause:** Cloud Run uses image digest, not tag. Pushing same tag without new digest doesn't trigger update.

**Solution:**
- CI/CD always pushes by digest (correct)
- If manually deploying, use digest not tag:
  ```bash
  # Wrong (might use cached revision)
  gcloud run deploy --image=registry/image:latest

  # Right (forces new revision)
  IMAGE_DIGEST=$(gcloud artifacts docker images describe registry/image:latest --format="value(image_summary.digest)")
  gcloud run deploy --image=registry/image@${IMAGE_DIGEST}
  ```

### Cold Start Latency

**Symptom:** First request after idle period is slow

**Expected behavior:**
- Cloud Run scales to zero when idle
- First request triggers cold start (~5-15s)
- Vertex AI credential init adds ~30-60s on first request

**Mitigations:**
1. Increase `min-instances` in Terraform (costs more)
2. Use Cloud Scheduler to ping health endpoint periodically
3. Accept cold start latency (zero cost when idle)

## Terraform

### State Lock Timeout

```bash
# Find who holds the lock
gsutil cat gs://<state-bucket>/main/default.tflock

# If GitHub Actions run is stuck/cancelled, force unlock
terraform -chdir=terraform/main force-unlock <lock-id>

# WARNING: Only force unlock if you're certain no other process is running
```

### Plan Drift Detected

**Symptom:** Terraform plan shows unexpected changes

**Common causes:**
1. Manual changes in GCP Console
2. Another deployment modified resources
3. Terraform state out of sync

**Solutions:**
```bash
# 1. Check what changed
terraform -chdir=terraform/main plan

# 2. If manual changes were intentional, import them
terraform -chdir=terraform/main import <resource> <id>

# 3. If drift is unwanted, apply to restore desired state
terraform -chdir=terraform/main apply
```

### Bootstrap State Lost

**Symptom:** Bootstrap terraform.tfstate file missing or corrupted

**Recovery:**
1. **Resources still exist:** Import existing resources into new state
   ```bash
   terraform -chdir=terraform/bootstrap/dev import google_artifact_registry_repository.main <project>/<location>/<repository>
   # Repeat for other resources
   ```

2. **Clean slate:** Delete all bootstrap resources and re-run
   ```bash
   # WARNING: This will break existing deployments until re-bootstrapped
   # Delete WIF, registry, state bucket manually in GCP Console
   terraform -chdir=terraform/bootstrap/dev apply
   ```

## General

### Environment Variable Not Set

**Symptom:** Error about missing required environment variable

**Check precedence:**
1. Environment variables (highest priority)
2. `.env` file (loaded via python-dotenv)
3. Default values in code (lowest priority)

**Debug:**
```bash
# Check .env file
cat .env

# Check environment
env | grep GOOGLE_

# Verify loaded in Python
uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('GOOGLE_CLOUD_PROJECT'))"
```

### Version Conflicts

**Symptom:** Dependency version errors or import failures

**Solutions:**
```bash
# Sync dependencies from lockfile
uv sync --locked

# If lockfile stale, regenerate
uv lock

# Update specific package
uv lock --upgrade-package <package-name>

# Nuclear option: delete .venv and reinstall
rm -rf .venv
uv sync --locked
```

### gcloud Command Not Found

**macOS/Linux:**
```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

**Verify installation:**
```bash
which gcloud
gcloud version
```

### Trace/Log Data Not Appearing

**Check:**
1. **OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT set?**
   ```bash
   echo $OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
   ```

2. **Correct project ID?**
   ```bash
   gcloud config get-value project
   ```

3. **Authentication configured?**
   ```bash
   gcloud auth application-default login
   ```

4. **Check for errors:**
   ```bash
   # Look for OTEL export errors
   LOG_LEVEL=DEBUG uv run server
   ```

**Delay:** Traces and logs can take 1-2 minutes to appear in Cloud Console after generation.

## See Also

- [Development](development.md) - Local development setup
- [CI/CD](cicd.md) - GitHub Actions workflows
- [Deployment](deployment.md) - Cloud Run deployment
- [Environment Variables](environment-variables.md) - Configuration reference
- [Observability](observability.md) - Traces and logs
