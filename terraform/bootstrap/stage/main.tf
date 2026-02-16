module "gcp" {
  source      = "../module/gcp"
  environment = "stage"

  project                                 = var.project
  location                                = var.location
  agent_name                              = var.agent_name
  repository_owner                        = var.repository_owner
  repository_name                         = var.repository_name
  registry_cleanup_general_retention_days = var.registry_cleanup_general_retention_days
  registry_cleanup_keep_count             = var.registry_cleanup_keep_count
  registry_cleanup_pr_retention_days      = var.registry_cleanup_pr_retention_days
}

module "github" {
  source      = "../module/github"
  environment = "stage"

  project                                            = var.project
  location                                           = var.location
  agent_name                                         = var.agent_name
  repository_owner                                   = var.repository_owner
  repository_name                                    = var.repository_name
  otel_instrumentation_genai_capture_message_content = var.otel_instrumentation_genai_capture_message_content
  artifact_registry_location                         = module.gcp.artifact_registry_location
  artifact_registry_uri                              = module.gcp.artifact_registry_uri
  workload_identity_provider_name                    = module.gcp.workload_identity_provider_name
  terraform_state_bucket                             = module.gcp.terraform_state_bucket
}


# Cross-project binding to allow docker image promotion
resource "google_artifact_registry_repository_iam_member" "promotion_source" {
  project    = var.promotion_source_project
  repository = var.promotion_source_artifact_registry_name
  role       = "roles/artifactregistry.reader"
  member     = module.gcp.workload_identity_pool_principal_identifier
}
