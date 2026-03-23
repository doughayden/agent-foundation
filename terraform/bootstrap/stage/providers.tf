provider "google" {
  project = var.project
  region  = var.region
}

provider "github" {
  owner = var.repository_owner
}
