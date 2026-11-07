variable "environment" {
  description = "Environment name (dev, stage, prod, prod-apply)"
  type        = string
  validation {
    condition     = contains(["dev", "stage", "prod", "prod-apply"], var.environment)
    error_message = "Environment must be: dev, stage, prod, or prod-apply"
  }
}

variable "project" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud Compute region"
  type        = string
}

variable "zone" {
  description = "Google Cloud Compute zone"
  type        = string
}

variable "google_cloud_location" {
  description = "Vertex AI model endpoint location"
  type        = string
}

variable "agent_name" {
  description = "Agent name to identify cloud resources and logs"
  type        = string
}

variable "otel_instrumentation_genai_capture_message_content" {
  description = "ADK GenAI message content capture mode: NO_CONTENT, EVENT_ONLY, SPAN_ONLY or SPAN_AND_EVENT"
  type        = string

  validation {
    condition     = contains(["NO_CONTENT", "EVENT_ONLY", "SPAN_ONLY", "SPAN_AND_EVENT"], var.otel_instrumentation_genai_capture_message_content)
    error_message = "Must be one of NO_CONTENT, EVENT_ONLY, SPAN_ONLY or SPAN_AND_EVENT."
  }
}

variable "repository_name" {
  description = "GitHub repository name"
  type        = string
}

variable "repository_owner" {
  description = "GitHub repository owner - username or organization"
  type        = string
}

# Environment protection
variable "deployment_branch_patterns" {
  description = "Branch patterns allowed to deploy to the environment (any ref when both pattern lists are empty)"
  type        = list(string)
  default     = []
}

variable "deployment_tag_patterns" {
  description = "Tag patterns allowed to deploy to the environment (any ref when both pattern lists are empty)"
  type        = list(string)
  default     = []
}

variable "reviewer_users" {
  description = "GitHub usernames whose approval releases jobs that target the environment"
  type        = list(string)
  default     = []
}

variable "reviewer_teams" {
  description = "GitHub team slugs whose approval releases jobs that target the environment"
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.reviewer_users) + length(var.reviewer_teams) <= 6
    error_message = "GitHub allows at most six required reviewers (users and teams combined)."
  }
}

variable "prevent_self_review" {
  description = "Stop the user who triggered a job from approving it"
  type        = bool
  default     = false
}

variable "can_admins_bypass" {
  description = "Let repository admins bypass the environment's protection rules"
  type        = bool
  default     = true
}

variable "wait_timer" {
  description = "Minutes to delay a job after approval is requested (null for none)"
  type        = number
  nullable    = true
  default     = null

  validation {
    condition     = coalesce(var.wait_timer, 0) >= 0 && coalesce(var.wait_timer, 0) <= 43200
    error_message = "GitHub allows a wait timer of 0 to 43200 minutes (30 days)."
  }
}

# Inputs from the gcp module
variable "artifact_registry_location" {
  description = "Artifact Registry Docker repository location"
  type        = string
}

variable "artifact_registry_uri" {
  description = "Artifact Registry Docker repository URI"
  type        = string
}

variable "workload_identity_provider_name" {
  description = "GitHub Actions workload identity provider resource name"
  type        = string
}

variable "terraform_state_bucket" {
  description = "Terraform state GCS bucket name for main module"
  type        = string
}

variable "workload_identity_pool_principal_identifier" {
  description = "GitHub Actions workload identity pool principalSet identifier"
  type        = string
}
