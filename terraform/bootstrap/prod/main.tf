module "gcp" {
  source      = "../module/gcp"
  environment = "prod"

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
  environment = "prod"

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

module "github_protected" {
  source      = "../module/github"
  environment = "prod-apply"

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

# Protect production release tags in GitHub
data "github_repository" "repo" {
  full_name = "${var.repository_owner}/${var.repository_name}"
}

resource "github_repository_ruleset" "production_tags" {
  name        = "Production Release Tag Protection"
  repository  = data.github_repository.repo.name
  target      = "tag"
  enforcement = "active"

  # Apply restriction to tags that match the pattern v* (e.g., v1.2.3, etc.)
  conditions {
    ref_name {
      include = ["refs/tags/v*"]
      exclude = []
    }
  }

  # Allow repository admins to bypass
  bypass_actors {
    actor_id    = 5
    actor_type  = "RepositoryRole"
    bypass_mode = "always"
  }

  rules {
    creation                = true
    update                  = true
    deletion                = true
    required_linear_history = false
    required_signatures     = false
    non_fast_forward        = true # Prevent force pushes to protected tags

    # Future: add required status checks when stage tests exist
    # required_status_checks {
    #   required_check {
    #     context = "stage-apply"
    #   }
    #   required_check {
    #     context = "stage-tests"
    #   }
    # }
  }
}
