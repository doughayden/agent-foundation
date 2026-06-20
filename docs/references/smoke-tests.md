# Smoke Tests

The smoke lane: post-deploy checks against a live Cloud Run revision.

## What it is

The smoke lane (`tests/smoke/`) hits the live deployed Cloud Run service URL after `terraform apply` to confirm a freshly deployed revision actually serves end to end. Unlike the integration lane, which builds the app in-process via httpx `ASGITransport`, nothing here is substituted: the request crosses the real network, the Auth Proxy sidecar, and Cloud SQL. The L2 turn invokes the real model, but the lane is still a deterministic gate. Behavioral correctness stays owned by the eval lane, pre-deploy wiring by the integration lane.

The lane runs only by explicit path (`uv run pytest tests/smoke`).

## What each layer catches

Checks run cheapest-first, each a distinct failure class so a failure localizes the broken subsystem:

- **L0 liveness**: `GET /health` -> 200. The revision serves HTTP at all.
- **L1 session create**: create a session, read it back -> 200. Cloud SQL is reachable through the Auth Proxy sidecar over VPC egress, and a session row persists. Deterministic, no model. A module-scoped fixture owns the create so teardown deletes the row unconditionally even when a later check fails.
- **L2 thin agent turn**: `POST /run_sse` with a trivial prompt, parse the SSE event stream, and assert at least one event carries a text part. The real model is invoked, but the assertion checks only that a text part returned, never what it says, so the check is robust to the model's stochastic output and carries no LLM-judge dependency.
- **L3 cleanup**: delete the smoke session, then a follow-up GET returns 404. Proves the delete path and leaves no residue.

## How authentication works

The service deploys `--no-allow-unauthenticated`, so Cloud Run requires a Google-signed OIDC ID token whose audience is the service URL. A caller's own credentials (a developer's gcloud login, or the CI WIF principal) cannot mint that token directly, so the lane impersonates a dedicated invoker service account to generate it. Impersonation runs in-process with `impersonated_credentials.IDTokenCredentials`, sourced from the caller's own Application Default Credentials, so the same test code works locally and in CI and no token is passed through the environment:

- **Locally**: set your ADC using `gcloud`. Run `gcloud auth application-default login` once if you have not. Your principal needs permission to mint ID tokens as the invoker SA; grant yourself `roles/iam.serviceAccountOpenIdTokenCreator` (it includes only the `iam.serviceAccounts.getOpenIdToken` permission) on the invoker SA.
- **In CI**: the GitHub Actions WIF principal, which `terraform/main/smoke.tf` grants `roles/iam.serviceAccountOpenIdTokenCreator` on the invoker SA.

The invoker SA is a least-privilege identity distinct from the runtime app SA, holding only `roles/run.invoker` on the app's Cloud Run service. The test client reads the invoker SA email from `SMOKE_INVOKER_SA`, mints the ID token by impersonation, and sends it as `Authorization: Bearer`. See [Security Posture](security-posture.md) for the identity model.

## Run it locally

The smoke lane targets a live deployed URL and reads two env vars: `SMOKE_BASE_URL` (the deployed service URL) and `SMOKE_INVOKER_SA` (the invoker SA email the client impersonates). Both are Terraform outputs (`smoke_target_url`, `smoke_invoker_service_account_email`), available from the GitHub Actions apply job summary (`gh run view <run-id>`) or the Cloud Console (the Cloud Run service URL; the SA under IAM & Admin). If you have the main module initialized locally, read them with `terraform output`:

```bash
SMOKE_BASE_URL="$(terraform -chdir=terraform/main output -raw smoke_target_url)" \
SMOKE_INVOKER_SA="$(terraform -chdir=terraform/main output -raw smoke_invoker_service_account_email)" \
  uv run pytest tests/smoke
```

Both are test-harness variables, not application runtime config, so they live here rather than in `docs/environment-variables.md`. No token env var is needed: the client mints the ID token in-process from your gcloud ADC.

## How CI runs it post-deploy

The `smoke.yml` reusable workflow authenticates to GCP via WIF and runs `uv run pytest tests/smoke` with `SMOKE_BASE_URL` and `SMOKE_INVOKER_SA` set, surfacing pass/fail in the GitHub job summary. The test impersonates the SA in-process, so no token crosses the environment. The service URL and invoker SA email come from `terraform-plan-apply.yml` outputs (`smoke_target_url`, `smoke_invoker_service_account_email`), threaded through `ci-cd.yml`. The smoke test workflow is called after each environment apply — `dev-smoke` after `dev-apply` on merge, and in production mode `stage-smoke` after `stage-apply` on merge and `prod-smoke` after `prod-apply` on tag. This runs post-deploy against the live revision, not in the PR gate.

---

← [Back to References](README.md) | [Documentation](../README.md)
