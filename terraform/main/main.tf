data "dotenv" "adk" {
  filename = "${path.cwd}/.env"
}

data "terraform_remote_state" "main" {
  # Using local state during initial development and will to GCS backend for production
  backend   = "local"
  workspace = terraform.workspace
}

# Get required Terraform variables from the project .env file unless explicitly passes as a root module input
locals {
  agent_name = coalesce(var.agent_name, data.dotenv.adk.entries.AGENT_NAME)
  project    = coalesce(var.project, data.dotenv.adk.entries.GOOGLE_CLOUD_PROJECT)
  location   = coalesce(var.location, data.dotenv.adk.entries.GOOGLE_CLOUD_LOCATION)

  # Prepare for future regional Cloud Run redundancy
  locations = toset([local.location])

  # Default model if not specified in .env
  default_model = "gemini-2.5-flash"

  run_app_env = {
    GOOGLE_GENAI_USE_VERTEXAI = data.dotenv.adk.entries.GOOGLE_GENAI_USE_VERTEXAI
    GOOGLE_CLOUD_PROJECT      = local.project
    GOOGLE_CLOUD_LOCATION     = local.location
    LOG_LEVEL                 = data.dotenv.adk.entries.LOG_LEVEL
    SERVE_WEB_INTERFACE       = data.dotenv.adk.entries.SERVE_WEB_INTERFACE
    AGENT_ENGINE              = data.dotenv.adk.entries.AGENT_ENGINE
    ROOT_AGENT_MODEL          = coalesce(var.model, try(data.dotenv.adk.entries.ROOT_AGENT_MODEL, local.default_model))
  }

  docker_image = coalesce(var.docker_image, try(data.terraform_remote_state.main.outputs.deployed_image, null))
}

resource "google_service_account" "app" {
  account_id   = local.agent_name
  description  = "${local.agent_name} Cloud Run service-attached service account"
  display_name = "${local.agent_name} Service Account"
}

resource "google_project_iam_member" "app" {
  for_each = var.app_iam_roles
  project  = local.project
  role     = each.key
  member   = google_service_account.app.member
}

resource "google_cloud_run_v2_service" "app" {
  for_each            = local.locations
  name                = local.agent_name
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
        timeout_seconds   = 30
        period_seconds    = 180
        failure_threshold = 1
        tcp_socket {
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

      # Ensure production workloads never enable agent hot reload
      env {
        name  = "RELOAD_AGENTS"
        value = "false"
      }

    }

    # Explicitly set the concurrency (defaults to 80 for CPU >= 1).
    max_instance_request_concurrency = 100
  }
}
