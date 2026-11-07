# Protection Strategies Reference

Branch, tag, and environment protection setup and rationale.

## Overview

Three protection layers ensure code quality and security:

1. **Branch Protection (main)** - Manual setup, requires PR approval and status checks
2. **Tag Protection (`prod-v*`)** - Automated by bootstrap (production mode), limits prod promotion to admins
3. **Environment Protection (prod, prod-apply)** - Automated by bootstrap from `terraform.tfvars`, approval gate for production

## Branch Protection (Manual Setup Required)

Main branch protection ensures code quality and prevents accidental commits to main.

### Prerequisites

- **Repository admin access** — only admins (or org owners) can configure branch protection rules.
- **Status check names must already exist before you can require them.** GitHub's required-status-check picker only offers check names it has seen at least once on the repository. If a workflow has never run, the check it produces won't appear as a selectable option. Three common paths:
  - *Existing repo:* the workflow is already on `main` and has run on prior pushes — the status check name is already in the picker.
  - *Fresh repo:* open a PR that adds `.github/workflows/ci.yml`. Workflows triggered by `pull_request` events run from the PR head ref (not the target branch), so the workflow runs on the PR even before protection is configured. After the first run completes, the status check name appears in the picker. Configure protection, then merge the PR.
  - *Migrating an existing repo to a renamed required check (like the `Required Checks / required-status` → `CI / status` rename):* open a PR with the new/renamed workflow. After the first run on the PR, edit the protection rule to add the new check name and remove the old one before merging. Doing the swap on the PR (rather than after merge) avoids a window where the rule references a check that no longer exists.

### What to Configure

1. **Require pull request before merging:**
   - Require approvals: 1 (minimum)
   - Dismiss stale reviews when new commits are pushed: ✅

2. **Require status checks to pass:**
   - Require branches to be up to date: ✅
   - Status checks required:
     - `CI / status` (from `.github/workflows/ci.yml`)

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
     - Search for and select: `CI / status`
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

A release is two tags on one commit: `vX.Y.Z` marks the release and deploys nothing, and `prod-vX.Y.Z` promotes it to prod. Bootstrap (`terraform/bootstrap/prod/`) creates the **Production Promotion Tag Protection** ruleset on `refs/tags/prod-v*`: only repository admins can create, move or delete a promotion tag, so only an admin can start the template's prod promotion pipeline. `v*` release tags have no ruleset, since pushing one deploys nothing.

> [!NOTE]
> The ruleset governs the template's pipeline, not every path to prod. The prod Workload Identity Federation provider is scoped to the repository, not to the GitHub environment, so a workflow on any branch of the repository can authenticate to the prod project.

### Verify

**GitHub UI:**
1. Settings → Rules → Rulesets
2. Confirm the ruleset exists: **Production Promotion Tag Protection**
3. Check details:
   - Enforcement: **Active**
   - Target: **Tags**
   - Patterns: `refs/tags/prod-v*`

**CLI:**
```bash
gh api repos/:owner/:repo/rulesets | jq '.[] | {name, enforcement, target}'
```

Expected output:
```json
{
  "name": "Production Promotion Tag Protection",
  "enforcement": "active",
  "target": "tag"
}
```

### Why Automated?

Tag protection is environment-specific infrastructure:
- Production mode **requires** tag protection (`prod-v*` tags trigger prod deployments)
- Dev-only mode **doesn't need** tag protection (no tag starts a deployment)

Bootstrap enforces this consistently based on deployment mode. No manual decision needed.

## Environment Protection (Automated)

Bootstrap creates and configures the `prod` and `prod-apply` GitHub Environments from `terraform/bootstrap/prod/terraform.tfvars`. Every bootstrap apply enforces those values, so change protection in `terraform.tfvars` and re-apply; a change made in the GitHub UI is reverted by the next apply. To set protection by hand outside bootstrap, see [Manual Environment Protection](manual-environment-protection.md).

### What Bootstrap Configures

| Setting | Environment | Source | Recommended |
|---|---|---|---|
| Deployment tag rule `prod-v*.*.*` | `prod`, `prod-apply` | Fixed in the prod root | Not configurable: the prod jobs only run on promotion tag pushes, so only a `prod-v*.*.*` tag can use either environment |
| Required reviewers | `prod-apply` | `prod_apply_reviewer_users` (GitHub logins), `prod_apply_reviewer_teams` (team slugs) | The users or teams who own production releases (up to six; one approval releases the job) |
| Prevent self-review | `prod-apply` | `prod_apply_prevent_self_review` | On for a team; off for a solo maintainer, who could otherwise never approve |
| Allow administrators to bypass | `prod-apply` | `prod_apply_can_admins_bypass` | Off for strict release control; on to keep a break-glass path |
| Wait timer | `prod-apply` | `prod_apply_wait_timer` (minutes) | Off (`null`), unless you want a cooling-off window |

The tag rule matches the promotion tag format the [tag ruleset](#tag-protection-automated) limits to admins, so only an admin-pushed promotion tag reaches the approval. `terraform.tfvars.example` sets a starting value for each variable; replace the placeholder reviewer with your own.

### Verify

**GitHub UI:** Settings → Environments → **prod-apply** shows the reviewers, the self-review and bypass settings, and the `prod-v*.*.*` tag rule under **Deployment branches and tags**. **prod** shows the same tag rule.

**CLI:**
```bash
gh api repos/:owner/:repo/environments/prod-apply --jq '{
  reviewers: [.protection_rules[] | select(.type == "required_reviewers") | .reviewers[] | {type, login: (.reviewer.login // .reviewer.slug)}],
  prevent_self_review: (.protection_rules[] | select(.type == "required_reviewers") | .prevent_self_review),
  wait_timer: ([.protection_rules[] | select(.type == "wait_timer") | .wait_timer][0] // 0),
  can_admins_bypass,
  deployment_branch_policy
}'
for env in prod prod-apply; do
  gh api repos/:owner/:repo/environments/$env/deployment-branch-policies --jq '[.branch_policies[] | {name, type}]'
done
```

Expected: the reviewers from `terraform.tfvars`, `custom_branch_policies: true`, and exactly one `{"name": "prod-v*.*.*", "type": "tag"}` policy per environment. A second policy (like an older `v*.*.*` rule created by hand) is not managed by bootstrap and keeps allowing those tags; delete it:

```bash
gh api repos/:owner/:repo/environments/prod-apply/deployment-branch-policies \
  --jq '.branch_policies[] | {id, name, type}'
gh api --method DELETE repos/:owner/:repo/environments/prod-apply/deployment-branch-policies/<policy-id>
```

### Private Repositories

GitHub gates environment protection by plan for private repositories ([deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)):

| Repository | Required reviewers, wait timer, admin bypass | Deployment branch and tag policy |
|---|---|---|
| Public, any plan | Available | Available |
| Private, GitHub Free | Not available | Not available |
| Private, GitHub Pro or Team | Not available | Available |
| Private, GitHub Enterprise | Available | Available |

On a private repository without GitHub Enterprise, leave `prod_apply_reviewer_users` and `prod_apply_reviewer_teams` empty.

> [!WARNING]
> On a private repository without GitHub Enterprise there is no approval gate: `prod-apply` deploys to production as soon as `prod-plan` finishes, with no reviewer prompt.

What still guards production on those plans:

- **`require-stage-success`.** `prod-promote` needs it, so a promotion tag deploys only a commit whose merge run passed `Apply Stage`, `Smoke Stage`, and `Judge Eval`. This holds on every plan because it is a job dependency, not an environment rule.
- **The deployment tag policy** (Pro and Team only). Only `prod-v*.*.*` tags reach `prod` and `prod-apply`.
- **Who can push a `prod-v*` tag.** The promotion tag ruleset limits this to admins where your plan enforces rulesets on private repositories; confirm it shows **Active** under Settings → Rules → Rulesets. Without it, anyone with write access can start the prod promotion pipeline.

To keep a human approval on a private fork, use GitHub Enterprise or make the repository public.

## How Approvals Work

### Production Deployment Flow

1. A release tag (`vX.Y.Z`) marks the commit and deploys nothing
2. After that commit's merge run passes its stage jobs, a repository admin pushes the promotion tag (`prod-vX.Y.Z`) on the same commit. Commands: [Infrastructure Guide: Deploy to Production](../infrastructure.md#deploy-to-production-production-mode)
3. GitHub Actions workflow starts. Metadata extraction fails unless the promotion tag has the form `prod-vX.Y.Z` and `vX.Y.Z` marks the same commit, and the tag must match the `prod-v*.*.*` tag rule to reach `prod` and `prod-apply`
4. Jobs run sequentially:
   - Resolve image digest from stage
   - Promote image to prod registry
   - Run Terraform plan for prod
5. **prod-apply job waits for approval** (requires `prod-apply` Environment configured reviewer from approved list)
6. Configured reviewer sees notification: "Review deployments waiting"
7. Reviewer checks:
   - Deployment logs and outputs
   - Plan changes
   - Staging environment validation
8. Reviewer approves or rejects
9. If approved: Terraform apply runs, deploys to production
10. If rejected: Workflow fails, no deployment

> [!NOTE]
> A tag that doesn't match the `prod-v*.*.*` tag rule is blocked by the environment before the approval prompt.

### Approving a Deployment

**GitHub UI:**
1. Go to **Actions** tab
2. Click on the waiting workflow run
3. Click **Review deployments** button
4. Select environment: `prod-apply`
5. Add comment (optional but recommended): "LGTM - staging validation passed"
6. Click **Approve and deploy** or **Reject**

**CLI:** `gh` has no approval subcommand, but the [pending deployments API](https://docs.github.com/en/rest/actions/workflow-runs#review-pending-deployments-for-a-workflow-run) approves as any required reviewer:

```bash
# Find the waiting run
gh run list --workflow=ci-cd.yml --status waiting

# Show what it is waiting on
gh api repos/:owner/:repo/actions/runs/<run-id>/pending_deployments \
  --jq '.[] | {environment: .environment.name, id: .environment.id}'

# Approve (or "rejected")
ENV_ID=$(gh api repos/:owner/:repo/environments/prod-apply --jq .id)
gh api --method POST repos/:owner/:repo/actions/runs/<run-id>/pending_deployments \
  -F "environment_ids[]=${ENV_ID}" -f state=approved -f comment="Stage validation passed"
```

## Protection Strategy Summary

| Protection | Type | When | Why |
|------------|------|------|-----|
| Branch (main) | Manual | After repo creation | Team-specific workflow preferences |
| Tags (`prod-v*`) | Automated | Bootstrap (prod mode) | Environment-specific requirement |
| Environments (prod, prod-apply) | Automated | Bootstrap (prod mode), from `terraform.tfvars` | Reviewers are a human decision recorded in code and enforced on every apply |

---

← [Back to References](README.md) | [Documentation](../README.md)
