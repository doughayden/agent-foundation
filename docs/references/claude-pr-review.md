# Claude PR Review

Automated code review on pull requests, powered by Claude.

## Overview

The `claude.yml` workflow adds two jobs to the repository:

- An automated code review on every pull request when it is opened.
- A manual `@claude` trigger for on-demand review or assistance from a comment.

Both jobs run in the `dev` GitHub Environment. The review model is pinned in `claude.yml` (`claude_args: --model`).

Findings tied to specific lines are posted as inline review comments on those lines, with a `suggestion` block where the fix is a drop-in replacement, so they can be committed from the Files changed tab. The tracking comment carries the summary and anything that spans the whole change. Review feedback also carries "Fix this" links that open Claude Code with the finding's context.

## Inline review comments

The tool that posts them is granted in `claude.yml` through `claude_args`:

```yaml
claude_args: |
  --allowedTools "mcp__github_inline_comment__create_inline_comment"
```

This is required, not decorative. `track_progress: true` puts the action in tag mode, whose tool allowlist is otherwise fixed, and the inline-comment MCP server is started only when the allowlist names one of its tools. Without this line the server never starts, Claude has no way to place a line comment, and every finding collapses into the single tracking comment. Multiple `--allowedTools` occurrences accumulate rather than override, so this grants the tool without displacing the ones tag mode adds.

`classify_inline_comments` is set to `"false"`. Left at its default, the action buffers each inline comment and, after the session, asks a model to classify it as real feedback or a test probe, dropping the ones judged to be probes and logging a warning. That classification only runs when an Anthropic API key is present, so it would silently make the set of posted comments depend on which model auth path the repository uses. Setting it to `"false"` posts every inline comment on all three paths.

## Choosing a model auth path

The workflow reaches Claude one of three ways. Vertex AI is the default; either of two repository secrets overrides it.

| | Vertex AI (default) | Anthropic API key | Claude Code OAuth token |
|---|---|---|---|
| Setup | Workload Identity Federation, provisioned by bootstrap | `ANTHROPIC_API_KEY` repository secret | `CLAUDE_CODE_OAUTH_TOKEN` repository secret |
| Requires GCP | Yes | No | No |
| Credential owner | The GCP organization | The Anthropic organization | An individual's Claude account |
| Billed to | The dev project's Google Cloud billing account | The Anthropic organization's workspace | The account's Claude subscription |
| Expires | No | No | Yes, about a year after creation |
| Model endpoint | `CLOUD_ML_REGION` in `claude.yml` | Anthropic API | Anthropic API |

**Precedence:** `ANTHROPIC_API_KEY` wins if both secrets are set, and either one takes precedence over Vertex AI. The workflow applies this explicitly rather than leaving it to credential resolution inside the action, so the rule is visible in `claude.yml`.

All three paths need the Claude GitHub App installed (below). Switching is adding or removing a secret. No workflow edit in any direction.

> [!TIP]
> Prefer the Anthropic API key over the OAuth token for a shared or organization-owned repository. The key is owned by the organization rather than a person, carries a workspace spend limit, is revocable independently of any individual, and does not expire. The OAuth token is the fastest path to a working review for an individual developer, at the cost of a yearly rotation.

## Prerequisites

### 1. Install the Claude GitHub App (all paths)

`claude-code-action` mints its GitHub token by exchanging an OIDC token with the Claude GitHub App. Without the app installed on the repository, the review cannot run regardless of which model auth path you use. Install it from [github.com/apps/claude](https://github.com/apps/claude).

### 2a. Vertex AI path: enable the Claude model in the dev project

Both review jobs run in the `dev` GitHub Environment and call Vertex in the dev project, so enable the model in the dev project only, even in production mode.

1. Enable the Claude model the workflow pins (model ID at `claude_args: --model <model_id>`) in the dev project and accept the Anthropic terms, following [Use Claude models on Google Cloud](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/use-claude).
2. Confirm the model supports the endpoint configured by `CLOUD_ML_REGION` in `claude.yml`.
3. Confirm the project has quota for that model on that endpoint.

The dev project's bootstrap already enables the Vertex AI API and grants its WIF principal `roles/aiplatform.user`, so no further API or IAM changes are needed.

> [!NOTE]
> Skip Anthropic's [Using with Amazon Bedrock and Google Cloud](https://code.claude.com/docs/en/github-actions#using-with-amazon-bedrock-and-google-cloud) guide's Workload Identity Federation and service-account steps. Bootstrap already provisions the WIF the workflow uses, and grants `roles/aiplatform.user` directly to the WIF principal rather than impersonating a service account, which is Google Cloud's recommended [direct resource access](https://docs.cloud.google.com/iam/docs/workload-identity-federation#access_management) pattern. `claude.yml` reads the `WORKLOAD_IDENTITY_PROVIDER` and `GOOGLE_CLOUD_PROJECT` GitHub Variables bootstrap creates.

### 2b. API key path: add an organization API key

1. In the [Anthropic Console](https://console.anthropic.com/settings/keys), create an API key under the organization. Scope it to a Workspace so its spend is capped and tracked separately.
2. Add it as the `ANTHROPIC_API_KEY` repository secret (GitHub Actions > Secrets and variables > Actions).
3. Confirm the workspace has access to the model the workflow pins.

Nothing else changes. The workflow skips its Google Cloud authentication step whenever either override secret is present, so the review runs without touching GCP.

> [!NOTE]
> Use an organization key rather than a personal one. It survives staff changes, is revocable independently of any individual, and carries the workspace's spend limit.

### 2c. OAuth token path: add a Claude Code OAuth token

1. Run `claude setup-token` in a terminal and complete the browser sign-in. It prints a long-lived OAuth token tied to the Claude account you signed in with.
2. Add it as the `CLAUDE_CODE_OAUTH_TOKEN` repository secret (GitHub Actions > Secrets and variables > Actions).
3. Confirm the account's plan covers the model the workflow pins.

Leave `ANTHROPIC_API_KEY` unset, or the API key takes precedence.

> [!IMPORTANT]
> The token expires roughly a year after creation, and nothing warns you beforehand. The review simply starts failing. Re-run `claude setup-token` and replace the secret to rotate it.

## Troubleshooting

**The review job fails with `is_error: true` and no review output.** The model call did not succeed. Start with the job's "Report model auth path" step, which names the path that ran. On Vertex AI, confirm the model is enabled in the dev project and that the project has quota for it on the endpoint `CLOUD_ML_REGION` configures. On the API key, confirm the key is valid and the workspace has both model access and remaining budget. On the OAuth token, confirm it has not expired and the account's plan covers the pinned model. Switching to another path is the fastest way to isolate whether the problem is model access.

**The review ran on an unexpected auth path.** Both override secrets are probably set. `ANTHROPIC_API_KEY` wins over `CLAUDE_CODE_OAUTH_TOKEN`; remove the one you do not want.

**The automatic review fails on a pull request from a fork.** GitHub withholds secrets from `pull_request` runs triggered by a fork and downgrades the token to read-only. No model auth path can work, and the job fails rather than being skipped, so the check goes red. This predates the override secrets and applies to the Vertex AI path too.

Commenting `@claude` on that same pull request does work. Comment events (`issue_comment`, `pull_request_review_comment`, `pull_request_review`) run in the base repository's context with full secrets and the workflow's declared permissions, so `claude-manual-trigger` authenticates normally. Use it to review an outside contribution.

## Editing the review workflow

`claude-code-action` obtains its GitHub token by exchanging an OIDC token, and that exchange only succeeds when `claude.yml` matches the version on the repository's default branch. This is a security guard in the action, not standard GitHub Actions behavior. A pull request that changes `claude.yml` therefore skips its own review, logging:

```text
Workflow validation failed. The workflow file must exist and have identical content to the version on the repository's default branch.
Action skipped due to workflow validation error. ... your workflow will begin working once you merge your PR.
```

This is expected ([claude-code-action#443](https://github.com/anthropics/claude-code-action/issues/443)). The updated review runs on pull requests opened after the change merges to the default branch. A fresh repo created from the template already ships the matching workflow, so its first pull request is reviewed normally.

Adding or removing the `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` secret is not a workflow edit and does not trigger this guard. It takes effect on the next run.

---

← [Back to References](README.md) | [Documentation](../README.md)
