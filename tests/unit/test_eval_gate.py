"""Offline tests for the eval lane's unscored-run check and gate exit codes.

The helpers live in ``tests/eval/test_agent_eval.py`` beside the gates they guard;
the ``eval_gate`` fixture loads that module by path. No model is called.
"""

import pytest


async def _passes() -> None:
    return None


async def _sub_threshold() -> None:
    raise AssertionError("response_match_score below threshold")


async def _cannot_run() -> None:
    raise ValueError("eval set has no cases")


class TestUnscoredRuns:
    """``_unscored_runs`` names every run that did not score every gating metric."""

    def test_fully_scored_runs_report_nothing(self, eval_gate, create_eval_case_result):
        results = [
            create_eval_case_result(scores={"tool_trajectory_avg_score": 1.0}),
            create_eval_case_result(scores={"tool_trajectory_avg_score": 0.5}),
        ]

        assert eval_gate._unscored_runs(results) == []

    def test_unscored_gating_metric_is_named_with_its_run(
        self, eval_gate, create_eval_case_result
    ):
        results = [
            create_eval_case_result(
                scores={"tool_trajectory_avg_score": None, "response_match_score": 0.6}
            ),
            create_eval_case_result(
                scores={"tool_trajectory_avg_score": 1.0, "response_match_score": 0.6}
            ),
        ]

        assert eval_gate._unscored_runs(results) == [
            "case (result 0): tool_trajectory_avg_score was not scored"
        ]

    def test_run_without_metric_results_is_reported(
        self, eval_gate, create_eval_case_result
    ):
        results = [create_eval_case_result()]

        assert eval_gate._unscored_runs(results) == [
            "case (result 0): produced no metric results"
        ]

    def test_unscored_informational_metric_is_ignored(
        self, eval_gate, create_eval_case_result
    ):
        results = [
            create_eval_case_result(
                scores={"safety_v1": 1.0}, informational={"token_usage_v1": None}
            )
        ]

        assert eval_gate._unscored_runs(results) == []

    def test_empty_capture_is_reported(self, eval_gate):
        assert eval_gate._unscored_runs([]) == ["no eval results were captured"]


class TestGate:
    """``_gate`` keeps ADK's verdict only over fully scored runs."""

    @pytest.fixture
    def capture(self, eval_gate, create_eval_case_result):
        def _factory(*runs):
            manager = eval_gate._CapturingEvalSetResultsManager()
            manager.save_eval_set_result(
                "app", "set", [create_eval_case_result(scores=s) for s in runs]
            )
            return manager

        return _factory

    async def test_pass_over_scored_runs_returns(self, eval_gate, capture):
        await eval_gate._gate(_passes(), capture({"safety_v1": 1.0}))

    async def test_sub_threshold_over_scored_runs_keeps_the_verdict(
        self, eval_gate, capture
    ):
        with pytest.raises(AssertionError, match="below threshold"):
            await eval_gate._gate(_sub_threshold(), capture({"safety_v1": 0.0}))

    async def test_pass_with_an_unscored_run_exits_eval_error(self, eval_gate, capture):
        results = capture({"safety_v1": 1.0}, {"safety_v1": None})

        with pytest.raises(pytest.exit.Exception) as exit_info:
            await eval_gate._gate(_passes(), results)

        assert exit_info.value.returncode == eval_gate.EVAL_ERROR_EXIT_CODE
        assert "safety_v1 was not scored" in str(exit_info.value)

    async def test_verdict_over_an_unscored_run_exits_eval_error_with_adk_report(
        self, eval_gate, capture
    ):
        results = capture({"safety_v1": None})

        with pytest.raises(pytest.exit.Exception) as exit_info:
            await eval_gate._gate(_sub_threshold(), results)

        assert exit_info.value.returncode == eval_gate.EVAL_ERROR_EXIT_CODE
        assert "ADK reported: response_match_score below threshold" in str(
            exit_info.value
        )

    async def test_non_assertion_error_exits_eval_error(self, eval_gate, capture):
        with pytest.raises(pytest.exit.Exception) as exit_info:
            await eval_gate._gate(_cannot_run(), capture())

        assert exit_info.value.returncode == eval_gate.EVAL_ERROR_EXIT_CODE
        assert "eval set has no cases" in str(exit_info.value)

    def test_eval_error_exit_code_is_not_a_pytest_code(self, eval_gate):
        pytest_codes = {code.value for code in pytest.ExitCode}

        assert eval_gate.EVAL_ERROR_EXIT_CODE not in pytest_codes
