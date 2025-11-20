terraform {
  required_version = ">= 1.13.3, < 2.0.0"
  required_providers {
    dotenv = {
      source  = "germanbrew/dotenv"
      version = ">= 1.2.9, < 2.0.0"
    }
    google = {
      source  = "hashicorp/google"
      version = ">= 7.12.0, < 8.0.0"
    }
    github = {
      source  = "integrations/github"
      version = ">= 6.6.0, < 7.0.0"
    }
  }
}
