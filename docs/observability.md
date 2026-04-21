# Agent Observability with OpenTelemetry

This project includes production-ready OpenTelemetry observability that provides consistent behavior across local development and deployed environments. The implementation automatically instruments LLM calls and application logs with minimal configuration while coexisting with ADK's internal telemetry infrastructure.

## What's Instrumented

- **LLM Operations**: Google Generative AI SDK calls with request/response details
- **Structured Logging**: JSON logs with automatic trace correlation for Google Cloud Logging
- **Agent Callbacks**: Lifecycle logging for agent start/end, model calls, and tool invocations

## Key Features

- **Consistent Setup**: Single `setup_opentelemetry()` function used across all environments (local and deployed)
- **Instance-Level Tracking**: Unique `SERVICE_INSTANCE_ID` per process (PID + UUID) for collision-free identification
- **Environment Grouping**: `SERVICE_NAMESPACE` automatically set to environment name in deployed environments (`dev`, `stage`, `prod`)
- **Version Tracking**: `SERVICE_VERSION` set to Cloud Run revision ID for deployment correlation
- **Google Cloud Integration**: Direct export to Google Cloud Trace (OTLP) and Cloud Logging
- **Trace Correlation**: Logs automatically include trace context via `LoggingInstrumentor`
- **Service Identification**: OpenTelemetry `service.name` set to `AGENT_NAME` environment variable
- **Authentication**: Uses Application Default Credentials (ADC) for Google Cloud APIs

## Configuration

**Required environment variables:**
- `AGENT_NAME`: OpenTelemetry service identifier (required)
- `GOOGLE_CLOUD_PROJECT`: GCP project ID for trace and log export (required)
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`: Capture LLM message content - `TRUE` or `FALSE` (required)

**Optional variables:**
- `GOOGLE_CLOUD_LOCATION`: Vertex AI region (default: `us-central1`)
- `LOG_LEVEL`: Logging verbosity - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
- `TELEMETRY_NAMESPACE`: Service namespace for trace grouping (default: `local`, auto-set to workspace in deployed environments)

See `.env.example` for complete configuration reference.

## Usage

Identical OpenTelemetry setup across local development and deployed environments:
- Traces and logs automatically exported to Google Cloud
- ADK web UI available locally (when web interface enabled)
- **Production tip**: Use INFO log level to minimize logging costs

## Viewing Traces and Logs

### Google Cloud Console (Recommended)

**[Cloud Trace](https://console.cloud.google.com/traces):** Filter by agent name, view spans, timing, and generative AI events

**[Logs Explorer](https://console.cloud.google.com/logs):** Query `logName="projects/{PROJECT_ID}/logs/{AGENT_NAME}-otel-logs"` for correlated logs (replace `{AGENT_NAME}` with your agent identifier)

### gcloud CLI

```bash
# Tail logs in real-time
gcloud logging tail "resource.type=cloud_run_revision" --format=json

# Filter by log name
gcloud logging tail "logName:projects/{PROJECT_ID}/logs/{AGENT_NAME}-otel-logs"

# View recent traces
gcloud trace list --limit=10
```

### VS Code GCP Extension

Install the [Google Cloud Code extension](https://cloud.google.com/code/docs/vscode/install) to view logs and traces directly in your IDE.

## Architecture

The observability module uses a two-phase initialization strategy to coexist with ADK's internal telemetry:

1. **Phase 1** (`configure_otel_resource()`): Set resource attributes via `OTEL_RESOURCE_ATTRIBUTES` env var *before* ADK starts. ADK reads these when constructing its internal `TracerProvider`.
2. **Phase 2** (`setup_opentelemetry()`): Run *after* `get_fast_api_app()` returns. Augment ADK's existing `TracerProvider` with a Cloud Trace span processor rather than replacing it. Configure logging exporters independently.

This approach preserves ADK's web UI traces (in-memory spans for local development) while adding Google Cloud export for all environments.

For the full explanation of why this design exists, including ADK's auto-instrumentation behavior and dependency decisions, see [OpenTelemetry Architecture](references/opentelemetry-architecture.md).

## Implementation Details

**Functions:** `configure_otel_resource()` sets resource attributes, `setup_opentelemetry()` configures exporters

**Components:** `GoogleGenAiSdkInstrumentor` (LLM ops), `LoggingInstrumentor` (trace context), `CloudLoggingExporter` (logs), `OTLPSpanExporter` (traces)

> [!NOTE]
> ADK auto-detects and calls `GoogleGenAiSdkInstrumentor().instrument()` when the package is installed. The explicit call in `observability.py` is redundant but idempotent — it serves as a defensive measure if the project ever stops using ADK's `get_fast_api_app()`.

### Resource Attributes

OpenTelemetry resource attributes uniquely identify your service instances in traces and logs:

| Attribute | Source | Example | Description |
|-----------|--------|---------|-------------|
| `service.name` | `AGENT_NAME` env var | `your-agent-name` | Service identifier (set explicitly in `.env`) |
| `service.namespace` | `TELEMETRY_NAMESPACE` env var | `dev`/`stage`/`prod` (deployed) or `local` (dev) | Environment name grouping for traces |
| `service.version` | `K_REVISION` env var | `your-agent-name-00042-abc` (deployed) or `local` (dev) | Cloud Run revision or local dev indicator |
| `service.instance.id` | Generated | `worker-1234-a1b2c3d4e5f6` | Unique process instance (PID + UUID) |
| `gcp.project_id` | `GOOGLE_CLOUD_PROJECT` env var | `my-project-id` | GCP project for resource correlation |

**Local Development:**
- `service.namespace`: Defaults to `"local"` (customize via `TELEMETRY_NAMESPACE` for multi-developer disambiguation)
- `service.version`: Set to `"local"`
- `service.instance.id`: Unique per server restart (includes UUID to prevent collisions)

**Deployed Environments:**
- `service.namespace`: Automatically set to environment name (`dev`, `stage`, `prod`)
- `service.version`: Automatically set to Cloud Run revision ID
- `service.instance.id`: Unique per container instance

## Callback Logging

`LoggingCallbacks` (in `callbacks.py`) logs agent lifecycle events (start/end, model calls, tool invocations) with automatic trace context correlation.

### Custom Gen AI Usage Attributes

`LoggingCallbacks.after_model` (registered as the root agent's `after_model_callback`) supplements the genai instrumentor's auto-emitted attributes with three token counts extracted from `GenerateContentResponseUsageMetadata`:

| Attribute | Source field | Semconv status |
|---|---|---|
| `gen_ai.usage.cache_read.input_tokens` | `cached_content_token_count` | Canonical (Development stability) — matches "tokens served from provider-managed cache" |
| `gen_ai.usage.reasoning_tokens` | `thoughts_token_count` | Draft / convention-consistent — name not yet final in semconv, but converging across Gemini / OpenAI / Anthropic telemetry |
| `gen_ai.usage.tool_use.input_tokens` | `tool_use_prompt_token_count` | Custom — no semconv equivalent yet; name follows the `cache_read.input_tokens` pattern for symmetry |

The genai instrumentor already auto-emits `gen_ai.usage.input_tokens` (from `prompt_token_count`) and `gen_ai.usage.output_tokens` (from `candidates_token_count`) on its `generate_content` span. The callback does not duplicate those. `total_token_count` is intentionally omitted — no corresponding semconv span attribute exists; the total is derivable as `input_tokens + output_tokens + reasoning_tokens + tool_use.input_tokens`.

String literals are used at the emission site rather than imported constants because the installed `opentelemetry-semantic-conventions` (0.58b0) does not yet export constants for the cache/reasoning/tool-use attributes. On future version bumps, check `opentelemetry.semconv._incubating.attributes.gen_ai_attributes` and switch to constant imports once upstream ships them.

## Message Content Capture

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` controls LLM content capture:
- `TRUE`: Full content (debugging, higher costs, sensitive data)
- `FALSE`: Metadata only (production, lower costs, privacy)

> [!IMPORTANT]
> Must be explicitly set to `TRUE` for ADK to capture conversation content

## Resources

- [Vertex AI | Agent Engine | Trace an Agent](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/manage/tracing)
- [Google Cloud Observability | Instrument ADK Applications with OpenTelemetry](https://cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk)
- [Google Cloud Trace | View Generative AI Events](https://cloud.google.com/trace/docs/finding-traces#view_generative_ai_events)
- [OpenTelemetry | Generative AI Instrumentation](https://opentelemetry.io/blog/2024/otel-generative-ai/)
- [OpenTelemetry | Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OpenTelemetry Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)

---

← [Back to Documentation](README.md)
