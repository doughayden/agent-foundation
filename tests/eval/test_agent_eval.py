"""Gate-fidelity eval runner for the template root agent.

Runs stock ``AgentEvaluator`` against the shipped eval set. The agent performs
real model inference; the ``App`` (and its plugins) is applied via the
App-aware eval patch (``agent_foundation._eval_app_aware_patch``), so these
runs score the same agent adk web chat and the deployed server run.

Two gates share the eval set:

- Deterministic (``test_config.json``, auto-discovered from the eval set's
  directory): exact tool-trajectory matching and ROUGE-1 response overlap, no
  LLM judge. This is the CI PR gate.
- Judge (``full_eval_config.json``, loaded explicitly): adds LLM-judge and
  safety metrics whose ``app_details`` context is populated in-process by the
  App-aware patch. This is the CI merge gate, run by ``judge-eval.yml``.

Both gates run the agent with live model inference, so both need real
credentials; the judge gate additionally calls the Gen AI evaluation service.

Both use ``AgentEvaluator``, which raises ``AssertionError`` on sub-threshold
metrics, so a pytest failure IS the gate. The ``adk eval`` CLI renders the same
eval set for interactive authoring but exits 0 even when cases fail, so it
cannot gate CI.

Preflight liveness tests make one minimal live call per model role before the gates run.
ADK silently drops inference-failed cases from scoring, so without them a totally
unreachable endpoint passes vacuously over an empty metric set (issue #229).
``test_liveness_agent_model`` probes the agent's inference model (both gates run
the agent); ``test_liveness_judge_model`` probes each autorater in the judge
config (``judge`` gate only). Each probe reads its role's own source of truth, so
changing a model re-points the matching probe automatically.

A failed probe arms ``session.shouldfail`` (the knob ``-x`` sets), so the lane
aborts before the paid ``AgentEvaluator`` tests run instead of grinding every
case against a dead endpoint. This keeps fail-fast in the module: ``maxfail`` via
``pytest_configure`` would need a ``conftest.py``, which this lane deliberately
omits. The liveness tests are defined before the eval tests so the abort lands
before any inference.

What a run scores is fixed in this module, not passed in: the file paths and run
counts below are plain constants. A consumer changing what is evaluated is already
editing ``tests/eval/data/``, so the values live one file away rather than behind
workflow inputs and environment variables.

Run with ``uv run pytest tests/eval`` (real credentials and LLM cost). It lives
under ``tests/eval/`` and exercises the live model.
"""

import importlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_set import EvalSet
from google.adk.models import LLMRegistry, LlmRequest
from google.genai import types

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# The agent module is the package directory under src/. The template has exactly one
# package there, so the lone dir with an __init__.py is unambiguous; the marker skips
# non-package entries (.DS_Store, *.egg-info). Discovered rather than hard-coded so a
# downstream fork that renames the package runs this gate with no edits. ADK loads the
# agent purely from this module; a case's ``session_input.app_name`` name-scopes the
# eval session and the Runner but does not select the agent.
SRC_DIR = Path(__file__).parents[2] / "src"
AGENT_MODULE = next(SRC_DIR.glob("*/__init__.py")).parent.name

EVAL_SET_FILE = DATA_DIR / "template_agent.evalset.json"
JUDGE_CONFIG_FILE = DATA_DIR / "full_eval_config.json"

# Times each case is run and averaged, per gate. The judge metrics return a binary
# verdict per run, so at 2 every threshold above 0.5 would demand unanimity and read
# as more tolerant than it is; 5 gives the average enough resolution for the shipped
# thresholds to mean what they say. Read that as "four of the five runs that produced
# a score": ADK drops a run whose metric evaluation errored rather than counting it as
# a miss. The deterministic gate keeps 2 because exact trajectory matching wants
# unanimity anyway and ROUGE scores continuously. ADK runs these serially, so the
# judge gate costs proportionally more wall clock.
DETERMINISTIC_NUM_RUNS = 2
JUDGE_NUM_RUNS = 5

# Exit code for "the judge eval could not run", as opposed to pytest's 1 for "a test
# failed". `judge-eval.yml` treats 1 as a sub-threshold score its `gating` input may
# absorb, so a lane error has to leave through a different door or a broken gate would
# report as a behavioral regression and pass in dev-only mode. Any value outside
# pytest's own 0-5 works; the workflow only tests for 0 and 1.
EVAL_ERROR_EXIT_CODE = 6

LIVENESS_PROMPT = "pls respond with a single 'ready' to confirm you're able to respond"
LIVENESS_MAX_OUTPUT_TOKENS = 16


def _judge_models(config_data: dict[str, Any]) -> list[str]:
    """Distinct autorater models an eval config's judge criteria call.

    Read from the config data the judge gate actually loads, so changing a
    ``judge_model`` in the JSON re-points the liveness probe with no code edit.

    Reads explicit ``judge_model`` entries only. A criterion relying on ADK's
    default autorater (no ``judge_model_options``, or none naming a model) is not
    probed, and a config where no criterion names one yields an empty list, which
    ``pytest.mark.parametrize`` turns into a skipped ``test_liveness_judge_model``
    rather than a failure. The #229 preflight is therefore only as complete as the
    config is explicit; ``full_eval_config.json`` names a model on every judge
    criterion, so keep naming it when adding one.
    """
    criteria = config_data["criteria"]
    models = sorted(
        {
            opts["judge_model"]
            for metric in criteria.values()
            if isinstance(metric, dict)
            and isinstance(opts := metric.get("judge_model_options"), dict)
            and opts.get("judge_model")
        }
    )
    logger.debug(f"Resolved judge models: {models}")
    return models


JUDGE_CONFIG_DATA = json.loads(JUDGE_CONFIG_FILE.read_text())
JUDGE_MODELS = _judge_models(JUDGE_CONFIG_DATA)
# Validated at import so a malformed config fails at collection rather than part-way
# through a paid judge run. Structural only: ADK validates dict criteria to base
# `BaseCriterion`, which allows extras, so a misspelled metric name or a bad
# `judge_model_options` still surfaces from the metric registry mid-run.
JUDGE_EVAL_CONFIG = EvalConfig.model_validate(JUDGE_CONFIG_DATA)


@pytest.fixture(scope="session", autouse=True)
def load_env() -> None:
    """Load the real ``.env`` for live inference (a no-op in CI)."""
    load_dotenv()


async def _assert_model_live(session: pytest.Session, model: str) -> None:
    """Fail if ``model`` can't be resolved or its endpoint doesn't answer.

    Resolution, request construction, and the live call all run inside the
    ``try`` so any failure (bad model string, registry miss, dead endpoint)
    arms ``session.shouldfail`` (the knob ``-x`` sets) so the lane
    aborts before the paid ``AgentEvaluator`` tests run — the eval is meaningless
    against a dead endpoint, and this keeps fail-fast in the module rather than in
    a command flag or a ``conftest.py`` this lane omits.

    One minimal live call resolved the same way ADK resolves a model string
    (``LLMRegistry``). Thinking is disabled so the low output cap yields a text
    reply instead of being spent on ``gemini-2.5-flash`` thinking tokens. This
    assumes a registry-resolvable model string; a fork that swaps a role to a
    connector instance (LiteLlm/Claude/Apigee) must call that instance directly.
    """

    def _abort(reason: str) -> None:
        session.shouldfail = "eval aborted: model endpoint liveness check failed"
        pytest.fail(reason)

    try:
        llm = LLMRegistry.new_llm(model)
        llm_request = LlmRequest(
            model=model,
            contents=[types.UserContent(LIVENESS_PROMPT)],
            config=types.GenerateContentConfig(
                max_output_tokens=LIVENESS_MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        responses = [resp async for resp in llm.generate_content_async(llm_request)]
    except Exception as exc:
        _abort(f"Model endpoint check failed for {model!r}: {exc!r}")

    errors = [
        f"{resp.error_code}: {resp.error_message}"
        for resp in responses
        if resp.error_code
    ]
    if errors:
        _abort(f"Model endpoint returned an error for {model!r}: {errors}")

    reply = "".join(
        part.text
        for resp in responses
        if resp.content and resp.content.parts
        for part in resp.content.parts
        if part.text
    )
    if not reply:
        _abort(f"Model endpoint for {model!r} returned no text: {responses!r}")

    logger.info(f"Model endpoint live for {model}: {reply}")


@pytest.mark.liveness
@pytest.mark.deterministic
@pytest.mark.judge
async def test_liveness_agent_model(request: pytest.FixtureRequest) -> None:
    """Preflight: the agent's inference model answers (both gates run the agent).

    ADK swallows per-case inference failures (403/quota/network/model-rename),
    sets ``inferences=None``, and drops the case from scoring, so a dead endpoint
    lets ``AgentEvaluator`` pass over an empty metric set (issue #229). ADK's
    per-case partial tolerance is preserved: only an unreachable model fails here.

    The model is read from the agent (``ROOT_AGENT_MODEL``) rather than restated,
    so an LLM swap can't leave this probing a model the eval no longer runs.
    """
    model = importlib.import_module(f"{AGENT_MODULE}.agent").ROOT_AGENT_MODEL
    await _assert_model_live(request.session, model)


@pytest.mark.liveness
@pytest.mark.judge
@pytest.mark.parametrize("model", JUDGE_MODELS)
async def test_liveness_judge_model(request: pytest.FixtureRequest, model: str) -> None:
    """Preflight: each autorater in the judge config answers (``judge`` gate only).

    Parametrized from ``full_eval_config.json`` at collection, so changing a
    ``judge_model`` re-points this probe automatically. The deterministic gate's
    ``test_config.json`` declares no judge model, so nothing extra runs there.
    """
    await _assert_model_live(request.session, model)


@pytest.mark.deterministic
async def test_template_agent_deterministic_eval() -> None:
    """PR-gate deterministic eval criteria.

    Criteria come from the ``test_config.json`` ADK auto-discovers beside the eval
    set, not from this module.
    """
    await AgentEvaluator.evaluate(
        agent_module=AGENT_MODULE,
        eval_dataset_file_path_or_dir=str(EVAL_SET_FILE),
        num_runs=DETERMINISTIC_NUM_RUNS,
    )


@pytest.mark.judge
async def test_template_agent_judge_eval() -> None:
    """LLM-judged eval criteria.

    ``AgentEvaluator`` signals a sub-threshold score with ``AssertionError``, which is
    the gate's verdict and propagates normally. Anything else it raises means the eval
    did not run (a missing eval extra, an empty dataset, an eval-service error), so it
    leaves through ``EVAL_ERROR_EXIT_CODE`` instead. Both are pytest exit 1 otherwise,
    and ``judge-eval.yml`` lets its ``gating`` input absorb exit 1.
    """
    eval_set = EvalSet.model_validate_json(EVAL_SET_FILE.read_text())
    try:
        await AgentEvaluator.evaluate_eval_set(
            agent_module=AGENT_MODULE,
            eval_set=eval_set,
            eval_config=JUDGE_EVAL_CONFIG,
            num_runs=JUDGE_NUM_RUNS,
        )
    except AssertionError:
        raise
    except Exception as exc:
        pytest.exit(
            reason=f"Judge eval could not run: {exc!r}",
            returncode=EVAL_ERROR_EXIT_CODE,
        )
