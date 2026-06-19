"""Gate-fidelity eval runner for the template root agent.

Runs ``AgentEvaluator.evaluate()`` against the deterministic criteria in
``eval/data/test_config.json`` (auto-discovered from the eval set's
directory). The agent performs real model inference, but the metrics are
deterministic: exact tool-trajectory matching and ROUGE-1 response overlap,
no LLM judge.

This pytest entry point is the CI gate because ``AgentEvaluator.evaluate()``
raises ``AssertionError`` on sub-threshold metrics. The ``adk eval`` CLI
renders the same eval set for interactive authoring but exits 0 even when
cases fail, so it cannot gate CI.

Run with ``uv run pytest eval`` (real credentials and LLM cost). It lives in the
top-level ``eval/`` directory and exercises the live model.
"""

from pathlib import Path

import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator

DATA_DIR = Path(__file__).parent / "data"

# The agent module is the package directory under src/. The template has exactly one
# package there, so the lone dir with an __init__.py is unambiguous; the marker skips
# non-package entries (.DS_Store, *.egg-info). Discovered rather than hard-coded so a
# downstream fork that renames the package runs this gate with no edits. ADK loads the
# agent purely from this module; the ``app_name`` in the eval data is a dummy ADK
# ignores during inference.
SRC_DIR = Path(__file__).parents[1] / "src"
AGENT_MODULE = next(SRC_DIR.glob("*/__init__.py")).parent.name

NUM_RUNS = 2


@pytest.fixture(scope="session", autouse=True)
def load_env() -> None:
    """Load the real ``.env`` for live inference (a no-op in CI)."""
    load_dotenv()


async def test_template_agent_deterministic_eval() -> None:
    """Template agent passes the deterministic PR-gate eval criteria."""
    await AgentEvaluator.evaluate(
        agent_module=AGENT_MODULE,
        eval_dataset_file_path_or_dir=str(DATA_DIR / "template_agent.evalset.json"),
        num_runs=NUM_RUNS,
    )
