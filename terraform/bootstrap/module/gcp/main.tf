locals {
  services = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "sts.googleapis.com",
    "telemetry.googleapis.com",
  ])

  github_workload_iam_roles = toset([
    "roles/aiplatform.user",
    "roles/artifactregistry.writer",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser", # Required for Cloud Run to attach service accounts during deployment
    "roles/resourcemanager.projectIamAdmin",
    "roles/run.admin",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/storage.admin",
  ])
}

resource "google_project_service" "main" {
  for_each           = toset(local.services)
  project            = var.project
  service            = each.value
  disable_on_destroy = false
}

data "github_repository" "agent" {
  full_name = "${var.repository_owner}/${var.repository_name}"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project
  workload_identity_pool_id = substr("gh-actions-${var.environment}-${data.github_repository.agent.repo_id}", 0, 32)
  display_name              = "GitHub Actions (${var.environment})"
  description               = "GitHub Actions - environment: ${var.environment}, repository: ${var.repository_owner}/${var.repository_name}, repo ID: ${data.github_repository.agent.repo_id}"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project
  workload_identity_pool_provider_id = substr("gh-oidc-${var.environment}-${data.github_repository.agent.repo_id}", 0, 32)
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  display_name                       = "GitHub OIDC (${var.environment})"
  description                        = "GitHub OIDC - environment: ${var.environment}, repository: ${var.repository_owner}/${var.repository_name}, repo ID: ${data.github_repository.agent.repo_id}"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.environment"      = "assertion.environment"
  }
  attribute_condition = "attribute.repository == '${var.repository_owner}/${var.repository_name}'"
}

resource "google_project_iam_member" "github" {
  for_each = toset(local.github_workload_iam_roles)
  project  = var.project
  role     = each.value
  member   = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.repository_owner}/${var.repository_name}"
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "terraform_state" {
  project  = var.project
  name     = "terraform-state-${var.agent_name}-${var.environment}-${random_id.bucket_suffix.hex}"
  location = "US"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_artifact_registry_repository" "docker" {
  project                = var.project
  repository_id          = "${var.agent_name}-${var.environment}"
  format                 = "DOCKER"
  description            = "Docker repository for ${var.agent_name} (${var.environment})"
  cleanup_policy_dry_run = false

  # Delete untagged images (intermediate layers when tags are reused)
  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state = "UNTAGGED"
    }
  }

  # General cleanup policy (all environments)
  cleanup_policies {
    id     = "general-cleanup"
    action = "DELETE"
    condition {
      older_than = "${var.registry_cleanup_general_retention_days * 86400}s"
    }
  }

  # Optional KEEP policy (dev uses this to prevent cleanup of recent images)
  dynamic "cleanup_policies" {
    for_each = var.registry_cleanup_keep_count != null ? ["keep"] : []
    content {
      id     = "keep-recent"
      action = "KEEP"
      most_recent_versions {
        keep_count = var.registry_cleanup_keep_count
      }
    }
  }

  # Optional PR cleanup policy (dev only)
  dynamic "cleanup_policies" {
    for_each = var.registry_cleanup_pr_retention_days != null ? ["pr"] : []
    content {
      id     = "pr-cleanup"
      action = "DELETE"
      condition {
        tag_prefixes = ["pr-"]
        older_than   = "${var.registry_cleanup_pr_retention_days * 86400}s"
      }
    }
  }

  # Keep buildcache indefinitely (needed for fast builds)
  cleanup_policies {
    id     = "keep-buildcache"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["buildcache"]
    }
  }

  depends_on = [google_project_service.main["artifactregistry.googleapis.com"]]
}
