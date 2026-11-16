# AGENTS.md: Terraform

Rules for editing `terraform/`. **Template Internals:** everything here except `terraform/main/services.tf`, `terraform/main/iam.tf`, `terraform/main/env.tf` and the `terraform/main/monitoring.tf` locals (the consumer extension points, see root `AGENTS.md` Consumer Extension Points). Cross-cutting rules live in the root `AGENTS.md`.

## Conventions

- **`for_each` for collections, `count` for an on/off switch:** `count = local.flag ? 1 : 0` for a single optional resource; `for_each` keyed by a set or map (like `toset(var.patterns)`) when there can be several

## Pre-Bootstrap

`terraform/bootstrap/pre/` creates one state bucket per env (`terraform_state_buckets` output). **Local state only — do not lose `terraform/bootstrap/pre/terraform.tfstate`.** Steps: `docs/references/bootstrap.md` Pre-Bootstrap.

## Bootstrap

One root per env (`dev/`, `stage/`, `prod/`) over shared modules (`gcp/`, `github/`), GCS remote state. Stage/prod roots also grant the WIF principal cross-project Artifact Registry read for promotion (`terraform/bootstrap/{stage,prod}/main.tf`). **WIF trust = repository AND environment:** each root's `github_environments` feeds the provider's `attribute_condition`; deployment policies on `stage`/`prod`/`prod-apply` decide which refs get that claim (`docs/references/security-posture.md` Identity Layer). Base-template services/roles ONLY — **do not modify to add custom services/roles** (extend `terraform/main/services.tf` / `iam.tf`). Detail: `docs/references/bootstrap.md`.

## Main Module

`terraform/main/`, resource list in `docs/references/deployment.md` Main Module. Inputs are `TF_VAR_*` from GitHub Environment Variables; requires `TF_VAR_environment`.

- **Cloud Run env vars:** template wiring in `run_app_env` (`main.tf`), per-environment runtime config in `run_app_env_config` (`env.tf`), merged last so an entry wins. **Never add a Terraform variable or `TF_VAR_*` line for runtime config**: it goes in `env.tf`. The capture-mode precondition on `google_cloud_run_v2_service.app` checks every environment's entry
- **Bastion cloud-init template** (`templates/bastion-cloud-init.yaml`): any change to an environment's rendered output replaces that bastion (`replace_triggered_by`). Indent `%{ if }` directives into the YAML block and write them `%{~ … ~}` (a column-0 `%` fails `check-yaml`; the strip markers remove the directive lines). Keep the `auto_stop = false` (dev) render byte-identical unless dev should change: compare `templatefile()` output in `terraform console` before and after
- Null `docker_image` reuses the previous image (`docs/references/deployment.md` Runtime Configuration)
- Shared proxy args, IAM layering, naming: `docs/references/deployment.md` Main Module and Resource Naming; `time_sleep` propagation: `docs/references/bootstrap.md` Extending the Main Module
- **Deletion protection stays on for stage/prod** (instance `deletion_protection`; no bucket `force_destroy`, no engine `FORCE`): a teardown flips them with uncommitted edits (`docs/references/environment-teardown.md`, run via the `teardown-environment` skill). `ABANDON` (SQL user owns pg_cron objects) and `REMOVE_PEERING` (Cloud SQL holds the connection after deletion) stay on: neither guards data
- `required_version` in each root stays a range; the exact pin is `.terraform-version` (root `AGENTS.md` Code Quality)

## Cloud Run Probes

App startup probe allows ~120s for credential init; the Auth Proxy sidecar has none (Cloud Run restarts it on crash). Local works but Cloud Run fails → credential or VPC egress issue.
