# Testing Strategy

Detailed testing patterns, organization, and requirements for the project.

## Test Lanes

A test's lane is decided by its runtime requirements and determinism, not by how many components it touches.

| Lane | Needs | Deterministic | Cost | Local command |
|---|---|---|---|---|
| unit | in-process only (mocks at boundaries) | yes | free/fast | `uv run pytest` (default) |
| integration | real external resource (Postgres) | yes | slower, no LLM/cloud | `uv run pytest tests/integration` |
| smoke | a live deployed URL | yes | needs a deploy | `uv run pytest tests/smoke` |
| eval | the real LLM (full suite) | gate metrics yes; judge metrics no | costs money | `uv run pytest tests/eval` |

Non-unit lanes run by explicit path, both locally and in CI — the command or CI job is the selector. `testpaths = ["tests/unit"]` in `pyproject.toml` scopes a bare `uv run pytest` to the fast, free, deterministic lane so it can't accidentally require Postgres or spend LLM money. An explicit path argument overrides it.

Only the unit lane runs `--cov` with the 100% gate.

## Coverage Requirements

**100% coverage required on production code.**

**Included:**
- All code in `src/` except explicitly excluded files (see below)

**Excluded:**
- `server.py` (FastAPI entrypoint - validate server behavior with integration tests)
- `**/agent.py` (pure ADK configuration - tests are the upstream project's responsibility)
- `**/prompt.py` (prompt templates - validate agent behavior with evaluations)
- `**/__init__.py` (module initialization)

## Test Organization

### Directory Structure

Lanes are top-level directories; unit test modules mirror source structure:

```
tests/
  conftest.py                    # Shared fixtures, mocks, and test environment setup (all lanes)
  unit/
    test_callbacks.py            # Tests for src/agent_foundation/callbacks.py
    test_tools.py                # Tests for src/agent_foundation/tools.py
    test_config.py               # Tests for src/agent_foundation/config.py
    ...
  integration/                   # Postgres + FastAPI lane
  smoke/                         # Live deployed-URL lane
  eval/                          # LLM eval lane
```

The root `conftest.py` applies to all lanes (auth/dotenv mocking). Per-lane `conftest.py` files (e.g. a Postgres fixture in `integration/`) live in their lane directory.

> [!NOTE]
> The eval lane is the exception to the auth/dotenv mocks: when an invocation targets only `tests/eval`, the root `pytest_configure()` skips them so the agent can authenticate for real model inference. Run the eval lane standalone (`uv run pytest tests/eval`) — in a mixed-lane invocation the mocks stay on and the eval test fails on the mocked credentials.

### Naming Conventions

- **Files:** test module path mirrors source path: `src/<pkg>/config.py → tests/unit/test_config.py`; nested source paths flatten with underscores (`<pkg>/sub/foo.py → test_sub_foo.py`)
- **Functions:** `test_<what>_<condition>_<expected>`
- **Classes:** Group related tests for the same module/class (style preference)

### Shared Fixtures

All reusable fixtures go in `tests/conftest.py`:
- Type hint fixture definitions with both parameters and return types
- Use pytest-mock type aliases for returns: `MockType`, `AsyncMockType`
- Factory pattern (not context managers)

## Fixture Patterns

### Test Double Naming

Test double classes and fixtures follow a strict naming convention (established in root `conftest.py`):

| Kind | Prefix | Example | Returns |
|---|---|---|---|
| Test double class | `Mock` | `MockState`, `MockOAuthContextStore` | — (defined in conftest) |
| Instance fixture | `mock_` | `mock_state`, `mock_chat_client` | Single mock instance |
| Factory fixture | `create_mock_` | `create_mock_state`, `create_mock_oauth_store` | `Callable` that builds instances |
| Convenience fixture | (none) | `oauth_flow_config`, `valid_server_env` | Real objects / test data |

Factory fixtures use `_factory` as their inner function name:

```python
@pytest.fixture
def create_mock_state() -> Callable[..., MockState]:
    def _factory(data: dict | None = None) -> MockState:
        return MockState(data)
    return _factory
```

### Type Hints

**Fixture definitions (strict in conftest.py):**
```python
from pytest_mock import MockerFixture
from pytest_mock.plugin import MockType

@pytest.fixture
def mock_session(mocker: MockerFixture) -> MockType:
    """Create a mock ADK session."""
    return mocker.MagicMock(spec=...)
```

**Test functions (relaxed):**
- Don't type hint custom fixtures (pytest handles DI by name)
- Optional type hints on built-in fixtures for IDE support

### Environment Mocking

**No base env vars in `pytest_configure()`:** No module in the test import graph reads env vars at module level. `server.py` does (`initialize_environment` at line 26), but it's never imported during collection (PEP 562 lazy loading, coverage-excluded). Environment variables are set in test fixtures using `mocker.patch.dict`:

```python
def test_config_with_custom_region(mocker: MockerFixture) -> None:
    """Test configuration with non-default region."""
    mocker.patch.dict(os.environ, {"GOOGLE_CLOUD_LOCATION": "us-west1"})
    # Test config loading with custom region
```

If a future import chain triggers env var reads at collection time, add direct `os.environ` assignments in `pytest_configure()` (see section below).

## ADK Mock Strategy

### Using Conftest Fixtures

Prefer fixtures from `conftest.py` for standard mocks:
- `mock_state` - ADK state object
- `mock_session` - ADK session
- `mock_context` - ReadonlyContext with user_id

### Never Import Mock Classes

Never import mock classes directly in test files. Always use or add a fixture in `conftest.py`. For edge cases requiring custom internal structure, add a specific named fixture (e.g., `mock_event_non_text_content`) rather than importing the class.

### Mirror Real Interfaces

ADK mocks must exactly mirror real ADK interfaces:
- Use `spec=` parameter to enforce interface
- Include all properties and methods used in code
- Match return types and signatures

## pytest_configure()

**Special case: unittest.mock before pytest-mock available**

`pytest_configure()` runs before test collection, so pytest-mock isn't available yet.
Use `unittest.mock` here for setup that must happen before tests load:

```python
def pytest_configure() -> None:
    """Configure test environment before test collection."""
    from unittest.mock import Mock, patch

    # Patch load_dotenv to prevent loading real .env
    patch("dotenv.load_dotenv").start()

    # Patch google.auth.default to prevent ADC lookup
    mock_creds = Mock(token="fake", valid=True, expired=False)
    patch("google.auth.default", return_value=(mock_creds, "test-project")).start()
    patch("google.auth._default.default", return_value=(mock_creds, "test-project")).start()

    # Environment variables: No module in the test import graph reads env vars at
    # module level. server.py does (initialize_environment(ServerEnv)), but it's
    # never imported during collection (PEP 562 lazy loading, coverage-excluded).
    # If a future import chain triggers env var reads at collection time, set
    # defaults here using direct assignment:
    # import os
    # os.environ["KEY"] = "value"
```

See `tests/conftest.py` for the complete implementation with detailed lifecycle comments.

## Pydantic Validation Testing

### Validation Timing

Pydantic validates at model creation, not at property access:

```python
# Validation happens here ✓
config = ServerEnv.model_validate(env_dict)

# NOT here ✗
value = config.some_property
```

### Testing Validation

Expect `ValidationError` at model creation:

```python
import pytest
from pydantic import ValidationError

def test_config_invalid_project_id():
    """Test that empty project ID raises validation error."""
    env_dict = {"GOOGLE_CLOUD_PROJECT": ""}

    with pytest.raises(ValidationError):
        ServerEnv.model_validate(env_dict)
```

## What to Test

### Behaviors

Test function outputs and state changes:
- Return values are correct
- State is modified as expected
- Side effects occur (logging, callbacks)

### Error Conditions

Test invalid inputs and edge cases:
- Invalid parameter types
- Missing required values
- Boundary conditions (empty, max, negative)

### Integration Points

App and agent wiring (callbacks registered, tools attached, configuration flow) is validated by the integration lane against a real server.

## Mypy Scope

mypy is scoped to the source package. Test modules are not type-checked; conftest typing is a team convention enforced by reviewers. Full rationale and the expected-error categories that surface if you run `uv run mypy src tests` are in [Code Quality → Test Suite Typing Strategy](code-quality.md#test-suite-typing-strategy).

## Running Tests

```bash
# Unit lane (default) with full coverage report
uv run pytest --cov --cov-report=term-missing

# HTML report for detailed view
uv run pytest --cov --cov-report=html
open htmlcov/index.html

# Other lanes by explicit path
uv run pytest tests/integration
uv run pytest tests/smoke
uv run pytest tests/eval

# Specific tests
uv run pytest tests/unit/test_callbacks.py -v
uv run pytest tests/unit/test_file.py::test_name -v

# Watch mode (requires pytest-watch)
uv run ptw
```

## Agent Evals

The eval lane scores real agent behavior against committed eval sets. One data set, two front-ends:

- **`uv run pytest tests/eval`** — the gate-fidelity runner. Calls `AgentEvaluator.evaluate()`, which raises `AssertionError` on sub-threshold metrics. This is what CI runs.
- **`adk eval src/agent_foundation <evalset> --config_file_path <config>`** and **`adk web src`** — the interactive authoring loop for creating, replaying, and debugging eval cases against the same `*.evalset.json` files.

> [!WARNING]
> Never gate CI on the `adk eval` CLI: it exits 0 even when eval cases fail (verified against google-adk 2.2.0), so a CLI-based gate is silently always green. Only the pytest runner fails the build.

### Artifacts

All eval data lives in `tests/eval/data/`:

| File | Role |
|---|---|
| `template_agent.evalset.json` | Eval cases (ADK `EvalSet` schema): user query, expected tool trajectory, reference response |
| `test_config.json` | Deterministic PR-gate criteria — auto-discovered by `AgentEvaluator` from the eval set's directory |
| `full_eval_config.json` | Full criteria including LLM-judge metrics (`final_response_match_v2`, `safety_v1`) for local deep evaluation and the deploy pipeline; pass explicitly via `--config_file_path` |

### Deterministic PR-Gate Metrics

`test_config.json` uses only metrics with no LLM judge — same inputs, same scores:

- **`tool_trajectory_avg_score` (threshold 1.0, `IN_ORDER` match)** — expected tool calls must occur in order with exact name and args; `IN_ORDER` tolerates extra calls (like an LLM-decided `load_memory`) without failing the case.
- **`response_match_score` (threshold 0.4)** — ROUGE-1 overlap between the actual response and the case's reference response. The agent under test still runs the real LLM, so reference texts use stable tokens (no dates or clock values) and a modest threshold absorbs phrasing variance.

The judge-metric thresholds, judge model, sampling (`num_samples`), and `temperature: 0` live in `full_eval_config.json` — intentionally not wired into the PR gate.

### Credentials and Cost

The deterministic gate has no judge, but inference is real: the eval lane needs Vertex AI auth (`GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` + ADC). Locally these come from `.env` (loaded by `tests/eval/conftest.py`); in CI the `agent-eval` job authenticates with the dev environment's WIF principal (`roles/aiplatform.user`) and sets the variables from environment-scoped GitHub Variables. Each gate run is a handful of flash-model calls — cheap, but not free; that's why the lane never runs from bare `pytest`.

> [!NOTE]
> Running `full_eval_config.json` metrics that delegate to the Vertex AI evaluation service (like `safety_v1`) may require `google-cloud-aiplatform[evaluation]`, which is not installed: the `google-adk[eval]` extra is unresolvable under this project's preventive `litellm` constraint (see `pyproject.toml`). The deterministic metrics and the ADK-native judge (`final_response_match_v2`) work with the committed dev dependencies (`rouge-score`, `pandas`, `tabulate`).

### CI Gate

The `agent-eval` job in `.github/workflows/ci.yml` runs the deterministic gate on every PR that touches code paths. The always-run `status` sentinel requires it, so the existing `CI / status` required check already blocks merges on eval failures — no new branch-protection registration is needed. To additionally require the eval job as its own named check:

```bash
gh api repos/:owner/:repo/branches/main/protection/required_status_checks/contexts \
  --method POST --input - <<< '["CI / Agent Eval (deterministic)"]'
```

### Adding Eval Cases

1. Author or capture a case: `adk web src` records sessions you can export as eval cases, or hand-edit `template_agent.evalset.json` (ADK `EvalSet` pydantic schema).
2. Pin the expected tool trajectory (exact tool name and args) and a reference response built from stable tokens.
3. Replay interactively: `adk eval src/agent_foundation tests/eval/data/template_agent.evalset.json --config_file_path tests/eval/data/test_config.json`
4. Validate gate fidelity and stability: run `uv run pytest tests/eval` at least 3 times before relying on the case in CI.

## Examples

See `tests/conftest.py` and existing test files for complete patterns:
- Fixture factories
- ADK mocks
- Environment mocking
- Pydantic validation tests
- Async test patterns (with pytest-asyncio)

---

← [Back to References](README.md) | [Documentation](../README.md)
