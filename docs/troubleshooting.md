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

**IAP tunnel connection failures:**
- Verify `roles/iap.tunnelResourceAccessor` is granted on your Google account
- Check `BASTION_INSTANCE` and `BASTION_ZONE` in `.env` match deployment outputs
- Confirm bastion VM is running: `gcloud compute instances describe $BASTION_INSTANCE --zone=$BASTION_ZONE`
- Check IAP tunnel container logs: `docker compose logs iap-tunnel`
- Verify gcloud config directory is readable: `ls -la ~/.config/gcloud/`

**Permission errors:**
- App container: Ensure `~/.config/gcloud/application_default_credentials.json` exists and is readable
- IAP tunnel: Ensure `~/.config/gcloud/` directory is readable (mounted as `/gcloud-config` via `CLOUDSDK_CONFIG`)

**Port already in use:**
```bash
# Check what's using port 8000
lsof -i :8000

# Stop the conflicting process or change PORT in .env
# (Update docker-compose.yml if changing port)
```

**Windows path compatibility:**
- `docker-compose.yml` uses `${HOME}` (Unix/Mac specific)
- Windows users need to update volume paths:
  - App container ADC: Replace `${HOME}/.config/gcloud/application_default_credentials.json` with Windows equivalent
  - IAP tunnel gcloud config: Replace `${HOME}/.config/gcloud` with Windows equivalent
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
- Auth Proxy sidecar crash (Cloud Run restarts automatically, check logs)
- VPC egress misconfiguration (Cloud SQL private IP unreachable)
- Missing or incorrect environment variables
- Credential initialization timeout (~30-60s for first request)

**Investigate:**

```bash
# 1. Check service logs for actual error
gcloud run services logs read <service-name> --region <region> --limit 50

# 2. Test locally with same config
docker compose up --build  # or: uv run server

# 3. Verify environment variables set correctly
gcloud run services describe <service-name> --region <region> --format="value(spec.template.spec.containers[0].env)"
```

### Cloud SQL Connectivity (Cloud Run)

**Symptom:** App fails to connect to Cloud SQL, database connection errors in logs

**Troubleshoot:**
1. Check that `roles/cloudsql.client` is granted to the app service account
2. Verify Cloud SQL instance is running with private IP enabled
3. Verify Cloud Run direct VPC egress is configured (check `vpc_access` in Terraform)
4. Check proxy sidecar logs for connection errors:
   ```bash
   gcloud run services logs read <service-name> --region <region> --limit 50
   ```
5. If using `db-f1-micro`, the shared-core instance may have slow connection accept times under load — consider upgrading the instance tier

### Bastion Host Health

**Symptom:** IAP tunnel connects but database queries fail

**Troubleshoot:**
1. SSH to bastion via IAP: `gcloud compute ssh <bastion-instance> --zone=<zone> --tunnel-through-iap`
2. Check Auth Proxy container: `docker ps` (Container-Optimized OS runs Docker)
3. Check Auth Proxy logs: `docker logs $(docker ps -q --filter name=cloud-sql-proxy)`
4. Verify bastion SA has `roles/cloudsql.client`
5. Confirm Cloud SQL instance private IP is reachable from the VPC subnet
6. Check COS iptables allows port 5432: `sudo iptables -L INPUT -n | grep 5432` — should show ACCEPT rule. COS default INPUT policy is DROP; the cloud-init `runcmd` must open port 5432 before starting the proxy.
7. Check proxy listens on all interfaces: `sudo ss -tlnp | grep 5432` — should show `*:5432` (all interfaces), not `127.0.0.1:5432`. The bastion proxy requires `--address=0.0.0.0` because IAP tunnel connections arrive from outside the loopback interface.
8. Verify bastion SA can impersonate app SA: the bastion SA needs `roles/iam.serviceAccountTokenCreator` on the app SA (granted via `google_service_account_iam_member` in Terraform). Without this, `--impersonate-service-account` fails.

**Common error:** `InvalidAuthorizationSpecificationError: Cloud SQL IAM service account authentication failed` — the bastion proxy cannot impersonate the app SA. Verify `roles/iam.serviceAccountTokenCreator` is granted to the bastion SA on the app SA.

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
