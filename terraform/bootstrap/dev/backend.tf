# GCS partial backend for Terraform state
# Bucket name passed via -backend-config during terraform init
# Example for dev (change both occurrences of 'dev' in the command to 'stage' or 'prod' to initialize bootstrap in those environments):
# terraform -chdir=terraform/bootstrap/dev init -backend-config="bucket=$(terraform -chdir=terraform/pre output -json terraform_state_buckets | jq -r '.dev')"
terraform {
  backend "gcs" {
    prefix = "bootstrap"
  }
}
