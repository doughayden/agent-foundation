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
- Code changes: Sync and restart the app within a few seconds via watch mode
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
# (Update compose.yml if changing port)
```

**Windows path compatibility:**
- `compose.yml` uses `${HOME}` (Unix/Mac specific)
- Windows users need to update volume paths:
  - App container ADC: Replace `${HOME}/.config/gcloud/application_default_credentials.json` with Windows equivalent
  - IAP tunnel gcloud config: Replace `${HOME}/.config/gcloud` with Windows equivalent
  - Or use `%USERPROFILE%` in PowerShell

### Customized Dockerfile

The shipped Dockerfile never installs the project: it runs the package from `/app/src` via `PYTHONPATH=/app/src` (`docs/references/dockerfile-strategy.md` explains why). Installing the project, like uv's stock Dockerfile does, changes that.

**Build fails with `failed to open file /app/README.md`:**
- `pyproject.toml` declares `readme = "README.md"`, so building the project package needs the file
- Keep the project uninstalled (`uv sync --no-install-project`), or copy `README.md` into the builder before the install step

**Web UI or `/list-apps` shows every installed package as an agent:**
- Cause: the project is installed and `PYTHONPATH` no longer points at `/app/src`, so Python imports the package from `.venv/lib/pythonX.Y/site-packages/`. `server.py` derives `AGENT_DIR` from its own location, which then points ADK at site-packages
- Check: `docker compose exec app python -c 'import agent_foundation; print(agent_foundation.__file__)'` prints a site-packages path
- The same cause breaks watch mode: Compose syncs edits to `/app/src`, but the running code is the installed copy
- Fix: restore `PYTHONPATH=/app/src` (with or without the install, `/app/src` then comes first on the import path), or set `AGENT_DIR=/app/src` to fix only the agent listing

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
- `ci.yml` has no path filter, so it runs on every push and pull request; `ci-cd.yml` and `deploy-docs.yml` both filter
- Only `prod-v*` promotion tags start `ci-cd.yml`, and they run regardless of paths. A `v*` release tag alone starts nothing
- GitHub creates no push event for tags when more than three tags arrive in one push ([push event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#push)), so `git push origin --tags` with several releases starts nothing. Push each promotion tag on its own
- `ci-cd.yml` filters in two layers: `paths-ignore` exclusions on the trigger prevent the CI/CD workflow from running on docs or local development changes, and the `changes` job's `deploy` and `eval` filters select which downstream jobs run when the change set passes exclusion. No run at all points at the `paths-ignore` exclusions; a run where everything after `Detect Changes` skipped points at the `changes` job filters. See [CI/CD Reference: Path filtering](references/cicd.md#ci-cdyml-orchestrator)

**Verify branch protection:**
```bash
# Check branch protection rules
gh api repos/:owner/:repo/branches/main/protection
```

### Promotion Tag Fails at Extract Build Metadata

**Symptom:** a `prod-vX.Y.Z` run fails in `Extract Build Metadata` with one of:
- `Promotion tag <tag> does not have the form <env>-vX.Y.Z`: the tag is not a promotion tag for a semantic version, like `prod-v1.0` or `prod-v1.0.0+build.5`. Delete it (repository admin) and push a correctly named one
- `Promotion tag prod-vX.Y.Z needs release tag vX.Y.Z on the same commit`: see the causes below

**Cause:** the promotion tag names a release tag that does not exist, or that marks a different commit. No prod deploy job starts (`Require Stage Success` still runs, since it needs only the workflow configuration).

**Fix when the release tag is missing:** release-please creates `vX.Y.Z` in the `Release` workflow run on the release pull request's merge commit. If that pull request merged and the promotion tag marks its merge commit, the run is still in progress or failed (an uninstalled App or a revoked private key): wait for it, or fix the App and re-run it, then use **Re-run failed jobs** on the failed promotion run.

If the release pull request has not merged, the promotion tag went out before that merge and sits on a commit that will never be the release commit. Leave the release tag to release-please rather than creating it by hand. Delete the promotion tag (repository admin), merge the release pull request, and promote the release commit once its merge run passes stage ([Release a Version](releasing.md#promote-to-production-production-mode)).
```bash
git push origin :refs/tags/prod-v1.0.1
git tag -d prod-v1.0.1
```

**Fix when releasing without the App:** if the promotion tag marks the commit you meant to release, create the release tag there, then use **Re-run failed jobs** on the failed run. The re-run checks out the repository again and finds the new tag ([Release Without the App](releasing.md#release-without-the-app)).
```bash
git tag -a v1.0.1 'prod-v1.0.1^{commit}' -m "Release v1.0.1"
git push origin v1.0.1
```

**Fix when the release tag marks a different commit:** the promotion tag is on the wrong commit. Leave the release tag where it is, delete the promotion tag (repository admin), and recreate it on the release commit. Fetch the release tag first: `git fetch` never overwrites a local tag, so a stale local `v1.0.1` would rebuild the same mistake.
```bash
git fetch origin --force tag v1.0.1
git push origin :refs/tags/prod-v1.0.1
git tag -d prod-v1.0.1
git tag -a prod-v1.0.1 'v1.0.1^{commit}' -m "Promote v1.0.1 to prod"
git push origin prod-v1.0.1
```

### GCP Auth Rejected or Environment Blocked

**Symptom:** a job fails in `google-github-actions/auth` with `The given credential is rejected by the attribute condition`, or never starts with `Branch "<branch>" is not allowed to deploy to <environment> due to environment protection rules`.

**Cause:** each environment's WIF provider accepts only tokens from jobs that declare one of its GitHub Environments, and `stage`, `prod` and `prod-apply` accept only the refs their deployment rules allow ([Security Posture](references/security-posture.md) Identity Layer).

**Fix:** add `environment: <env>` to the job that authenticates. A job on a ref the environment rejects belongs on an allowed ref (`main` or a `prod-v*` tag); to allow another ref, add a pattern in the environment's bootstrap root and re-apply it.

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
docker compose up --build  # Same image and backends; needs the deployed-resource values in .env

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
5. If connection timeouts occur under load, upgrade the instance tier in `database.tf` or enable managed connection pooling (Enterprise Plus edition). See [Cloud SQL Scaling](./infrastructure.md#cloud-sql-scaling)

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

### ADC quota project and billing errors

**Symptom:** Terraform fails to read its GCS state with a 403 `UserProjectAccountProblem` or a billing account error.

The gcloud CLI and Application Default Credentials (ADC) use separate credentials. ADC login can set a quota project from the current gcloud configuration, but changing the CLI project later does not update an existing ADC quota project. A quota project without active billing can cause API requests to fail.

Check that billing is enabled on the intended project and set it as the ADC quota project:

```bash
gcloud billing projects describe YOUR_DEV_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_DEV_PROJECT_ID
```

Setting the quota project requires `serviceusage.services.use`, included in `roles/serviceusage.serviceUsageConsumer`. The quota project determines quota and billing attribution for applicable client API requests. It does not enable billing or change where Terraform creates resources. If the error persists, check the state bucket's project and billing status too. See [Google Cloud authentication](https://cloud.google.com/docs/authentication/application-default-credentials#personal) and the [ADC quota-project command](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/set-quota-project).

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
2. `.env` file (read by `ServerEnv` and ADK's agent loader)
3. Default values in code (lowest priority)

**Debug:**
```bash
# Check .env file
cat .env

# Check environment
env | grep GOOGLE_

# Verify what the server resolves (the environment wins over .env)
uv run python -c "from agent_foundation.config import ServerEnv; print(ServerEnv().google_cloud_project)"
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
- `OTEL_SDK_DISABLED=true` in the shell or `.env`, which turns all export off. Startup still prints the usual telemetry lines, since the SDK, not the template, reads the variable
- Wrong project ID or missing authentication
- Logs queried under the wrong log name: application logs land in `otlp`, GenAI events in `gen_ai.client.inference.operation.details`
- Normal delay: Traces and logs take 1-2 minutes to appear in Cloud Console

**Debug:**
```bash
# Check telemetry settings in .env and the shell
cat .env | grep OTEL_
env | grep OTEL_
cat .env | grep GOOGLE_

# Verify auth
gcloud auth application-default login

# Export errors print to the console; debug logging adds more detail
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
│     └─→ Strategy 2: Hotfix + Release (10-20 minutes)
│
├─ Bad container image (won't start, missing dependencies)
│  │
│  ├─ Old revision exists + have GCP access?
│  │  └─→ Strategy 1: Cloud Run Traffic Split (instant)
│  │
│  └─ No old revision or no GCP access?
│     └─→ Strategy 2: Hotfix + Release (10-20 minutes)
│
├─ Configuration regression (wrong env vars, feature flags)
│  │
│  ├─ Config in GitHub Environment variables?
│  │  └─→ Manual GitHub UI edit + re-trigger deployment
│  │
│  └─ Config in application code?
│     └─→ Strategy 2: Hotfix + Release
│
└─ Infrastructure regression (IAM, GCS, Cloud Run config)
   └─→ Strategy 2: Infrastructure Hotfix + Release
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

### Strategy 2: Hotfix + Release (10-20 minutes)

**When to use:** No GCP access, or need to fix config/code permanently

**Steps:** revert or fix on a branch, merge the PR, then release the fix as a new version (`v1.0.1`, then `prod-v1.0.1` once the merge run's stage jobs pass) and approve the `prod-apply` job. Commands: [Release a Version: Hotfixes and Rollback](releasing.md#hotfixes-and-rollback).

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
