# Environment Variables

Complete configuration reference. Single source of truth.

See `.env.example` in the repository root for template configuration with inline comments.

> [!NOTE]
> A variable set in the environment (your shell, a command prefix like `LOG_LEVEL=DEBUG uv run server`, or the platform) always wins over the same key in `.env`. `.env` only fills in variables that are unset. See [Precedence](#precedence).

## Quick Reference

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| **[GOOGLE_GENAI_USE_ENTERPRISE](#google-cloud-vertex-ai)** | ✅ | - | Enable Vertex AI authentication |
| **[GOOGLE_CLOUD_PROJECT](#google-cloud-vertex-ai)** | ✅ | - | GCP project ID |
| **[GOOGLE_CLOUD_LOCATION](#google-cloud-vertex-ai)** | ✅ | - | Vertex AI model endpoint location |
| **[AGENT_NAME](#agent-identification)** | ✅ | - | Unique agent identifier |
| **[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT](#opentelemetry)** | ✅ | - | GenAI message content capture mode |
| **[BASTION_INSTANCE](#cloud-resources)** | Recommended | - | Bastion host name for IAP tunnel (docker-compose) |
| **[BASTION_ZONE](#cloud-resources)** | Recommended | - | Bastion host zone for IAP tunnel (docker-compose) |
| **[SESSION_SERVICE_URI](#cloud-resources)** | Recommended | in-memory | Session persistence |
| **[MEMORY_SERVICE_URI](#cloud-resources)** | Recommended | in-memory | Memory persistence |
| **[ARTIFACT_SERVICE_URI](#cloud-resources)** | Recommended | in-memory | Artifact storage |
| [LOG_LEVEL](#logging) | Optional | `INFO` | Logging verbosity |
| [OTEL_RESOURCE_ATTRIBUTES](#opentelemetry-export) | Optional | unset | Override or add resource attributes |
| [ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS](#opentelemetry) | Optional | `true` (deployed: `false` with `NO_CONTENT`) | ADK's live streaming content attribute |
| [SERVE_WEB_INTERFACE](#agent-features) | Optional | `FALSE` | Enable ADK web UI |
| [RELOAD_AGENTS](#agent-features) | Optional | `FALSE` | Hot-reload on file changes |
| [ALLOW_ORIGINS](#cors) | Optional | `["http://127.0.0.1:8000", "http://localhost:8000"]` | CORS allowed origins |
| [AGENT_DIR](#advanced) | Optional | Auto-detected | Override agent directory |
| [HOST](#advanced) | Optional | `127.0.0.1` | Server bind address |
| [PORT](#advanced) | Optional | `8000` | Server listening port |
| [ADK_EXPERIMENTAL_TELEMETRY](#advanced) | Optional | `FALSE` (template sets `TRUE`) | ADK's experimental metrics and span data |
| [ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS](#advanced) | Optional | `FALSE` | Suppress ADK warnings |

**Cloud Run auto-set:** [K_CONFIGURATION](#cloud-run-auto-set-read-only)

**CI/CD only:** [TF_VAR_*](#terraform-inputs-tf_var_) variables and [repository secrets](#repository-secrets) (GitHub Actions)

**Test lanes:** [test lane inputs](#test-lane-inputs) (set by CI, or as a prefix on a local test command)

---

## Required

These must be set for the agent to function.

### Google Cloud Vertex AI

**GOOGLE_GENAI_USE_ENTERPRISE**
- **Value:** `TRUE`
- **Purpose:** Enables Vertex AI authentication for Gemini models
- **Where:** Set locally in `.env`, auto-configured in Cloud Run
- **Note:** Replaces `GOOGLE_GENAI_USE_VERTEXAI`, deprecated in ADK 2.4.0. The old name still resolves, but every request that reads it emits a `DeprecationWarning`. Update an existing local `.env` to silence it. When both are set, `GOOGLE_GENAI_USE_ENTERPRISE` wins

**GOOGLE_CLOUD_PROJECT**
- **Value:** Your GCP project ID (e.g., `your-project-id`)
- **Purpose:** Identifies the Google Cloud project for Vertex AI and other GCP services
- **Where:** Set locally in `.env`, configured via Terraform for Cloud Run

**GOOGLE_CLOUD_LOCATION**
- **Value:** Vertex AI model endpoint location (e.g., `global` or `us-central1`)
- **Purpose:** Routes Vertex AI model calls only. Does not set the deployment region. Infrastructure placement is controlled separately by the `region` Terraform variable (`REGION` GitHub Environment Variable)
- **Where:** Set locally in `.env`, configured via Terraform for Cloud Run (`TF_VAR_google_cloud_location`)

### Agent Identification

**AGENT_NAME**
- **Value:** Unique identifier (e.g., `your-agent`)
- **Purpose:** Identifies cloud resources, logs, and traces
- **Where:** Set locally in `.env`, set before bootstrap (used for Terraform resource naming)
- **Note:** Used as base name for Terraform resources (`{agent_name}-{environment}`)

### OpenTelemetry

**OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT**
- **Options** (exact, uppercase; `ServerEnv` rejects anything else, including `TRUE` and `FALSE`):
  - `NO_CONTENT` - No message content (pair with `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` to keep live streaming content out too)
  - `EVENT_ONLY` - Put prompts and responses on `gen_ai.client.inference.operation.details` log records (GenAI events), shown in Cloud Trace's Input/Output view
  - `SPAN_ONLY` - Put them on span attributes: `gen_ai.input.messages` and `gen_ai.output.messages` on model calls, `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` on tool calls
  - `SPAN_AND_EVENT` - Both
- **Purpose:** Controls whether and where ADK records GenAI message content, including tool arguments and results. Live streaming content follows `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` instead
- **Where:** Set locally in `.env`, set before bootstrap
- **Reference:** [Message Content Capture](observability.md#message-content-capture) (recommended values and why) and OpenTelemetry's [GenAI utilities](https://github.com/open-telemetry/opentelemetry-python-genai/tree/main/util/opentelemetry-util-genai)
- **Security:** For sensitive data, set `NO_CONTENT` and `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`

**ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS**
- **Default:** `true` when unset (ADK's default, independent of the capture mode); the Cloud Run service sets `false` whenever its capture mode is `NO_CONTENT`
- **Purpose:** Read by ADK, not `ServerEnv`. Under ADK's default telemetry schema it only controls live streaming (`/run_live`): the content sent to the model, on the `gcp.vertex.agent.data` span attribute. It also controls content on ADK's deprecated legacy schema (`ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN=otel_semconv_1_36`). `false` leaves them empty
- **Where:** `.env` locally; derived from the capture mode in `terraform/main/main.tf` on Cloud Run
- **Reference:** [Message Content Capture](observability.md#message-content-capture)

---

## Cloud Resources

Production-ready persistence for sessions, memory, and artifacts. Configure after first deployment.

**BASTION_INSTANCE**
- **Value:** Bastion VM instance name (e.g., `my-agent-dev-bastion`)
- **Purpose:** IAP tunnel target for docker-compose Cloud SQL connectivity
- **Where:** Set locally in `.env` for docker-compose (the IAP tunnel container uses this)
- **How to get:** GitHub Actions job summary or `terraform output bastion_instance`
- **Note:** Only used by docker-compose, not by the application. Cloud Run connects to Cloud SQL via direct VPC egress.

**BASTION_ZONE**
- **Value:** GCE zone (e.g., `us-central1-b`)
- **Purpose:** Zone of the bastion host for IAP tunnel
- **Where:** Set locally in `.env` for docker-compose
- **How to get:** GitHub Actions job summary or `terraform output bastion_zone`
- **Note:** Only used by docker-compose.

**SESSION_SERVICE_URI**
- **Value:** Service-specific URI with protocol prefix (e.g., `postgresql+asyncpg://sa-name@project.iam:@localhost:5432/agent_sessions`)
- **Purpose:** Session persistence (production-consistent behavior)
- **Where:** Set locally in `.env` after first deployment, auto-configured in Cloud Run
- **How to get:** GitHub Actions job summary (`gh run view <run-id>`) or `terraform output session_service_uri`
- **Note:** Database Session Service connects through Cloud SQL Auth Proxy on localhost. IAM database auth — no password needed. Defaults to in-memory if unset.

**MEMORY_SERVICE_URI**
- **Value:** Service-specific URI with protocol prefix (e.g., `agentengine://projects/123/locations/us-central1/reasoningEngines/456`)
- **Purpose:** Memory persistence (production-consistent behavior)
- **Where:** Set locally in `.env` after first deployment, auto-configured in Cloud Run
- **How to get:** GitHub Actions job summary (`gh run view <run-id>`) or `terraform output memory_service_uri`
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

### OpenTelemetry Export

Every signal exports to the Google Cloud Telemetry API with Application Default Credentials. `telemetry.py` passes the endpoint to every exporter explicitly, so the SDK's `OTEL_EXPORTER_OTLP_*` endpoint variables have no effect. On Cloud Run, metrics go to Google automatically; locally they go only when you add `cloud.region=<region>` to `OTEL_RESOURCE_ATTRIBUTES`. The OpenTelemetry SDK reads these variables itself, from `.env` or the shell.

> [!NOTE]
> Only `uv run server` and the container entry point run the template's telemetry setup. `adk web`, `adk api_server` and `adk run` use ADK's own telemetry setup instead.

**OTEL_RESOURCE_ATTRIBUTES**
- **Default:** unset (no `service.namespace`)
- **Purpose:** Override or add resource attributes on every signal. A key set here wins over the template's value (like `service.name`). Set `service.namespace` to a unique value, like your name, so teammates can filter to your local experiments
- **Where:** `.env` or the shell; Terraform sets `service.namespace=<environment>` on the Cloud Run service
- **Format:** comma-separated `key=value` pairs, like `OTEL_RESOURCE_ATTRIBUTES=service.name=my-agent,service.namespace=alice-local`
- **Metrics locally:** add `cloud.region=<region>` (like `cloud.region=us-central1`) to send metrics to Google from your machine; without a region, metrics are off
- **Note:** The SDK also honors the standard `OTEL_SERVICE_NAME`, which wins over `service.name` in `OTEL_RESOURCE_ATTRIBUTES`; the template neither sets nor prints it

The SDK reads its other standard variables too, like `OTEL_TRACES_SAMPLER` for trace sampling; the template sets none of them on Cloud Run. See the OpenTelemetry [SDK environment variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/).

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

### CORS

**ALLOW_ORIGINS**
- **Default:** `'["http://127.0.0.1:8000", "http://localhost:8000"]'`
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

**ADK_EXPERIMENTAL_TELEMETRY**
- **Default:** `FALSE` when unset; `.env.example` and the Cloud Run service (`terraform/main/main.tf`) set `TRUE`
- **Purpose:** Read by ADK, not `ServerEnv`. Adds ADK's `adk.experimental.*` metrics (token breakdowns, workflow call counts, skill loads, compactions) and experimental span data. ADK's seven default `gen_ai.*` metrics need no flag
- **Where:** `.env` locally; fixed in the Terraform env map on Cloud Run

**ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS**
- **Default:** `FALSE`
- **Purpose:** Suppress ADK experimental feature warnings
- **Options:**
  - `FALSE` - Show warnings
  - `TRUE` - Suppress warnings

### Cloud Run Auto-Set (Read-Only)

These variables are automatically set by Cloud Run. Do not set manually.

**K_CONFIGURATION**
- **Default:** unset (local development)
- **Purpose:** Cloud Run configuration name. `telemetry.py` reads it for the `configuration_name` label that places OTLP logs on the `cloud_run_revision` resource; the GCP resource detector supplies the other labels
- **Where:** Auto-set by Cloud Run
- **Example:** `your-agent-dev`

---

## CI/CD Only

These variables are used exclusively in GitHub Actions workflows. Do not set locally.

### Terraform Inputs (TF_VAR_*)

GitHub Environment Variables are mapped to Terraform inputs via `TF_VAR_*` prefix:

**TF_VAR_project**
- **Source:** `${{ vars.GOOGLE_CLOUD_PROJECT }}` (GitHub Environment Variable)
- **Purpose:** GCP project ID for Terraform

**TF_VAR_region**
- **Source:** `${{ vars.REGION }}` (GitHub Environment Variable)
- **Purpose:** GCP region for compute resource placement

**TF_VAR_zone**
- **Source:** `${{ vars.ZONE }}` (GitHub Environment Variable)
- **Purpose:** GCP zone for bastion host placement

**TF_VAR_google_cloud_location**
- **Source:** `${{ vars.GOOGLE_CLOUD_LOCATION }}` (GitHub Environment Variable, optional)
- **Purpose:** Vertex AI model endpoint routing (recommended default `"global"` in bootstrap terraform.tfvars.example)

**TF_VAR_agent_name**
- **Source:** `${{ vars.IMAGE_NAME }}` (GitHub Environment Variable)
- **Purpose:** Agent name for resource naming

**TF_VAR_terraform_state_bucket**
- **Source:** `${{ vars.TERRAFORM_STATE_BUCKET }}` (GitHub Environment Variable)
- **Purpose:** GCS bucket for Terraform state

**TF_VAR_otel_instrumentation_genai_capture_message_content**
- **Source:** `${{ vars.OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT }}` (GitHub Environment Variable, written by bootstrap from `otel_instrumentation_genai_capture_message_content` in each bootstrap root's `terraform.tfvars`)
- **Purpose:** Message content capture mode on the Cloud Run service. Required: Terraform validation accepts only the four capture modes, so deleting the GitHub variable fails the plan. With `NO_CONTENT`, Terraform also sets `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`
- **Recommended:** `SPAN_AND_EVENT` in dev to debug prompts, responses and tool calls; `NO_CONTENT` in stage and prod (the bootstrap `terraform.tfvars.example` files)
- **Change:** set the bootstrap value and re-apply bootstrap, which rewrites the GitHub variable

**TF_VAR_docker_image**
- **Source:** `${{ inputs.docker_image }}` (workflow input)
- **Purpose:** Immutable image digest for deployment

**TF_VAR_environment**
- **Source:** Set by workflow (dev/stage/prod)
- **Purpose:** Environment-specific resource naming

**TF_VAR_workload_identity_pool_principal_identifier**
- **Source:** `${{ vars.WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER }}` (GitHub Environment Variable, auto-created by bootstrap)
- **Purpose:** WIF principal identifier for binding additional IAM roles in `terraform/main/iam.tf`

### Runtime Configuration Overrides

Override runtime config via GitHub Environment Variables (mapped to `TF_VAR_*`):

**TF_VAR_log_level**
- **Source:** `${{ vars.LOG_LEVEL }}` (optional GitHub Environment Variable)
- **Purpose:** Override LOG_LEVEL for Cloud Run deployment

**TF_VAR_serve_web_interface**
- **Source:** `${{ vars.SERVE_WEB_INTERFACE }}` (optional GitHub Environment Variable)
- **Purpose:** Override SERVE_WEB_INTERFACE for Cloud Run deployment
- **Set:** `gh variable set SERVE_WEB_INTERFACE --env dev --body "TRUE"` (or Settings → Environments), then re-run the latest CI/CD workflow to redeploy. The web interface is then at `http://localhost:8000` through `gcloud run services proxy`

### Test Lane Inputs

Read by test lanes rather than by the application, so they never appear in `ServerEnv` or on Cloud Run. CI sets them from workflow inputs; set them locally only to run a lane by hand, as a prefix on the command itself.

> [!NOTE]
> `.env` does not set these. The smoke lane never loads `.env` at all and raises on an unset `SMOKE_*`. The eval lane takes no environment input: what it scores is fixed in constants in `tests/eval/test_agent_eval.py`, so a run cannot be reconfigured from outside the file it is defined in.

**SMOKE_BASE_URL**, **SMOKE_INVOKER_SA**
- **Source:** `smoke.yml`, from the apply job's `smoke_target_url` and `smoke_invoker_service_account_email` outputs
- **Purpose:** Deployed service URL and the invoker SA the smoke client impersonates. See [Smoke Tests](references/smoke-tests.md)

**INTEGRATION_DATABASE_URI**
- **Source:** Not set in CI (the lane starts a throwaway `postgres:18` via testcontainers)
- **Purpose:** Point the integration lane at an already-running Postgres instead. See [Integration Tests](references/integration-tests.md)

### Repository Secrets

Set in GitHub Actions > Secrets and variables > Actions. Both select the model auth path for the `claude.yml` PR review; when neither is set, the review authenticates via Workload Identity Federation and calls Vertex AI. See [Claude PR Review](references/claude-pr-review.md).

**ANTHROPIC_API_KEY**
- **Source:** Repository secret (optional, set manually)
- **Purpose:** Runs the review against the Anthropic API with an organization API key instead of Vertex AI. Takes precedence over `CLAUDE_CODE_OAUTH_TOKEN`

**CLAUDE_CODE_OAUTH_TOKEN**
- **Source:** Repository secret (optional, set manually; generate with `claude setup-token`)
- **Purpose:** Runs the review against the Anthropic API with an individual account's Claude Code OAuth token instead of Vertex AI. Ignored when `ANTHROPIC_API_KEY` is set. Expires about a year after creation and must be rotated

> [!NOTE]
> These two names are also what the local Claude Code CLI reads for its own authentication. The "do not set locally" guidance above applies to the `TF_VAR_*` variables, not to these.

---

## Reference

### Where Variables Are Set

**Local Development:**
- `.env` file in the directory where you run the server
- Command line (e.g., `LOG_LEVEL=DEBUG uv run server`)
- `docker-compose.yml` (Docker Compose)

**Cloud Run:**
- Terraform `main` module (`terraform/main/main.tf`)
- GitHub Environment Variables → `TF_VAR_*` → Terraform → Cloud Run environment

**CI/CD:**
- GitHub Environment Variables (auto-created by bootstrap)
- Workflow inputs and outputs

### Precedence

The environment wins over `.env`, everywhere `.env` is read:

1. `initialize_environment()` (`config.py`) runs first in `server.py`. It finds `.env` by searching upward from the working directory and copies it into `os.environ` with python-dotenv's `load_dotenv()`, without overriding any variable already set. `ServerEnv` then reads `os.environ`; `.env` keys it does not define are ignored.
2. ADK's agent loader then finds `.env` by searching upward from the agent's package and loads it with `override=True`, but first snapshots every variable already in `os.environ` and restores those after loading. Everything `initialize_environment()` set is in that snapshot, so ADK only adds keys that neither the environment nor the working directory's `.env` set. `adk web`, `adk api_server` and `adk run` skip step 1, so there ADK's loader is the only one.
3. The eval lane loads `.env` with `python-dotenv` without overriding set variables.

Because `.env` reaches `os.environ` before anything else in startup, every reader sees it: `ServerEnv`, the OpenTelemetry SDK's `OTEL_*` variables, ADK, and the Google SDKs.

Cloud Run never reads `.env` (`.dockerignore` keeps it out of the image), and Docker Compose passes it to the container through `env_file:`, so the platform's values always apply there.

> [!NOTE]
> A variable exported in your shell profile, like a global `GOOGLE_CLOUD_PROJECT`, overrides this project's `.env`. Unset it or run the server from a shell without it when the two differ.

### Security

- **Never commit `.env` files** to version control - Already gitignored
- **Workload Identity Federation** - No service account keys needed for CI/CD
- **Sensitive data** - Set `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT` and `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` when handling sensitive information

---

← [Back to Documentation](README.md)
