# GCS partial backend for Terraform state
# Bucket name passed via -backend-config during terraform init
# Example (local): terraform -chdir=terraform/main init -backend-config="bucket=$(terraform -chdir=terraform/bootstrap/dev output -raw terraform_state_bucket)"
# Example (CI/CD): terraform init -backend-config="bucket=${{ vars.TERRAFORM_STATE_BUCKET }}"
terraform {
  backend "gcs" {
    prefix = "main"
  }
}
