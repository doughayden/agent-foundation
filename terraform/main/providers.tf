provider "google" {
  project = local.project
  region  = local.location
}

provider "dotenv" {}
