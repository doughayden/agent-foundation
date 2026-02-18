# Protection Strategies Reference

Branch, tag, and environment protection setup and rationale.

## Overview

Three protection layers ensure code quality and security:

1. **Branch Protection (main)** - Manual setup, requires PR approval and status checks
2. **Tag Protection (v*)** - Automated by bootstrap (production mode), prevents tag manipulation
3. **Environment Protection (prod-apply)** - Manual reviewers, approval gate for production

## Branch Protection (Manual Setup Required)

Main branch protection ensures code quality and prevents accidental commits to main.

### What to Configure

1. **Require pull request before merging:**
   - Require approvals: 1 (minimum)
   - Dismiss stale reviews when new commits are pushed: ✅

2. **Require status checks to pass:**
   - Require branches to be up to date: ✅
   - Status checks required:
     - `Required Checks / required-status` (from `.github/workflows/required-checks.yml`)

3. **Do not allow bypassing settings:**
   - Allow specific actors to bypass: Repository admins only

4. **Other settings:**
   - ❌ Require linear history (optional, not required)
   - ❌ Allow force pushes (keep disabled)
   - ❌ Allow deletions (keep disabled)

### How to Configure (GitHub UI)

1. Go to repository **Settings** → **Branches**
2. Click **Add branch protection rule**
3. Enter branch name pattern: `main`
4. Configure protection settings:
   - ✅ **Require a pull request before merging**
     - Required approvals: `1`
     - ✅ Dismiss stale pull request approvals when new commits are pushed
   - ✅ **Require status checks to pass before merging**
     - ✅ Require branches to be up to date before merging
     - Search for and select: `Required Checks / required-status`
   - ✅ **Do not allow bypassing the above settings**
     - Allow specific actors to bypass: Repository admins (optional)
   - ❌ Require linear history (optional)
   - ❌ Allow force pushes (disabled)
   - ❌ Allow deletions (disabled)
5. Click **Create** or **Save changes**

### Verify

**GitHub UI:**
1. Settings → Branches
2. Confirm `main` branch protection rule exists
3. Check rule shows: 1 required approval, required status checks, dismiss stale reviews

**CLI:**
```bash
gh api repos/:owner/:repo/branches/main/protection | jq '{
  pr_reviews: .required_pull_request_reviews.required_approving_review_count,
  dismiss_stale: .required_pull_request_reviews.dismiss_stale_reviews,
  status_checks: .required_status_checks.contexts
}'
```

### Why Manual?

Branch protection rules are repository-wide policy decisions that vary by team workflow. Terraform would override manual adjustments on every apply.

Different teams may want:
- Different approval counts (1 vs 2)
- Different required status checks
- Different bypass permissions
- CODEOWNERS enforcement

Bootstrap can't predict these preferences, so we make it a manual configuration step.

## Tag Protection (Automated)

Production tag protection is **automatically configured** by bootstrap in production mode.

### What Bootstrap Creates

Bootstrap (`terraform/bootstrap/prod/`) creates a `github_repository_ruleset` that protects `v*` tags:

**Protection rules:**
- Prevents: tag creation, update, deletion by non-admins
- Prevents: force pushes to tags
- Allows: Repository admins to bypass (for tag management)

**Ruleset configuration:**
- Name: "Production Release Tag Protection"
- Target: Tags matching `refs/tags/v*`
- Enforcement: Active

### Verify

**GitHub UI:**
1. Settings → Rules → Rulesets
2. Confirm ruleset exists: **Production Release Tag Protection**
3. Check details:
   - Enforcement: **Active**
   - Target: **Tags**
   - Patterns: `refs/tags/v*`

**CLI:**
```bash
gh api repos/:owner/:repo/rulesets | jq '.[] | {name, enforcement, target}'
```

Expected output:
```json
{
  "name": "Production Release Tag Protection",
  "enforcement": "active",
  "target": "tag"
}
```

### Why Automated?

Tag protection is environment-specific infrastructure:
- Production mode **requires** tag protection (tags trigger prod deployments)
- Dev-only mode **doesn't need** tag protection (tags just version dev deployments)

Bootstrap enforces this consistently based on deployment mode. No manual decision needed.

## Environment Protection (Manual Approval Setup Required)

The `prod-apply` GitHub Environment requires manual approval before production deployments.

### What Bootstrap Creates

**Automated by bootstrap (production mode):**
- GitHub Environment: `prod-apply`
- Environment variables scoped to `prod-apply`

**Bootstrap does NOT configure:**
- Required reviewers (manual setup required)
- Wait timer
- Deployment branch policy

### What You Must Configure Manually

**Required reviewers** - Users or teams who can approve production deployments.

**How to configure:**

1. Go to **Settings** → **Environments** → **prod-apply**
2. Under **Deployment protection rules**:
   - ✅ Check **Required reviewers**
   - Click **Add reviewers** search box
   - Add individual users (e.g., tech leads, SREs) or teams (e.g., @org/platform-team)
   - **Optional:** Check **Prevent self-review** (requires different approver than workflow trigger)
   - **Optional:** Check **Wait timer** and set delay (e.g., 5 minutes before allowing approval)
   - **Optional:** Check **Allow administrators to bypass** (admin override for emergencies)
3. Click **Save protection rules**
4. Under **Deployment branches and tags**:
   - Click dropdown → Select **Selected branches and tags**
   - Add branch rule: `main` (only main branch can trigger prod deployments)
   - Add tag rule: `v*.*.*` or `v*` (version tags can trigger prod deployments)
5. Click **Save protection rules**

### Verify

**GitHub UI:**
1. Settings → Environments
2. Confirm `prod-apply` environment exists
3. Click on `prod-apply` to view details
4. Check **Deployment protection rules** shows:
   - Required reviewers configured
   - Wait timer (if enabled)
   - Self-review prevention (if enabled)
5. Check **Deployment branches and tags** shows:
   - Branch rule: `main`
   - Tag rule: `v*.*.*` or `v*`

**CLI:**
```bash
gh api repos/:owner/:repo/environments/prod-apply | jq '{
  name: .name,
  protection_rules: .protection_rules
}'
```

Expected output shows non-empty `reviewers` array.

### Why Manual?

Reviewer selection is a **human security decision** that changes over time:

- Team composition changes (new hires, departures, role changes)
- Responsibility shifts (different teams own production approvals)
- Organization structure evolves

Bootstrap creates the environment, but your team decides who can approve production deployments. The bootstrap module explicitly ignores reviewer changes (`lifecycle.ignore_changes`) to prevent Terraform from overwriting your manual selections.

## How Approvals Work

### Production Deployment Flow

1. Repository Admin (allowed to bypass tag protection ruleset) pushes tag matching allowed pattern: `git tag -a v1.0.0 -m "Release v1.0.0" && git push origin v1.0.0`
2. GitHub Actions workflow starts (tag must match `v*.*.*` or `v*` pattern configured in environment)
3. Jobs run sequentially:
   - Resolve image digest from stage
   - Promote image to prod registry
   - Run Terraform plan for prod
4. **prod-apply job waits for approval** (requires `prod-apply` Environment configured reviewer from approved list)
5. Configured reviewer sees notification: "Review deployments waiting"
6. Reviewer checks:
   - Deployment logs and outputs
   - Plan changes
   - Staging environment validation
7. Reviewer approves or rejects
8. If approved: Terraform apply runs, deploys to production
9. If rejected: Workflow fails, no deployment

**Note:** If tag doesn't match allowed pattern or workflow triggered from non-main branch, deployment to `prod-apply` environment will be blocked by environment rules.

### Approving a Deployment

**GitHub UI:**
1. Go to **Actions** tab
2. Click on the waiting workflow run
3. Click **Review deployments** button
4. Select environment: `prod-apply`
5. Add comment (optional but recommended): "LGTM - staging validation passed"
6. Click **Approve and deploy** or **Reject**

**CLI:**
```bash
# View pending deployments
gh run list --workflow=ci-cd.yml | grep "waiting"

# Approve deployment (requires GitHub UI, no CLI support for approval)
```

**Note:** GitHub CLI doesn't support approving deployments. Use the GitHub UI.

## Protection Strategy Summary

| Protection | Type | When | Why |
|------------|------|------|-----|
| Branch (main) | Manual | After repo creation | Team-specific workflow preferences |
| Tag (v*) | Automated | Bootstrap (prod mode) | Environment-specific requirement |
| Environment (prod-apply) | Manual reviewers | After prod bootstrap | Human security decision, changes over time |

---

← [Back to References](README.md) | [Documentation](../README.md)
