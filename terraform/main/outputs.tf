output "project" {
  description = "Project ID"
  value       = local.project
}

output "region" {
  description = "Compute region"
  value       = local.location
}

output "service_account_email" {
  description = "GCE instance service account email"
  value       = google_service_account.app.email
}

output "service_account_roles" {
  description = "Service account project IAM policy roles"
  value       = [for role in var.app_iam_roles : role]
}
