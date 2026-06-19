# Integration Tests

The integration lane: the real FastAPI app exercised against a real Postgres session service.

## What it is

The integration lane (`tests/integration/`) exercises the real FastAPI app against a real Postgres session service with no mocks. It builds the production app via ADK `get_fast_api_app()` with a `postgresql+asyncpg://` URI (a real `DatabaseSessionService`) and drives it in-process with httpx `ASGITransport`. The only substitution is the LLM: `root_agent.model` is replaced with a deterministic stub, so the run path persists and reads session state without a network call or cost.

The lane is deterministic and runs only by explicit path (`uv run pytest tests/integration`); it never calls the live model.

## What it covers

- Session lifecycle through the API: create, get, list, delete
- An agent run that persists events and reads back session state
- Postgres dialect strictness: asyncpg rejects ISO strings for `timestamptz` where sqlite tolerates them, so direct SQL binds native Python objects via typed `bindparam`. These tests demonstrate the asyncpg strictness constraint that motivates the typed-bindparam convention in AGENTS.md; the session-lifecycle and agent-run tests are what actually catch dialect regressions through `DatabaseSessionService`.

## Run it locally

Start an ephemeral Postgres container, run the lane, then tear it down:

```bash
docker run -d --rm --name your-agent-pg \
  -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=sessions \
  postgres:18

uv run pytest tests/integration

docker stop your-agent-pg
```

The connection defaults to `postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sessions`. Override it with the `INTEGRATION_DATABASE_URI` environment variable to point at a different host or port. This is a test-harness variable, not application runtime config, so it lives here rather than in `docs/environment-variables.md`.

> [!NOTE]
> The lane needs no GCP credentials. An autouse session fixture (`_mock_gcp_credentials`) in the test module patches `dotenv.load_dotenv` and `google.auth.default`. A fixture suffices because the lane imports the source package lazily — inside `integration_app`, after collection — so the patch lands before any agent code runs.

## How CI provides Postgres

The `ci.yml` `integration` job runs a `postgres:18` service container (with a `pg_isready` health check) and sets `INTEGRATION_DATABASE_URI` to reach it. The major version tracks the deployed Cloud SQL instance (`POSTGRES_18` in `terraform/main/database.tf`), so the lane exercises the dialect production actually runs. It is gated on the `changes` job and folded into the always-runs `status` sentinel, so the single required check `CI / status` covers it. The job runs `uv run pytest tests/integration` without `--cov` — the 100% coverage gate is unit-lane-only.

---

← [Back to References](README.md) | [Documentation](../README.md)
