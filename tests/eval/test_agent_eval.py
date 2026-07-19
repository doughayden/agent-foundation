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
  App-aware patch. Runs locally; its own WIF->Vertex CI job is future work.

Both gates run the agent with live model inference, so both need real
credentials; the judge gate additionally calls the Gen AI evaluation service.

Both use ``AgentEvaluator``, which raises ``AssertionError`` on sub-threshold
metrics, so a pytest failure IS the gate. The ``adk eval`` CLI renders the same
eval set for interactive authoring but exits 0 even when cases fail, so it
cannot gate CI.

Preflight liveness tests make one minimal live call per model role before the
gates run. ADK silently drops inference-failed cases from scoring, so without
them a totally unreachable endpoint passes vacuously over an empty metric set
(issue #229). ``test_liveness_agent_model`` probes the agent's inference model
(both gates run the agent); ``test_liveness_judge_model`` probes each autorater
in the judge config (``judge`` gate only). Each probe reads its role's own
source of truth, so changing a model re-points the matching probe automatically.

A failed probe arms ``session.shouldfail`` (the knob ``-x`` sets), so the lane
aborts before the paid ``AgentEvaluator`` tests run instead of grinding every
case against a dead endpoint. This keeps fail-fast in the module: ``maxfail`` via
``pytest_configure`` would need a ``conftest.py``, which this lane deliberately
omits. The liveness tests are defined before the eval tests so the abort lands
before any inference.

Run with ``uv run pytest tests/eval`` (real credentials and LLM cost). It lives
under ``tests/eval/`` and exercises the live model.
"""

import importlib
import json
import logging
from pathlib import Path

import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_config import get_evaluation_criteria_or_default
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

NUM_RUNS = 2

LIVENESS_PROMPT = "pls respond with a single 'ready' to confirm you're able to respond"
LIVENESS_MAX_OUTPUT_TOKENS = 16


def _judge_models(config_file: Path) -> list[str]:
    """Distinct autorater models an eval config's judge criteria call.

    Read from the config file the judge gate actually loads, so changing a
    ``judge_model`` in the JSON re-points the liveness probe with no code edit.
    Reads explicit ``judge_model`` entries only; a criterion that relies on
    ADK's default autorater (no ``judge_model_options``) is not probed.
    """
    criteria = json.loads(config_file.read_text())["criteria"]
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


JUDGE_MODELS = _judge_models(JUDGE_CONFIG_FILE)


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

    logger.info("Model endpoint live for %s: %r", model, reply)


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
    """PR-gate deterministic eval criteria."""
    await AgentEvaluator.evaluate(
        agent_module=AGENT_MODULE,
        eval_dataset_file_path_or_dir=str(EVAL_SET_FILE),
        num_runs=NUM_RUNS,
    )


@pytest.mark.judge
async def test_template_agent_judge_eval() -> None:
    """LLM-judged eval criteria."""
    eval_config = get_evaluation_criteria_or_default(str(JUDGE_CONFIG_FILE))
    eval_set = EvalSet.model_validate_json(EVAL_SET_FILE.read_text())
    await AgentEvaluator.evaluate_eval_set(
        agent_module=AGENT_MODULE,
        eval_set=eval_set,
        eval_config=eval_config,
        num_runs=NUM_RUNS,
    )
