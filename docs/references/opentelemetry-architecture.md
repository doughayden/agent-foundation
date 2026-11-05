# OpenTelemetry Architecture

Provider ownership, the ADK telemetry patch, exporter selection, the resource, and dependency decisions for `telemetry.py`.

## Provider Ownership

The application owns all three OpenTelemetry providers. `server.py` runs, at import time:

```python
env, telemetry_env = initialize_environment()   # ServerEnv, TelemetryEnv
configure_telemetry(...)          # tracer and logger providers (meter with a collector) set globally
app = get_fast_api_app(...)       # ADK attaches only its web UI processors
instrument_app(app)               # FastAPI spans and metrics
```

`configure_telemetry()` builds one resource and the providers that share it, then sets them globally: a `TracerProvider` with a `BatchSpanProcessor` and a `LoggerProvider` with a `BatchLogRecordProcessor` always, and a `MeterProvider` with a `PeriodicExportingMetricReader` (default 60 second interval) only when metrics have a destination (see Metrics below). The meter provider gets its own resource: the shared one without the `cloud_run_revision` attributes. It also attaches the OTel logging handler to the root logger through `LoggingInstrumentor` (trace context on every record) and instruments asyncpg.

It must run before `get_fast_api_app()`: the patched ADK setup raises `RuntimeError` when the providers are not set yet.

## The ADK Telemetry Patch

`get_fast_api_app()` calls ADK's private `google.adk.cli.api_server._setup_telemetry()`, passing the web UI's processors: `ApiServerSpanExporter` and `InMemoryExporter` for spans, and `WebUiLogExporter` for the GenAI event records that show message content in the trace view. Unpatched, that function:

- Builds its own providers with OTLP/HTTP exporters when any `OTEL_EXPORTER_OTLP_*` endpoint is set, and instruments the GenAI SDK. With the application's providers already set, its `set_*_provider` calls do nothing, and the web UI processors passed in the same call are dropped
- Never attaches log processors to a logger provider set elsewhere, on any path

`telemetry.py` replaces it at import with `_attach_web_ui_processors()`, which adds the web UI's span and log processors to the global providers and does nothing else. ADK then builds no providers, exporters or instrumentation of its own, whatever OTLP variables are set. With the web UI off, ADK passes no processors and the function returns.

The patch follows ADK's own direction: [google/adk-python#3548](https://github.com/google/adk-python/pull/3548) made the default path reuse an initialized tracer provider. It is removable once an ADK release attaches the processors to already-set providers on every path. `tests/unit/test_telemetry.py` asserts it is applied.

## Exporter Selection

`TelemetryEnv` (`config.py`) resolves one endpoint per signal; an empty variable counts as unset:

| Signal | Resolution order |
|---|---|
| Traces | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT`, then `TELEMETRY_API_ENDPOINT` |
| Logs | `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT`, then `TELEMETRY_API_ENDPOINT` |
| Metrics | `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT`, then `TELEMETRY_API_ENDPOINT` when the meter resource has `cloud.region`, else no export |

`configure_telemetry()` passes each resolved endpoint to its exporter explicitly. The OpenTelemetry SDK still reads the other `OTEL_EXPORTER_OTLP_*` variables itself: headers, certificates, compression and timeout. An exporter aimed at `TELEMETRY_API_ENDPOINT` (default `https://telemetry.googleapis.com:443`) gets TLS channel credentials carrying Application Default Credentials; any other endpoint gets none, so its TLS follows the URL scheme (`http://` is plaintext) and the SDK's certificate variables. `TelemetryEnv.print_config()` prints each signal's resolved destination at startup.

**Metrics:** `TelemetryEnv` resolves only the collector part; `metrics_endpoint()` in `telemetry.py` makes the full decision because the region check needs the built resource. The Telemetry API rejects metric points without a location, so metrics go there only when the meter resource has `cloud.region`. On Cloud Run the GCP resource detector and `CLOUD_RUN_REGION` both supply it, so metrics flow automatically. Locally, add `cloud.region=<region>` to `OTEL_RESOURCE_ATTRIBUTES` to send them to Google. With no destination, no meter provider is set, so ADK's and FastAPI's metric calls do nothing. Metrics land in Cloud Monitoring as `prometheus.googleapis.com/<name>/<kind>` on the `prometheus_target` resource, beside Cloud Run's native `run.googleapis.com` metrics, which the [alert policies](../observability.md#alerting) read.

ADC is only read when a signal goes to `TELEMETRY_API_ENDPOINT`, so a fully redirected setup needs no Google credentials for telemetry.

`OTEL_SDK_DISABLED=true` (`TelemetryEnv.otel_sdk_disabled`) turns export off: `configure_telemetry()` still sets the tracer and logger providers, which the SDK makes no-ops, so the web UI patch finds the providers it expects, but builds no exporters or processors, never reads Google credentials and sets no meter provider. Logging, asyncpg and FastAPI instrumentation stay installed and record against the no-op providers. `print_config()` reports telemetry as disabled.

Export is OTLP gRPC only. An OTLP/HTTP endpoint (port 4318) or `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` is not supported.

Only `server.py` (`uv run server` and the container entry point) runs this setup. `adk web`, `adk api_server` and `adk run` build their app through ADK's own telemetry setup.

Telemetry API permissions for the runtime service account: `roles/telemetry.tracesWriter` (traces), `roles/logging.logWriter` (logs) and `roles/monitoring.metricWriter` (metrics), all in `app_iam_roles` in `terraform/main/main.tf`.

## Resource

`build_resource()` merges, lowest precedence first:

1. The SDK defaults (`telemetry.sdk.*`)
2. The GCP resource detector (`opentelemetry-resourcedetector-gcp`): `cloud.*` and `faas.*` attributes on Cloud Run, nothing locally
3. The template's values from `ServerEnv` and `TelemetryEnv`: `service.name`, `service.namespace`, `service.version`, `service.instance.id`, `gcp.project_id`
4. The environment's `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`

On Cloud Run (`K_SERVICE` set), `configure_telemetry()` then merges the `cloud_run_revision` attributes `cloud_run_resource()` builds from `TelemetryEnv` (see Log Placement). The result is the one resource every provider uses.

## Log Placement

**Log names:** the Telemetry API names a log after a record's `event_name`, or `otlp` when it has none. Application logs land in `otlp` and GenAI events in `gen_ai.client.inference.operation.details`. Filter by service through the resource labels.

**Resource type:** the Telemetry API maps OTLP logs to `generic_task` unless the resource names a monitored resource. On Cloud Run, the shared resource carries `gcp.resource_type=cloud_run_revision` with `project_id`, `service_name` (`K_SERVICE`), `revision_name` (`K_REVISION`), `configuration_name` (`K_CONFIGURATION`) and `location` (`CLOUD_RUN_REGION`, which Terraform sets from `var.region`), so the logs appear in the service's Logs tab beside stdout. `TelemetryEnv` fails startup when `K_SERVICE` is set without `K_CONFIGURATION` and `CLOUD_RUN_REGION`. ADK uses the same mechanism to place Agent Engine logs. Traces carry the attributes too. The meter resource leaves them off, because the Telemetry API drops metric points that carry `gcp.resource_type`; it keeps `cloud.region` from the detector, `CLOUD_RUN_REGION` or `OTEL_RESOURCE_ATTRIBUTES`, in that rising order of precedence.

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
| `opentelemetry-instrumentation-fastapi` | HTTP server spans and metrics |
| `opentelemetry-instrumentation-asyncpg` | Spans for Cloud SQL session store queries |
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

## HTTP Layer Instrumentation (FastAPI)

`opentelemetry-instrumentation-fastapi` adds HTTP server spans and metrics, with the server span as the parent of ADK's `invoke_workflow` span. `server.py` calls `instrument_app(app)` right after `get_fast_api_app()` returns.

A typical enabled trace tree looks like:

```
POST /some-route                     (FastAPI server span)
├── POST /some-route http receive    (ASGI http.request event)
├── <your custom handler spans>
│   └── invoke_workflow              (ADK)
│       └── invoke_agent {agent}
│           └── generate_content {model}
├── POST /some-route http send       (ASGI http.response.start)
└── POST /some-route http send       (ASGI http.response.body)
```

**Why `instrument_app(app)` instead of the global `.instrument()`:**

`FastAPIInstrumentor` provides two APIs:

| API | Effect |
|---|---|
| `FastAPIInstrumentor().instrument()` | Patches `FastAPI.__init__` so any FastAPI app **constructed after this call** gets auto-instrumented |
| `FastAPIInstrumentor().instrument_app(app)` | Wraps middleware on the **existing** `app` instance |

ADK constructs the FastAPI app inside `get_fast_api_app()` from its own `from fastapi import FastAPI` binding, captured when ADK is imported. The global `.instrument()` form swaps only the `fastapi.FastAPI` module attribute, so it can't reach ADK's binding; `instrument_app(app)` wraps the returned instance instead.

**Two `http send` spans per request:**

The ASGI instrumentor (to which `FastAPIInstrumentor` delegates) creates one span per outbound ASGI message. HTTP responses always produce two messages: `http.response.start` (status + headers) and `http.response.body` (body frame). Each span is tagged with an `asgi.event.type` attribute carrying the message type verbatim, so the two spans are distinguishable in Cloud Trace by inspecting that attribute. This is normal ASGI behavior, not a duplication bug. Source: `opentelemetry/instrumentation/asgi/__init__.py` (the `send_span.set_attribute("asgi.event.type", message["type"])` path).

---

← [Back to References](README.md) | [Documentation](../README.md)
