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

variable "location" {
  description = "Google Cloud location (Compute region)"
  type        = string
}

variable "agent_name" {
  description = "Agent name to identify cloud resources and logs"
  type        = string
}

variable "otel_instrumentation_genai_capture_message_content" {
  description = "Capture LLM message content in OpenTelemetry traces (TRUE/FALSE)"
  type        = string
}

variable "repository_name" {
  description = "GitHub repository name"
  type        = string
}

variable "repository_owner" {
  description = "GitHub repository owner - username or organization"
  type        = string
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
