# Alert policies on native Cloud Run metrics; each condition mirrors a service Metrics tab chart.
# Dry-run by default: policies evaluate and open incidents in Cloud Monitoring but notify nobody until
# a notification channel ID is added for the environment below. Thresholds are starting points; tune them
# to your SLOs. Guide: docs/observability.md Alerting.
locals {
  # Notification channel IDs (projects/PROJECT/notificationChannels/ID) per environment
  alert_notification_channels = {
    dev   = []
    stage = []
    prod  = []
  }

  alert_thresholds = {
    latency_p95_ms        = 60000 # p95 request latency; agent turns call an LLM and run for seconds
    traffic_requests_rate = 10    # requests per second; each request spends model tokens
    error_ratio_5xx       = 0.05  # share of requests answered with a 5xx
    cpu_utilization       = 0.8   # p99 container CPU utilization (0 to 1)
    memory_utilization    = 0.8   # p99 container memory utilization (0 to 1)
    instance_count_ratio  = 0.8   # instances as a share of the service's max_instance_count
    concurrency_ratio     = 0.8   # p99 max concurrent requests as a share of max_instance_request_concurrency
  }

  notification_channels = local.alert_notification_channels[var.environment]

  run_revision_filter = {
    for location in local.locations : location => "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${local.resource_name}\" AND resource.labels.location = \"${location}\""
  }
}

resource "google_monitoring_alert_policy" "latency" {
  for_each              = local.locations
  display_name          = "${local.resource_name} latency (${each.key})"
  combiner              = "OR"
  severity              = "WARNING"
  notification_channels = local.notification_channels
  user_labels           = local.labels

  conditions {
    display_name = "p95 request latency above ${local.alert_thresholds.latency_p95_ms} ms"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/request_latencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = local.alert_thresholds.latency_p95_ms
      duration        = "300s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_PERCENTILE_95"
        group_by_fields      = ["resource.label.service_name"]
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Chart: Cloud Run service Metrics tab, Request latencies. Check Cloud Trace for slow model or tool spans."
  }

  depends_on = [
    time_sleep.service_enablement_propagation["monitoring.googleapis.com"],
    time_sleep.wif_iam_propagation["roles/monitoring.alertPolicyEditor"],
  ]
}

resource "google_monitoring_alert_policy" "traffic" {
  for_each              = local.locations
  display_name          = "${local.resource_name} traffic (${each.key})"
  combiner              = "OR"
  severity              = "WARNING"
  notification_channels = local.notification_channels
  user_labels           = local.labels

  conditions {
    display_name = "Request rate above ${local.alert_thresholds.traffic_requests_rate}/s"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/request_count\""
      comparison      = "COMPARISON_GT"
      threshold_value = local.alert_thresholds.traffic_requests_rate
      duration        = "300s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Chart: Cloud Run service Metrics tab, Request count. A sustained spike multiplies model spend; confirm the callers are expected."
  }

  depends_on = [
    time_sleep.service_enablement_propagation["monitoring.googleapis.com"],
    time_sleep.wif_iam_propagation["roles/monitoring.alertPolicyEditor"],
  ]
}

resource "google_monitoring_alert_policy" "errors" {
  for_each              = local.locations
  display_name          = "${local.resource_name} errors (${each.key})"
  combiner              = "OR"
  severity              = "ERROR"
  notification_channels = local.notification_channels
  user_labels           = local.labels

  conditions {
    display_name = "5xx ratio above ${local.alert_thresholds.error_ratio_5xx}"
    condition_threshold {
      filter             = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      denominator_filter = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/request_count\""
      comparison         = "COMPARISON_GT"
      threshold_value    = local.alert_thresholds.error_ratio_5xx
      duration           = "300s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }
      denominator_aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Chart: Cloud Run service Metrics tab, Request count grouped by response code class. Check Cloud Logging for ERROR entries on the failing revision."
  }

  depends_on = [
    time_sleep.service_enablement_propagation["monitoring.googleapis.com"],
    time_sleep.wif_iam_propagation["roles/monitoring.alertPolicyEditor"],
  ]
}

resource "google_monitoring_alert_policy" "saturation" {
  for_each              = local.locations
  display_name          = "${local.resource_name} saturation (${each.key})"
  combiner              = "OR"
  severity              = "WARNING"
  notification_channels = local.notification_channels
  user_labels           = local.labels

  conditions {
    display_name = "p99 container CPU utilization above ${local.alert_thresholds.cpu_utilization}"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/container/cpu/utilizations\""
      comparison      = "COMPARISON_GT"
      threshold_value = local.alert_thresholds.cpu_utilization
      duration        = "600s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_PERCENTILE_99"
        group_by_fields      = ["resource.label.service_name"]
      }
    }
  }

  conditions {
    display_name = "p99 container memory utilization above ${local.alert_thresholds.memory_utilization}"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/container/memory/utilizations\""
      comparison      = "COMPARISON_GT"
      threshold_value = local.alert_thresholds.memory_utilization
      duration        = "300s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_PERCENTILE_99"
        group_by_fields      = ["resource.label.service_name"]
      }
    }
  }

  conditions {
    display_name = "Instance count above ${local.alert_thresholds.instance_count_ratio * 100}% of max instances"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/container/instance_count\""
      comparison      = "COMPARISON_GT"
      threshold_value = google_cloud_run_v2_service.app[each.key].scaling[0].max_instance_count * local.alert_thresholds.instance_count_ratio
      duration        = "300s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }
    }
  }

  conditions {
    display_name = "p99 max concurrent requests above ${local.alert_thresholds.concurrency_ratio * 100}% of max concurrency"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/container/max_request_concurrencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = google_cloud_run_v2_service.app[each.key].template[0].max_instance_request_concurrency * local.alert_thresholds.concurrency_ratio
      duration        = "300s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_PERCENTILE_99"
        group_by_fields      = ["resource.label.service_name"]
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Charts: Cloud Run service Metrics tab, Container CPU utilization, Container memory utilization, Container instance count and Max concurrent requests. Raise CPU, memory, max instances or concurrency, or find the request driving the load."
  }

  depends_on = [
    time_sleep.service_enablement_propagation["monitoring.googleapis.com"],
    time_sleep.wif_iam_propagation["roles/monitoring.alertPolicyEditor"],
  ]
}

# Unhealthy instances: readiness failures (Container health checks chart) and failed probes, which cover a startup
# probe that never passes, so a rollout whose new revision never becomes ready still alerts
resource "google_monitoring_alert_policy" "unhealthy_instances" {
  for_each              = local.locations
  display_name          = "${local.resource_name} unhealthy instances (${each.key})"
  combiner              = "OR"
  severity              = "ERROR"
  notification_channels = local.notification_channels
  user_labels           = local.labels

  conditions {
    display_name = "Instances reporting UNHEALTHY"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/container/instance_count_with_readiness\" AND metric.labels.readiness_status = \"UNHEALTHY\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.revision_name"]
      }
    }
  }

  conditions {
    display_name = "Health check probe failed"
    condition_threshold {
      filter          = "${local.run_revision_filter[each.key]} AND metric.type = \"run.googleapis.com/container/completed_probe_count\" AND metric.labels.is_healthy = false"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.revision_name"]
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "An instance failed its readiness probe (Cloud Run stops routing requests to it) or a health check probe ended unhealthy. Chart: Cloud Run service Metrics tab, Container health checks; the failed-probe condition has no chart, use Metrics Explorer on completed_probe_count. A startup probe that never passes means the new revision takes no traffic while the previous revision keeps serving. Check the revision's system logs, then rerun the deploy if the same image deployed cleanly before (a transient infrastructure failure)."
  }

  depends_on = [
    time_sleep.service_enablement_propagation["monitoring.googleapis.com"],
    time_sleep.wif_iam_propagation["roles/monitoring.alertPolicyEditor"],
  ]
}
