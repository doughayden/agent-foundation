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
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/storage.bucketViewer",
    "roles/storage.objectUser",
    "roles/telemetry.tracesWriter",
  ])

  # Prepare for future regional Cloud Run redundancy
  locations = toset([var.region])

  # Cloud Run service environment variables
  run_app_env = {
    ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS         = coalesce(var.adk_suppress_experimental_feature_warnings, "TRUE")
    AGENT_NAME                                         = var.agent_name
    ALLOW_ORIGINS                                      = jsonencode(["http://127.0.0.1", "http://127.0.0.1:8000"]) # Localhost-only for gcloud proxy access (add client service origins when UI is deployed)
    ARTIFACT_SERVICE_URI                               = google_storage_bucket.artifact_service.url
    GOOGLE_CLOUD_LOCATION                              = var.google_cloud_location
    GOOGLE_CLOUD_PROJECT                               = var.project
    GOOGLE_GENAI_USE_VERTEXAI                          = "TRUE"
    LOG_LEVEL                                          = coalesce(var.log_level, "INFO")
    MEMORY_SERVICE_URI                                 = "agentengine://${google_vertex_ai_reasoning_engine.session_and_memory.id}"
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = coalesce(var.otel_instrumentation_genai_capture_message_content, "FALSE")
    RELOAD_AGENTS                                      = "FALSE"
    SERVE_WEB_INTERFACE                                = coalesce(var.serve_web_interface, "FALSE")
    SESSION_SERVICE_URI                                = "postgresql+asyncpg://${google_sql_user.app.name}@localhost:5432/${google_sql_database.sessions.name}"
    TELEMETRY_NAMESPACE                                = var.environment
  }

  # Cloud SQL Auth Proxy args — shared between bastion and Cloud Run sidecar
  cloud_sql_proxy_args = [
    google_sql_database_instance.sessions.connection_name,
    "--private-ip",
    "--port=5432",
    "--auto-iam-authn",
    "--structured-logs",
  ]

  # Create a unique Agent resource name per deployment environment
  resource_name = "${var.agent_name}-${var.environment}"

  # Service account IDs — GCP 30-char limit. Truncate agent_name (prefix) to preserve environment suffix.
  sa_limit = 30

  sa_suffix_app = "-${var.environment}"
  sa_prefix_app = substr(var.agent_name, 0, local.sa_limit - length(local.sa_suffix_app))
  sa_id_app     = "${local.sa_prefix_app}${local.sa_suffix_app}"

  sa_suffix_bastion = "-bastion-${var.environment}"
  sa_prefix_bastion = substr(var.agent_name, 0, local.sa_limit - length(local.sa_suffix_bastion))
  sa_id_bastion     = "${local.sa_prefix_bastion}${local.sa_suffix_bastion}"

  # Create labels for billing organization
  labels = {
    application = var.agent_name
    environment = var.environment
  }

  # Recycle docker_image from previous deployment if not provided
  docker_image = coalesce(var.docker_image, try(data.terraform_remote_state.main.outputs.deployed_image, null))
}

resource "google_service_account" "app" {
  account_id   = local.sa_id_app
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
  region       = var.region

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

    # Cloud SQL Auth Proxy sidecar (no startup probe — Cloud Run restarts on crash)
    containers {
      image = "gcr.io/cloud-sql-connectors/cloud-sql-proxy:2"
      args  = concat(local.cloud_sql_proxy_args, ["--exit-zero-on-sigterm"])
    }

    # Direct VPC egress for Cloud SQL private IP connectivity
    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    # Explicitly set the concurrency (defaults to 80 for CPU >= 1).
    max_instance_request_concurrency = 100
  }
}

# Read Cloud Run service state after resource modification completes to work around GCP API eventual
# consistency - Terraform's dependency graph ensures this data source is read after the resource is
# updated, guaranteeing outputs reflect the actual deployed revision rather than stale cached data.
data "google_cloud_run_v2_service" "app" {
  for_each = local.locations
  name     = google_cloud_run_v2_service.app[each.key].name
  location = each.key
}
