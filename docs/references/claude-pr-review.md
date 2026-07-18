# Claude PR Review

Automated code review on pull requests, powered by Claude on Vertex AI.

## Overview

The `claude.yml` workflow adds two jobs to the repository:

- An automated code review on every pull request when it is opened.
- A manual `@claude` trigger for on-demand review or assistance from a comment.

Both jobs run in the `dev` GitHub Environment, authenticate with the dev project's Workload Identity Federation (provisioned by bootstrap), and call Claude on Vertex AI in the dev project. The review model and endpoint are pinned in `claude.yml` (`claude_args: --model` and `CLOUD_ML_REGION`).

## Prerequisites

Two one-time manual steps that Terraform cannot perform. Bootstrap already provisions the Workload Identity Federation and Vertex access the workflow uses, so these are the only extra steps.

### 1. Install the Claude GitHub App

`claude-code-action` mints its GitHub token by exchanging an OIDC token with the Claude GitHub App. Without the app installed on the repository, the review cannot run. Install it from [github.com/apps/claude](https://github.com/apps/claude), following Anthropic's [Using with Amazon Bedrock and Google Cloud](https://code.claude.com/docs/en/github-actions#using-with-amazon-bedrock-and-google-cloud).

> [!NOTE]
> Skip that guide's Workload Identity Federation and service-account steps. Bootstrap already provisions the WIF the workflow uses, and grants `roles/aiplatform.user` directly to the WIF principal rather than impersonating a service account, which is Google Cloud's recommended [direct resource access](https://docs.cloud.google.com/iam/docs/workload-identity-federation#access_management) pattern. `claude.yml` reads the `WORKLOAD_IDENTITY_PROVIDER` and `GOOGLE_CLOUD_PROJECT` GitHub Variables bootstrap creates, so you only need the app install here.

### 2. Enable the Claude model in the dev project

Both review jobs run in the `dev` GitHub Environment and call Vertex in the dev project, so enable the model in the dev project only, even in production mode.

1. Enable the Claude model the workflow pins (model ID at `claude_args: --model <model_id>`) in the dev project and accept the Anthropic terms, following [Use Claude models on Google Cloud](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/use-claude).
2. Confirm the model supports the endpoint configured by `CLOUD_ML_REGION` in `claude.yml`.

The dev project's bootstrap already enables the Vertex AI API and grants its WIF principal `roles/aiplatform.user`, so no further API or IAM changes are needed.

> [!NOTE]
> Without this step the review job fails fast with `is_error: true` (a 403 on the model call). This is separate from the agent's own Gemini model, which is enabled by default.

## Editing the review workflow

`claude-code-action` obtains its GitHub token by exchanging an OIDC token, and that exchange only succeeds when `claude.yml` matches the version on the repository's default branch. This is a security guard in the action, not standard GitHub Actions behavior. A pull request that changes `claude.yml` therefore skips its own review, logging:

```text
Workflow validation failed. The workflow file must exist and have identical content to the version on the repository's default branch.
Action skipped due to workflow validation error. ... your workflow will begin working once you merge your PR.
```

This is expected ([claude-code-action#443](https://github.com/anthropics/claude-code-action/issues/443)). The updated review runs on pull requests opened after the change merges to the default branch. A fresh repo created from the template already ships the matching workflow, so its first pull request is reviewed normally.

---

← [Back to References](README.md) | [Documentation](../README.md)
