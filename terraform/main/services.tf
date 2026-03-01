locals {
  services = toset([
    # APIs needed by the main module not configured in bootstrap (consumers fill this in)
  ])
}

resource "google_project_service" "main" {
  for_each           = local.services
  project            = var.project
  service            = each.key
  disable_on_destroy = false
}

# One sleep instance per service — created only when that service is added to the set.
# When services is empty (default), no instances are created and no delay occurs.
#
# google_project_service is synchronous (Terraform waits for Service Usage API to confirm
# enabled), but some GCP services have async backend initialization after that confirmation.
# This sleep guards against errors when creating resources immediately after API enablement.
#
# Consumer pattern — add depends_on for each service a new resource requires:
#
#   resource "google_bigquery_dataset" "example" {
#     ...
#     depends_on = [time_sleep.service_enablement_propagation["bigquery.googleapis.com"]]
#   }
#
# If a resource requires multiple newly-enabled services, list each one explicitly:
#
#   depends_on = [
#     time_sleep.service_enablement_propagation["bigquery.googleapis.com"],
#     time_sleep.service_enablement_propagation["pubsub.googleapis.com"],
#   ]
resource "time_sleep" "service_enablement_propagation" {
  for_each        = local.services
  create_duration = "120s"

  triggers = {
    service_id = google_project_service.main[each.key].id
  }
}
