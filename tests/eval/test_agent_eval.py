"""Gate-fidelity eval runner for the template root agent.

Runs stock ``AgentEvaluator`` against the shipped eval set. The agent performs
real model inference; ADK builds the eval runner from the module's ``App`` (and
its plugins), so these runs score the same agent adk web chat and the deployed
server run.

Two gates share the eval set:

- Deterministic (``test_config.json``): exact tool-trajectory matching and
  ROUGE-1 response overlap, no LLM judge. This is the CI PR gate. The file sits
  beside the eval set, where ``adk eval`` and the adk web eval tab also find it.
- Judge (``full_eval_config.json``): adds LLM-judge and safety metrics whose
  ``app_details`` context is populated in-process from the ``App``. This is the
  CI merge gate, run by ``judge-eval.yml``.

Both configs are loaded explicitly and both gates call
``AgentEvaluator.evaluate_eval_set`` the same way, through ``_gate``.

Both gates run the agent with live model inference, so both need real
credentials; the judge gate additionally calls the Gen AI evaluation service.

Both use ``AgentEvaluator``, which raises ``AssertionError`` on sub-threshold
metrics, so a pytest failure IS the gate. The ``adk eval`` CLI renders the same
eval set for interactive authoring but exits 0 even when cases fail, so it
cannot gate CI.

ADK's verdict alone does not prove every run was scored. It isolates a failed
metric evaluation by recording no score for that run and then averages only the
scores that exist, so a threshold can be decided by the surviving runs; inside a
rubric metric, a rubric the judge never scored drops out the same way. It also
reports a run whose inference failed through the same ``AssertionError`` as a
low score. Both gates therefore capture every run's results and leave through
``EVAL_ERROR_EXIT_CODE`` when any run went unscored, keeping exit 1 for a
sub-threshold verdict over fully scored runs (issue #240). The gate fails its test
normally with the cause chained, so pytest's report carries the traceback and the
captured logs that hold the reason a run went unscored, and the lane's
``conftest.py`` sets the session's exit code. Run with ``-s`` to stream ADK's
output (the logging plugin, progress bars, results tables) as it happens.

Preflight liveness tests make one minimal live call per model role before the gates run.
An unreachable model would otherwise fail every run of every case before
reporting; the probes fail in seconds instead, and outside the scored step, so
``judge-eval.yml``'s ``gating`` input never sees that failure.
``test_liveness_agent_model`` probes the agent's inference model (both gates run
the agent); ``test_liveness_judge_model`` probes each autorater in the judge
config (``judge`` gate only). Each probe reads its role's own source of truth, so
changing a model re-points the matching probe automatically.

A failed probe arms ``session.shouldfail`` (the knob ``-x`` sets), so the lane
aborts before the paid ``AgentEvaluator`` tests run instead of grinding every
case against a dead endpoint. The abort stays next to the probes rather than in
the lane conftest, which holds only the exit-code hook. The liveness tests are
defined before the eval tests so the abort lands before any inference.

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
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_metrics import EvalMetricResult, EvalStatus
from google.adk.evaluation.eval_result import EvalCaseResult, EvalSetResult
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.eval_set_results_manager import EvalSetResultsManager
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
DETERMINISTIC_CONFIG_FILE = DATA_DIR / "test_config.json"
JUDGE_CONFIG_FILE = DATA_DIR / "full_eval_config.json"

# Times each case is run and averaged, per gate. ADK means the per-invocation scores of
# every run together, so judge scores land on multiples of 1/(rubrics x num_runs x
# invocations) and a threshold between two of them silently rounds up to the next
# achievable score. The gate case is single-turn (one invocation), so what is left to
# tune here is the run count: 5 puts the shipped thresholds on achievable scores, where
# 2 would make a single-rubric metric demand unanimity. A run with a missing score never
# shrinks that denominator: `_gate` rejects the eval instead. The deterministic gate
# keeps 2 because exact trajectory matching wants unanimity anyway and ROUGE-1 is
# finely spaced (not continuous: its denominator counts the response's tokens, so it
# shifts per run at token scale). ADK runs these serially, so the judge gate costs
# proportionally more wall clock.
# Threshold arithmetic: docs/references/agent-evals.md, "How a judge score is built".
DETERMINISTIC_NUM_RUNS = 2
JUDGE_NUM_RUNS = 5

# Exit code for "the eval could not run or left runs unscored", as opposed to pytest's 1
# for "a test failed". Both gates use it. `judge-eval.yml` treats 1 as a sub-threshold
# score its `gating` input may absorb, so a broken eval has to leave through a different
# door or it would report as a behavioral regression and pass in dev-only mode. Any
# value outside pytest's own 0-5 works; the workflow only tests for 0 and 1.
EVAL_ERROR_EXIT_CODE = 6

LIVENESS_PROMPT = "pls respond with a single 'ready' to confirm you're able to respond"
LIVENESS_MAX_OUTPUT_TOKENS = 64
LIVENESS_TIMEOUT_MS = 60_000


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
# Configs and the eval set are validated at import, so malformed eval data fails at
# collection (in CI, the always-blocking preflight step) instead of reading as a score
# verdict part-way through a paid run. Structural only: ADK validates dict criteria to
# base `BaseCriterion`, which allows extras, so a misspelled metric name or a bad
# `judge_model_options` still surfaces from the metric registry mid-run.
JUDGE_EVAL_CONFIG = EvalConfig.model_validate(JUDGE_CONFIG_DATA)
DETERMINISTIC_EVAL_CONFIG = EvalConfig.model_validate(
    json.loads(DETERMINISTIC_CONFIG_FILE.read_text())
)
EVAL_SET = EvalSet.model_validate_json(EVAL_SET_FILE.read_text())


@pytest.fixture(scope="session", autouse=True)
def load_env() -> None:
    """Load the real ``.env`` for live inference (a no-op in CI)."""
    load_dotenv()


async def _assert_model_live(session: pytest.Session, model: str) -> None:
    """Fail if ``model`` can't be resolved or its endpoint doesn't answer.

    Resolution, request construction, and the live call all run inside the
    ``try`` so any failure (bad model string, registry miss, dead endpoint,
    a call exceeding ``LIVENESS_TIMEOUT_MS``) arms ``session.shouldfail`` (the
    knob ``-x`` sets) so the lane aborts before the paid ``AgentEvaluator`` tests
    run — the eval is meaningless against a dead endpoint, and this keeps
    fail-fast next to the probes rather than in a command flag.

    One minimal live call resolved the same way ADK resolves a model string
    (``LLMRegistry``). Thinking is set to ``MINIMAL`` so the output cap yields a
    text reply instead of being spent on thinking tokens (at ``LOW``,
    ``gemini-3.5-flash`` hits ``MAX_TOKENS`` before replying). Accepted levels
    vary by model: ``gemini-3.8-flash`` rejects ``MINIMAL`` with a 400, so a fork
    that swaps a probed model must re-check this level. The
    request timeout turns a hung endpoint into a fast abort instead of a job
    that waits out its own timeout. This assumes a registry-resolvable model
    string; a fork that swaps a role to a connector instance
    (LiteLlm/Claude/Apigee) must call that instance directly.
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
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
                http_options=types.HttpOptions(timeout=LIVENESS_TIMEOUT_MS),
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

    A dead endpoint would fail every run of every case, but only after paying for
    each attempt; this fails in seconds instead, and in CI outside the scored step,
    so ``judge-eval.yml``'s ``gating`` input never sees it. Runs that fail for other
    reasons are the unscored-run check's job (``_gate``).

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


class _CapturingEvalSetResultsManager(EvalSetResultsManager):
    """Keeps every run's ``EvalCaseResult`` in memory so a gate can inspect it.

    ADK saves results before raising its threshold ``AssertionError``, so the capture
    holds on passing and failing evals alike. In memory rather than ADK's local file
    manager, which writes into the workspace and double-encodes its JSON
    (google/adk-python#3993). The eval path calls only ``save_eval_set_result``; the
    read methods serve ``adk web``'s eval history, which never sees this manager.
    """

    def __init__(self) -> None:
        self.eval_case_results: list[EvalCaseResult] = []

    def save_eval_set_result(
        self,
        app_name: str,
        eval_set_id: str,
        eval_case_results: list[EvalCaseResult],
    ) -> None:
        self.eval_case_results.extend(eval_case_results)

    def get_eval_set_result(
        self, app_name: str, eval_set_result_id: str
    ) -> EvalSetResult:
        raise NotImplementedError

    def list_eval_set_results(self, app_name: str) -> list[str]:
        raise NotImplementedError


def _is_gating(metric: EvalMetricResult) -> bool:
    """Whether ADK counts ``metric`` toward its verdict.

    Mirrors ``AgentEvaluator``'s own rule: a metric gates unless it is
    ``INFORMATIONAL`` or carries neither a threshold nor a criterion. The second
    half matters when an auto-added efficiency metric crashes, since ADK then
    reports it as not evaluated rather than informational. A unit test checks this
    rule against the metrics ADK actually builds for both gate configs, so a change
    to how ADK builds them fails the unit lane.
    """
    return metric.eval_status != EvalStatus.INFORMATIONAL and not (
        metric.threshold is None and metric.criterion is None
    )


def _is_scored(score: float | None) -> bool:
    """A score exists and is a number (NaN is how some evaluators say "no score")."""
    return score is not None and not math.isnan(score)


def _unjudged_rubrics(metric: EvalMetricResult) -> list[str]:
    """Rubric ids configured on ``metric`` that its run result has no score for.

    A rubric metric's run score is the mean of every rubric verdict from every judge
    sample, skipping verdicts that never arrived. A rubric missing from every sample
    therefore drops out, and the score rests on the remaining rubrics while looking
    complete. A rubric missing from only some samples still has a score from the
    rest; that is fewer votes, not an unjudged rubric.
    """
    rubrics = getattr(metric.criterion, "rubrics", None) or []
    configured = [
        rubric["rubric_id"] if isinstance(rubric, dict) else rubric.rubric_id
        for rubric in rubrics
    ]
    judged = {
        rubric_score.rubric_id
        for rubric_score in metric.details.rubric_scores or []
        if _is_scored(rubric_score.score)
    }
    return [rubric_id for rubric_id in configured if rubric_id not in judged]


def _unscored_runs(eval_case_results: list[EvalCaseResult]) -> list[str]:
    """Describe each run that did not score every gating metric.

    Each ``EvalCaseResult`` is one run of one case. A run is unscored when it
    produced no metric results at all (its inference failed), when a gating
    metric's overall score for that run is missing or NaN, or when a rubric metric
    has no score for one of its configured rubrics. A missing score means the
    metric's evaluation raised or it found nothing to score in that run (like a
    groundedness metric on a reply with no text); the captured result cannot tell
    those apart, and both leave the threshold resting on the other runs, so both
    fail. The check reads each run's overall score per metric rather than its
    per-invocation scores. Capturing nothing at all counts as unscored too, since
    there is then no evidence behind a verdict.

    A run is named by its eval session: ADK saves results in completion order and
    gives them no run number, while each run has its own session unless the case
    pins ``session_input.session_id``, which every run of that case then shares.
    """
    if not eval_case_results:
        return ["no eval results were captured"]
    unscored = []
    for case in eval_case_results:
        label = f"{case.eval_id} (session {case.session_id})"
        if not case.overall_eval_metric_results:
            unscored.append(f"{label}: produced no metric results")
            continue
        for metric in filter(_is_gating, case.overall_eval_metric_results):
            if not _is_scored(metric.score):
                unscored.append(f"{label}: {metric.metric_name} was not scored")
                continue
            unscored.extend(
                f"{label}: {metric.metric_name} rubric {rubric_id} was not judged"
                for rubric_id in _unjudged_rubrics(metric)
            )
    return unscored


async def _gate(
    eval_config: EvalConfig,
    num_runs: int,
    set_exit_status: Callable[[int], None],
) -> None:
    """Run the eval set and keep ADK's verdict only over fully scored runs.

    ``AssertionError`` is ADK's verdict on the scores. It propagates only when every
    run was scored. An unscored run means the verdict rests on partial evidence, and
    any other exception means the eval did not run; both fail the test with the
    cause chained, so pytest's report carries the traceback, captured logs (ADK logs
    each failed metric evaluation there), and stdout, and both set the session's
    exit code to ``EVAL_ERROR_EXIT_CODE`` through the lane conftest. pytest reports
    every plain failure as exit 1, which ``judge-eval.yml`` lets its ``gating``
    input absorb. Whether an unscored run should warn instead is a policy choice;
    the template fails.
    """
    results_manager = _CapturingEvalSetResultsManager()
    verdict: AssertionError | None = None
    try:
        await AgentEvaluator.evaluate_eval_set(
            agent_module=AGENT_MODULE,
            eval_set=EVAL_SET,
            eval_config=eval_config,
            num_runs=num_runs,
            app_name=AGENT_MODULE,
            eval_set_results_manager=results_manager,
        )
    except AssertionError as exc:
        verdict = exc
    except Exception as exc:
        set_exit_status(EVAL_ERROR_EXIT_CODE)
        raise pytest.fail.Exception("Eval could not run.") from exc

    unscored = _unscored_runs(results_manager.eval_case_results)
    if unscored:
        set_exit_status(EVAL_ERROR_EXIT_CODE)
        raise pytest.fail.Exception(
            f"Eval verdict rests on unscored runs: {unscored}"
        ) from verdict
    if verdict is not None:
        raise verdict


@pytest.mark.deterministic
async def test_template_agent_deterministic_eval(
    set_exit_status: Callable[[int], None],
) -> None:
    """PR-gate deterministic eval criteria from ``test_config.json``."""
    await _gate(DETERMINISTIC_EVAL_CONFIG, DETERMINISTIC_NUM_RUNS, set_exit_status)


@pytest.mark.judge
async def test_template_agent_judge_eval(
    set_exit_status: Callable[[int], None],
) -> None:
    """LLM-judged eval criteria, run by ``judge-eval.yml`` as the merge gate."""
    await _gate(JUDGE_EVAL_CONFIG, JUDGE_NUM_RUNS, set_exit_status)
