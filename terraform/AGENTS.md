# AGENTS.md: Terraform

Rules for editing `terraform/`. **Template Internals:** everything here except `terraform/main/services.tf`, `terraform/main/iam.tf` and the `terraform/main/monitoring.tf` locals (the consumer extension points, see root `AGENTS.md` Consumer Extension Points). Cross-cutting rules live in the root `AGENTS.md`.

## Pre-Bootstrap

`terraform/bootstrap/pre/` creates one state bucket per env (`terraform_state_buckets` output). **Local state only — do not lose `terraform/bootstrap/pre/terraform.tfstate`.** Steps: `docs/references/bootstrap.md` Pre-Bootstrap.

## Bootstrap

One root per env (`dev/`, `stage/`, `prod/`) over shared modules (`gcp/`, `github/`), GCS remote state. Stage/prod roots also grant the WIF principal cross-project Artifact Registry read for promotion (`terraform/bootstrap/{stage,prod}/main.tf`). Base-template services/roles ONLY — **do not modify to add custom services/roles** (extend `terraform/main/services.tf` / `iam.tf`). Detail: `docs/references/bootstrap.md`.

## Main Module

`terraform/main/`, resource list in `docs/references/deployment.md` Main Module. Inputs are `TF_VAR_*` from GitHub Environment Variables; requires `TF_VAR_environment`.

- Overrides: `coalesce()` skips empty/null `TF_VAR_*`; null `docker_image` reuses the previous image; service URIs and CORS have no override (`docs/references/deployment.md` Runtime Configuration)
- Shared proxy args, IAM layering, naming: `docs/references/deployment.md` Main Module and Resource Naming; `time_sleep` propagation: `docs/references/bootstrap.md` Extending the Main Module
- `required_version` in each root stays a range; the exact pin is `.terraform-version` (root `AGENTS.md` Code Quality)

## Cloud Run Probes

App startup probe allows ~120s for credential init; the Auth Proxy sidecar has none (Cloud Run restarts it on crash). Local works but Cloud Run fails → credential or VPC egress issue.
