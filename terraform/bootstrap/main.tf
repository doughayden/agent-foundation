data "dotenv" "adk" {
  filename = "${path.cwd}/.env"
}

# Get required Terraform variables from the project .env file unless explicitly passes as a root module input
locals {
  agent_name       = coalesce(var.agent_name, data.dotenv.adk.entries.AGENT_NAME)
  project          = coalesce(var.project, data.dotenv.adk.entries.GOOGLE_CLOUD_PROJECT)
  location         = coalesce(var.region, data.dotenv.adk.entries.GOOGLE_CLOUD_LOCATION)
  repository_name  = coalesce(var.repository_name, data.dotenv.adk.entries.GITHUB_REPO_NAME)
  repository_owner = coalesce(var.repository_owner, data.dotenv.adk.entries.GITHUB_REPO_OWNER)
}

resource "google_project_service" "main" {
  for_each           = toset(var.services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "${local.agent_name}-github"
  display_name              = "GitHub Actions: ${local.agent_name}"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_provider_id = "${local.agent_name}-oidc"
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  display_name                       = "GitHub OIDC: ${local.agent_name}"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
  }
  attribute_condition = "attribute.repository == '${local.repository_owner}/${local.repository_name}'"
}

resource "google_project_iam_member" "github" {
  for_each = toset(var.github_workload_iam_roles)
  project  = local.project
  role     = each.value
  member   = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.repository_owner}/${local.repository_name}"
}

resource "google_artifact_registry_repository" "cloud_run" {
  repository_id          = local.agent_name
  format                 = "DOCKER"
  description            = "${local.agent_name} Cloud Run Docker repository"
  cleanup_policy_dry_run = false

  # Delete untagged images (intermediate layers when tags are reused)
  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state = "UNTAGGED"
    }
  }

  # Delete tagged images older than 30 days (buildcache protected by the keep policy below)
  cleanup_policies {
    id     = "delete-old-tagged"
    action = "DELETE"
    condition {
      tag_state  = "TAGGED"
      older_than = "30d"
    }
  }

  # Keep 5 most recent versions (exemption from age deletion)
  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
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

resource "google_vertex_ai_reasoning_engine" "session_and_memory" {
  display_name = "Session and Memory Engine: ${local.agent_name}"
  description  = "Managed Session and Memory Bank Service"
}

# GitHub
locals {
  github_variables = {
    GCP_WORKLOAD_IDENTITY_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_PROJECT_ID                 = local.project
    ARTIFACT_REGISTRY_LOCATION     = google_artifact_registry_repository.cloud_run.location
    ARTIFACT_REGISTRY_URI          = google_artifact_registry_repository.cloud_run.registry_uri
    IMAGE_NAME                     = local.agent_name
  }
}

resource "github_actions_variable" "variable" {
  for_each      = local.github_variables
  repository    = local.repository_name
  variable_name = each.key
  value         = each.value
}
