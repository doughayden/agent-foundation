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
  description = "Agent/application name"
  type        = string
}

variable "terraform_state_bucket" {
  description = "Terraform state GCS bucket name"
  type        = string
}

variable "repository_owner" {
  description = "GitHub repository owner"
  type        = string
}

variable "repository_name" {
  description = "GitHub repository name"
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

variable "registry_cleanup_general_retention_days" {
  description = "Days to retain images generally"
  type        = number
}

variable "registry_cleanup_keep_count" {
  description = "Number of recent images to keep (null to disable KEEP policy)"
  type        = number
  nullable    = true
  default     = null
}

variable "registry_cleanup_pr_retention_days" {
  description = "Days to retain PR-tagged images (null to disable, dev only)"
  type        = number
  nullable    = true
  default     = null
}

# Required for cross-project Artifact Registry docker image promotion to non-dev projects
variable "promotion_source_project" {
  description = "Artifact Registry source for docker image promotion Google Cloud project ID"
  type        = string
  nullable    = true
  default     = null
}

variable "promotion_source_artifact_registry_name" {
  description = "Artifact Registry source for docker image promotion repository name"
  type        = string
  nullable    = true
  default     = null
}

# prod-apply approval gate (required reviewers on a private repository need GitHub Enterprise)
variable "prod_apply_reviewer_users" {
  description = "GitHub usernames whose approval releases the prod apply"
  type        = list(string)
  default     = []
}

variable "prod_apply_reviewer_teams" {
  description = "GitHub team slugs whose approval releases the prod apply"
  type        = list(string)
  default     = []
}

variable "prod_apply_prevent_self_review" {
  description = "Stop the user who pushed the promotion tag from approving the prod apply"
  type        = bool
  default     = false
}

variable "prod_apply_can_admins_bypass" {
  description = "Let repository admins deploy prod without an approval"
  type        = bool
  default     = true
}

variable "prod_apply_wait_timer" {
  description = "Minutes to delay the prod apply after approval is requested (null for none)"
  type        = number
  nullable    = true
  default     = null
}
