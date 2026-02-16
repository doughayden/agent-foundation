provider "google" {
  project               = var.project
  region                = var.location
  billing_project       = var.project
  user_project_override = true
}

provider "random" {}
