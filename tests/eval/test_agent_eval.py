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

Run with ``uv run pytest tests/eval`` (real credentials and LLM cost). It lives
under ``tests/eval/`` and exercises the live model.
"""

from pathlib import Path

import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_config import get_evaluation_criteria_or_default
from google.adk.evaluation.eval_set import EvalSet

DATA_DIR = Path(__file__).parent / "data"

# The agent module is the package directory under src/. The template has exactly one
# package there, so the lone dir with an __init__.py is unambiguous; the marker skips
# non-package entries (.DS_Store, *.egg-info). Discovered rather than hard-coded so a
# downstream fork that renames the package runs this gate with no edits. ADK loads the
# agent purely from this module; the ``app_name`` in the eval data is a dummy ADK
# ignores during inference.
SRC_DIR = Path(__file__).parents[2] / "src"
AGENT_MODULE = next(SRC_DIR.glob("*/__init__.py")).parent.name

EVAL_SET_FILE = DATA_DIR / "template_agent.evalset.json"
JUDGE_CONFIG_FILE = DATA_DIR / "full_eval_config.json"

NUM_RUNS = 2


@pytest.fixture(scope="session", autouse=True)
def load_env() -> None:
    """Load the real ``.env`` for live inference (a no-op in CI)."""
    load_dotenv()


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
