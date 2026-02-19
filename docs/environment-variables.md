# Environment Variables

Complete configuration reference. Single source of truth.

See `.env.example` in the repository root for template configuration with inline comments.

## Quick Reference

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| **[GOOGLE_GENAI_USE_VERTEXAI](#google-cloud-vertex-ai)** | ✅ | - | Enable Vertex AI authentication |
| **[GOOGLE_CLOUD_PROJECT](#google-cloud-vertex-ai)** | ✅ | - | GCP project ID |
| **[GOOGLE_CLOUD_LOCATION](#google-cloud-vertex-ai)** | ✅ | - | GCP region |
| **[AGENT_NAME](#agent-identification)** | ✅ | - | Unique agent identifier |
| **[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT](#opentelemetry)** | ✅ | - | Capture LLM content in traces |
| **[AGENT_ENGINE](#cloud-resources)** | Recommended | in-memory | Session/memory persistence |
| **[ARTIFACT_SERVICE_URI](#cloud-resources)** | Recommended | in-memory | Artifact storage |
| [LOG_LEVEL](#logging) | Optional | `INFO` | Logging verbosity |
| [TELEMETRY_NAMESPACE](#logging) | Optional | `local` | Trace grouping |
| [SERVE_WEB_INTERFACE](#agent-features) | Optional | `FALSE` | Enable ADK web UI |
| [RELOAD_AGENTS](#agent-features) | Optional | `FALSE` | Hot-reload on file changes |
| [ROOT_AGENT_MODEL](#agent-features) | Optional | `gemini-2.5-flash` | Override default model |
| [ALLOW_ORIGINS](#cors) | Optional | `["http://localhost", "http://localhost:8000"]` | CORS allowed origins |
| [AGENT_DIR](#advanced) | Optional | Auto-detected | Override agent directory |
| [HOST](#advanced) | Optional | `127.0.0.1` | Server bind address |
| [PORT](#advanced) | Optional | `8000` | Server listening port |
| [ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS](#advanced) | Optional | `FALSE` | Suppress ADK warnings |

**Cloud Run auto-set:** [K_REVISION](#cloud-run-auto-set-read-only)

**CI/CD only:** [TF_VAR_*](#cicd-only) variables (GitHub Actions)

---

## Required

These must be set for the agent to function.

### Google Cloud Vertex AI

**GOOGLE_GENAI_USE_VERTEXAI**
- **Value:** `TRUE`
- **Purpose:** Enables Vertex AI authentication for Gemini models
- **Where:** Set locally in `.env`, auto-configured in Cloud Run

**GOOGLE_CLOUD_PROJECT**
- **Value:** Your GCP project ID (e.g., `your-project-id`)
- **Purpose:** Identifies the Google Cloud project for Vertex AI and other GCP services
- **Where:** Set locally in `.env`, configured via Terraform for Cloud Run

**GOOGLE_CLOUD_LOCATION**
- **Value:** GCP region (e.g., `us-central1`)
- **Purpose:** Sets the region for Vertex AI model calls and resource deployment
- **Where:** Set locally in `.env`, configured via Terraform for Cloud Run

### Agent Identification

**AGENT_NAME**
- **Value:** Unique identifier (e.g., `your-agent`)
- **Purpose:** Identifies cloud resources, logs, and traces
- **Where:** Set locally in `.env`, set before bootstrap (used for Terraform resource naming)
- **Note:** Used as base name for Terraform resources (`{agent_name}-{environment}`)

### OpenTelemetry

**OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT**
- **Options:**
  - `TRUE` - Capture full prompts and responses in traces
  - `FALSE` - Capture metadata only (no message content)
- **Purpose:** Controls LLM message content capture in OpenTelemetry traces
- **Where:** Set locally in `.env`, set before bootstrap
- **Reference:** [OpenTelemetry GenAI Instrumentation](https://opentelemetry.io/blog/2024/otel-generative-ai/#example-usage)
- **Security:** Set to `FALSE` if handling sensitive data

---

## Cloud Resources

Production-ready persistence for sessions, memory, and artifacts. Configure after first deployment.

**AGENT_ENGINE**
- **Value:** Agent Engine resource name (e.g., `projects/123/locations/us-central1/reasoningEngines/456`)
- **Purpose:** Session and memory persistence (production-consistent behavior)
- **Where:** Set locally in `.env` after first deployment, auto-configured in Cloud Run
- **How to get:** GitHub Actions job summary (`gh run view <run-id>`) or GCP Console (Vertex AI → Agent Builder → Agent Engines)
- **Note:** Defaults to in-memory if unset (not recommended for development)

**ARTIFACT_SERVICE_URI**
- **Value:** GCS bucket URI (e.g., `gs://your-artifact-bucket`)
- **Purpose:** Artifact storage persistence (production-consistent behavior)
- **Where:** Set locally in `.env` after first deployment, auto-configured in Cloud Run
- **How to get:** GitHub Actions job summary (`gh run view <run-id>`) or GCP Console (Cloud Storage → Buckets)
- **Note:** Defaults to in-memory if unset (not recommended for development)

---

## Runtime Configuration (Optional)

### Logging

**LOG_LEVEL**
- **Options:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Default:** `INFO`
- **Purpose:** Controls logging verbosity
- **Where:** Set locally via `.env` or command line, configure via GitHub Environment Variables for Cloud Run
- **Usage:**
  ```bash
  LOG_LEVEL=DEBUG uv run server
  ```

**TELEMETRY_NAMESPACE**
- **Default:** `local`
- **Purpose:** Groups traces and logs by developer or environment in Cloud Trace
- **Where:** Set locally via `.env`, auto-set to environment name in Cloud Run deployments (dev/stage/prod)
- **Usage:** Filter traces in Cloud Trace by namespace to isolate your development traces
- **Example:** `TELEMETRY_NAMESPACE=alice-local`

### Agent Features

**SERVE_WEB_INTERFACE**
- **Default:** `FALSE`
- **Purpose:** Enables ADK web UI at http://127.0.0.1:8000
- **Where:** Set locally via `.env`, configure via GitHub Environment Variables for Cloud Run
- **Options:**
  - `FALSE` - API-only mode
  - `TRUE` - Enable web interface

**RELOAD_AGENTS**
- **Default:** `FALSE`
- **Purpose:** Enable agent hot-reloading on file changes (development only)
- **Where:** Local development only
- **WARNING:** Set to `FALSE` in production (Cloud Run forces `FALSE`)

**ROOT_AGENT_MODEL**
- **Default:** `gemini-2.5-flash`
- **Options:** Any Gemini model (e.g., `gemini-2.5-pro`, `gemini-2.0-flash-exp`)
- **Purpose:** Override default root agent model
- **Where:** Set locally via `.env`, configure via GitHub Environment Variables for Cloud Run

### CORS

**ALLOW_ORIGINS**
- **Default:** `'["http://localhost", "http://localhost:8000"]'`
- **Format:** JSON array string
- **Purpose:** Configure CORS allowed origins
- **Where:** Hard-coded in Terraform for Cloud Run, configurable locally via `.env`
- **Example:** `ALLOW_ORIGINS='["https://your-domain.com", "http://127.0.0.1:3000"]'`

### Advanced

**AGENT_DIR**
- **Default:** Auto-detected (parent directory of `server.py`)
- **Purpose:** Override agent directory path for ADK
- **Where:** Set in Dockerfile (`/app/src`), rarely needed locally
- **Note:** Only override if you need non-standard directory structure

**HOST**
- **Default:** `127.0.0.1`
- **Purpose:** Server bind address
- **Where:** Rarely needs override - defaults work for most use cases
- **Note:** Docker Compose overrides to `0.0.0.0` in container for host access, Cloud Run manages internally

**PORT**
- **Default:** `8000`
- **Purpose:** Server listening port
- **Where:** Rarely needs override - Cloud Run always uses 8000, Docker Compose maps to host port 8000
- **Note:** Only override if you have port conflicts on your local machine

**ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS**
- **Default:** `FALSE`
- **Purpose:** Suppress ADK experimental feature warnings
- **Options:**
  - `FALSE` - Show warnings
  - `TRUE` - Suppress warnings

### Cloud Run Auto-Set (Read-Only)

These variables are automatically set by Cloud Run. Do not set manually.

**K_REVISION**
- **Purpose:** Cloud Run revision identifier
- **Where:** Auto-set by Cloud Run (used for `service.version` in traces)
- **Example:** `your-agent-dev-00042-abc`

---

## CI/CD Only

These variables are used exclusively in GitHub Actions workflows. Do not set locally.

### Terraform Inputs (TF_VAR_*)

GitHub Environment Variables are mapped to Terraform inputs via `TF_VAR_*` prefix:

**TF_VAR_project**
- **Source:** `${{ vars.GCP_PROJECT_ID }}` (GitHub Environment Variable)
- **Purpose:** GCP project ID for Terraform

**TF_VAR_location**
- **Source:** `${{ vars.GCP_LOCATION }}` (GitHub Environment Variable)
- **Purpose:** GCP region for Terraform

**TF_VAR_agent_name**
- **Source:** `${{ vars.IMAGE_NAME }}` (GitHub Environment Variable)
- **Purpose:** Agent name for resource naming

**TF_VAR_terraform_state_bucket**
- **Source:** `${{ vars.TERRAFORM_STATE_BUCKET }}` (GitHub Environment Variable)
- **Purpose:** GCS bucket for Terraform state

**TF_VAR_docker_image**
- **Source:** `${{ inputs.docker_image }}` (workflow input)
- **Purpose:** Immutable image digest for deployment

**TF_VAR_environment**
- **Source:** Set by workflow (dev/stage/prod)
- **Purpose:** Environment-specific resource naming

### Runtime Configuration Overrides

Override runtime config via GitHub Environment Variables (mapped to `TF_VAR_*`):

**TF_VAR_log_level**
- **Source:** `${{ vars.LOG_LEVEL }}` (optional GitHub Environment Variable)
- **Purpose:** Override LOG_LEVEL for Cloud Run deployment

**TF_VAR_root_agent_model**
- **Source:** `${{ vars.ROOT_AGENT_MODEL }}` (optional GitHub Environment Variable)
- **Purpose:** Override ROOT_AGENT_MODEL for Cloud Run deployment

**TF_VAR_serve_web_interface**
- **Source:** `${{ vars.SERVE_WEB_INTERFACE }}` (optional GitHub Environment Variable)
- **Purpose:** Override SERVE_WEB_INTERFACE for Cloud Run deployment

**TF_VAR_otel_instrumentation_genai_capture_message_content**
- **Source:** `${{ vars.OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT }}` (optional GitHub Environment Variable)
- **Purpose:** Override OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT for Cloud Run deployment

---

## Reference

### Where Variables Are Set

**Local Development:**
- `.env` file (loaded via `python-dotenv`)
- Command line (e.g., `LOG_LEVEL=DEBUG uv run server`)
- `docker-compose.yml` (Docker Compose)

**Cloud Run:**
- Terraform `main` module (`terraform/main/main.tf`)
- GitHub Environment Variables → `TF_VAR_*` → Terraform → Cloud Run environment

**CI/CD:**
- GitHub Environment Variables (auto-created by bootstrap)
- Workflow inputs and outputs

### Security

- **Never commit `.env` files** to version control - Already gitignored
- **Workload Identity Federation** - No service account keys needed for CI/CD
- **Sensitive data** - Set `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=FALSE` when handling sensitive information

---

← [Back to Documentation](README.md)