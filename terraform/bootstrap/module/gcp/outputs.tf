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

output "github_repository_full_name" {
  description = "Full GitHub repository name (owner/repo)"
  value       = "${var.repository_owner}/${var.repository_name}"
}

output "github_repository_id" {
  description = "GitHub repository ID"
  value       = data.github_repository.agent.repo_id
}

output "enabled_services" {
  description = "Enabled Google Cloud services"
  value       = [for service in google_project_service.main : service.service]
}

output "workload_identity_pool_principal_identifier" {
  description = "GitHub Actions workload identity pool principalSet identifier"
  value       = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.repository_owner}/${var.repository_name}"
}

output "workload_identity_provider_name" {
  description = "GitHub Actions workload identity provider resource name"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "workload_identity_roles" {
  description = "GitHub Actions workload identity project IAM roles"
  value       = [for role in google_project_iam_member.github : role.role]
}

output "terraform_state_bucket" {
  description = "Terraform state GCS bucket name for main module"
  value       = google_storage_bucket.terraform_state.name
}

output "artifact_registry_name" {
  description = "Artifact Registry repository name"
  value       = google_artifact_registry_repository.docker.name
}

output "artifact_registry_uri" {
  description = "Artifact Registry Docker repository URI"
  value       = google_artifact_registry_repository.docker.registry_uri
}

output "artifact_registry_location" {
  description = "Artifact Registry Docker repository location"
  value       = google_artifact_registry_repository.docker.location
}
