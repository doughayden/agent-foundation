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

variable "terraform_state_bucket" {
  description = "Terraform state GCS bucket name"
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

variable "serve_web_interface" {
  description = "Enable web UI"
  type        = string
  nullable    = true
  default     = null
}

variable "agent_engine" {
  description = "Agent Engine resource name (optional override)"
  type        = string
  nullable    = true
  default     = null

}

variable "artifact_service_uri" {
  description = <<-EOT
    Artifact service bucket URI ('gs://your-bucket-name', optional override).

    IMPORTANT: External buckets must be in the same GCP project as this deployment.
    Project-level IAM roles (storage.bucketViewer, storage.objectUser) only grant
    access to buckets within the project. Cross-project bucket access requires
    additional IAM configuration outside this module.

    Omit this variable to use the auto-created bucket (recommended).
  EOT
  type        = string
  nullable    = true
  default     = null
}

variable "allow_origins" {
  description = "Allow these origins for CORS (JSON array string)"
  type        = string
  nullable    = true
  default     = null
}

variable "root_agent_model" {
  description = "Root agent Vertex AI model name"
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
