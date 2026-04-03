# Local Development with Cloud Resources

Advanced options for connecting `uv run server` to cloud resources and selecting service backends using environment variables.

See [Environment Variables: Cloud Resources](../environment-variables.md#cloud-resources) for where to get each value.

## Connect `uv run server` to Cloud SQL

When `SESSION_SERVICE_URI` is unset, `uv run server` uses SQLite sessions (`.adk/` directory). To connect to Cloud SQL for production-consistent session persistence, run the IAP tunnel in a separate terminal or background process.

**1. Start IAP tunnel to bastion:**

```bash
gcloud compute start-iap-tunnel <bastion-instance> 5432 \
  --zone=<zone> \
  --project=<project-id> \
  --local-host-port=localhost:5432
```

**2. Set SESSION_SERVICE_URI:**

```bash
SESSION_SERVICE_URI=postgresql+asyncpg://SA_NAME@PROJECT.iam:@localhost:5432/agent_sessions
```

**3. Run the server:**

```bash
uv run server
```

The app connects to `localhost:5432` through the IAP tunnel, same as Docker Compose and Cloud Run.

> [!IMPORTANT]
> Requires `roles/iap.tunnelResourceAccessor` on your Google account.

## Select Agent Engine for Sessions

Cloud SQL is the default session backend in deployed environments. To use Agent Engine for sessions instead (the managed ADK session service), set `SESSION_SERVICE_URI` to an `agentengine://` URI:

```bash
SESSION_SERVICE_URI=agentengine://projects/YOUR_PROJECT_ID/locations/YOUR_LOCATION/reasoningEngines/YOUR_ENGINE_ID
```

This uses the same Agent Engine instance already deployed for memory. ADK's `get_fast_api_app()` routes `agentengine://` URIs to `VertexAiSessionService` automatically.

**Trade-offs:**
- Agent Engine sessions are fully managed (no database infrastructure)
- Cloud SQL sessions offer enterprise data compliance, SQL querying, and row-level locking
- Both use IAM authentication with no passwords

## Selective Cloud Resource URIs

Each service URI environment variable is independent — set or omit each one to control the agent backend connections:

| Variable | Set | Unset |
|----------|-----|-------|
| `SESSION_SERVICE_URI` | Cloud SQL or Agent Engine | Local SQLite (`.adk/` directory) |
| `MEMORY_SERVICE_URI` | Agent Engine | In-memory (lost on restart) |
| `ARTIFACT_SERVICE_URI` | GCS bucket | In-memory (lost on restart) |

**Examples:**

Use Cloud SQL sessions with local memory and artifacts (no Agent Engine dependency):
```bash
SESSION_SERVICE_URI=postgresql+asyncpg://SA_NAME@PROJECT.iam:@localhost:5432/agent_sessions
# MEMORY_SERVICE_URI=     (commented out — in-memory)
# ARTIFACT_SERVICE_URI=   (commented out — in-memory)
```

Use GCS artifacts with local sessions and memory:
```bash
# SESSION_SERVICE_URI=    (commented out — local SQLite)
# MEMORY_SERVICE_URI=     (commented out — in-memory)
ARTIFACT_SERVICE_URI=gs://YOUR_BUCKET_NAME
```

Use all cloud resources via `uv run server` (requires manual IAP tunnel for Cloud SQL):
```bash
SESSION_SERVICE_URI=postgresql+asyncpg://SA_NAME@PROJECT.iam:@localhost:5432/agent_sessions
MEMORY_SERVICE_URI=agentengine://projects/YOUR_PROJECT_ID/locations/YOUR_LOCATION/reasoningEngines/YOUR_ENGINE_ID
ARTIFACT_SERVICE_URI=gs://YOUR_BUCKET_NAME
```

> [!NOTE]
> Docker Compose configures all three URIs automatically. These options are for `uv run server` workflows where you want selective cloud connectivity.

---

← [Back to References](README.md) | [Documentation](../README.md)
