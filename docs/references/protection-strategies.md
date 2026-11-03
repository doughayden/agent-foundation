# Protection Strategies Reference

Branch, tag, and environment protection setup and rationale.

## Overview

Three protection layers ensure code quality and security:

1. **Branch Protection (main)** - Manual setup, requires PR approval and status checks
2. **Tag Protection (v*)** - Automated by bootstrap (production mode), prevents tag manipulation
3. **Environment Protection (prod-apply)** - Manual reviewers, approval gate for production

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

**Bootstrap does NOT configure** (the module lists these in `lifecycle.ignore_changes`, so a later bootstrap apply never overwrites them):
- Required reviewers
- Prevent self-review
- Wait timer
- Deployment branch and tag policy

Admin bypass is on by default for a new environment.

### What to Configure

| Setting | Recommended | Why |
|---|---|---|
| Required reviewers | The users or teams who own production releases (up to six; one approval releases the job) | The approval gate itself |
| Prevent self-review | On for a team; off for a solo maintainer | Stops the person who pushed the tag from approving their own deployment. A solo maintainer who turns it on can never approve |
| Wait timer | Off, unless you want a cooling-off window | Delays the job after approval is requested |
| Allow administrators to bypass | Off for strict release control; on to keep a break-glass path | An admin can deploy without an approval |
| Deployment branches and tags | **Selected branches and tags**, with tag rule `v*.*.*` | The `prod-apply` job only runs on tag pushes, so GitHub checks the rule against a `refs/tags/...` ref. Leave out a `main` branch rule: it never matches a prod run, and it would let any future job that targets `prod-apply` on a main push deploy |

The tag rule matches the release tag format the [tag ruleset](#tag-protection-automated) protects, so only a protected version tag can reach the approval.

### Configure in the GitHub UI

1. Go to **Settings** → **Environments** → **prod-apply**
2. Under **Deployment protection rules**:
   - Check **Required reviewers** and add users or teams
   - Set **Prevent self-review** per the table above
   - Optionally set **Wait timer**
   - Set **Allow administrators to bypass** per the table above
3. Click **Save protection rules**
4. Under **Deployment branches and tags**, select **Selected branches and tags** and add a tag rule `v*.*.*`
5. Click **Save protection rules**

### Configure with `gh api`

The [environments REST API](https://docs.github.com/en/rest/deployments/environments) sets the protection rules in one `PUT`, and the [deployment branch policies API](https://docs.github.com/en/rest/deployments/branch-policies) adds the tag rule.

```bash
# Look up the reviewer's numeric ID (a team: gh api orgs/<org>/teams/<team-slug> --jq .id)
REVIEWER_ID=$(gh api users/<github-login> --jq .id)

# Reviewers, self-review, wait timer, and a custom branch/tag policy
gh api --method PUT repos/:owner/:repo/environments/prod-apply --input - <<EOF
{
  "reviewers": [{"type": "User", "id": ${REVIEWER_ID}}],
  "prevent_self_review": false,
  "wait_timer": 0,
  "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}
}
EOF

# Allow only version tags to deploy
gh api --method POST repos/:owner/:repo/environments/prod-apply/deployment-branch-policies \
  -f name='v*.*.*' -f type=tag
```

The `PUT` body has no admin-bypass field: set **Allow administrators to bypass** in the UI.

### Verify

**GitHub UI:** Settings → Environments → **prod-apply** shows the reviewers, the self-review and bypass settings, and the `v*.*.*` tag rule under **Deployment branches and tags**.

**CLI:**
```bash
gh api repos/:owner/:repo/environments/prod-apply --jq '{
  reviewers: [.protection_rules[] | select(.type == "required_reviewers") | .reviewers[] | {type, login: (.reviewer.login // .reviewer.slug)}],
  prevent_self_review: (.protection_rules[] | select(.type == "required_reviewers") | .prevent_self_review),
  wait_timer: ([.protection_rules[] | select(.type == "wait_timer") | .wait_timer][0] // 0),
  can_admins_bypass,
  deployment_branch_policy
}'
gh api repos/:owner/:repo/environments/prod-apply/deployment-branch-policies \
  --jq '[.branch_policies[] | {name, type}]'
```

Expected: a non-empty `reviewers` list, `custom_branch_policies: true`, and a `{"name": "v*.*.*", "type": "tag"}` policy.

### Private Repositories

GitHub gates environment protection by plan for private repositories ([deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)):

| Repository | Required reviewers, wait timer, admin bypass | Deployment branch and tag policy |
|---|---|---|
| Public, any plan | Available | Available |
| Private, GitHub Free | Not available | Not available |
| Private, GitHub Pro or Team | Not available | Available |
| Private, GitHub Enterprise | Available | Available |

> [!WARNING]
> On a private repository without GitHub Enterprise there is no approval gate: `prod-apply` deploys to production as soon as `prod-plan` finishes, with no reviewer prompt.

What still guards production on those plans:

- **`require-stage-success`.** `prod-promote` needs it, so a tag deploys only a commit whose merge run passed `Apply Stage`, `Smoke Stage`, and `Judge Eval`. This holds on every plan because it is a job dependency, not an environment rule.
- **The deployment tag policy** (Pro and Team only). Only `v*.*.*` tags reach `prod-apply`.
- **Who can push a `v*` tag.** The tag ruleset limits this to admins where your plan enforces rulesets on private repositories; confirm it shows **Active** under Settings → Rules → Rulesets. Without it, anyone with write access can push a release tag.

To keep a human approval on a private fork, use GitHub Enterprise or make the repository public.

### Why Manual?

Reviewer selection is a **human security decision** that changes over time:

- Team composition changes (new hires, departures, role changes)
- Responsibility shifts (different teams own production approvals)
- Organization structure evolves

Bootstrap creates the environment, but your team decides who can approve production deployments. The bootstrap module explicitly ignores reviewer changes (`lifecycle.ignore_changes`) to prevent Terraform from overwriting your manual selections.

## How Approvals Work

### Production Deployment Flow

1. Repository Admin (allowed to bypass tag protection ruleset) pushes tag matching allowed pattern: `git tag -a v1.0.0 -m "Release v1.0.0" && git push origin v1.0.0`
2. GitHub Actions workflow starts (the tag must match the environment's `v*.*.*` tag rule to reach `prod-apply`)
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

**Note:** A tag that doesn't match the `v*.*.*` tag rule is blocked by the environment before the approval prompt.

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
| Tag (v*) | Automated | Bootstrap (prod mode) | Environment-specific requirement |
| Environment (prod-apply) | Manual reviewers | After prod bootstrap | Human security decision, changes over time |

---

← [Back to References](README.md) | [Documentation](../README.md)
