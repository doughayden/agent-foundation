variable "project" {
  description = "Google Cloud project ID"
  type        = string
}

variable "location" {
  description = "GCP region"
  type        = string
}

variable "agent_name" {
  description = "Agent/application name"
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
  description = "Capture LLM message content in OpenTelemetry traces (TRUE/FALSE)"
  type        = string
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
