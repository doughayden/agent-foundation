# Infrastructure

Deployment, CI/CD, and infrastructure management.

> [!IMPORTANT]
> Complete bootstrap setup and configure protection rules before deploying in Production Mode.

## Bootstrap Setup

Bootstrap creates CI/CD infrastructure one time per environment:
- Workload Identity Federation (keyless GitHub Actions auth)
- Artifact Registry (Docker images with cleanup policies)
- Terraform State Bucket (remote state for main module)
- GitHub Environments and Variables
- Tag protection and cross-project IAM (production mode)

First time? See [Getting Started](getting-started.md) for complete walkthrough including prerequisites.

Setting up production mode or need full detail? See [Bootstrap Reference](references/bootstrap.md).

## Protection Strategies

Configure protection rules after bootstrap (manual setup):

**Branch Protection (main):**
1. Settings → Branches → Add rule for `main`
2. Require PR with 1 approval, dismiss stale reviews
3. Require status checks: `Required Checks / required-status`
4. No force pushes, no deletions

**Tag Protection (production mode, automated):**
- Bootstrap creates ruleset protecting `v*` tags
- Verify: Settings → Rules → Rulesets

**Environment Protection (production mode, manual):**
1. Settings → Environments → prod-apply
2. Configure Required reviewers
3. Add users/teams who can approve production deployments

See [Protection Strategies](references/protection-strategies.md) for detailed UI setup and rationale.

## Deployment Modes

**Dev-Only Mode:**
- Single GCP project, single environment
- Workflow: PR → plan, Merge → deploy to dev
- Use: Experiments, prototypes, internal tools

**Production Mode:**
- Three GCP projects (dev/stage/prod)
- Workflow: PR → plan, Merge → dev+stage, Tag → prod (approval required)
- Use: Production services, staged deployment, compliance

**Switch modes:** Edit `production_mode` in `.github/workflows/ci-cd.yml`

See [Deployment Modes](references/deployment.md) for mode comparison, workflow details, and switching instructions.

## Workflow Behavior

What GitHub Actions does at each trigger:

**PR Flow:**
- Builds Docker image → pushes to dev registry as `pr-{number}-{sha}`
- Runs Terraform plan for dev
- Comments plan on PR
- No deployment

**Merge Flow (dev-only mode):**
- Builds image → pushes as `{sha}`, `latest`
- Deploys to dev

**Merge Flow (production mode):**
- Builds image → pushes to dev registry
- Deploys to dev and stage (parallel after build)

**Tag Flow (production mode):**
- Resolves image from stage registry
- Promotes to prod registry
- Deploys to prod (requires approval in prod-apply environment)

See [CI/CD Workflows](references/cicd.md) for workflow architecture, job details, and customization.

## Deployment Operations

### Deploy to Dev (Automatic)

Create PR and merge to main:
```bash
# Create feature branch
git checkout -b feat/your-feature

# Make changes, commit
git add .
git commit -m "feat: add new feature"

# Push and create PR
git push origin feat/your-feature
gh pr create

# After approval, merge PR (via GitHub UI or CLI)
gh pr merge --squash
```

GitHub Actions automatically builds and deploys to dev (+ stage in production mode) when PR is merged.

Monitor: Actions tab → CI/CD Pipeline

### Enable Dev Deployment on Pull Request (Optional)

> [!NOTE]
> By default, the pipeline deploys to dev only on merge to main. Enable PR deploys to deploy dev on every PR for immediate feedback in live environment.

**Impact:**
- Every PR and commit deploys to dev (concurrency prevents simultaneous deploys: new commits cancel in-progress PR deploys)
- Dev becomes unstable (last PR wins)
- Requires team coordination for concurrent PRs
- Useful for complex integrations requiring live environment testing

**Enable:** Change `.github/workflows/ci-cd.yml` line 98:
```yaml
# From:
if: github.ref_type == 'branch' && github.event_name == 'push'

# To:
if: github.ref_type == 'branch'
```

### Deploy to Production (Production Mode)

> [!IMPORTANT]
> Requires manual approval gate setup: Repository admin must configure required reviewers for `prod-apply` environment (Settings → Environments → prod-apply → Required reviewers). See [Protection Strategies](references/protection-strategies.md).

1. Ensure dev and stage deployments successful
2. Create and push annotated tag:
   ```bash
   git checkout main
   git pull
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```
3. Monitor workflow: Actions tab → CI/CD Pipeline
4. **Repository admin or approved reviewer:** Actions → prod-apply job → Review deployments → Approve
5. Verify production deployment

### Rollback (Production)

**Strategy 1: Cloud Run Traffic Split (instant)**

Requires GCP access:
```bash
# List revisions
gcloud run revisions list --service=<service> --region=<region>

# Rollback to previous
gcloud run services update-traffic <service> \
  --to-revisions=<previous-revision>=100 \
  --region=<region>
```

**Strategy 2: Hotfix + Tag (10-20 min)**

No GCP access needed:
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
```

See [Troubleshooting](troubleshooting.md) for detailed rollback decision tree.

## Monitoring Deployments

### View Workflow Status

**GitHub Actions UI:**
1. Actions tab → CI/CD Pipeline
2. Click run to view:
   - Job summaries (deployment outputs, Cloud Run URL, resources)
   - Individual job logs
   - PR plan comments

**GitHub CLI:**
```bash
# List recent runs
gh run list --workflow=ci-cd.yml --limit 5

# View specific run
gh run view <run-id>

# View logs
gh run view <run-id> --log
```

### Trace Deployed Image

```bash
# Get deployed image
IMAGE=$(gcloud run services describe <service> \
  --region <region> \
  --format='value(spec.template.spec.containers[0].image)')

# Get commit SHA (first tag)
gcloud artifacts docker images describe "$IMAGE" \
  --format="value(tags)" | cut -d',' -f1
```

### View Traces and Logs

**Cloud Console:**
- Cloud Trace → Trace Explorer
- Logs Explorer

See [Observability](observability.md) for query examples and trace analysis.

## Terraform Structure

**Bootstrap Module** (`terraform/bootstrap/{dev,stage,prod}/`):
- One-time CI/CD infrastructure per environment (WIF, Artifact Registry, state bucket, GitHub environments/variables)
- Local state, runs manually by infrastructure owners

**Main Module** (`terraform/main/`):
- Application deployment: Cloud Run, service account, Agent Engine, GCS bucket
- Remote state (bucket created by bootstrap), runs automatically in CI/CD

See [Deployment Modes: Terraform Structure](references/deployment.md#terraform-structure) for resource details and naming conventions.

## Image Promotion (Production Mode)

Production mode promotes images between registries instead of rebuilding, ensuring exact tested bytes deploy across environments:

**Dev → Stage:** Triggered on merge to main
**Stage → Prod:** Triggered on tag push (requires manual approval)

Cross-project IAM for promotion is configured automatically during bootstrap.

See [Deployment Modes: Image Promotion](references/deployment.md#image-promotion) for promotion details and cross-project IAM.

---

← [Back to Documentation](README.md)
