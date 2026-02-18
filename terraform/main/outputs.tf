output "project" {
  description = "Google Cloud project ID"
  value       = var.project
}

output "location" {
  description = "Google Cloud location (Compute region)"
  value       = var.location
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

output "agent_engine" {
  description = "Vertex AI Agent Engine resource name (for local .env AGENT_ENGINE)"
  value       = google_vertex_ai_reasoning_engine.session_and_memory.id
}

output "artifact_service_uri" {
  description = "Artifact service GCS bucket URL (for local .env ARTIFACT_SERVICE_URI)"
  value       = google_storage_bucket.artifact_service.url
}

output "cloud_run_services" {
  description = "Agent app Cloud Run service details per location"
  value = { for loc, svc in data.google_cloud_run_v2_service.app_actual :
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
