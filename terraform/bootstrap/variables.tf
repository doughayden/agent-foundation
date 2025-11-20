variable "agent_name" {
  type        = string
  description = "Agent name used to name Terraform resources"
  nullable    = true
  default     = null
}

variable "project" {
  type        = string
  description = "Google Cloud project ID"
  nullable    = true
  default     = null
}

variable "region" {
  description = "Google Cloud region"
  type        = string
  nullable    = true
  default     = null
}

variable "repository_name" {
  description = "GitHub repository name"
  type        = string
  nullable    = true
  default     = null
}

variable "repository_owner" {
  description = "GitHub repository owner - username or organization"
  type        = string
  nullable    = true
  default     = null
}

variable "services" {
  description = "Google Cloud APIs to enable"
  type        = list(string)
  default = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "sts.googleapis.com",
    "telemetry.googleapis.com",
  ]
}

variable "github_workload_iam_roles" {
  description = "Github federated workload IAM roles"
  type        = list(string)
  default = [
    "roles/aiplatform.user",
    "roles/artifactregistry.writer",
  ]
}
