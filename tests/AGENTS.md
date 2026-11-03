# AGENTS.md: Tests

Rules for writing and changing tests under `tests/`. Consumer-owned: forks add tests freely. The eval-gate internals below (`_gate`, liveness, failure reporting) are **Template Internals**. Rules that apply before you open a test file (lane commands, coverage, eval cost, no root conftest) live in the root `AGENTS.md` Testing Patterns.

## Lanes

A test's lane = runtime requirements + determinism. Lanes select by explicit path; `testpaths = ["tests/unit"]` keeps a bare `pytest` off Postgres. Only `unit` carries the `--cov` 100% gate. Credential posture is per lane (`docs/references/testing.md` Directory Structure).

## Eval Lane

Full surface: `docs/references/agent-evals.md`.

- **Runner:** pytest calling `AgentEvaluator.evaluate_eval_set` is the only gate runner. **NEVER gate CI on `adk eval`** (exits 0 on failed cases, authoring only)
- **Gates:** `deterministic` = PR gate (`test_config.json`, `ci.yml` `agent-eval`); `judge` = merge gate (`full_eval_config.json`, `judge-eval.yml`, blocking only in production mode). Both run live inference with real Vertex creds. Never put deterministic criteria in `full_eval_config.json`
- **NO run knobs:** eval set, configs and run counts are module constants in `tests/eval/test_agent_eval.py`; never add workflow inputs or env overrides
- **A judge threshold is not the number you typed** (resolution = `rubrics x num_runs x invocations`; rubric subsidy floors at `(R-1)/R`): recompute effective thresholds when adding a rubric, a run or a multi-turn case, using "How a judge score is built" (do not re-derive)
- **Judge config:** `judge_model` and `http_options.timeout` explicit on every criterion; ADK sampling defaults, never `temperature: 0` plus a vote. `JUDGE_MODEL` in `tests/unit/test_pinned_versions.py` pins every judge and simulator model (bump together); never couple it to `ROOT_AGENT_MODEL`
- **Gate integrity (Template Internals):** `_gate` turns unscored runs and non-assertion errors into `EVAL_ERROR_EXIT_CODE`, so exit 1 means only a scored sub-threshold verdict; liveness probes run first as their own always-blocking step ("The CI gates", "What each gate proves")
- **Failure reporting (Template Internals):** native pytest only. **NEVER `pytest.exit` or `capsys`**; never drive `AgentEvaluator` underscore methods or run `adk eval` beside the gate. Pass `-s` on every eval command
- **Stress-test by looping the command**, not by raising `num_runs`
- `tests/unit/test_eval_gate.py` covers the gate offline; keep it in the unit lane. `agent.py` must keep exporting `app` (App-aware evals). Cross-session memory is not eval-testable

## Smoke Lane

Post-deploy only (`smoke.yml`, called from `ci-cd.yml` after each env apply), never in `ci.yml`. Single module, no conftest, real creds; authenticates by impersonating the invoker SA in-process for an OIDC ID token (no token through env). Layers, auth, and CI wiring: `docs/references/smoke-tests.md`.

## Conftests and pytest_configure()

**pytest_configure()** - the only place using `unittest.mock` (runs before pytest-mock exists); mocks Google auth before collection and sets no env vars (if one is ever needed: `os.environ["KEY"] = "value"`, never `setdefault()`). Detail: `docs/references/testing.md` pytest_configure().

Lane conftests are allowed (only a ROOT `tests/conftest.py` is forbidden): integration holds ONLY Docker setup, eval ONLY the exit-status hook (`docs/references/integration-tests.md` Run it locally). Keep those docs runtime-agnostic: describe the context/socket mechanism, never a specific runtime or local shim.

## Fixtures and Mocks

- Type hints: `MockerFixture` → `MockType` return (mypy-enforced in `conftest.py`). Annotate `mocker.Mock(...)` before returning it (`x: MockType = mocker.Mock(...)`), since mypy infers `Any`
- Factory pattern (not context managers): `def _factory() -> MockType` returned by fixture
- Environment mocking: `mocker.patch.dict(os.environ, env_dict)`
- Test functions: Don't type hint custom fixtures, optional hints on built-ins for IDE
- Naming: `Mock` prefix for test double classes (e.g., `MockState`); `mock_xxx` for instance fixtures; `create_mock_xxx` for factory fixtures returning `Callable`; no prefix for convenience fixtures returning real objects (e.g., `oauth_flow_config`); factory inner function named `_factory`

**ADK Mocks:** Custom mocks mirror real ADK interfaces and live in `tests/unit/conftest.py` (readonly contexts, callback contexts, tool contexts, LLM request/response shapes, etc.). For edge cases requiring custom internal structure, add a specific named fixture.

**Mock Usage:** Never import mock classes directly in test files — always use or add a fixture in `conftest.py`.

## Organization

Test module path mirrors source path (`src/<pkg>/config.py` → `tests/unit/test_config.py`); nested source paths flatten with underscores (`<pkg>/sub/foo.py` → `test_sub_foo.py`). Duplicate cross-lane values per lane instead of sharing them (no root conftest). Class grouping. Descriptive names (`test_<what>_<condition>_<expected>`).

**Package-name discovery:** Lanes resolve the package at runtime (`next(SRC_DIR.glob("*/__init__.py")).parent.name`) instead of hard-coding it — unit `conftest.py`, integration `APP_NAME`, eval `AGENT_MODULE` — so a renamed fork reuses every lane unedited. **Do not wrap the bare `next()`** (intentional fail-fast on the single-package invariant) and **do not centralize it** (duplicated per lane by design). Rationale: `docs/references/testing.md` Package-Name Discovery.

## Writing Tests

**Validation:** Pydantic `@field_validator` (validate at model creation). Tests expect `ValidationError` at `model_validate()`, not at property access. Property simplified with `# pragma: no cover` for impossible edge cases.

**Mypy scope:** strict over `src/` and `tests/`; `tests.*` relaxes ONLY `arg-type`, `no-untyped-def`, `no-untyped-call` (conftests re-enable the latter two). Patch via `mocker.patch.object`, never assignment. Override mechanics and test-typing rules: `docs/references/code-quality.md` Test Suite Typing Strategy.

**Coverage:** Test behaviors (errors, edge cases, return values, logging), not just statements. Exclusions defined in `pyproject.toml`.

**Parameterization:** Thoughtfully. Inline loops OK for documenting complex behavior (e.g., boolean field parsing).

**ADK patterns:**
- **InstructionProvider:** Function `def fn(ctx: ReadonlyContext) -> str`. Pass function ref (not called) to `GlobalInstructionPlugin(fn)`. Plugin calls at runtime. Test with `MockReadonlyContext`.
- **Async callbacks:** `asyncio_mode = "auto"` in pyproject.toml, verify caplog.
- **Controlled errors:** `MockMemoryCallbackContext(should_raise, error_message)`.
