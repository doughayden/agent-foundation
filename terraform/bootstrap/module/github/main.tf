locals {
  github_environment_variables = {
    ARTIFACT_REGISTRY_LOCATION                         = var.artifact_registry_location
    ARTIFACT_REGISTRY_URI                              = var.artifact_registry_uri
    GOOGLE_CLOUD_LOCATION                              = var.google_cloud_location
    GOOGLE_CLOUD_PROJECT                               = var.project
    IMAGE_NAME                                         = var.agent_name
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = var.otel_instrumentation_genai_capture_message_content
    REGION                                             = var.region
    ZONE                                               = var.zone
    TERRAFORM_STATE_BUCKET                             = var.terraform_state_bucket
    WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER        = var.workload_identity_pool_principal_identifier
    WORKLOAD_IDENTITY_PROVIDER                         = var.workload_identity_provider_name
  }
}

data "github_user" "reviewer" {
  for_each = toset(var.reviewer_users)
  username = each.value
}

data "github_team" "reviewer" {
  for_each = toset(var.reviewer_teams)
  slug     = each.value
}

resource "github_repository_environment" "env" {
  repository          = var.repository_name
  environment         = var.environment
  can_admins_bypass   = var.can_admins_bypass
  prevent_self_review = var.prevent_self_review
  wait_timer          = var.wait_timer

  dynamic "reviewers" {
    for_each = length(var.reviewer_users) + length(var.reviewer_teams) > 0 ? [1] : []
    content {
      users = [for user in data.github_user.reviewer : tonumber(user.id)]
      teams = [for team in data.github_team.reviewer : tonumber(team.id)]
    }
  }

  dynamic "deployment_branch_policy" {
    for_each = var.deployment_tag_pattern == null ? [] : [1]
    content {
      protected_branches     = false
      custom_branch_policies = true
    }
  }
}

resource "github_repository_environment_deployment_policy" "tag" {
  count       = var.deployment_tag_pattern == null ? 0 : 1
  repository  = var.repository_name
  environment = github_repository_environment.env.environment
  tag_pattern = var.deployment_tag_pattern
}

resource "github_actions_environment_variable" "variable" {
  for_each      = local.github_environment_variables
  repository    = var.repository_name
  environment   = github_repository_environment.env.environment
  variable_name = each.key
  value         = each.value
}
