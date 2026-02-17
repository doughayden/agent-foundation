# Environment Variables

Complete configuration reference. Single source of truth.

## Required

These must be set for the agent to function.

### Google Cloud Vertex AI

**GOOGLE_GENAI_USE_VERTEXAI**
- **Value:** `TRUE`
- **Purpose:** Enables Vertex AI authentication for Gemini models
- **Where:** Set locally in `.env`, auto-configured in Cloud Run

**GOOGLE_CLOUD_PROJECT**
- **Value:** Your GCP project ID (e.g., `my-project-123`)
- **Purpose:** Identifies the Google Cloud project for Vertex AI and other GCP services
- **Where:** Set locally in `.env`, configured via Terraform for Cloud Run

**GOOGLE_CLOUD_LOCATION**
- **Value:** GCP region (e.g., `us-central1`)
- **Purpose:** Sets the region for Vertex AI model calls and resource deployment
- **Where:** Set locally in `.env`, configured via Terraform for Cloud Run

### Agent Identification

**AGENT_NAME**
- **Value:** Unique identifier (e.g., `my-agent`)
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

## Optional - Cloud Resources

Add these for production-consistent testing with durable persistence. Defaults to in-memory services if unset.

**AGENT_ENGINE**
- **Value:** Agent Engine resource name (e.g., `projects/123/locations/us-central1/reasoningEngines/456`)
- **Default:** Unset (in-memory ephemeral sessions)
- **Purpose:** Enables session persistence across server restarts
- **Where:** Set locally in `.env` after first deployment
- **How to get:** GitHub Actions job summary (`gh run view <run-id>`) or GCP Console (Vertex AI → Agent Builder → Reasoning Engines)

**ARTIFACT_SERVICE_URI**
- **Value:** GCS bucket URI (e.g., `gs://my-artifact-bucket`)
- **Default:** Unset (in-memory ephemeral storage)
- **Purpose:** Enables artifact storage persistence
- **Where:** Set locally in `.env` after first deployment
- **How to get:** GitHub Actions job summary (`gh run view <run-id>`) or GCP Console (Cloud Storage → Buckets)

---

## Optional - Runtime Configuration

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

### Server

**HOST**
- **Default:** `127.0.0.1`
- **Purpose:** Server bind address
- **Note:** `127.0.0.1` binds to localhost only (recommended for local development)

**PORT**
- **Default:** `8000`
- **Purpose:** Server listening port
- **Note:** Cloud Run always uses port 8000, Docker Compose maps to host port 8000

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
- **Default:** `["http://127.0.0.1", "http://127.0.0.1:8000"]`
- **Format:** JSON array string
- **Purpose:** Configure CORS allowed origins
- **Where:** Hard-coded in Terraform for Cloud Run, configurable locally via `.env`
- **Example:** `ALLOW_ORIGINS='["https://your-domain.com", "http://127.0.0.1:3000"]'`

### Advanced

**ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS**
- **Default:** `FALSE`
- **Purpose:** Suppress ADK experimental feature warnings
- **Options:**
  - `FALSE` - Show warnings
  - `TRUE` - Suppress warnings

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
- Hard-coded in workflow files

### Precedence

1. **Environment variables** (highest priority)
2. **`.env` file** (loaded via `python-dotenv`)
3. **Default values** (defined in code)

### Security

- **Never commit `.env` files** - Already gitignored
- **Use Workload Identity Federation** - No service account keys needed for CI/CD
- **Rotate credentials** - If `.env` is accidentally committed, rotate all credentials
- **Limit OTEL content capture** - Set `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=FALSE` for sensitive data

### See Also

- `.env.example` - Template configuration with inline comments
- [Development](development.md) - Local development setup
- [Deployment](deployment.md) - Cloud Run deployment and GitHub Environment Variables
- [CI/CD](cicd.md) - GitHub Actions workflows
