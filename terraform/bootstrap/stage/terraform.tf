terraform {
  required_version = ">= 1.14.0, < 2.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.12.0, < 8.0.0"
    }
    github = {
      source  = "integrations/github"
      version = ">= 6.6.0, < 7.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.7.2, < 4.0.0"
    }
  }
}
