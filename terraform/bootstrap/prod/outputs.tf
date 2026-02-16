output "project" {
  description = "Google Cloud project ID"
  value       = module.gcp.project
}

output "location" {
  description = "Google Cloud location (Compute region)"
  value       = module.gcp.location
}

output "agent_name" {
  description = "Agent name to identify cloud resources and logs"
  value       = module.gcp.agent_name
}

output "github_repository_full_name" {
  description = "Full GitHub repository name (owner/repo)"
  value       = module.gcp.github_repository_full_name
}

output "github_repository_id" {
  description = "GitHub repository ID"
  value       = module.gcp.github_repository_id
}

output "enabled_services" {
  description = "Enabled Google Cloud services"
  value       = module.gcp.enabled_services
}

output "workload_identity_pool_principal_identifier" {
  description = "GitHub Actions workload identity pool principalSet identifier"
  value       = module.gcp.workload_identity_pool_principal_identifier
}

output "workload_identity_provider_name" {
  description = "GitHub Actions workload identity provider resource name"
  value       = module.gcp.workload_identity_provider_name
}

output "workload_identity_roles" {
  description = "GitHub Actions workload identity project IAM roles"
  value       = module.gcp.workload_identity_roles
}

output "terraform_state_bucket" {
  description = "Terraform state GCS bucket name for main module"
  value       = module.gcp.terraform_state_bucket
}

output "artifact_registry_name" {
  description = "Artifact Registry repository name"
  value       = module.gcp.artifact_registry_name
}

output "artifact_registry_uri" {
  description = "Artifact Registry Docker repository URI"
  value       = module.gcp.artifact_registry_uri
}

output "artifact_registry_location" {
  description = "Artifact Registry Docker repository location"
  value       = module.gcp.artifact_registry_location
}

output "github_actions_environment_variables" {
  description = "GitHub Actions environment variables configured"
  value       = module.github.github_actions_environment_variables
}

output "production_tag_ruleset_rules" {
  description = "GitHub tag protection ruleset rules for production"
  value       = github_repository_ruleset.production_tags.rules
}
