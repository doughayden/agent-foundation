variable "project" {
  type        = string
  description = "Google Cloud project ID"
  nullable    = true
  default     = null
}

variable "location" {
  description = "Google Cloud location (Compute region)"
  type        = string
  nullable    = true
  default     = null
}

variable "agent_name" {
  type        = string
  description = "Agent name to identify cloud resources and logs"
  nullable    = true
  default     = null
}

variable "otel_instrumentation_genai_capture_message_content" {
  description = "Capture LLM message content in OpenTelemetry traces (TRUE/FALSE)"
  type        = string
  nullable    = true
  default     = null
}

variable "repository_name" {
  description = "GitHub repository name"
  type        = string
}

variable "repository_owner" {
  description = "GitHub repository owner - username or organization"
  type        = string
}
