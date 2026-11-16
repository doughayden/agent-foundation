locals {
  bastion_iam_roles = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])

  # Service account ID 30-char limit: truncate prefix to preserve environment suffix
  sa_suffix_bastion = "-bastion-${var.environment}"
  sa_prefix_bastion = substr(var.agent_name, 0, 30 - length(local.sa_suffix_bastion))
  sa_id_bastion     = "${local.sa_prefix_bastion}${local.sa_suffix_bastion}"

  # Stage and prod bastions exist mainly to bootstrap pg_cron, so they stay powered off
  bastion_auto_stop          = var.environment != "dev"
  bastion_auto_stop_schedule = "0 6 * * *"

  # Template syntax: https://developer.hashicorp.com/terraform/language/expressions/strings#directives
  bastion_user_data = templatefile(
    "${path.module}/templates/bastion-cloud-init.yaml",
    {
      proxy_args          = join(" ", local.cloud_sql_proxy_args)
      app_service_account = google_service_account.app.email
      app_sa_db_user      = google_sql_user.app.name
      auto_stop           = local.bastion_auto_stop
    }
  )
}

resource "google_service_account" "bastion" {
  account_id   = local.sa_id_bastion
  display_name = "${local.resource_name} Bastion Service Account"
  description  = "Service account attached to the ${local.resource_name} Cloud SQL Auth Proxy bastion"
}

resource "google_project_iam_member" "bastion" {
  for_each = local.bastion_iam_roles
  project  = var.project
  role     = each.key
  member   = google_service_account.bastion.member
}

# Bastion proxy impersonates the app SA for IAM database auth (--impersonate-service-account)
resource "google_service_account_iam_member" "bastion_impersonate_app" {
  service_account_id = google_service_account.app.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = google_service_account.bastion.member
}

resource "terraform_data" "bastion_user_data" {
  triggers_replace = sha256(local.bastion_user_data)
}

resource "google_compute_instance" "bastion" {
  name         = "${local.resource_name}-bastion"
  machine_type = "e2-micro"
  zone         = var.zone
  tags         = ["bastion"]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id
    # No access_config — no public IP (IAP tunnel only)
  }

  metadata = {
    user-data                 = local.bastion_user_data
    enable-oslogin            = "TRUE"
    cos-update-strategy       = "update_enabled"
    google-logging-enabled    = "true"
    google-monitoring-enabled = "true"
  }

  service_account {
    email  = google_service_account.bastion.email
    scopes = ["cloud-platform"]
  }

  resource_policies = google_compute_resource_policy.bastion_stop[*].id

  depends_on = [time_sleep.compute_agent_iam_propagation]

  lifecycle {
    replace_triggered_by = [terraform_data.bastion_user_data]
  }
}

resource "google_compute_resource_policy" "bastion_stop" {
  count       = local.bastion_auto_stop ? 1 : 0
  name        = "${local.resource_name}-bastion-stop"
  region      = var.region
  description = "Stops a developer-started ${local.resource_name} bastion (no start action)"

  instance_schedule_policy {
    vm_stop_schedule {
      schedule = local.bastion_auto_stop_schedule
    }
    time_zone = "UTC"
  }
}

data "google_project" "main" {
  count = local.bastion_auto_stop ? 1 : 0
}

# Instance schedules act as the Compute Engine service agent, which needs compute.instances.stop
resource "google_project_iam_member" "compute_agent_instance_admin" {
  count   = local.bastion_auto_stop ? 1 : 0
  project = var.project
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:service-${data.google_project.main[0].number}@compute-system.iam.gserviceaccount.com"
}

# Compute checks the agent's permission when the schedule attaches at instance creation
resource "time_sleep" "compute_agent_iam_propagation" {
  count           = local.bastion_auto_stop ? 1 : 0
  create_duration = "120s"

  triggers = {
    iam_member_id = google_project_iam_member.compute_agent_instance_admin[0].id
  }
}
