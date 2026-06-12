"""Gate-fidelity eval runner for the template root agent.

Runs ``AgentEvaluator.evaluate()`` against the deterministic criteria in
``tests/eval/data/test_config.json`` (auto-discovered from the eval set's
directory). The agent under test performs real model inference, but the
metrics themselves are deterministic — exact tool-trajectory matching and
ROUGE-1 response overlap, no LLM judge.

This pytest entry point is the CI gate because ``AgentEvaluator.evaluate()``
raises ``AssertionError`` on sub-threshold metrics. The ``adk eval`` CLI
renders the same eval set for interactive authoring but exits 0 even when
cases fail (verified against google-adk 2.2.0), so it cannot gate CI.

Run with ``uv run pytest tests/eval`` (real credentials and LLM cost; never
part of the bare ``pytest`` unit lane).
"""

from pathlib import Path

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

pytestmark = pytest.mark.eval

DATA_DIR = Path(__file__).parent / "data"
NUM_RUNS = 1


async def test_template_agent_deterministic_eval() -> None:
    """Template agent passes the deterministic PR-gate eval criteria."""
    await AgentEvaluator.evaluate(
        agent_module="agent_foundation",
        eval_dataset_file_path_or_dir=str(DATA_DIR / "template_agent.evalset.json"),
        num_runs=NUM_RUNS,
    )
