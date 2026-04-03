output "project" {
  description = "Google Cloud project ID"
  value       = var.project
}

output "region" {
  description = "Google Cloud Compute region"
  value       = var.region
}

output "zone" {
  description = "Google Cloud Compute zone"
  value       = var.zone
}

output "agent_name" {
  description = "Agent name to identify cloud resources and logs"
  value       = var.agent_name
}

output "terraform_state_bucket" {
  description = "Terraform state GCS bucket name"
  value       = var.terraform_state_bucket
}

output "deployed_image" {
  description = "Deployed Docker image URI"
  value       = local.docker_image
}

output "service_account_email" {
  description = "Agent app service account email"
  value       = google_service_account.app.email
}

output "service_account_roles" {
  description = "Agent app service account project IAM roles"
  value       = local.app_iam_roles
}

output "cloud_sql_instance_connection_name" {
  description = "Cloud SQL instance connection name (for Auth Proxy)"
  value       = google_sql_database_instance.sessions.connection_name
}

output "session_service_uri" {
  description = "Session service URI for ADK get_fast_api_app() factory"
  value       = local.run_app_env.SESSION_SERVICE_URI
}

output "memory_service_uri" {
  description = "Memory service URI for ADK get_fast_api_app() factory"
  value       = local.run_app_env.MEMORY_SERVICE_URI
}

output "artifact_service_uri" {
  description = "Artifact service GCS bucket URL (for local .env ARTIFACT_SERVICE_URI)"
  value       = google_storage_bucket.artifact_service.url
}

output "bastion_instance" {
  description = "Bastion host instance name (for IAP tunnel)"
  value       = google_compute_instance.bastion.name
}

output "bastion_zone" {
  description = "Bastion host zone (for IAP tunnel)"
  value       = google_compute_instance.bastion.zone
}

output "bastion_service_account_email" {
  description = "Bastion host service account email"
  value       = google_service_account.bastion.email
}

output "bastion_service_account_roles" {
  description = "Bastion host service account project IAM roles"
  value       = local.bastion_iam_roles
}

output "cloud_run_services" {
  description = "Agent app Cloud Run service details per location"
  value = { for loc, svc in data.google_cloud_run_v2_service.app :
    loc => {
      latest_ready_revision = split("revisions/", svc.latest_ready_revision)[1]
      update_time           = svc.update_time
      uri                   = svc.uri
    }
  }
}

output "configured_environment_variables" {
  description = "Configured Cloud Run service environment variables"
  value       = local.run_app_env
}

output "workload_identity_pool_principal_identifier" {
  description = "GitHub Actions workload identity pool principalSet identifier"
  value       = var.workload_identity_pool_principal_identifier
}
