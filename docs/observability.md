# Agent Observability with OpenTelemetry

The server exports traces, logs and metrics over OTLP gRPC, to Google Cloud by default or to any OTLP collector you name, with the same setup locally and on Cloud Run. The ADK web UI keeps its trace view when enabled.

## What's Instrumented

- **Agent runs**: ADK spans for each invocation, agent, model call and tool call, plus ADK's GenAI metrics (operation duration, token usage, agent and tool call counts, and the `adk.experimental.*` breakdowns that `ADK_EXPERIMENTAL_TELEMETRY` adds) whenever metrics have a destination
- **GenAI events**: Model call details as log records, with message content when [capture](#message-content-capture) is on
- **HTTP requests**: FastAPI server spans and metrics, the parents of ADK's spans
- **Session store**: asyncpg spans for Cloud SQL queries
- **Application logs**: Python `logging` records with trace context, including the [callback logging](#callback-logging)

## Key Features

- **Owned providers**: `configure_telemetry()` sets the tracer, logger and (when metrics have a destination) meter providers before `get_fast_api_app()`; ADK only attaches its web UI processors to them
- **Google by default**: Traces and logs go to the [Telemetry API](https://cloud.google.com/stackdriver/docs/reference/telemetry/overview) with Application Default Credentials, landing in Cloud Trace and Cloud Logging
- **Metrics where a location is known**: On Cloud Run, metrics go to Google automatically. Locally they go to Google only when you add `cloud.region=<region>` to `OTEL_RESOURCE_ATTRIBUTES`; otherwise they are off unless a collector is set. Google metrics land in Cloud Monitoring beside Cloud Run's native metrics
- **Any collector**: Standard `OTEL_EXPORTER_OTLP_*` variables redirect every signal, or one, to an OTLP endpoint ([Custom OTLP Endpoint](#custom-otlp-endpoint))
- **Consistent resource**: One resource on every signal, with `service.name` from `AGENT_NAME`, `service.namespace` per environment, `service.version` per Cloud Run revision and a unique `service.instance.id` per process
- **Cloud Run logs in place**: On Cloud Run, the shared resource carries the `cloud_run_revision` attributes, so logs appear in the service's Logs tab beside stdout

## Configuration

**Required environment variables:**
- `AGENT_NAME`: OpenTelemetry `service.name` (required)
- `GOOGLE_CLOUD_PROJECT`: GCP project ID (required)
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`: Message content capture mode (required, see [Message Content Capture](#message-content-capture))

**Optional variables:**
- `LOG_LEVEL`: Logging verbosity - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
- `OTEL_EXPORTER_OTLP_ENDPOINT` and the per-signal endpoints: export to a collector instead of Google
- `OTEL_RESOURCE_ATTRIBUTES`: override or add resource attributes, like `OTEL_RESOURCE_ATTRIBUTES=service.namespace=alice-local` to group your local experiments (Terraform sets `service.namespace` to the environment name when deployed)

Details and defaults: [Environment Variables](environment-variables.md).

## Custom OTLP Endpoint

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to send traces, logs and metrics to an OTLP gRPC collector instead of Google. The exporters read the rest of the standard [OTLP exporter variables](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/) (headers, certificates, timeout, compression) themselves. Set only `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` or `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` to redirect one signal; the others keep their Google destination (metrics only where a region is known).

Set these in `.env` or the shell. Export is OTLP gRPC only: an OTLP/HTTP endpoint (port 4318) or `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` is not supported.

> [!NOTE]
> Only `uv run server` and the container entry point run this setup. `adk web`, `adk api_server` and `adk run` use ADK's own telemetry setup instead.

**Local stack:** [grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm) runs a collector with Tempo, Loki and Prometheus behind Grafana:

```bash
docker run -d --rm --name otel-lgtm -p 3000:3000 -p 4317:4317 grafana/otel-lgtm
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 uv run server
```

Open Grafana at `http://localhost:3000`. Metrics export every 60 seconds, so give them a full interval before querying. From Docker Compose, the app container reaches a collector on your machine at `http://host.docker.internal:4317`, not `localhost`.

**Hosted collector:** point the endpoint at a collector you run elsewhere, like a private Cloud Run service on the same VPC, and pass any credentials it needs through `OTEL_EXPORTER_OTLP_HEADERS`.

## Viewing Telemetry in Google Cloud

**[Cloud Trace](https://console.cloud.google.com/traces):** Filter by service name, view spans, timing, and generative AI events.

**[Logs Explorer](https://console.cloud.google.com/logs):** Application logs land in the log `otlp` and GenAI events in `gen_ai.client.inference.operation.details`. On Cloud Run both are on the `cloud_run_revision` resource; locally they are on `generic_task`.

```text
logName="projects/{PROJECT_ID}/logs/otlp"
resource.type="cloud_run_revision"
resource.labels.service_name="{AGENT_NAME}-{ENVIRONMENT}"
```

**[Metrics Explorer](https://console.cloud.google.com/monitoring/metrics-explorer):** ADK's GenAI metrics (like `gen_ai.client.token.usage`) and the FastAPI HTTP metrics appear as `prometheus.googleapis.com/<name>/<kind>` on the `prometheus_target` resource, beside Cloud Run's native metrics on the service's Metrics tab. On Cloud Run, metrics go to Google automatically. Locally they go to Google only when you add `cloud.region=<region>` to `OTEL_RESOURCE_ATTRIBUTES`; otherwise they are off unless a collector is set.

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

`server.py` calls `configure_telemetry()` before `get_fast_api_app()`. It builds the resource and the tracer, logger and meter providers (the meter provider only when metrics have a destination), sets them globally, and instruments logging and asyncpg. `telemetry.py` replaces ADK's internal telemetry setup with a function that only attaches the web UI's span and log processors to those providers, so ADK builds no providers, exporters or instrumentation of its own. After the app exists, `instrument_app()` adds FastAPI spans and metrics.

Design decisions, the ADK patch, and dependencies: [OpenTelemetry Architecture](references/opentelemetry-architecture.md).

### Resource Attributes

| Attribute | Source | Example |
|-----------|--------|---------|
| `service.name` | `AGENT_NAME` | `your-agent-name` |
| `service.namespace` | `OTEL_RESOURCE_ATTRIBUTES` (default `local`) | `dev`/`stage`/`prod` (deployed) or `local` |
| `service.version` | `K_REVISION` | `your-agent-name-dev-00042-abc` (deployed) or `local` |
| `service.instance.id` | Generated per process (PID + UUID) | `worker-1234-a1b2c3d4e5f6` |
| `gcp.project_id` | `GOOGLE_CLOUD_PROJECT` | `my-project-id` |
| `cloud.*`, `faas.*` | GCP resource detector | `cloud.region=us-central1` on Cloud Run |

`OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` win over these on a shared key, and the template's values win over the detector's.

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

### Custom Gen AI Usage Attributes

`LoggingCallbacks.after_model` (registered as the root agent's `after_model_callback`) supplements ADK's token usage attributes with three token counts extracted from `GenerateContentResponseUsageMetadata`:

| Attribute | Source field | Semconv status |
|---|---|---|
| `gen_ai.usage.cache_read.input_tokens` | `cached_content_token_count` | Canonical (Development stability) — matches "tokens served from provider-managed cache" |
| `gen_ai.usage.reasoning_tokens` | `thoughts_token_count` | Draft / convention-consistent — name not yet final in semconv, but converging across Gemini / OpenAI / Anthropic telemetry |
| `gen_ai.usage.tool_use.input_tokens` | `tool_use_prompt_token_count` | Custom — no semconv equivalent yet; name follows the `cache_read.input_tokens` pattern for symmetry |

ADK already records `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` on its `generate_content` span. The callback does not duplicate those. `total_token_count` is intentionally omitted — no corresponding semconv span attribute exists; the total is derivable as `input_tokens + output_tokens + reasoning_tokens + tool_use.input_tokens`.

String literals are used at the emission site rather than imported constants because the installed `opentelemetry-semantic-conventions` (0.58b0) does not yet export constants for the cache/reasoning/tool-use attributes. On future version bumps, check `opentelemetry.semconv._incubating.attributes.gen_ai_attributes` and switch to constant imports once upstream ships them.

## Message Content Capture

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` controls whether and where ADK records prompts and responses. It takes exactly one of these four values:

| Value | Content goes to |
|---|---|
| `NO_CONTENT` | Nowhere (metadata only) |
| `EVENT_ONLY` | GenAI event log records (`gen_ai.client.inference.operation.details`) |
| `SPAN_ONLY` | Inference span attributes `gen_ai.input.messages` and `gen_ai.output.messages` |
| `SPAN_AND_EVENT` | Both |

`EVENT_ONLY` does not put content on spans: query the GenAI events log for it, or use `SPAN_ONLY` or `SPAN_AND_EVENT` to see it in Cloud Trace. Captured content raises logging costs and stores user data, so deployed environments default to `NO_CONTENT`.

## Resources

- [Google Cloud Observability | Instrument ADK Applications with OpenTelemetry](https://cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk)
- [Google Cloud Trace | View Generative AI Events](https://cloud.google.com/trace/docs/finding-traces#view_generative_ai_events)
- [OpenTelemetry | Generative AI Instrumentation](https://opentelemetry.io/blog/2024/otel-generative-ai/)
- [OpenTelemetry | Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OpenTelemetry Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)

---

← [Back to Documentation](README.md)
