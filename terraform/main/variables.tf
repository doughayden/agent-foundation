variable "environment" {
  description = "Deployment environment (dev, stage, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Must be dev, stage, or prod"
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

variable "google_cloud_location" {
  description = "Vertex AI model endpoint location"
  type        = string
}

variable "agent_name" {
  description = "Agent name to identify cloud resources and logs"
  type        = string
}

variable "terraform_state_bucket" {
  description = "Terraform state GCS bucket name"
  type        = string
}

variable "workload_identity_pool_principal_identifier" {
  description = "WIF principal identifier for additional IAM role bindings"
  type        = string
}

variable "docker_image" {
  description = "Docker image URI to deploy (defaults to previous deployment)"
  type        = string
  nullable    = true
  default     = null
}

# Optional app runtime environment variables
variable "log_level" {
  description = "Agent app logging verbosity"
  type        = string
  nullable    = true
  default     = null
}

variable "otel_instrumentation_genai_capture_message_content" {
  description = "Capture LLM message content in OpenTelemetry traces (TRUE/FALSE)"
  type        = string
  nullable    = true
  default     = null
}

variable "serve_web_interface" {
  description = "Enable web UI"
  type        = string
  nullable    = true
  default     = null
}

variable "adk_suppress_experimental_feature_warnings" {
  description = "Suppress ADK experimental feature warnings"
  type        = string
  nullable    = true
  default     = null
}
