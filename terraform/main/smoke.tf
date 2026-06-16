# Post-deploy smoke-test identity. The smoke lane (.github/workflows/smoke.yml)
# hits the live Cloud Run revision after each env apply. The GitHub Actions WIF
# principal impersonates this dedicated invoker SA to mint a Cloud Run ID token,
# rather than reusing the runtime app SA, so smoke access is scoped and auditable
# on its own identity.

locals {
  # Service account IDs — GCP 30-char limit. Mirror main.tf's truncation: keep the
  # environment suffix intact, truncate the agent_name prefix to fit.
  sa_suffix_smoke = "-smoke-${var.environment}"
  sa_prefix_smoke = substr(var.agent_name, 0, local.sa_limit - length(local.sa_suffix_smoke))
  sa_id_smoke     = "${local.sa_prefix_smoke}${local.sa_suffix_smoke}"
}

resource "google_service_account" "smoke_invoker" {
  account_id = local.sa_id_smoke
  # smoke.yml resolves this SA's email by display name (decoupling from the 30-char
  # account_id truncation), so keep the display name stable.
  display_name = "${local.resource_name} Smoke Invoker"
  description  = "Identity impersonated by CI to invoke the ${local.resource_name} Cloud Run service for post-deploy smoke tests"
}

# Grant the invoke role at the service resource level (not project-wide) so this
# identity can call only the app service. for_each over the same locations as the
# Cloud Run service so the binding tracks every deployed location.
resource "google_cloud_run_v2_service_iam_member" "smoke_invoker" {
  for_each = local.locations
  project  = google_cloud_run_v2_service.app[each.key].project
  location = google_cloud_run_v2_service.app[each.key].location
  name     = google_cloud_run_v2_service.app[each.key].name
  role     = "roles/run.invoker"
  member   = google_service_account.smoke_invoker.member
}

# Let the WIF principal mint ID tokens as the invoker SA. ID tokens (not access
# tokens) authenticate to Cloud Run, so this is serviceAccountOpenIdTokenCreator,
# not serviceAccountTokenCreator.
resource "google_service_account_iam_member" "smoke_token_creator" {
  service_account_id = google_service_account.smoke_invoker.name
  role               = "roles/iam.serviceAccountOpenIdTokenCreator"
  member             = var.workload_identity_pool_principal_identifier
}

# GCP SA-level IAM is eventually consistent. On a first apply (or SA replace) the
# token-mint impersonation can fail before this binding propagates, surfacing as a
# false-negative smoke result. Gate apply completion on a short propagation wait,
# mirroring time_sleep.wif_iam_propagation in iam.tf. The trigger on the binding id
# fires this only on create/replace; steady-state applies don't re-wait.
resource "time_sleep" "smoke_token_creator_propagation" {
  create_duration = "60s"

  triggers = {
    iam_member_id = google_service_account_iam_member.smoke_token_creator.id
  }
}

output "smoke_invoker_service_account_email" {
  description = "Email of the SA the CI smoke lane impersonates to invoke Cloud Run"
  value       = google_service_account.smoke_invoker.email
}
