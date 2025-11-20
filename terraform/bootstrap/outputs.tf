output "agent_name" {
  description = "Agent name used to name Terraform resources"
  value       = local.agent_name
}

output "project" {
  description = "Google Cloud project ID"
  value       = local.project
}

output "region" {
  description = "Google Cloud region"
  value       = local.location
}

output "repository_full_name" {
  description = "Full GitHub repository name (owner/repo)"
  value       = "${local.repository_owner}/${local.repository_name}"
}

output "enabled_services" {
  description = "List of enabled Google Cloud services"
  value       = [for service in google_project_service.main : service.service]
}

output "workload_identity_provider_name" {
  description = "Full name of the workload identity provider for GitHub Actions"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "workload_identity_roles" {
  description = "List of IAM roles granted to the GitHub Actions workload identity"
  value       = [for role in google_project_iam_member.github : role.role]
}

output "artifact_registry_repository_uri" {
  description = "Artifact Registry Docker repository URI"
  value       = google_artifact_registry_repository.cloud_run.registry_uri
}

output "reasoning_engine_resource_name" {
  description = "Vertex AI Reasoning Engine resource name"
  value       = google_vertex_ai_reasoning_engine.session_and_memory.id
}

output "github_variables_configured" {
  description = "List of GitHub variables configured"
  value       = keys(local.github_variables)
}
