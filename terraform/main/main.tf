# Read own previous deployment (for docker_image default)
data "terraform_remote_state" "main" {
  backend   = "gcs"
  workspace = terraform.workspace

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

  run_app_env = {
    ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS = coalesce(var.adk_suppress_experimental_feature_warnings, "TRUE")
    AGENT_ENGINE                               = coalesce(var.agent_engine, google_vertex_ai_reasoning_engine.session_and_memory.id)
    AGENT_NAME                                 = var.agent_name
    ALLOW_ORIGINS                              = coalesce(var.allow_origins, jsonencode(["http://127.0.0.1", "http://127.0.0.1:8000"]))
    ARTIFACT_SERVICE_URI                       = coalesce(var.artifact_service_uri, google_storage_bucket.artifact_service.url)
    GOOGLE_CLOUD_LOCATION                      = var.location
    GOOGLE_CLOUD_PROJECT                       = var.project
    GOOGLE_GENAI_USE_VERTEXAI                  = "TRUE"
    LOG_LEVEL                                  = coalesce(var.log_level, "INFO")
    RELOAD_AGENTS                              = "FALSE"
    ROOT_AGENT_MODEL                           = coalesce(var.root_agent_model, "gemini-2.5-flash")
    SERVE_WEB_INTERFACE                        = coalesce(var.serve_web_interface, "FALSE")
  }

  # Recycle docker_image from previous deployment if not provided
  docker_image = coalesce(var.docker_image, try(data.terraform_remote_state.main.outputs.deployed_image, null))
}

resource "google_service_account" "app" {
  account_id   = var.agent_name
  description  = "${var.agent_name} Cloud Run service-attached service account"
  display_name = "${var.agent_name} Service Account"
}

resource "google_project_iam_member" "app" {
  for_each = local.app_iam_roles
  project  = var.project
  role     = each.key
  member   = google_service_account.app.member
}

resource "google_vertex_ai_reasoning_engine" "session_and_memory" {
  display_name = "Session and Memory: ${var.agent_name}"
  description  = "Managed Session and Memory Bank Service"
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "artifact_service" {
  name     = "artifact-service-${var.agent_name}-${random_id.bucket_suffix.hex}"
  location = "US"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_cloud_run_v2_service" "app" {
  for_each            = local.locations
  name                = var.agent_name
  location            = each.key
  deletion_protection = false
  launch_stage        = "GA"
  ingress             = "INGRESS_TRAFFIC_ALL"

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
