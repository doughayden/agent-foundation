provider "google" {
  project = local.project
  region  = local.location
}

provider "github" {
  owner = local.repository_owner
}

provider "dotenv" {}
