# Testing Strategy

Detailed testing patterns, organization, and requirements for the project.

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

Tests mirror source structure:

```
tests/
  conftest.py                    # Shared fixtures, mocks, and test environment setup
  test_callbacks.py              # Tests for src/agent_foundation/callbacks.py
  test_tools.py                  # Tests for src/agent_foundation/tools.py
  ...
```

### Naming Conventions

- **Files:** `test_<module>.py` mirroring source module name
- **Functions:** `test_<what>_<condition>_<expected>`
- **Classes:** Group related tests for the same module/class (style preference)

### Shared Fixtures

All reusable fixtures go in `tests/conftest.py`:
- Type hint fixture definitions with both parameters and return types
- Use pytest-mock type aliases for returns: `MockType`, `AsyncMockType`
- Factory pattern (not context managers)

## Fixture Patterns

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

**Base test environment:** Set in `pytest_configure()` using direct `os.environ` assignments (see pytest_configure section below).

**One-off overrides in specific tests:** Use `mocker.patch.dict` when you need to override or add environment variables for a single test:

```python
def test_config_with_custom_region(mocker: MockerFixture) -> None:
    """Test configuration with non-default region."""
    # Override just the region for this test
    mocker.patch.dict(os.environ, {"GOOGLE_CLOUD_LOCATION": "us-west1"})
    # Test config loading with custom region
```

This approach keeps base env vars in `pytest_configure()` and only uses mocking for test-specific overrides.

## ADK Mock Strategy

### Using Conftest Fixtures

Prefer fixtures from `conftest.py` for standard mocks:
- `mock_state` - ADK state object
- `mock_session` - ADK session
- `mock_context` - ReadonlyContext with user_id

### When to Import Mock Classes

Import mock classes directly only when:
- Creating fixtures for many variants adds more complexity than value
- Guideline: >3 variants → import class; standard cases → use/add fixture

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
import os
from unittest.mock import MagicMock, patch

def pytest_configure() -> None:
    """Configure test environment before test collection."""
    # Mock google.auth before modules import it
    with patch("google.auth.default", return_value=(MagicMock(), "project")):
        pass

    # Set environment directly (not setdefault)
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    os.environ["AGENT_NAME"] = "test-agent"
```

See `tests/conftest.py` for complete example with detailed comments.

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

Test connections between components:
- Callbacks are registered and invoked
- Tools are added to agent correctly
- Configuration flows through system

## Mypy Override for Tests

Tests use relaxed type checking for pragmatism:

```toml
[[tool.mypy.overrides]]
module = "tests.*"
disable_error_code = ["arg-type"]
```

Still type hint `conftest.py` fully, but test functions can be more flexible.

## Running Tests

```bash
# Full coverage report
uv run pytest --cov --cov-report=term-missing

# HTML report for detailed view
uv run pytest --cov --cov-report=html
open htmlcov/index.html

# Specific tests
uv run pytest tests/test_integration.py -v
uv run pytest tests/test_file.py::test_name -v

# Watch mode (requires pytest-watch)
uv run ptw
```

## Examples

See `tests/conftest.py` and existing test files for complete patterns:
- Fixture factories
- ADK mocks
- Environment mocking
- Pydantic validation tests
- Async test patterns (with pytest-asyncio)

---

← [Back to References](README.md) | [Documentation](../README.md)
