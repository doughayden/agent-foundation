variable "environment" {
  description = "Environment name (dev, stage, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Environment must be: dev, stage, or prod"
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

variable "repository_name" {
  description = "GitHub repository name"
  type        = string
}

variable "repository_owner" {
  description = "GitHub repository owner - username or organization"
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
