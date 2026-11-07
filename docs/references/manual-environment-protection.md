# Manual Environment Protection

Configure the `prod-apply` approval gate by hand in the GitHub UI or with `gh api`, for repositories whose environments bootstrap does not manage.

Bootstrap configures environment protection from `terraform/bootstrap/prod/terraform.tfvars` and `terraform/bootstrap/stage/main.tf` ([Protection Strategies](protection-strategies.md#environment-protection-automated)). Use this page when you set protection on an environment outside that root, or when you need the raw API calls to inspect or repair a setting.

> [!WARNING]
> In a repository where `terraform/bootstrap/prod` and `terraform/bootstrap/stage` manage the environments, every bootstrap apply reverts settings made here to the values in those roots. Make lasting changes there, or the next apply undoes them.

## Settings

| Setting | Recommended | Why |
|---|---|---|
| Required reviewers | The users or teams who own production releases (up to six; one approval releases the job) | The approval gate itself |
| Prevent self-review | On for a team; off for a solo maintainer | Stops the person who pushed the promotion tag from approving their own deployment. A solo maintainer who turns it on can never approve |
| Wait timer | Off, unless you want a cooling-off window | Delays the job after approval is requested |
| Allow administrators to bypass | Off for strict release control; on to keep a break-glass path | An admin can deploy without an approval |
| Deployment branches and tags | **Selected branches and tags**, with tag rule `prod-v*.*.*` | Prod jobs only run on promotion tag pushes, so GitHub checks the rule against a `refs/tags/...` ref. Leave out a `main` branch rule: it never matches a prod run, and it would let any future job that targets the environment on a main push deploy |

Apply the same tag rule to the `prod` environment, which `prod-promote`, `prod-plan` and `prod-smoke` target, so a tag outside the promotion format cannot reach prod credentials through those jobs. Give the `stage` environment a `main` branch rule and the same tag rule: stage jobs run on pushes to `main`, and promotion runs read the stage registry under `stage`. Each environment's WIF provider trusts only its environments' tokens, so these rules decide which refs can reach the stage and prod projects.

## Configure in the GitHub UI

1. Go to **Settings** → **Environments** → **prod-apply**
2. Under **Deployment protection rules**:
   - Check **Required reviewers** and add users or teams
   - Set **Prevent self-review** per the table above
   - Optionally set **Wait timer**
   - Set **Allow administrators to bypass** per the table above
3. Click **Save protection rules**
4. Under **Deployment branches and tags**, select **Selected branches and tags** and add a tag rule `prod-v*.*.*`
5. Click **Save protection rules**
6. Repeat step 4 for the **prod** environment
7. For the **stage** environment, select **Selected branches and tags**, add a branch rule `main` and a tag rule `prod-v*.*.*`, and save

## Configure with `gh api`

The [environments REST API](https://docs.github.com/en/rest/deployments/environments) sets the protection rules in one `PUT`, and the [deployment branch policies API](https://docs.github.com/en/rest/deployments/branch-policies) adds the tag rule.

> [!WARNING]
> The `PUT` replaces the environment's reviewers, self-review setting and wait timer with the body's values. Include every reviewer you want to keep, or they are removed.

```bash
# Look up the reviewer's numeric ID (a team: gh api orgs/<org>/teams/<team-slug> --jq .id)
REVIEWER_ID=$(gh api users/<github-login> --jq .id)

# Reviewers, self-review, wait timer, and a custom branch/tag policy.
# prevent_self_review is false for a solo maintainer; set it to true for a team
gh api --method PUT repos/:owner/:repo/environments/prod-apply --input - <<EOF
{
  "reviewers": [{"type": "User", "id": ${REVIEWER_ID}}],
  "prevent_self_review": false,
  "wait_timer": 0,
  "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}
}
EOF

# Allow only promotion tags to deploy
gh api --method POST repos/:owner/:repo/environments/prod-apply/deployment-branch-policies \
  -f name='prod-v*.*.*' -f type=tag
```

The `PUT` body has no admin-bypass field: set **Allow administrators to bypass** in the UI.

To replace an existing tag rule, list the rules, delete the old one by ID, then add the new one:

```bash
gh api repos/:owner/:repo/environments/prod-apply/deployment-branch-policies \
  --jq '.branch_policies[] | {id, name, type}'
gh api --method DELETE repos/:owner/:repo/environments/prod-apply/deployment-branch-policies/<policy-id>
gh api --method POST repos/:owner/:repo/environments/prod-apply/deployment-branch-policies \
  -f name='prod-v*.*.*' -f type=tag
```

For the `prod` environment, the same calls apply with `prod` in place of `prod-apply`; send only `deployment_branch_policy` in its `PUT` body. For `stage`, send the same `deployment_branch_policy` body, add the same tag rule, and add a branch rule:

```bash
gh api --method POST repos/:owner/:repo/environments/stage/deployment-branch-policies \
  -f name='main' -f type=branch
```

## Verify

**GitHub UI:** Settings → Environments → **prod-apply** shows the reviewers, the self-review and bypass settings, and the `prod-v*.*.*` tag rule under **Deployment branches and tags**.

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

Expected: a non-empty `reviewers` list, `custom_branch_policies: true`, and a `{"name": "prod-v*.*.*", "type": "tag"}` policy.

Plan availability for private repositories is in [Protection Strategies](protection-strategies.md#private-repositories).

---

← [Back to References](README.md) | [Documentation](../README.md)
