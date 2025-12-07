data "dotenv" "config" {
  filename = "${path.cwd}/.env"
}

# Get required Terraform variables from the project .env file unless explicitly passed as a root module input
locals {
  project                                            = coalesce(var.project, data.dotenv.config.entries.GOOGLE_CLOUD_PROJECT)
  location                                           = coalesce(var.location, data.dotenv.config.entries.GOOGLE_CLOUD_LOCATION)
  agent_name                                         = coalesce(var.agent_name, data.dotenv.config.entries.AGENT_NAME)
  otel_instrumentation_genai_capture_message_content = coalesce(var.otel_instrumentation_genai_capture_message_content, data.dotenv.config.entries.OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT)
  repository_name                                    = coalesce(var.repository_name, data.dotenv.config.entries.GITHUB_REPO_NAME)
  repository_owner                                   = coalesce(var.repository_owner, data.dotenv.config.entries.GITHUB_REPO_OWNER)

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
    "roles/storage.admin",
  ])
}

resource "google_project_service" "main" {
  for_each           = toset(local.services)
  project            = local.project
  service            = each.value
  disable_on_destroy = false
}

data "github_repository" "agent" {
  full_name = "${local.repository_owner}/${local.repository_name}"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = local.project
  workload_identity_pool_id = substr("actions-${data.github_repository.agent.repo_id}", 0, 32)
  display_name              = "GitHub Actions"
  description               = "GitHub Actions - repository: ${local.repository_owner}/${local.repository_name}, repo ID: ${data.github_repository.agent.repo_id}"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = local.project
  workload_identity_pool_provider_id = substr("gh-oidc-${data.github_repository.agent.repo_id}", 0, 32)
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  display_name                       = "GitHub OIDC"
  description                        = "GitHub OIDC - repository: ${local.repository_owner}/${local.repository_name}, repo ID: ${data.github_repository.agent.repo_id}"
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
  for_each = toset(local.github_workload_iam_roles)
  project  = local.project
  role     = each.value
  member   = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.repository_owner}/${local.repository_name}"
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "terraform_state" {
  project  = local.project
  name     = "terraform-state-${local.agent_name}-${random_id.bucket_suffix.hex}"
  location = "US"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_artifact_registry_repository" "cloud_run" {
  project                = local.project
  repository_id          = local.agent_name
  format                 = "DOCKER"
  description            = "Cloud Run Docker repository: ${local.agent_name}"
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

locals {
  github_variables = {
    ARTIFACT_REGISTRY_LOCATION                         = google_artifact_registry_repository.cloud_run.location
    ARTIFACT_REGISTRY_URI                              = google_artifact_registry_repository.cloud_run.registry_uri
    GCP_LOCATION                                       = local.location
    GCP_PROJECT_ID                                     = local.project
    GCP_WORKLOAD_IDENTITY_PROVIDER                     = google_iam_workload_identity_pool_provider.github.name
    IMAGE_NAME                                         = local.agent_name
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = local.otel_instrumentation_genai_capture_message_content
    TERRAFORM_STATE_BUCKET                             = google_storage_bucket.terraform_state.name
  }
}

resource "github_actions_variable" "variable" {
  for_each      = local.github_variables
  repository    = local.repository_name
  variable_name = each.key
  value         = each.value
}
