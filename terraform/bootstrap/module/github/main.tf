locals {
  github_environment_variables = {
    ARTIFACT_REGISTRY_LOCATION                         = var.artifact_registry_location
    ARTIFACT_REGISTRY_URI                              = var.artifact_registry_uri
    GCP_LOCATION                                       = var.location
    GCP_PROJECT_ID                                     = var.project
    GCP_WORKLOAD_IDENTITY_PROVIDER                     = var.workload_identity_provider_name
    IMAGE_NAME                                         = var.agent_name
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = var.otel_instrumentation_genai_capture_message_content
    TERRAFORM_STATE_BUCKET                             = var.terraform_state_bucket
  }
}

resource "github_repository_environment" "env" {
  repository  = var.repository_name
  environment = var.environment

  # Prevent manual changes to required reviewers in prod from affecting bootstrap state
  lifecycle {
    ignore_changes = [
      prevent_self_review,
      wait_timer,
      deployment_branch_policy,
      reviewers,
    ]
  }
}

resource "github_actions_environment_variable" "variable" {
  for_each      = local.github_environment_variables
  repository    = var.repository_name
  environment   = github_repository_environment.env.environment
  variable_name = each.key
  value         = each.value
}
