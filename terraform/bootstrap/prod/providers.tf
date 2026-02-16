provider "google" {
  project = var.project
  region  = var.location
}

provider "github" {
  owner = var.repository_owner
}

provider "random" {}
