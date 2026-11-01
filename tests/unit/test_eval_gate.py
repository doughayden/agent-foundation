"""Offline tests for the eval lane's unscored-run check and gate exit codes.

The helpers live in ``tests/eval/test_agent_eval.py`` beside the gates they guard;
the ``eval_gate`` fixture loads that module by path. ``AgentEvaluator`` is patched,
so no model is called.
"""

import math

import pytest
from google.adk.evaluation.eval_config import get_eval_metrics_from_config
from google.adk.evaluation.eval_metrics import EvalMetricResult, EvalStatus

RUBRIC_METRIC = "rubric_based_final_response_quality_v1"


class TestGatingRule:
    """``_is_gating`` agrees with ADK about which metrics decide the verdict."""

    @pytest.mark.parametrize(
        "config_name", ["DETERMINISTIC_EVAL_CONFIG", "JUDGE_EVAL_CONFIG"]
    )
    def test_only_configured_criteria_gate_among_metrics_adk_builds(
        self, eval_gate, config_name
    ):
        config = getattr(eval_gate, config_name)

        for metric in get_eval_metrics_from_config(config):
            crashed = EvalMetricResult(
                score=None, eval_status=EvalStatus.NOT_EVALUATED, **metric.model_dump()
            )

            assert eval_gate._is_gating(crashed) == (
                metric.metric_name in config.criteria
            ), metric.metric_name


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
            "case (session session): tool_trajectory_avg_score was not scored"
        ]

    def test_nan_score_counts_as_unscored(self, eval_gate, create_eval_case_result):
        results = [create_eval_case_result(scores={"custom_metric": math.nan})]

        assert eval_gate._unscored_runs(results) == [
            "case (session session): custom_metric was not scored"
        ]

    def test_run_without_metric_results_is_reported(
        self, eval_gate, create_eval_case_result
    ):
        results = [create_eval_case_result()]

        assert eval_gate._unscored_runs(results) == [
            "case (session session): produced no metric results"
        ]

    def test_each_unscored_run_is_named_by_case_and_session(
        self, eval_gate, create_eval_case_result
    ):
        results = [
            create_eval_case_result(
                scores={"safety_v1": 1.0}, eval_id="first", session_id="s1"
            ),
            create_eval_case_result(
                scores={"safety_v1": None}, eval_id="second", session_id="s2"
            ),
            create_eval_case_result(
                scores={"safety_v1": None}, eval_id="first", session_id="s3"
            ),
        ]

        assert eval_gate._unscored_runs(results) == [
            "second (session s2): safety_v1 was not scored",
            "first (session s3): safety_v1 was not scored",
        ]

    @pytest.mark.parametrize("efficiency_score", [1151.5, None])
    def test_efficiency_metrics_are_ignored_even_when_they_crash(
        self, eval_gate, create_eval_case_result, efficiency_score
    ):
        results = [
            create_eval_case_result(
                scores={"safety_v1": 1.0},
                efficiency={"token_usage_v1": efficiency_score},
            )
        ]

        assert eval_gate._unscored_runs(results) == []

    def test_fully_judged_rubrics_report_nothing(
        self, eval_gate, create_eval_case_result
    ):
        results = [
            create_eval_case_result(
                rubrics={RUBRIC_METRIC: ["answers_query", "concise"]},
                rubric_scores={RUBRIC_METRIC: {"answers_query": 1.0, "concise": 1.0}},
            )
        ]

        assert eval_gate._unscored_runs(results) == []

    @pytest.mark.parametrize(
        "judged",
        [{"concise": 1.0}, {"answers_query": None, "concise": 1.0}],
        ids=["rubric-missing", "rubric-without-score"],
    )
    def test_unjudged_rubric_is_reported_though_the_metric_scored(
        self, eval_gate, create_eval_case_result, judged
    ):
        results = [
            create_eval_case_result(
                rubrics={RUBRIC_METRIC: ["answers_query", "concise"]},
                rubric_scores={RUBRIC_METRIC: judged},
            )
        ]

        assert eval_gate._unscored_runs(results) == [
            f"case (session session): {RUBRIC_METRIC} rubric answers_query "
            "was not judged"
        ]

    def test_empty_capture_is_reported(self, eval_gate):
        assert eval_gate._unscored_runs([]) == ["no eval results were captured"]


class TestGate:
    """``_gate`` keeps ADK's verdict only over fully scored runs."""

    async def test_pass_over_scored_runs_returns(
        self,
        eval_gate,
        create_eval_case_result,
        create_mock_evaluate_eval_set,
        mock_set_exit_status,
    ):
        evaluate = create_mock_evaluate_eval_set(
            runs=[create_eval_case_result(scores={"safety_v1": 1.0})]
        )
        set_exit_status = mock_set_exit_status

        await eval_gate._gate(eval_gate.JUDGE_EVAL_CONFIG, 5, set_exit_status)

        set_exit_status.assert_not_called()
        kwargs = evaluate.await_args.kwargs
        assert kwargs["eval_set"] is eval_gate.EVAL_SET
        assert kwargs["eval_config"] is eval_gate.JUDGE_EVAL_CONFIG
        assert kwargs["num_runs"] == 5
        assert kwargs["app_name"] == eval_gate.AGENT_MODULE

    async def test_sub_threshold_over_scored_runs_keeps_the_verdict(
        self,
        eval_gate,
        create_eval_case_result,
        create_mock_evaluate_eval_set,
        mock_set_exit_status,
    ):
        create_mock_evaluate_eval_set(
            runs=[create_eval_case_result(scores={"safety_v1": 0.0})],
            raises=AssertionError("safety_v1 below threshold"),
        )
        set_exit_status = mock_set_exit_status

        with pytest.raises(AssertionError, match="below threshold"):
            await eval_gate._gate(eval_gate.JUDGE_EVAL_CONFIG, 5, set_exit_status)

        set_exit_status.assert_not_called()

    async def test_unscored_run_fails_and_sets_eval_error_exit(
        self,
        eval_gate,
        create_eval_case_result,
        create_mock_evaluate_eval_set,
        mock_set_exit_status,
    ):
        create_mock_evaluate_eval_set(
            runs=[
                create_eval_case_result(scores={"safety_v1": 1.0}),
                create_eval_case_result(scores={"safety_v1": None}),
            ]
        )
        set_exit_status = mock_set_exit_status

        with pytest.raises(pytest.fail.Exception, match="safety_v1 was not scored"):
            await eval_gate._gate(eval_gate.JUDGE_EVAL_CONFIG, 5, set_exit_status)

        set_exit_status.assert_called_once_with(eval_gate.EVAL_ERROR_EXIT_CODE)

    async def test_verdict_over_an_unscored_run_is_chained_as_the_cause(
        self,
        eval_gate,
        create_eval_case_result,
        create_mock_evaluate_eval_set,
        mock_set_exit_status,
    ):
        verdict = AssertionError("safety_v1 was not evaluated")
        create_mock_evaluate_eval_set(
            runs=[create_eval_case_result(scores={"safety_v1": None})], raises=verdict
        )
        set_exit_status = mock_set_exit_status

        with pytest.raises(pytest.fail.Exception) as failure:
            await eval_gate._gate(eval_gate.JUDGE_EVAL_CONFIG, 5, set_exit_status)

        assert failure.value.__cause__ is verdict
        set_exit_status.assert_called_once_with(eval_gate.EVAL_ERROR_EXIT_CODE)

    async def test_non_assertion_error_fails_with_its_cause_and_sets_eval_error_exit(
        self,
        eval_gate,
        create_mock_evaluate_eval_set,
        mock_set_exit_status,
    ):
        error = KeyError("missing_metric")
        create_mock_evaluate_eval_set(raises=error)
        set_exit_status = mock_set_exit_status

        with pytest.raises(
            pytest.fail.Exception, match="Eval could not run"
        ) as failure:
            await eval_gate._gate(eval_gate.JUDGE_EVAL_CONFIG, 5, set_exit_status)

        assert failure.value.__cause__ is error
        set_exit_status.assert_called_once_with(eval_gate.EVAL_ERROR_EXIT_CODE)

    def test_eval_error_exit_code_is_not_a_pytest_code(self, eval_gate):
        pytest_codes = {code.value for code in pytest.ExitCode}

        assert eval_gate.EVAL_ERROR_EXIT_CODE not in pytest_codes


class TestExitStatusHook:
    """The eval lane conftest ends the session with the code a test recorded."""

    def test_recorded_code_replaces_the_session_exit_status(
        self, eval_lane_conftest, create_mock_session
    ):
        session = create_mock_session(
            exitstatus=1, stash_entries={eval_lane_conftest.EXIT_STATUS_KEY: 6}
        )

        eval_lane_conftest.pytest_sessionfinish(session, 1)

        assert session.exitstatus == 6

    def test_no_recorded_code_leaves_the_exit_status(
        self, eval_lane_conftest, create_mock_session
    ):
        session = create_mock_session(exitstatus=1)

        eval_lane_conftest.pytest_sessionfinish(session, 1)

        assert session.exitstatus == 1
