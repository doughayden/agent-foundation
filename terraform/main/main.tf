# Read own previous deployment (for docker_image default)
data "terraform_remote_state" "main" {
  backend = "gcs"

  config = {
    bucket = var.terraform_state_bucket
    prefix = "main"
  }
}

locals {
  # Run app service account roles
  app_iam_roles = toset([
    "roles/aiplatform.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/storage.bucketViewer",
    "roles/storage.objectUser",
    "roles/telemetry.tracesWriter",
  ])

  # Prepare for future regional Cloud Run redundancy
  locations = toset([var.location])

  # Cloud Run service environment variables
  run_app_env = {
    ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS         = coalesce(var.adk_suppress_experimental_feature_warnings, "TRUE")
    AGENT_ENGINE                                       = google_vertex_ai_reasoning_engine.session_and_memory.id
    AGENT_NAME                                         = var.agent_name
    ALLOW_ORIGINS                                      = jsonencode(["http://127.0.0.1", "http://127.0.0.1:8000"]) # Localhost-only for gcloud proxy access (add client service origins when UI is deployed)
    ARTIFACT_SERVICE_URI                               = google_storage_bucket.artifact_service.url
    GOOGLE_CLOUD_LOCATION                              = var.location
    GOOGLE_CLOUD_PROJECT                               = var.project
    GOOGLE_GENAI_USE_VERTEXAI                          = "TRUE"
    LOG_LEVEL                                          = coalesce(var.log_level, "INFO")
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = coalesce(var.otel_instrumentation_genai_capture_message_content, "FALSE")
    RELOAD_AGENTS                                      = "FALSE"
    ROOT_AGENT_MODEL                                   = coalesce(var.root_agent_model, "gemini-2.5-flash")
    SERVE_WEB_INTERFACE                                = coalesce(var.serve_web_interface, "FALSE")
    TELEMETRY_NAMESPACE                                = var.environment
  }

  # Create a unique Agent resource name per deployment environment
  resource_name = "${var.agent_name}-${var.environment}"

  # Service account ID has 30 character limit - truncate agent_name but preserve environment
  sa_max_agent_length = 30 - length(var.environment) - 1 # Reserve space for "-environment"
  sa_id               = "${substr(var.agent_name, 0, local.sa_max_agent_length)}-${var.environment}"

  # Create labels for billing organization
  labels = {
    application = var.agent_name
    environment = var.environment
  }

  # Recycle docker_image from previous deployment if not provided
  docker_image = coalesce(var.docker_image, try(data.terraform_remote_state.main.outputs.deployed_image, null))
}

resource "google_service_account" "app" {
  account_id   = local.sa_id
  display_name = "${local.resource_name} Service Account"
  description  = "Service account attached to the ${local.resource_name} Cloud Run service"
}

resource "google_project_iam_member" "app" {
  for_each = local.app_iam_roles
  project  = var.project
  role     = each.key
  member   = google_service_account.app.member
}

resource "google_vertex_ai_reasoning_engine" "session_and_memory" {
  display_name = "${local.resource_name} Sessions and Memory"
  description  = "Managed Session and Memory Bank Service for the ${local.resource_name} app"

  # Prevent plan and apply diffs with an empty spec for managed sessions and memory bank only (no runtime code)
  spec {}
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "artifact_service" {
  name     = "${local.resource_name}-artifact-service-${random_id.bucket_suffix.hex}"
  location = "US"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_cloud_run_v2_service" "app" {
  for_each            = local.locations
  name                = local.resource_name
  location            = each.key
  deletion_protection = false
  launch_stage        = "GA"
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels

  # Service-level scaling (updates without creating new revisions)
  scaling {
    # Set min_instance_count to 1 or more in production to avoid cold start latency
    # min_instance_count = 1
    max_instance_count = 100
  }

  template {
    service_account       = google_service_account.app.email
    timeout               = "300s"
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    containers {
      image = local.docker_image

      ports {
        name           = "http1"
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        # true = Request-based billing, false = instance-based billing
        # https://cloud.google.com/run/docs/configuring/billing-settings#setting
        cpu_idle = true
      }

      startup_probe {
        failure_threshold     = 5
        initial_delay_seconds = 20
        timeout_seconds       = 15
        period_seconds        = 20
        http_get {
          path = "/health"
          port = 8000
        }
      }

      dynamic "env" {
        for_each = local.run_app_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }

    # Explicitly set the concurrency (defaults to 80 for CPU >= 1).
    max_instance_request_concurrency = 100
  }
}

# Read Cloud Run service state after resource modification completes to work around GCP API eventual
# consistency - Terraform's dependency graph ensures this data source is read after the resource is
# updated, guaranteeing outputs reflect the actual deployed revision rather than stale cached data.
data "google_cloud_run_v2_service" "app_actual" {
  for_each = local.locations
  name     = google_cloud_run_v2_service.app[each.key].name
  location = each.key
}
