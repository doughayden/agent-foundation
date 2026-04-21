# Cloud Run Concurrency Tuning for Async Python Agents

How to reason about `max_instance_request_concurrency`, instance sizing, and scaling for an ADK-based agent deployed as a single async uvicorn process on Cloud Run.

This guide is generic — the runtime model, limits, and rationale apply to any self-hosted Python async agent on Cloud Run, not just this template.

## Runtime Model

The server entrypoint runs `uvicorn.run(app, ...)` with no `workers=` argument. That yields:

- **One process** per container instance
- **One asyncio event loop** inside that process
- **No threads** doing request work (FastAPI handlers are `async def`)

Every `await` in a handler yields control back to the event loop, letting other in-flight requests progress during I/O waits (LLM streams, DB queries, outbound HTTP). The loop is the sole request multiplexer — there is no thread pool or worker pool behind it.

## What `max_instance_request_concurrency` Actually Bounds

`max_instance_request_concurrency` on `google_cloud_run_v2_service.template` is the number of HTTP requests Cloud Run will route to a single instance *before spinning up a new instance*. It is not:

- A thread count (no threads)
- A worker count (no workers)
- An OS-level concurrency primitive

All it does is tell the Cloud Run load balancer when to fan out. That single async process absorbs every request routed to it.

Once Cloud Run reaches `max_instance_count` instances *and* each is at `max_instance_request_concurrency`, additional requests queue. Queue depth shows up as latency.

Reference: [Cloud Run — About container concurrency](https://docs.cloud.google.com/run/docs/about-concurrency).

## Effective Concurrency Limits

The event loop itself can juggle large numbers of concurrent awaits cheaply — [Piccolo's coroutine-scaling experiments](https://piccolo-orm.com/blog/what-is-the-maximum-number-of-coroutines-you-should-run-concurrently/) report asyncio comfortably running tens of thousands of coroutines, with external bottlenecks (rate limits, DB connection caps, network timeouts) binding long before the loop itself. What actually bounds safe per-instance concurrency:

### 1. Memory per in-flight request

Each concurrent request pins a stack of objects in memory for its duration. Order-of-magnitude contributions for a typical ADK agent:

| Contributor | Typical size | Notes |
|---|---|---|
| Loaded session events | 100 KB – 5 MB | 20–100 events; bloats when past tool outputs (API responses, retrieved documents) are embedded in event content |
| LLM response buffers | 5–50 KB | Streamed LLM response accumulates as it arrives; 500–10K tokens ≈ 2–40 KB text plus chunk overhead |
| Tool output payloads | 10 KB – 10 MB | Highly variable; an API tool returning 1K records at ~500 B each ≈ 500 KB; JSON parse+validate transiently doubles |
| Pydantic model graph | 1–5 MB | `Event` / `Content` / `Part` instances × hundreds per request; Python object overhead dominates |
| OpenTelemetry spans | 50 KB – 1 MB | ~1 KB per span; 50–200 spans per complex request before export flushes |
| Background task state | 1–5 MB | BG task builds its own event stream + clients while running (see §2) |
| HTTP client buffers | ~100 KB | httpx pools, active TLS sessions per outbound call |

Summed ranges:

- **Light** (greeting, no tool calls): **2–5 MB**
- **Medium** (1–2 tool calls with small results): **5–15 MB**
- **Heavy** (bulk tool outputs, long sessions, many LLM turns): **20–50+ MB**

> [!NOTE]
> These are component estimates, not measurements. Before tuning based on them, measure actual resident set size (RSS) growth per in-flight request under realistic load — e.g., compare steady-state memory at low vs target concurrency, or expose a `/debug/memory` endpoint that reports `resource.getrusage(RUSAGE_SELF).ru_maxrss`. RSS is the process's non-swapped physical memory footprint, which is what Cloud Run compares against the `memory` limit.

`memory / per_request_budget` is the hard ceiling. Exceed it and the instance OOMs.

### 2. BackgroundTasks inflation

If your agent spawns FastAPI `BackgroundTasks` or other post-response async work (streaming event delivery, webhook fan-out, cleanup), those keep running after the HTTP response returns. Cloud Run's `max_instance_request_concurrency` counts HTTP requests in-flight, not BG tasks — so it may route a new request while the previous one's BG task is still executing, holding memory. Agents with no post-response work have `D_bg = 0` and the multiplier below reduces to 1×; the rest of this section applies when `D_bg > 0`.

Applying [Little's law](https://en.wikipedia.org/wiki/Little%27s_law) at steady state, with HTTP arrivals at rate R, HTTP handler duration `D_http`, and BG task duration `D_bg`:

```
in_flight_http  ≈ R × D_http        (capped by max_instance_request_concurrency)
in_flight_bg    ≈ R × D_bg
total_in_flight ≈ in_flight_http × (1 + D_bg/D_http)
```

The inflation multiplier is `1 + D_bg/D_http` and is workload-dependent:

- **Single-turn** (handler returns after the only response event): `D_bg ≈ 0`, multiplier ~1×
- **Multi-turn with streamed follow-up** (handler returns after first event; BG streams remaining LLM turns + tool calls): `D_bg` commonly equals or exceeds `D_http`, multiplier 2×–4×
- **Tool-heavy agent flows** (many post-response LLM turns, bulk tool responses): multiplier can reach 5× or more

Measure `D_bg` and `D_http` from your own traces rather than assuming a multiplier. Size memory budget for `max_instance_request_concurrency × (1 + D_bg/D_http) × per_request_MB`, not the HTTP cap alone.

### 3. SQLAlchemy connection pool

SQLAlchemy's async engine defaults to 5 connections + 10 overflow = 15 max per engine. Each engine has its own pool, so a deployment with multiple stores (e.g., session state plus any secondary store — OAuth contexts, job queues, audit logs) multiplies the per-instance connection count. Concurrency higher than pool size causes requests to wait for a connection to free.

Tune pool size with `create_async_engine(uri, pool_size=N, max_overflow=M)` if concurrency justifies it.

### 4. Cloud SQL (or other DB) connection cap

The database tier sets a hard max-connection limit. Per-instance connection count has two regimes:

- **Steady state** (`sum(pool_size) × instances`) — connections held open under typical concurrency. Fast operations (1–10 ms reads/writes) return to the pool quickly, so actual in-use count stays close to `pool_size × engines` most of the time.
- **Peak with overflow** (`sum(pool_size + max_overflow) × instances`) — theoretical ceiling during bursts, slow queries, or pool warmup on new instances. Overflow connections open on demand when the base pool is saturated.

Aggregate: `max_instances × connections_per_instance ≤ db_max_connections`, minus Postgres reservations (~3 for superuser/replication). On small tiers the formula can bind before memory or CPU — raising `max_instance_count` without matching DB headroom leads to intermittent connection failures under load (pool timeouts or driver-level rejections from the DB).

## The GIL, Processes, and Parallelism

Python's Global Interpreter Lock (GIL) lets only one thread execute Python bytecode at a time within a single process. Async coroutines on one event loop face the same limit — they parallelize only during I/O waits that release the GIL (socket reads, DB drivers with C extensions). Pure Python work (JSON parsing, pydantic validation, event shaping, prompt construction, card rendering) serializes on the one thread holding the GIL.

Two ways to get real Python parallelism:

1. **Multiple processes** (gunicorn/uvicorn workers, Agent Engine's managed runtime). Each process owns its own GIL. Cost: every process duplicates the app's in-memory state — runner, connection pools, observability exporters, plugin registries, loaded models.
2. **C extensions that release the GIL** during compute (numpy, some DB drivers). Free when applicable.

**The relevant question isn't "how many vCPUs do I have?" — it's "how much of each request is Python compute?"** For an I/O-dominant agent (time spent awaiting LLM / REST / DB), a single async process handles concurrency well regardless of vCPU count — the event loop multiplexes I/O waits and there's little Python compute to parallelize. Multi-process Python earns its keep only when both (a) you have multiple vCPUs *and* (b) per-request Python compute is significant enough that parallelizing it materially improves throughput.

vCPU count is a cost/complexity dial, not a fixed baseline: smaller is cheaper and forces the single-process model; larger opens the door to multi-process if the compute mix justifies it. Start with the smallest size that fits your per-request memory footprint and scale up only when profiling shows Python compute is the bottleneck.

## Why Agent Engine Uses 9 Processes and This Doesn't

Vertex AI Agent Engine's [optimize-runtime documentation](https://docs.cloud.google.com/agent-builder/agent-engine/optimize-runtime) recommends `container_concurrency` as a multiple of 9 because their managed runtime bakes **9 agent processes per container**. Each process handles `container_concurrency / 9` in-flight requests. This is a gunicorn-worker model wrapping your agent inside their container.

### vCPU is a rate limit, not a thread cap

A Cloud Run `cpu = "N"` limit means "the container gets N vCPU-seconds per wall-clock second across all its threads and processes" — enforced by cgroups CPU quota. You can run more processes than vCPUs; they just time-share the budget. For an I/O-dominant workload, time-sharing is fine — most processes are parked on I/O waits at any instant, so oversubscription costs little.

Agent Engine's 9 processes fit their container for the same reason a single async process fits many concurrent requests on one event loop: concurrency exceeds parallelism because work is I/O-bound.

### The real constraints on adding processes

Two reasons not to run multiple processes, applicable at any vCPU size:

1. **Memory duplication.** Each Python process duplicates the full resident state — ADK runner, plugin registries, loaded module graph, SQLAlchemy pools, observability exporters, in-memory caches. Ballpark for a non-trivial agent: 150–300 MB per process. N processes costs roughly `N × 250 MB` in resident memory before per-request data lands. Agent Engine's containers must be sized to absorb 9× state; cost-tuned Cloud Run services usually aren't.

2. **Parallelism gain depends on Python compute being significant.** Multi-process Python's headline benefit is GIL parallelism — N processes use N cores simultaneously for Python bytecode. That's only useful when (a) you provision ≥ N vCPUs *and* (b) per-request Python compute is a meaningful slice of wall-clock time. For I/O-dominant workloads, (b) rarely holds: the Python compute slice is thin, so parallelizing it yields modest throughput gains against a 2×–9× memory cost.

At small vCPU counts there's also no parallelism to extract — only one instruction stream runs at a time regardless of process count. Multi-process there buys only *isolation* (one crashed process doesn't kill the others), which a single-purpose agent rarely values enough to pay for.

### Choosing vCPU and process count together

vCPU size and process count are a paired decision driven by the Python-compute share of each request:

- **I/O-dominant** (e.g., ~95% awaiting LLM / REST / DB): one async process, smallest vCPU that fits per-request memory. Scaling goes horizontal via `max_instance_count`, not vertical.
- **Mixed compute + I/O**: one async process per vCPU, sized to the compute share. Memory must absorb `N × app_state`. Consider DB tier implications — N× connection pools can exhaust a small DB.
- **Python-compute dominant** (large prompt assembly, bulk validation, local inference, data transformation): multiple processes across multiple vCPUs is how you extract throughput. Memory + DB headroom are prerequisites.

For I/O-dominant workloads specifically, the effective levers for latency and throughput are elsewhere: bigger DB tier, horizontal scaling via `max_instance_count`, keeping connection pools warm (see `cpu_idle` section), reducing LLM turns per user query. Provisioning more vCPU without a matching Python-compute bottleneck is mostly idle cores.

If you migrate the agent to host inside Agent Engine, re-tune to their 9× model (e.g., `36`, `72`). That's their container architecture, not a universal rule.

## Starting-Point Profile

For an I/O-dominant async Python agent with modest traffic, as a cost-tuned starting point:

| Setting | Value | Rationale |
|---|---|---|
| [`min_instance_count`](https://docs.cloud.google.com/run/docs/configuring/min-instances) | `1` | Avoids cold start on first request of the day |
| [`max_instance_count`](https://docs.cloud.google.com/run/docs/configuring/max-instances-limits) | `10` | Bounds runaway cost for a single-tenant workload; plenty of headroom (project quota typically 1000) |
| [`max_instance_request_concurrency`](https://docs.cloud.google.com/run/docs/about-concurrency) | `10` | Sized so `10 × (1 + D_bg/D_http) × per_request_MB` fits `memory` — see Effective Concurrency Limits for the math |
| `cpu` | `"1"` | Cheap tier; matches a single async process naturally. Raise only if profiling shows Python compute bottleneck |
| `memory` | `"2Gi"` | Starting budget; revisit with measured per-request MB and BG inflation multiplier |
| [`cpu_idle`](https://docs.cloud.google.com/run/docs/configuring/cpu-allocation) | `true` | Request-based billing; idle instances cheap while keeping `min=1` warm |

> [!NOTE]
> These are starting points for a specific profile (I/O-dominant, cost-tuned, modest traffic). vCPU and memory are genuine tuning dials, not fixed assumptions — measure per-request memory and Python-compute share under realistic load, then adjust.

## Example: Validating the Starting Point

Applying the formulas from Effective Concurrency Limits against the Starting-Point Profile, for a Medium workload typical of a multi-tool agent (1–2 upstream API calls per user turn, streamed follow-up via background tasks):

**Inputs:**

- Per-request memory: Medium band midpoint ≈ **10 MB** (conversation's in-memory footprint during its active lifetime)
- BG inflation: handler returns after the first response event; BG task streams follow-up events. `D_bg ≈ D_http` for light multi-turn → multiplier ≈ **2×**
- Baseline resident memory: ≈ **300–500 MB** (ADK runner, plugins, SQLAlchemy engines, OTel exporters, Python interpreter — estimate, unmeasured)

**Per-instance memory fit:**

```
in_flight_memory ≈ 10 × 2 × 10 MB = 200 MB
total_rss        ≈ 400 MB baseline + 200 MB in-flight ≈ 600 MB of 2048 MB
```

Comfortable headroom. The model treats HTTP- and BG-phase in-flight items as separate 10 MB slots, which is slightly conservative — a conversation's HTTP and BG phases share the same loaded session + event list, so real memory is somewhat less.

**Heavy-tail check:** per-request 40 MB × inflation 5× × concurrency 10 = 2000 MB for in-flight alone, approaching the 2 Gi ceiling. If traffic skews heavy, raise `memory` before `max_instance_request_concurrency`.

**Event loop:** 10 HTTP + ~20 BG = 30 concurrent async tasks on one event loop. Three orders of magnitude below the coroutine counts asyncio handles routinely (see Effective Concurrency Limits intro) — no contention risk at this scale.

**Horizontal-scale constraint — DB connections:**

Two SQLAlchemy engines per instance (session service + OAuth store), each defaulting to `pool_size=5, max_overflow=10`. Two regimes:

- **Steady state** — fast ops cycle connections back to the pool quickly, so actual in-use count per instance stays near `pool_size × engines ≈ 10` under typical concurrency. At `max_instance_count = 10` that aggregates to ~100 connections against a `db-custom-1-3840` tier with ~97 effective connections (after Postgres reservations for superuser/replication).
- **Peak with overflow** — bursts, slow queries, or new-instance pool warmup can push per-instance count to `(pool_size + max_overflow) × engines ≈ 30`, reaching ~300 aggregate. At that point Cloud SQL rejects new connection attempts; failures surface to the app as SQLAlchemy connection errors (pool timeout when the local pool can't serve a request within `pool_timeout`, or a wrapped driver exception — e.g., `asyncpg.exceptions.TooManyConnectionsError` — when the DB itself refuses a new connection).

Operational reality: at `max_instance_count = 10` we sit *at* the tier budget at steady peak (no wiggle room) and *blow past it* during any burst. Before pushing `max_instance_count` further, **bump the DB tier** — `db-custom-2-7680` supports ~200 connections, doubling burst headroom. See [Cloud SQL Scaling](cloud-sql.md). Reducing `max_overflow` per engine is an alternative that trades burst-connection rejection for burst latency (requests wait longer for pooled connections).

**Conclusion:** the starting point holds for the Medium workload on a single instance — memory sits near 30% utilization and the event loop has ample headroom. Under horizontal scale, DB connections bind first, not memory or CPU. Measure per-request RSS and `D_bg` / `D_http` in production to confirm these estimates match reality before relying on them.

## `cpu_idle` and First-Request Latency After Idle

`min_instance_count = 1` eliminates cold start (container boot, app import, lifespan init) but does not guarantee the first request after an idle period will be fast. Two separate latency regimes exist:

- **Cold start:** no instance exists. Container + app boot is the penalty.
- **Warm-idle-to-active:** instance exists but hasn't served a request in a while. A different set of penalties apply.

### What `cpu_idle = true` does

With `cpu_idle = true` (request-based billing), the instance's CPU is throttled to <5% while no requests are in-flight, and unthrottled when a request arrives. Billing accrues only during request processing.

With `cpu_idle = false` (instance-based billing), CPU is always fully allocated while the instance exists. Billing is continuous.

References: [Cloud Run — CPU allocation](https://docs.cloud.google.com/run/docs/configuring/cpu-allocation), [Billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings).

### What's slow on first-after-idle

1. **CPU unthrottle ramp** — small (~100 ms), real but usually not dominant
2. **Stale connection pools** — the bigger penalty:
   - Cloud SQL Auth Proxy ↔ Cloud SQL backend keepalive expires → first query re-handshakes TLS + auth
   - httpx async clients to upstream APIs (LLM provider, external REST services) drop idle connections → new TLS handshake on first call
   - SQLAlchemy pool recycles stale connections via `pool_pre_ping` or `pool_recycle`
3. **ADC / IAM token refresh** — identity tokens refresh on a cadence; first request after idle may trigger one
4. **Python GC and OS page cache** — long idle periods invite full GC cycles and page eviction; next request pays for reload
5. **In-process caches** — any session-service or in-memory caches may have been GC'd

Under throttled CPU, housekeeping that would overlap an idle period (keepalives, background tasks) runs slowly or not at all, so pools stay stale longer and re-establishment costs are paid in the request path.

### Options

| Option | Effect | Cost |
|---|---|---|
| `cpu_idle = false` | CPU always allocated; background housekeeping keeps pools and caches warm; first-after-idle request fast | ~2× instance cost (billed during idle too) |
| Cloud Scheduler → `/health` every ~60s | Instance never sits idle long enough for pools to die; CPU briefly unthrottles each ping | Trivial (one scheduler job + ~1 request/min) |
| Application-level keepalive task | Periodic async task pings DB/APIs to keep pools warm | Complexity; fights Cloud Run's stateless model |
| Accept it | Simplest | Slow first-after-idle request |

### Decision heuristics

- **Dev or low-traffic** — `cpu_idle = true` is fine. First-after-idle slowness shows up but rarely matters.
- **Low-traffic with latency SLOs** — Cloud Scheduler pinger is the best ROI: keeps pools warm without flipping the billing model.
- **Steady prod traffic** — `cpu_idle = true` is fine; natural traffic keeps the instance active.
- **Prod with unpredictable traffic + latency SLO** — `cpu_idle = false` is the clean answer; you're paying for `min=1` anyway, might as well keep it hot.

The template defaults to `cpu_idle = true` because cost predictability matters more than sub-second first-request latency for most early-stage deployments. Revisit when an SLO makes the tradeoff concrete.

Reference: [Cloud Run — General development tips](https://docs.cloud.google.com/run/docs/tips/general) (cold start and latency mitigation).

## When to Scale Up vs Out vs Add Workers

**Scale out (raise `max_instance_count`)** when:
- Queue depth / tail latency grows under load
- Memory per instance stays healthy
- Cost per request is acceptable

**Scale up memory (raise `memory`)** when:
- Instances OOM before hitting concurrency cap
- You want to raise per-instance concurrency without OOM risk
- Pool sizes or cached state grow

**Scale up CPU (raise `cpu`)** when:
- Profiling shows CPU-bound time inside request handlers (not I/O waits)
- Event loop tasks are observably starved
- You plan to add uvicorn workers (below)

**Add uvicorn workers** (only after raising CPU) when:
- `cpu ≥ 2` and CPU profile shows GIL contention
- Per-request Python compute is significant (heavy serialization, parsing, validation)
- Memory can absorb `N × app_state` duplication

**Raise `max_instance_request_concurrency`** when:
- Instances are consistently underutilized (low CPU, low memory)
- No queue depth, no tail latency issues
- BackgroundTasks are light or absent

## Observability Checklist

Before tuning any of the above, confirm you can see:

- Per-instance memory usage (Cloud Run container metrics)
- Per-instance request count and queue depth
- Event loop lag (custom metric if not provided by your observability stack)
- DB connection pool saturation (SQLAlchemy pool status or DB-side connection count)
- Request tail latency (p95, p99)

Tune based on signal, not vibes.

---

← [Back to References](README.md) | [Documentation](../README.md)
