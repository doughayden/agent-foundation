# GCS partial backend for Terraform state
# Bucket name passed via -backend-config during terraform init
terraform {
  backend "gcs" {
    prefix = "bootstrap"
  }
}
