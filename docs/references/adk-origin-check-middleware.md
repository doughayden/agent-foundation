# ADK Origin Check Middleware

How ADK's `_OriginCheckMiddleware` validates request origins and how to configure `ALLOW_ORIGINS`.

## What It Is

ADK 1.27.3 introduced `_OriginCheckMiddleware` ([google/adk-python#4947](https://github.com/google/adk-python/issues/4947)), an ASGI middleware that blocks cross-origin state-changing requests. It rejects `POST`, `PUT`, and `DELETE` requests unless the `Origin` header matches one of the configured allowed origins or the request's own host.

Safe methods (`GET`, `HEAD`, `OPTIONS`) always pass through regardless of origin.

## How It Works

1. The middleware inspects the `Origin` header on every incoming request
2. For safe methods (`GET`, `HEAD`, `OPTIONS`), the request proceeds unconditionally
3. For state-changing methods (`POST`, `PUT`, `DELETE`):
   - If no `Origin` header is present, the request proceeds (same-origin requests from non-browser clients)
   - If the `Origin` header matches one of the configured allowed origins (exact string match), the request proceeds
   - If the `Origin` header matches the request's own `Host` header, the request proceeds (same-origin)
   - Otherwise, the middleware returns `403 Forbidden` with body `"Forbidden: origin not allowed"`

## Exact String Matching

The middleware compares origins as exact strings. This means:

- `http://localhost` does **not** match `http://localhost:8000`
- `http://127.0.0.1` does **not** match `http://127.0.0.1:8000`
- `http://localhost:8000` does **not** match `http://127.0.0.1:8000`

Ports must always be included when the origin has a non-default port (anything other than 80 for HTTP or 443 for HTTPS).

## Why Both localhost and 127.0.0.1

Browsers may resolve `localhost` to either `127.0.0.1` (IPv4) or `::1` (IPv6), and the `Origin` header reflects what the browser actually resolved. When accessing the agent via `http://localhost:8000`, some browsers send `Origin: http://localhost:8000` while others may send `Origin: http://127.0.0.1:8000`. Configure both to cover all cases.

The default `ALLOW_ORIGINS` value includes both:

```json
["http://127.0.0.1:8000", "http://localhost:8000"]
```

## Interaction with CORSMiddleware

ADK adds both `_OriginCheckMiddleware` and Starlette's `CORSMiddleware` to the ASGI stack. They serve different purposes:

- **CORSMiddleware** handles preflight (`OPTIONS`) requests and adds CORS response headers (`Access-Control-Allow-Origin`, etc.)
- **_OriginCheckMiddleware** validates the `Origin` header on actual (`POST`, `PUT`, `DELETE`) requests

Both use the same `ALLOW_ORIGINS` list. A request must satisfy both middlewares to succeed.

## Configuration

Set `ALLOW_ORIGINS` as a JSON array string:

```bash
# Default (local development)
ALLOW_ORIGINS='["http://127.0.0.1:8000", "http://localhost:8000"]'

# Custom frontend on different port
ALLOW_ORIGINS='["http://localhost:3000", "http://127.0.0.1:3000"]'

# Production with deployed frontend
ALLOW_ORIGINS='["https://your-frontend.example.com"]'
```

For Cloud Run deployments, `ALLOW_ORIGINS` is hard-coded in Terraform (`terraform/main/main.tf`). Update the Terraform configuration to add client service origins when a separate UI is deployed.

## Diagnosing Failures

**Symptom:** `403 Forbidden` response with body `"Forbidden: origin not allowed"` and very fast response time (~1ms).

The fast response time is the key indicator -- the middleware rejects the request before it reaches the application. Normal application errors take longer because they go through model inference or database operations.

**Steps to diagnose:**

1. Check the request's `Origin` header in browser DevTools (Network tab, click the request, check Request Headers)
2. Compare it exactly against the configured `ALLOW_ORIGINS` values
3. Verify the port is included and matches exactly
4. For `gcloud run services proxy`, the browser sends `Origin: http://localhost:8000` -- ensure this exact string is in the allowed origins list

---

← [Back to References](README.md) | [Documentation](../README.md)
