"""Schema validation for the shipped agent-eval artifacts.

Loads every eval data file through ADK's own pydantic schemas and metric
registry, the same way ``adk eval`` parses them, so a malformed eval set,
criteria config, or conversation scenario fails on every PR in the fast unit
lane (no LLM cost) instead of only when the live eval lane runs.
"""

from pathlib import Path

import pytest
from google.adk.evaluation.conversation_scenarios import ConversationScenarios
from google.adk.evaluation.eval_case import SessionInput
from google.adk.evaluation.eval_config import (
    get_eval_metrics_from_config,
    get_evaluation_criteria_or_default,
)
from google.adk.evaluation.eval_set import EvalSet

DATA_DIR = Path(__file__).resolve().parents[2] / "tests" / "eval" / "data"

EVAL_SET_FILES = [
    "template_agent.evalset.json",
    "multi_turn.evalset.json",
    "simple_time_query.test.json",
]
CONFIG_FILES = [
    "test_config.json",
    "full_eval_config.json",
    "user_sim_config.json",
]


class TestEvalArtifactsMatchSchema:
    """Every shipped eval artifact parses under the installed ADK schema."""

    @pytest.mark.parametrize("filename", EVAL_SET_FILES)
    def test_eval_set_and_test_files_match_schema(self, filename):
        EvalSet.model_validate_json((DATA_DIR / filename).read_text())

    @pytest.mark.parametrize("filename", CONFIG_FILES)
    def test_criteria_configs_resolve_metrics(self, filename):
        config = get_evaluation_criteria_or_default(str(DATA_DIR / filename))
        assert get_eval_metrics_from_config(config), "no metrics resolved from config"

    def test_conversation_scenarios_match_schema(self):
        ConversationScenarios.model_validate_json(
            (DATA_DIR / "conversation_scenarios.json").read_text()
        )

    def test_session_input_matches_schema(self):
        SessionInput.model_validate_json((DATA_DIR / "session_input.json").read_text())
