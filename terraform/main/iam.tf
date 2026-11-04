locals {
  # Roles added here are granted to the GitHub Actions WIF principal and applied
  # by CI/CD — no bootstrap re-run required.
  wif_additional_roles = toset([
    # WIF principal IAM roles not granted in bootstrap (consumers fill this in).
  ])
}

resource "google_project_iam_member" "wif_additional_roles" {
  for_each = local.wif_additional_roles
  project  = var.project
  role     = each.key
  member   = var.workload_identity_pool_principal_identifier
}

# One sleep instance per role — created only when that role is added to wif_additional_roles.
# When wif_additional_roles is empty (default), no instances are created and no delay occurs.
#
# GCP IAM propagation is eventually consistent. This sleep ensures the new binding has
# propagated before any resource that depends on it attempts to use the role.
#
# Consumer pattern — add depends_on for each role a new resource requires:
#
#   resource "google_bigquery_dataset" "example" {
#     ...
#     depends_on = [time_sleep.wif_iam_propagation["roles/bigquery.admin"]]
#   }
#
# If a resource requires multiple new roles, list each one explicitly:
#
#   depends_on = [
#     time_sleep.wif_iam_propagation["roles/bigquery.admin"],
#     time_sleep.wif_iam_propagation["roles/pubsub.editor"],
#   ]
resource "time_sleep" "wif_iam_propagation" {
  for_each        = local.wif_additional_roles
  create_duration = "120s"

  # triggers accepts attribute references (unlike depends_on which requires static refs).
  # Recording the IAM member's ID here creates a data-flow dependency on that specific member
  # and forces this sleep to re-create — and re-fire — if the member is ever replaced.
  triggers = {
    iam_member_id = google_project_iam_member.wif_additional_roles[each.key].id
  }
}
