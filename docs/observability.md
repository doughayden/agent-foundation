# Agent Observability with OpenTelemetry

The server exports traces, logs and metrics over OTLP gRPC to Google Cloud, with the same setup locally and on Cloud Run. The ADK web UI keeps its trace view when enabled.

## What's Instrumented

- **Agent runs**: ADK spans for each invocation, agent, model call and tool call, plus ADK's GenAI metrics (operation duration, token usage, agent and tool call counts, and the `adk.experimental.*` breakdowns that `ADK_EXPERIMENTAL_TELEMETRY` adds) whenever metrics are on
- **GenAI events**: Model call details as log records, with message content when [capture](#message-content-capture) is on
- **Application logs**: Python `logging` records with trace context, including the [callback logging](#callback-logging)

## Key Features

- **Owned providers**: `configure_telemetry()` sets the tracer, logger and (when the resource has `cloud.region`) meter providers before `get_fast_api_app()`; ADK only attaches its web UI processors to them
- **Google Cloud**: Traces and logs go to the [Telemetry API](https://cloud.google.com/stackdriver/docs/reference/telemetry/overview) with Application Default Credentials, landing in Cloud Trace and Cloud Logging
- **Metrics where a location is known**: On Cloud Run, metrics go to Google automatically. Locally they go to Google only when you add `cloud.region=<region>` to `OTEL_RESOURCE_ATTRIBUTES`; otherwise they are off. Google metrics land in Cloud Monitoring beside Cloud Run's native metrics
- **One backend**: Telemetry targets Google Cloud only. To use another backend, replace `telemetry.py`
- **Consistent resource**: Every signal carries the same identifying attributes: `service.name` from `AGENT_NAME`, `service.namespace` per environment, a unique `service.instance.id` per process, and the Cloud Run revision as `faas.version` from the resource detector
- **Cloud Run logs in place**: On Cloud Run, the traces and logs resource adds the `cloud_run_revision` attributes, so logs appear in the service's Logs tab beside stdout. Metrics use a separate resource without them, because the Telemetry API drops metric points that carry `gcp.resource_type`, so metric queries cannot filter on revision labels

## Configuration

**Required environment variables:**
- `AGENT_NAME`: OpenTelemetry `service.name` (required)
- `GOOGLE_CLOUD_PROJECT`: GCP project ID (required)
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`: Message content capture mode (required, see [Message Content Capture](#message-content-capture))

**Optional variables:**
- `LOG_LEVEL`: Logging verbosity - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
- `OTEL_RESOURCE_ATTRIBUTES`: override or add resource attributes, like `OTEL_RESOURCE_ATTRIBUTES=service.namespace=alice-local` to group your local experiments (Terraform sets `service.namespace` to the environment name when deployed)

Details and defaults: [Environment Variables](environment-variables.md).

> [!NOTE]
> Only `uv run server` and the container entry point run this setup. `adk web`, `adk api_server` and `adk run` use ADK's own telemetry setup instead.

## Viewing Telemetry in Google Cloud

**[Cloud Trace](https://console.cloud.google.com/traces):** Filter by service name, view spans, timing, and generative AI events.

On Cloud Run, a request's traces, logs and metrics can arrive late on a quiet service, because CPU is allocated only during requests. Causes and options: [OpenTelemetry Architecture](references/opentelemetry-architecture.md#export).

**[Logs Explorer](https://console.cloud.google.com/logs):** Application logs land in the log `otlp` and GenAI events in `gen_ai.client.inference.operation.details`. On Cloud Run both are on the `cloud_run_revision` resource; locally they are on `generic_task`.

```text
logName="projects/{PROJECT_ID}/logs/otlp"
resource.type="cloud_run_revision"
resource.labels.service_name="{AGENT_NAME}-{ENVIRONMENT}"
```

**[Metrics Explorer](https://console.cloud.google.com/monitoring/metrics-explorer):** ADK's GenAI metrics (like `gen_ai.client.token.usage`) appear as `prometheus.googleapis.com/<name>/<kind>` on the `prometheus_target` resource, beside Cloud Run's native metrics on the service's Metrics tab. On Cloud Run, metrics go to Google automatically. Locally they go to Google only when you add `cloud.region=<region>` to `OTEL_RESOURCE_ATTRIBUTES`; otherwise they are off.

### gcloud CLI

```bash
# Tail the service's OpenTelemetry logs
gcloud logging tail 'logName="projects/{PROJECT_ID}/logs/otlp" AND resource.type="cloud_run_revision"' --format=json

# View recent traces
gcloud trace list --limit=10
```

### VS Code GCP Extension

Install the [Google Cloud Code extension](https://cloud.google.com/code/docs/vscode/install) to view logs and traces directly in your IDE.

## Architecture

`server.py` calls `configure_telemetry()` before `get_fast_api_app()`. It builds the resource and the tracer, logger and meter providers (the meter provider only when the resource has `cloud.region`), sets them globally, and instruments logging. `telemetry.py` replaces ADK's internal telemetry setup with a function that only attaches the web UI's span and log processors to those providers, so ADK builds no providers, exporters or instrumentation of its own.

Design decisions, the ADK patch, and dependencies: [OpenTelemetry Architecture](references/opentelemetry-architecture.md).

### Resource Attributes

| Attribute | Source | Example |
|-----------|--------|---------|
| `service.name` | `AGENT_NAME` | `your-agent-name` |
| `service.namespace` | `OTEL_RESOURCE_ATTRIBUTES` (unset by default) | `dev`/`stage`/`prod` (deployed) or `alice-local` |
| `service.instance.id` | Generated per process (PID + UUID) | `worker-1234-a1b2c3d4e5f6` |
| `gcp.project_id` | `GOOGLE_CLOUD_PROJECT` | `my-project-id` |
| `cloud.*`, `faas.*` | GCP resource detector | `cloud.region=us-central1`, `faas.version=your-agent-name-dev-00042-abc` on Cloud Run |

`OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` win over these on a shared key, and the template's values win over the detector's. The standard `OTEL_SDK_DISABLED=true` turns all export off (SDK behavior) and leaves the web UI trace view empty.

## Alerting

The main module ships dry-run Cloud Monitoring alert policies for the four [golden signals](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals) (latency, traffic, errors, saturation), plus unhealthy instances, on the deployed Cloud Run service. Each condition reads a native `run.googleapis.com` metric with the aggregation its chart uses, so every alert maps to a chart on the service's Metrics tab in the [Cloud Run console](https://cloud.google.com/run/docs/monitoring). The template adds alert policies only, no dashboard.

| Policy | Metric | Default condition | Metrics tab chart |
|---|---|---|---|
| Latency | `request_latencies` | p95 above 60 s for 5 minutes | Request latencies |
| Traffic | `request_count` | above 10 requests/s for 5 minutes | Request count |
| Errors | `request_count` (`response_code_class = "5xx"` over all) | 5xx ratio above 5% for 5 minutes | Request count |
| Saturation | `container/cpu/utilizations`, `container/memory/utilizations`, `container/instance_count`, `container/max_request_concurrencies` | p99 CPU above 80% for 10 minutes, p99 memory above 80% for 5 minutes, instances above 80% of `max_instance_count`, or p99 concurrent requests above 80% of `max_instance_request_concurrency`, each for 5 minutes | Container CPU utilization, Container memory utilization, Container instance count, Max concurrent requests |
| Unhealthy instances | `container/instance_count_with_readiness` (`readiness_status = "UNHEALTHY"`), `container/completed_probe_count` (`is_healthy = false`) | any instance failing readiness, or any failed probe | Container health checks (failed probes: Metrics Explorer) |

The traffic policy fires on a spike rather than on silence: an idle environment scaled to zero is normal, while a sustained burst multiplies model spend. The service runs a readiness probe on `/health` after the startup probe passes, and Cloud Run stops routing requests to an instance that fails it. The unhealthy-instances policy alerts on those readiness failures and on any failed probe. Readiness only starts once startup passes, so the failed-probe condition is what catches a rollout whose new revision never starts while the previous revision keeps serving traffic, which otherwise shows up only as a failed deploy job. `/health` checks no dependencies, so readiness confirms the process still answers requests.

**Dry-run posture:** the policies evaluate and open incidents in [Cloud Monitoring alerting](https://console.cloud.google.com/monitoring/alerting) but notify nobody, so a fork inherits no inbox noise or paging.

**Activate notifications:** create a [notification channel](https://cloud.google.com/monitoring/support/notification-options) (email, Slack, PagerDuty and others), then add its ID (`projects/PROJECT_ID/notificationChannels/CHANNEL_ID`) to the environment's list in `alert_notification_channels` in `terraform/main/monitoring.tf`. The next deploy attaches it to every policy.

**Tune thresholds:** `alert_thresholds` in the same file holds every default. They are starting points for an LLM agent; set them to your own SLOs.

**Build from the console:** each chart on the Metrics tab has a bell icon that opens the alert builder prefilled with that chart's metric and aggregation, and its View Code button shows the policy JSON. Use it to try a threshold or draft a new policy, then carry the filter and aggregation into `monitoring.tf`.

## Callback Logging

`LoggingCallbacks` (in `callbacks.py`) logs agent lifecycle events (start/end, model calls, tool invocations) with automatic trace context correlation.

### Gen AI Usage Attributes

ADK records token usage on its `generate_content` span from `GenerateContentResponseUsageMetadata`:

| Attribute | Source fields |
|---|---|
| `gen_ai.usage.input_tokens` | `prompt_token_count` + `tool_use_prompt_token_count` |
| `gen_ai.usage.output_tokens` | `candidates_token_count` + `thoughts_token_count` |
| `gen_ai.usage.cache_read.input_tokens` | `cached_content_token_count` |
| `gen_ai.usage.reasoning.output_tokens` | `thoughts_token_count` |

For usage analysis over time, use ADK's token metrics (`gen_ai.client.token.usage` and the `adk.experimental.*` token histograms) rather than span attributes.

## Message Content Capture

Two settings decide where user content (prompts, responses, tool arguments and results) lands in telemetry:

| Setting | Controls | Default |
|---|---|---|
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Standard GenAI content: GenAI event log records and the `gen_ai.input.messages` / `gen_ai.output.messages` span attributes | Required. Deployed, bootstrap writes it from each root's `terraform.tfvars` |
| `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` | ADK's own `gcp.vertex.agent.*` span attributes: the full model request and response, and tool arguments and results. The ADK web UI trace view reads them | ADK default `true`, whatever the capture mode |

The capture mode takes exactly one of these four values:

| Value | Standard content goes to |
|---|---|
| `NO_CONTENT` | Nowhere (metadata only) |
| `EVENT_ONLY` | GenAI event log records (`gen_ai.client.inference.operation.details`), shown in the span's Input/Output view in Cloud Trace |
| `SPAN_ONLY` | Inference span attributes `gen_ai.input.messages` and `gen_ai.output.messages` |
| `SPAN_AND_EVENT` | Both |

> [!IMPORTANT]
> `NO_CONTENT` alone does not keep user content out of traces: ADK still writes it to its `gcp.vertex.agent.*` span attributes. Set `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` as well. Deployed, Terraform sets it whenever the capture mode is `NO_CONTENT`; locally, set both in `.env`.

Captured content raises logging costs and stores user data. Use `NO_CONTENT` for sensitive workloads.

## Resources

- [Google Cloud Observability | Instrument ADK Applications with OpenTelemetry](https://cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk)
- [Google Cloud Trace | View Generative AI Events](https://cloud.google.com/trace/docs/finding-traces#view_generative_ai_events)
- [OpenTelemetry | Generative AI Instrumentation](https://opentelemetry.io/blog/2024/otel-generative-ai/)
- [OpenTelemetry | Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OpenTelemetry Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)

---

← [Back to Documentation](README.md)
