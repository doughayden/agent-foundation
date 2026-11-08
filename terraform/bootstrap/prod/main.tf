locals {
  # GitHub environment deployment policy pattern for prod promotion tags (prod-vX.Y.Z)
  promotion_tag_pattern = "prod-v*.*.*"
}

module "gcp" {
  source              = "../module/gcp"
  environment         = "prod"
  github_environments = ["prod", "prod-apply"]

  project                                 = var.project
  region                                  = var.region
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
  zone                                               = var.zone
  region                                             = var.region
  google_cloud_location                              = var.google_cloud_location
  agent_name                                         = var.agent_name
  repository_owner                                   = var.repository_owner
  repository_name                                    = var.repository_name
  otel_instrumentation_genai_capture_message_content = var.otel_instrumentation_genai_capture_message_content
  artifact_registry_location                         = module.gcp.artifact_registry_location
  artifact_registry_uri                              = module.gcp.artifact_registry_uri
  workload_identity_provider_name                    = module.gcp.workload_identity_provider_name
  workload_identity_pool_principal_identifier        = module.gcp.workload_identity_pool_principal_identifier
  terraform_state_bucket                             = var.terraform_state_bucket
  deployment_tag_patterns                            = [local.promotion_tag_pattern]
}

module "github_protected" {
  source      = "../module/github"
  environment = "prod-apply"

  project                                            = var.project
  zone                                               = var.zone
  region                                             = var.region
  google_cloud_location                              = var.google_cloud_location
  agent_name                                         = var.agent_name
  repository_owner                                   = var.repository_owner
  repository_name                                    = var.repository_name
  otel_instrumentation_genai_capture_message_content = var.otel_instrumentation_genai_capture_message_content
  artifact_registry_location                         = module.gcp.artifact_registry_location
  artifact_registry_uri                              = module.gcp.artifact_registry_uri
  workload_identity_provider_name                    = module.gcp.workload_identity_provider_name
  workload_identity_pool_principal_identifier        = module.gcp.workload_identity_pool_principal_identifier
  terraform_state_bucket                             = var.terraform_state_bucket
  deployment_tag_patterns                            = [local.promotion_tag_pattern]
  reviewer_users                                     = var.prod_apply_reviewer_users
  reviewer_teams                                     = var.prod_apply_reviewer_teams
  prevent_self_review                                = var.prod_apply_prevent_self_review
  can_admins_bypass                                  = var.prod_apply_can_admins_bypass
  wait_timer                                         = var.prod_apply_wait_timer
}

# Cross-project binding to allow docker image promotion
resource "google_artifact_registry_repository_iam_member" "promotion_source" {
  project    = var.promotion_source_project
  repository = var.promotion_source_artifact_registry_name
  role       = "roles/artifactregistry.reader"
  member     = module.gcp.workload_identity_pool_principal_identifier
}

data "github_repository" "repo" {
  full_name = "${var.repository_owner}/${var.repository_name}"
}

# A prod-v* tag deploys prod, so only repository admins may create, move or delete one
resource "github_repository_ruleset" "production_tags" {
  name        = "Production Promotion Tag Protection"
  repository  = data.github_repository.repo.name
  target      = "tag"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["refs/tags/prod-v*"]
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
  }
}
