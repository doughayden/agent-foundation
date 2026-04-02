# OpenTelemetry Architecture

ADK coexistence strategy, instrumentation decisions, and dependency management for the custom observability module.

## ADK Coexistence Strategy

The custom OpenTelemetry setup in `utils/observability.py` must coexist with ADK's internal telemetry infrastructure. ADK creates its own `TracerProvider` (with in-memory exporters for the web UI) during `get_fast_api_app()`. The project augments this provider rather than replacing it.

### Two-Phase Initialization

The initialization is split across two functions called at specific points in `server.py`:

**Phase 1 — `configure_otel_resource()` (before ADK starts):**

```python
# server.py — module-level (runs at import time)
configure_otel_resource(agent_name=env.agent_name, project_id=env.google_cloud_project)
app = get_fast_api_app(...)  # ADK creates TracerProvider, reads OTEL_RESOURCE_ATTRIBUTES
```

This function builds and sets the `OTEL_RESOURCE_ATTRIBUTES` environment variable with service identity attributes (`service.name`, `service.namespace`, `service.version`, `service.instance.id`, `gcp.project_id`). It must run *before* `get_fast_api_app()` because ADK's `TracerProvider` constructor reads `OTEL_RESOURCE_ATTRIBUTES` to build its `Resource` object. Setting attributes after construction has no effect.

**Phase 2 — `setup_opentelemetry()` (after ADK starts):**

```python
# server.py — main() function (runs at server start)
setup_opentelemetry(project_id=..., agent_name=..., log_level=...)
```

This function adds Cloud Trace and Cloud Logging exporters. For tracing, it detects ADK's existing `TracerProvider` via an `isinstance` check and adds a `BatchSpanProcessor` with an `OTLPSpanExporter` to it — preserving ADK's in-memory spans for the web UI while adding Google Cloud export. If no `TracerProvider` exists (theoretical deployment-only case), it creates one.

### Why Environment Variables Instead of Programmatic Resource Objects

OpenTelemetry's Python SDK allows creating `Resource` objects programmatically and passing them to `TracerProvider()`. However, this project uses the `OTEL_RESOURCE_ATTRIBUTES` environment variable instead because:

- ADK creates its own `TracerProvider` internally — the project has no control over that constructor call
- `OTEL_RESOURCE_ATTRIBUTES` is the standard mechanism for influencing any provider's resource configuration before it is constructed
- Both ADK's provider and any provider the project creates pick up the same attributes automatically

### ADK Auto-Instrumentation

ADK's `_setup_instrumentation_lib_if_installed()` (in `adk_web_server.py`) auto-detects `opentelemetry-instrumentation-google-genai` at startup. When the package is importable, ADK calls `GoogleGenAiSdkInstrumentor().instrument()` to monkey-patch `google.genai.Models.generate_content` and related methods.

The explicit `GoogleGenAiSdkInstrumentor().instrument()` call in `observability.py` is therefore redundant. It is kept as a defensive measure — if the project ever stops using `get_fast_api_app()`, the instrumentor would still be applied. The call is idempotent: OTel's `BaseInstrumentor` tracks instrumentation state and skips re-instrumentation.

### ADK Span Hierarchy

ADK produces its own span hierarchy using the `gcp.vertex.agent` tracer:

| Span Name | Purpose |
|---|---|
| `invocation` | Top-level span for a runner invocation |
| `invoke_agent {name}` | Agent-level span with agent name, session ID |
| `call_llm` | Wraps the LLM call |
| `generate_content {model}` | Model inference (delegated to genai instrumentor when installed) |
| `execute_tool {name}` | Individual tool execution |

When `opentelemetry-instrumentation-google-genai` is installed, ADK delegates `generate_content` span creation to the instrumentor and attaches extra attributes (agent name, conversation ID, user ID) via a context key mechanism. Without the instrumentor, ADK creates the span itself.

## Instrumentation Strategy

### Why `google-genai` Over `vertexai` Instrumentation

Two OpenTelemetry instrumentor packages exist for Google's generative AI SDKs:

| Package | Instruments | Status |
|---|---|---|
| `opentelemetry-instrumentation-google-genai` | `google.genai` SDK (`google.genai.Client`) | Active, recommended |
| `opentelemetry-instrumentation-vertexai` | Legacy `vertexai.generative_models` SDK | Active, but instruments a deprecated SDK |

ADK uses the `google-genai` SDK internally (via the `Gemini` model wrapper). The legacy `vertexai.generative_models` API is deprecated (June 2025) with removal planned for June 2026. `opentelemetry-instrumentation-vertexai` provides no value for ADK-based projects.

### Direct Dependency vs. ADK Extra

ADK's `[otel-gcp]` extra includes `opentelemetry-instrumentation-google-genai>=0.6b0`. This project installs it as a direct dependency instead, for explicit version control in `pyproject.toml` and `uv.lock`. Both approaches produce the same runtime behavior.

### What ADK Instruments Automatically

ADK's built-in tracing covers the agent orchestration layer:

- `invocation` → `call_llm` → `generate_content` / `execute_tool` spans
- Agent name, session ID, model, token usage, tool args/responses as span attributes
- Gen AI semantic convention attributes (`gen_ai.operation.name`, `gen_ai.request.model`, etc.)

ADK does **not** instrument HTTP routes. There are no `GET /health`, `POST /run`, or similar spans.

### FastAPI Instrumentation (Not Included)

`opentelemetry-instrumentation-fastapi` would add complementary HTTP-layer spans (not duplicates) as parent spans to ADK's `invocation` spans. This provides visibility into FastAPI routing, middleware, and response serialization latency. It is not included in the template but is useful for projects with custom routes.

To add it:

```python
# In server.py, after get_fast_api_app() returns
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
```

## Dependency Management

### Direct Dependencies

| Package | Purpose |
|---|---|
| `opentelemetry-exporter-otlp-proto-grpc` | OTLP trace export to Cloud Trace. No cross-constraint with genai instrumentation (they share only `opentelemetry-api`) |
| `opentelemetry-exporter-gcp-logging` | Cloud Logging export via `CloudLoggingExporter` |
| `opentelemetry-instrumentation-logging` | Bridges Python `logging` module to OTel (injects trace context into `LogRecord` attributes) |
| `opentelemetry-instrumentation-google-genai` | Genai SDK instrumentation. ADK's `[otel-gcp]` extra includes this, but the project maintains explicit version control |

### Transitive Dependencies (via ADK)

ADK pulls in a set of OpenTelemetry packages through its core and optional dependencies:

- `opentelemetry-api`, `opentelemetry-sdk` — Core API and SDK
- `opentelemetry-semantic-conventions` — Standard attribute names
- `opentelemetry-proto` — Protocol buffer definitions
- `opentelemetry-exporter-gcp-monitoring` — Cloud Monitoring export
- `opentelemetry-exporter-gcp-trace` — Cloud Trace export (GCP-native, not OTLP)
- `opentelemetry-resourcedetector-gcp` — Auto-detect GCP resource attributes

The project uses OTLP export (`opentelemetry-exporter-otlp-proto-grpc`) rather than GCP-native export (`opentelemetry-exporter-gcp-trace`) because OTLP is the vendor-neutral standard and supports the Cloud Trace v2 API endpoint directly.

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
            with contextlib.suppress(ValueError):
                otel_context.detach(token)
```

**Why suppress `ValueError` on detach:**

Python's [`ContextVar.reset()`](https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar.reset) raises `ValueError` when the token was created in a different `contextvars.Context`. Starlette runs background tasks in a separate context copy, so the OTel token from `attach()` cannot be cleanly detached. This is a [known issue](https://github.com/open-telemetry/opentelemetry-python/issues/2606) in the OpenTelemetry Python SDK. The suppress is safe because:

- The `attach()` succeeded — spans are correctly linked to the parent trace
- The background task is about to exit — no leaked context to clean up
- OTel's own `detach()` implementation also catches all exceptions internally

---

← [Back to References](README.md) | [Documentation](../README.md)
