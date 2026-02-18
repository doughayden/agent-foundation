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

### Terraform State Lock

See [Terraform State Lock](#state-lock-timeout) in Terraform section below.

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

### Startup Failures

**Symptom:** Cloud Run service won't start, health check timeout

**Common causes:**

**Investigate:**

```bash
# 1. Check service logs for actual error
gcloud run services logs read <service-name> --region <region> --limit 50

# 2. Test locally with same config
docker compose up --build  # or: uv run server

# 3. Verify environment variables set correctly
gcloud run services describe <service-name> --region <region> --format="value(spec.template.spec.containers[0].env)"
```

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

### Trace/Log Data Not Appearing

**Common causes:**
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` not set to `TRUE`
- Wrong project ID or missing authentication
- Normal delay: Traces and logs take 1-2 minutes to appear in Cloud Console

**Debug:**
```bash
# Check required configuration
cat .env | grep OTEL_
cat .env | grep GOOGLE_

# Verify auth
gcloud auth application-default login

# Run with debug logging to see OTEL errors
LOG_LEVEL=DEBUG uv run server
```

## Rollback Strategies

### Rollback Decision Tree

```
Production issue detected?
│
├─ App code regression (crashes, errors, bad behavior)
│  │
│  ├─ Have direct GCP prod access?
│  │  └─→ Strategy 1: Cloud Run Traffic Split (instant)
│  │
│  └─ No direct GCP access?
│     └─→ Strategy 2: Hotfix + Tag (10-20 minutes)
│
├─ Bad container image (won't start, missing dependencies)
│  │
│  ├─ Old revision exists + have GCP access?
│  │  └─→ Strategy 1: Cloud Run Traffic Split (instant)
│  │
│  └─ No old revision or no GCP access?
│     └─→ Strategy 2: Hotfix + Tag (10-20 minutes)
│
├─ Configuration regression (wrong env vars, feature flags)
│  │
│  ├─ Config in GitHub Environment variables?
│  │  └─→ Manual GitHub UI edit + re-trigger deployment
│  │
│  └─ Config in application code?
│     └─→ Strategy 2: Hotfix + Tag
│
└─ Infrastructure regression (IAM, GCS, Cloud Run config)
   └─→ Strategy 2: Infrastructure Hotfix + Tag
```

### Strategy 1: Cloud Run Traffic Split (Instant)

**When to use:** App code or image regression, have direct GCP access, old revision exists

**Steps:**
```bash
# List revisions
gcloud run revisions list --service=<service-name> --region=<region>

# Split traffic (instant rollback to previous revision)
gcloud run services update-traffic <service-name> \
  --to-revisions=<previous-revision>=100 \
  --region=<region>
```

**Pros:**
- Instant rollback (seconds)
- No rebuild or redeployment
- Can quickly test or roll forward again

**Cons:**
- Requires GCP access
- Only works if old revision still exists
- Doesn't fix root cause (need follow-up)

### Strategy 2: Hotfix + Tag (10-20 minutes)

**When to use:** No GCP access, or need to fix config/code permanently

**Steps:**
```bash
# Create hotfix branch
git checkout -b hotfix/revert-bad-change

# Revert or cherry-pick fix
git revert <bad-commit>

# Push and create PR
git push origin hotfix/revert-bad-change
gh pr create

# After approval, merge PR
gh pr merge --squash

# Tag for production (annotated)
git checkout main
git pull
git tag -a v1.0.1 -m "Hotfix: revert bad change"
git push origin v1.0.1

# Approve in prod-apply when workflow runs
```

**Pros:**
- Works without GCP access
- Fixes root cause (proper git history)
- Goes through full CI/CD pipeline (validation)

**Cons:**
- Takes 10-20 minutes
- Requires PR approval + prod deployment approval
- Slower than traffic split

---

← [Back to Documentation](README.md)
