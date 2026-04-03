resource "random_password" "postgres_root" {
  length  = 30
  special = true
}

resource "google_sql_database_instance" "sessions" {
  name                = "${local.resource_name}-sessions"
  database_version    = "POSTGRES_18"
  region              = var.region
  root_password       = random_password.postgres_root.result
  deletion_protection = true

  # ref: https://docs.cloud.google.com/sql/docs/postgres/machine-series-overview
  settings {
    edition               = "ENTERPRISE"
    tier                  = "db-custom-1-3840"
    connector_enforcement = "REQUIRED"

    # Enable SQL Studio access in the dev environment
    data_api_access = var.environment == "dev" ? "ALLOW_DATA_API" : "DISALLOW_DATA_API"

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.main.id
      enable_private_path_for_google_cloud_services = true
      ssl_mode                                      = "TRUSTED_CLIENT_CERTIFICATE_REQUIRED"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
      }
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 6 # 06:00 UTC (offset from 03:00 backup window)
      update_track = "stable"
    }

    password_validation_policy {
      enable_password_policy      = true
      min_length                  = 30
      complexity                  = "COMPLEXITY_DEFAULT"
      disallow_username_substring = true
    }
  }

  # ref: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database_instance#private-ip-instance
  depends_on = [google_service_networking_connection.private_db]
}

resource "google_sql_database" "sessions" {
  name     = "agent_sessions"
  instance = google_sql_database_instance.sessions.name
}

resource "time_sleep" "cloud_sql_ready" {
  depends_on      = [google_sql_database.sessions]
  create_duration = "30s"
}

resource "google_sql_user" "app" {
  # Ref: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_user
  name     = trimsuffix(google_service_account.app.email, ".gserviceaccount.com")
  instance = google_sql_database_instance.sessions.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
  # cloudsqlsuperuser is Cloud SQL's standard IAM database role (not Postgres SUPERUSER).
  # Grants DDL + DML ownership — required for ADK DatabaseSessionService auto-schema creation.
  database_roles = ["cloudsqlsuperuser"]

  depends_on = [time_sleep.cloud_sql_ready]
}
