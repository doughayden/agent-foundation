terraform {
  required_providers {
    dotenv = {
      source  = "germanbrew/dotenv"
      version = ">= 1.2.9, < 2.0.0"
    }
    google = {
      source  = "hashicorp/google"
      version = ">= 7.12.0, < 8.0.0"
    }
  }
  required_version = ">= 1.12.2"
}
