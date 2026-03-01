variable "agent_name" {
  description = "Agent/application name"
  type        = string
}

variable "projects" {
  description = "Google Cloud project IDs mapped by environment"
  type        = map(string)
}

terraform {
  required_version = ">= 1.14.0, < 2.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.12.0, < 8.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.7.2, < 4.0.0"
    }
  }
}

provider "google" {}

provider "random" {}

resource "random_id" "bucket_suffix" {
  for_each    = var.projects
  byte_length = 4
}

resource "google_storage_bucket" "terraform_state" {
  for_each = var.projects
  project  = each.value
  name     = "terraform-state-${var.agent_name}-${each.key}-${random_id.bucket_suffix[each.key].hex}"
  location = "US"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

output "agent_name" {
  description = "Agent/application name"
  value       = var.agent_name
}

output "bucket_suffix_attributes" {
  description = "random_id.bucket_suffix hex and b64_url attribute values per environment. You can use b64_url to import the random_id resource into another terraform state."
  value = { for key, suffix in random_id.bucket_suffix : key =>
    {
      hex     = suffix.hex
      b64_url = suffix.b64_url
    }
  }
}

output "terraform_state_buckets" {
  description = "Terraform state GCS bucket names"
  value       = { for key, bucket in google_storage_bucket.terraform_state : key => bucket.name }
}
