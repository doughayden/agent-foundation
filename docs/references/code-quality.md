# Code Quality

Detailed code quality tools, enforcement strategies, and exclusion guidelines.

## Overview

Tools to enforce code quality:
1. **Ruff** - Fast linting and formatting (replaces flake8, isort, black)
2. **Mypy** - Static type checking
3. **Pytest** - Testing with coverage

All configured in `pyproject.toml`.

## Running Quality Checks

**Run before every commit:**
```bash
# Use ruff to format code first (line length, quotes, whitespace)
uv run ruff format

# Then lint with ruff auto-fix (security, bugs, style violations)
uv run ruff check --fix

# Type check
uv run mypy

# Tests with coverage
uv run pytest --cov --cov-report=term-missing
```

**One-liner for commit:**
```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest --cov
```

## Ruff Configuration

### What We Enforce

From `pyproject.toml`:
```toml
[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors (PEP 8 violations)
    "W",   # pycodestyle warnings
    "F",   # pyflakes (unused imports, undefined names)
    "I",   # isort (import sorting)
    "B",   # flake8-bugbear (common bugs and design problems)
    "C4",  # flake8-comprehensions (better list/dict comprehensions)
    "UP",  # pyupgrade (modern Python syntax)
    "N",   # pep8-naming (naming conventions)
    "S",   # flake8-bandit (security issues)
    "SIM", # flake8-simplify (code simplification)
    "PTH", # flake8-use-pathlib (use Path instead of os.path)
]
```

**Key enforcements:**
- **E501**: Line too long (88 characters)
- **PTH (pathlib rules)**: Use `pathlib.Path` instead of `os.path`
  - **PTH123**: Use `Path.open()` instead of `open()`
  - **PTH118**: Use `Path.joinpath()` instead of `os.path.join()`
  - Why: Modern API, cross-platform, chainable (`path / "subdir"`), type-safe
  - Ruff auto-fixes many os.path calls to Path
- **S (security rules)**: Catch common security issues
  - **S101**: Use of `assert` (banned in production, allowed in tests via per-file ignore)
  - **S104**: Binding to 0.0.0.0 (flagged for security, intentional in containers)
  - **S105**: Possible hardcoded password (detects patterns like "password = 'secret'")

### Per-file Exclusions

From `pyproject.toml`:
```toml
[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]  # Allow assert statements in tests
```

**Why:** Tests use `assert` for validation. This is standard pytest practice and not a security concern.

### Inline Exclusions

**Real example from our codebase:**
```python
# tests/conftest.py:42
mock_credentials.token = "test-mock-token-totally-not-real"  # noqa: S105
```

**Rule:** S105 (Possible hardcoded password)
**Why excluded:** This is a test mock credential, not a real secret. The string content makes it obvious it's not production.

**Real example from tests:**
```python
# tests/test_config.py
"HOST": "0.0.0.0",  # noqa: S104
```

**Rule:** S104 (Binding to all interfaces)
**Why excluded:** Docker containers need to bind to 0.0.0.0 to accept connections from the host. This is intentional and documented.

**When to use `# noqa`:**
- Security rules (S*) with false positives on test code
- Line length (E501) for URLs or data that can't be split
- Specific rule violation that's intentional and safe

**Prefer specific rule codes:**
```python
# Good - clear what's being suppressed
url = "https://example.com/very/long/api/path"  # noqa: E501

# Avoid - unclear what's being allowed
some_code()  # noqa
```

Use `# noqa` only when:
- Rule violation is intentional and well-justified
- Auto-fix would make code less readable
- External constraint prevents compliance (e.g., third-party API format)

### Ruff Auto-fix

Ruff can automatically fix many issues:

```bash
# Auto-fix all fixable issues
uv run ruff check --fix

# Preview fixes without applying (safe mode)
uv run ruff check --diff
```

**What gets auto-fixed:**
- Import sorting (rule I)
- Unused imports (rule F401)
- Whitespace and indentation (rules E, W)
- Quote style normalization (rules Q)
- Trailing commas (rules COM)
- Simple code transformations (e.g., `os.path.join()` → `Path.joinpath()`)

**What requires manual fixing:**
- Complex logic issues
- Security concerns (rule S)
- Naming violations (rule N)
- Code simplification requiring logic changes (rule SIM)

**Best practice:**
1. Run `uv run ruff format` first (formats code)
2. Run `uv run ruff check --fix` second (auto-fixes linting issues)
3. Review remaining issues and fix manually

## Mypy Configuration

### What We Enforce

From `pyproject.toml`:
```toml
[tool.mypy]
python_version = "3.13"
mypy_path = "src"
packages = ["agent_foundation"]

# Completeness checks
disallow_untyped_defs = true         # All functions must have type hints
disallow_incomplete_defs = true      # Complete type hints (all args and return)
disallow_untyped_decorators = true   # Decorators must preserve types

# Type system strictness
no_implicit_optional = true          # Explicit Optional[] for None values
strict_equality = true               # Proper type checking in == comparisons

# Warnings and errors
warn_return_any = true               # Flag functions returning Any
warn_unused_configs = true           # Flag unused config options
warn_redundant_casts = true          # No unnecessary casts
warn_unused_ignores = true           # Remove unused # type: ignore
warn_no_return = true                # Functions must return or raise
warn_unreachable = true              # Detect unreachable code

# Additional strictness
check_untyped_defs = true            # Check function bodies even without annotations
show_error_codes = true              # Show error codes for easier suppression
```

**This is stricter than mypy's default** - every function, every parameter, every return value must be typed.

**Key enforcements:**
- **disallow_untyped_defs**: Every function needs type hints (args + return)
- **disallow_incomplete_defs**: Can't mix typed and untyped parameters
- **no_implicit_optional**: `def foo(x: str = None)` is an error (must use `str | None`)
- **warn_return_any**: Flag when functions return `Any` (type safety leak)
- **strict_equality**: `if my_str == 5:` is an error (comparing incompatible types)
- **warn_unreachable**: Detect dead code after returns/raises

### Example Errors and Fixes

**Error: disallow_untyped_defs**
```python
# mypy error: Function is missing a return type annotation
def process_data(items: list[str]):
    return len(items)

# Fixed
def process_data(items: list[str]) -> int:
    return len(items)
```

**Error: disallow_incomplete_defs**
```python
# mypy error: Function is missing a type annotation for one or more arguments
def fetch_user(id: int, cache):
    return cache.get(id)

# Fixed
def fetch_user(id: int, cache: dict[int, User]) -> User | None:
    return cache.get(id)
```

**Error: no_implicit_optional**
```python
# mypy error: Incompatible default for argument (expected str, got None)
def greet(name: str = None) -> str:
    return f"Hello, {name or 'stranger'}"

# Fixed - explicit None in union
def greet(name: str | None = None) -> str:
    return f"Hello, {name or 'stranger'}"
```

### Per-module Exclusions

From `pyproject.toml`:
```toml
[[tool.mypy.overrides]]
module = "tests.*"
disable_error_code = "arg-type"  # Allow duck-typed mocks in tests
```

**Why:** Test files can pass duck-typed mocks to functions without arg-type errors, enabling pragmatic testing patterns.

**Important caveat:** We still strictly type `conftest.py` fixture definitions as a team practice (see Team Practices section for rationale).

### Inline Exclusions

**When you might need `# type: ignore`:**
```python
# Third-party library without type stubs
import untyped_library  # type: ignore[import-untyped]

# Mypy bug or limitation (add TODO)
result = complex_function()  # type: ignore[return-value]  # TODO: Fix when mypy supports this pattern
```

**Always prefer:**
1. Fix the actual type issue (restructure code to make types clear)
2. Add type stubs for third-party libraries
3. **Use type narrowing** - validate types at runtime with `isinstance()` checks or type guards

**Never use `cast()` - use type narrowing instead:**

Why `cast()` is bad:
- **Bypasses type safety:** Tells mypy to trust you without verification
- **Runtime risk:** No runtime validation - type mismatch crashes at runtime
- **Dishonest about code behavior:** Hides the actual types being used
- **Maintenance burden:** Future changes break assumptions silently

**Type narrowing is always better:**
```python
# Bad - using cast() (DON'T DO THIS)
from typing import cast
result = some_function()
value = cast(str, result)  # Trust me, it's a string! (no runtime check)

# Good - type narrowing with isinstance()
result = some_function()
if not isinstance(result, str):
    raise TypeError(f"Expected str, got {type(result)}")
value = result  # mypy knows this is str now, AND we validated at runtime
```

Type narrowing keeps you honest about what the code actually does - it satisfies both mypy and provides runtime safety.

## Coverage Configuration

### What We Enforce

From `pyproject.toml`:
```toml
[tool.coverage.run]
source = ["src"]
branch = true  # Check both line and branch coverage

[tool.coverage.report]
fail_under = 100  # Require 100% coverage
```

**100% coverage is non-negotiable** for production code.

### File-level Exclusions

From `pyproject.toml`:
```toml
[tool.coverage.run]
omit = [
    # __init__.py files: namespace marker, no logic
    "src/agent_foundation/**/__init__.py",

    # server.py: FastAPI setup and ADK initialization (integration tested via CI/CD)
    "src/agent_foundation/server.py",

    # agent.py: LlmAgent instantiation (tested through callbacks, not in isolation)
    "src/agent_foundation/**/agent.py",

    # prompt.py: Prompt text and formatting (integration tested via agent runs)
    "src/agent_foundation/**/prompt.py",

    # observability.py: OpenTelemetry setup (infrastructure initialization)
    "src/agent_foundation/utils/observability.py",
]
```

**Rationale for each:**
- **`__init__.py`**: Pure namespace markers with no logic
- **`server.py`**: FastAPI entrypoint with ADK initialization - tested via integration tests in CI/CD
- **`agent.py`**: Pure ADK configuration (plugin registration, model selection) - tested through agent behavior
- **`prompt.py`**: Prompt templates and formatting - tested via agent evaluations, not unit tests
- **`observability.py`**: OpenTelemetry infrastructure setup - validated through trace output, not unit tests

**Pattern:** We exclude configuration and infrastructure initialization files. Business logic and utilities must have 100% coverage.

### Inline Exclusions

**Real example from our codebase:**
```python
# src/agent_foundation/utils/config.py:234
if not isinstance(result, list):  # pragma: no cover
    # Pydantic validation makes this unreachable
    msg = "Invalid allow_origins format"
    raise TypeError(msg)
```

**Why:** The `@field_validator` above this property ensures `result` is always a list. This defensive check exists for static type safety but is unreachable at runtime. Pydantic guarantees it.

**When to use `# pragma: no cover`:**
- Defensive code (provably unreachable) needed to satisfy the static type-checker
- Platform-specific branches not testable in CI (e.g., Windows-only code)
- Error paths that require external system failures (rare)

**When NOT to use it:**
- "This is hard to test" - write better tests or use better code patterns to facilitate testing
- "Coverage is annoying" - coverage is finding gaps as intended
- Normal error handling - always test error paths

## Workflow Integration

### When to Run Checks

**Before every commit:**
```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest --cov
```

**During development:**
- Run `ruff format` and `ruff check --fix` frequently as you code
- Run mypy after adding new functions or changing signatures
- Run tests after behavior changes

**IDE Integration:**
- Configure your editor to run ruff format on save
- Enable mypy real-time checking for immediate feedback
- Use pytest plugin for test execution and debugging

**CI Enforcement:**
All checks run automatically in GitHub Actions on every PR:
- Code quality workflow runs ruff, mypy, pytest
- Blocks merge if any check fails
- Ensures main branch always passes quality gates

### Team Practices

**Test Suite Typing Strategy:**

We disable mypy `arg-type` checking for test files, but maintain strict discipline in `conftest.py`:

```python
# conftest.py - strictly typed even though mypy doesn't enforce it
@pytest.fixture
def mock_state() -> MockState:
    """Create a mock state with test data."""
    return MockState({"user_id": "user123", "session_data": {"key": "value"}})

@pytest.fixture
def mock_content() -> MockContent:
    """Create a mock content with test data."""
    return MockContent({"text": "Hello, agent!"})
```

**Why this works:**
- Test files can pass duck-typed mocks without mypy errors (pragmatic testing)
- `conftest.py` fixtures have clear type contracts (self-documenting, IDE support)
- Best of both worlds: strict where it matters, flexible where it helps

This is a **team practice**, not enforced by tooling. Maintain discipline when writing fixtures.

## Philosophy

### Why These Standards?

**Strict typing (mypy):**
- Catch bugs before runtime
- Enable powerful IDE features
- Document code contracts
- Facilitate safe refactoring

**100% coverage:**
- Confidence in changes
- Forces thinking about edge cases
- Documents all code paths
- Prevents untested code accumulation

**Automated formatting (ruff):**
- Eliminates style debates
- Consistent codebase
- Fast code review
- Auto-fix reduces friction

**Security checks (bandit via ruff):**
- Catch common security mistakes
- Enforce safe defaults
- Educate developers on risks

### When to Add Exclusions

**Never add exclusions:**
- To make broken code pass checks
- Because it's "too much work"
- For personal style preference
- To ship faster without fixing issues

**Acceptable exclusions:**
- Third-party library limitations (document why, add TODO if fixable)
- Tool bugs (add TODO to fix when tool updates)
- Provably unreachable defensive code (rare, requires strong justification)
- Test-specific patterns (e.g., assert in tests, mock credentials)

**Best practices:**
1. **Be specific:** Use rule codes (`# noqa: S105`) not blanket suppression (`# noqa`)
2. **Document why:** Add comment explaining the exclusion
3. **Add TODOs:** If it's a workaround, plan to fix it later
4. **Review regularly:** Remove exclusions when underlying issue is fixed

**Always prefer fixing the issue over adding exclusions.**

---

← [Back to References](README.md) | [Documentation](../README.md)
