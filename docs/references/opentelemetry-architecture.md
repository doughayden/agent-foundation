# OpenTelemetry Architecture

Provider ownership, the ADK telemetry patch, export to Google Cloud, the resource, and dependency decisions for `telemetry.py`.

## Provider Ownership

The application owns all three OpenTelemetry providers. `server.py` runs, at import time:

```python
env = initialize_environment()    # ServerEnv
configure_telemetry(...)          # tracer, logger and (with cloud.region) meter providers set globally
app = get_fast_api_app(...)       # ADK attaches only its web UI processors
```

`configure_telemetry()` builds one resource and the providers that share it, then sets them globally: a `TracerProvider` with the template's sampler (see Trace Context and Sampling) and a `BatchSpanProcessor`, a `LoggerProvider` with a `BatchLogRecordProcessor` always, and a `MeterProvider` with a `PeriodicExportingMetricReader` (default 60 second interval) only when the resource has `cloud.region` (see Export). The meter provider gets its own resource: the shared one without the `cloud_run_revision` attributes. It also attaches the OTel logging handler to the root logger through `LoggingInstrumentor` (trace context on every record). A filter on the `uvicorn.access` logger drops `/health` access lines (Cloud Run probes), so they reach neither stdout nor Cloud Logging; it is a logger filter because uvicorn's logging config replaces handlers but keeps filters.

It must run before `get_fast_api_app()`: the patched ADK setup raises `RuntimeError` when the providers are not set yet.

## The ADK Telemetry Patch

`get_fast_api_app()` calls ADK's private `google.adk.cli.api_server._setup_telemetry()`, passing the web UI's processors: `ApiServerSpanExporter` and `InMemoryExporter` for spans, and `WebUiLogExporter` for the GenAI event records that show message content in the trace view. Unpatched, that function:

- Builds its own providers with OTLP/HTTP exporters when any `OTEL_EXPORTER_OTLP_*` endpoint is set, and instruments the GenAI SDK. With the application's providers already set, its `set_*_provider` calls do nothing, and the web UI processors passed in the same call are dropped
- Never attaches log processors to a logger provider set elsewhere, on any path

`telemetry.py` replaces it at import with `_attach_web_ui_processors()`, which adds the web UI's span and log processors to the global providers and does nothing else. ADK then builds no providers, exporters or instrumentation of its own, whatever OTLP variables are set. With the web UI off, ADK passes no processors and the function returns.

The patch follows ADK's own direction: [google/adk-python#3548](https://github.com/google/adk-python/pull/3548) made the default path reuse an initialized tracer provider. It is removable once an ADK release attaches the processors to already-set providers on every path. `tests/unit/test_telemetry.py` asserts it is applied.

## Export

Every signal exports to the Google Cloud Telemetry API (`TELEMETRY_API_ENDPOINT` in `telemetry.py`, `https://telemetry.googleapis.com:443`) over TLS channel credentials carrying Application Default Credentials (`cloud-platform` scope). Telemetry targets Google Cloud only; to use another backend, replace `telemetry.py`.

`configure_telemetry()` passes the endpoint to every exporter explicitly, so the SDK's `OTEL_EXPORTER_OTLP_*` endpoint variables and its `localhost:4317` default never apply. The SDK still reads the other `OTEL_EXPORTER_OTLP_*` variables itself: headers, certificates, compression and timeout. At startup it prints the endpoint, whether metrics are on for the run, and the exported resource attributes.

**Metrics on Google:** the Telemetry API rejects metric points without a location, so metrics go there only when the meter resource has `cloud.region`. On Cloud Run the GCP resource detector supplies it from the metadata server, so metrics flow automatically. Locally, add `cloud.region=<region>` to `OTEL_RESOURCE_ATTRIBUTES` to send them to Google. Without a region, no meter provider is set, so ADK's metric calls do nothing. Metrics land in Cloud Monitoring as `prometheus.googleapis.com/<name>/<kind>` on the `prometheus_target` resource, beside Cloud Run's native `run.googleapis.com` metrics, which the [alert policies](../observability.md#alerting) read.

The standard `OTEL_SDK_DISABLED=true` turns export off: the SDK providers read it themselves and hand out no-op tracers, loggers and meters, so nothing is recorded or exported and the web UI trace view stays empty. `configure_telemetry()` does not read it, so startup still looks up Application Default Credentials and prints the usual lines.

**Export timing on Cloud Run:** every signal exports from background batch processors (spans and logs every few seconds, metrics every 60 seconds). The service allocates CPU only while it handles requests (`cpu_idle = true` in `terraform/main/main.tf`), so after a request ends the export threads barely run, and that request's traces, logs and metrics can reach Google only when a later request gives the instance CPU again. On a busy service the delay is short; on a quiet one it can be minutes. Two ways to remove it, neither applied by the template:

- Flush at the end of each request: middleware that calls `force_flush()` on the tracer and logger providers before the response completes. Costs a little latency per request, no extra billing.
- Keep CPU allocated between requests: `cpu_idle = false`. Exports run on schedule, and the service moves to instance-based billing for CPU.

Only `server.py` (`uv run server` and the container entry point) runs this setup. `adk web`, `adk api_server` and `adk run` build their app through ADK's own telemetry setup.

Telemetry API permissions for the runtime service account: `roles/telemetry.tracesWriter` (traces), `roles/logging.logWriter` (logs) and `roles/telemetry.metricsWriter` (metrics), all in `app_iam_roles` in `terraform/main/main.tf`.

## Trace Context and Sampling

ADK's `get_fast_api_app()` runs a middleware on every request that continues the caller's trace: when the request carries a W3C `traceparent` header and `GOOGLE_CLOUD_AGENT_ENGINE_ID` is unset, ADK makes that header's span the parent of its `invoke_workflow` span (since ADK 2.14.0, [google/adk-python#7846](https://github.com/google/adk-python/pull/7846)). Without the header, `invoke_workflow` starts a new trace.

Cloud Run adds a `traceparent` to every request but marks only some of them sampled: it [samples at most 0.1 requests per second per instance](https://cloud.google.com/run/docs/trace), a rate cap rather than a percentage, so each instance sends at most one sampled request every 10 seconds and the rest arrive unsampled. The SDK's default sampler, `ParentBased(ALWAYS_ON)`, follows a remote parent's sampled flag. Under it, an agent turn is recorded only when it happens to be the request Cloud Run sampled, and every other turn's spans are dropped. Which turns survive depends on arrival order, since health checks and session calls compete for the same slot, and the share kept shrinks as traffic grows (about 1% at 10 requests per second on one instance). `build_sampler()` returns `ParentBased(root=ALWAYS_ON, remote_parent_not_sampled=ALWAYS_ON)` instead:

- Every agent request is traced, whatever Cloud Run sampled
- ADK's spans keep the caller's trace ID, so on Cloud Run the request log entry, the application logs and the agent spans share one trace ID. Cloud Run stores its own span for the request only when it sampled it
- A caller that sends its own `traceparent`, like another instrumented service, gets the agent spans inside its trace

Recording every turn suits development and low-volume services. Span volume, cost and noise grow with traffic, so a high-volume service should sample by ratio instead. Setting the standard `OTEL_TRACES_SAMPLER` replaces this sampler: `build_sampler()` returns `None` and the SDK reads the variable. Pick a sampler that ignores the parent's flag, like `traceidratio` with `OTEL_TRACES_SAMPLER_ARG=0.1` to keep a tenth of agent turns regardless of what Cloud Run sampled. A parent-based value, like `parentbased_always_on` (the SDK default), brings back Cloud Run's rate cap described above. Every recorded span counts toward [Cloud Trace pricing](https://cloud.google.com/products/observability/pricing#trace-costs); Cloud Run's own spans are free.

## Resource

`build_resources()` merges, lowest precedence first:

1. The SDK defaults (`telemetry.sdk.*`)
2. The GCP resource detector (`opentelemetry-resourcedetector-gcp`): `cloud.*` and `faas.*` attributes on Cloud Run, nothing locally
3. The template's values: `service.name` (`AGENT_NAME`), `service.instance.id`, `gcp.project_id` (`GOOGLE_CLOUD_PROJECT`)
4. The environment's `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`

The result is the meter resource. When the detector reports `cloud.platform=gcp_cloud_run`, the traces and logs resource adds the `cloud_run_revision` attributes mapped from the detected ones (see Log Placement); elsewhere both are the same resource. The Telemetry API rejects logs whose resource lacks `gcp.project_id`.

## Log Placement

**Log names:** the Telemetry API names a log after a record's `event_name`, or `otlp` when it has none. Application logs land in `otlp` and GenAI events in `gen_ai.client.inference.operation.details`. Filter by service through the resource labels.

**Resource type:** the Telemetry API maps OTLP logs to `generic_task` unless the resource names a monitored resource. On Cloud Run, the traces and logs resource carries `gcp.resource_type=cloud_run_revision` with `project_id`, `service_name` (`faas.name`), `revision_name` (`faas.version`), `configuration_name` (`K_CONFIGURATION`, which the detector reads but does not export) and `location` (`cloud.region`), so the logs appear in the service's Logs tab beside stdout. Locally the detector reports nothing, so logs stay on `generic_task`; `service.namespace` in `OTEL_RESOURCE_ATTRIBUTES` tells developers apart. ADK uses the same mechanism to place Agent Engine logs. Traces carry the attributes too. The meter resource leaves them off, because the Telemetry API drops metric points that carry `gcp.resource_type`; it keeps `cloud.region` from the detector or `OTEL_RESOURCE_ATTRIBUTES`, which wins.

**SDK diagnostics:** the `opentelemetry` logger writes to the console with propagation off, so an export failure is printed rather than handed back to the log exporter that is failing.

## GenAI Instrumentation

ADK records the model call span (`generate_content {model}`), the GenAI event log records, token usage and its GenAI metrics itself. The template does not install `GoogleGenAiSdkInstrumentor`: ADK hands it the inference span only under `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`, and with that opt-in and content capture on, the instrumentor fails to serialize a Pydantic tool response such as `load_memory`'s.

The template does not set `OTEL_SEMCONV_STABILITY_OPT_IN`. ADK's default telemetry schema already emits the experimental GenAI semantic conventions, and the opt-in only routes the inference span to the GenAI SDK instrumentor, which the template does not install.

Message content placement is ADK's: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` selects events, spans or both ([Message Content Capture](../observability.md#message-content-capture)).

### ADK Span Hierarchy

ADK produces its own span hierarchy using the `gcp.vertex.agent` tracer. The names below are ADK's default telemetry schema (OpenTelemetry GenAI semconv v2); setting `ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN=otel_semconv_1_36` restores the legacy schema, which names the top-level span `invocation` and wraps each model call in a `call_llm` span:

| Span Name | Purpose |
|---|---|
| `invoke_workflow` | Top-level span for a runner invocation |
| `invoke_agent {name}` | Agent-level span with agent name, session ID |
| `generate_content {model}` | Model inference |
| `execute_tool {name}` | Individual tool execution |

### ADK Metrics

ADK records into the global `MeterProvider` (meter `gcp.vertex.agent`) whenever one is set. Seven `gen_ai.*` histograms are on by default: operation duration, token usage (`gen_ai.client.token.usage`, input and output), agent, workflow and tool durations, and per-agent inference and tool call counts. `ADK_EXPERIMENTAL_TELEMETRY=TRUE`, which the template sets locally (`.env.example`) and on Cloud Run, adds the `adk.experimental.*` set: per-agent and per-workflow token breakdowns (cache reads, reasoning, tool input), workflow call counts, skill loads and compactions, plus experimental span attributes such as context-cache and grounding data. `ADK_EXPERIMENTAL_TELEMETRY_FEATURES` selects individual features instead.

## Dependency Management

### Direct Dependencies

| Package | Purpose |
|---|---|
| `opentelemetry-exporter-otlp-proto-grpc` | OTLP gRPC exporters for all three signals |
| `opentelemetry-instrumentation-logging` | Attaches the OTel handler to the root logger and adds trace context to `LogRecord`s |
| `opentelemetry-resourcedetector-gcp` | Cloud Run resource attributes, including the region the log placement needs |

### Transitive Dependencies (via ADK)

`opentelemetry-api` and `opentelemetry-sdk` come from ADK, which caps their version; the OTLP exporter and contrib instrumentations follow that cap. ADK's `[gcp]` and `[otel-gcp]` extras also install packages the template does not import, like the GCP-native trace, logging and monitoring exporters and the GenAI SDK instrumentor.

## Background Task Context Propagation

FastAPI `BackgroundTasks` (via Starlette) does not propagate Python's `contextvars` across the async boundary. Any OpenTelemetry spans started in a background task are orphaned from the parent trace unless the OTel context is manually forwarded.

**Pattern:**

```python
from opentelemetry import context as otel_context

# In the request handler — capture context before scheduling
current_ctx = otel_context.get_current()
background_tasks.add_task(my_background_fn, ..., parent_otel_context=current_ctx)

# In the background function — attach and detach in try/finally
async def my_background_fn(..., parent_otel_context=None):
    token = (
        otel_context.attach(parent_otel_context)
        if parent_otel_context is not None
        else None
    )
    try:
        with tracer.start_as_current_span("my_span"):
            ...  # spans are linked to the parent trace
    finally:
        if token is not None:
            otel_context.detach(token)
```

Both `attach()` and `detach()` execute inside the background task's own async `contextvars.Context`. Because the token is created and released in the same context, no `ValueError` is raised and no defensive suppression is needed. This invariant is load-bearing: any refactor that moves `otel_context.attach(...)` outside the background task (e.g., back into the sync request handler) will introduce the "Token was created in a different Context" class of error.

---

← [Back to References](README.md) | [Documentation](../README.md)
