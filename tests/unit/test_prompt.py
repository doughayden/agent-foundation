"""Unit tests for prompt definitions."""

from datetime import UTC, datetime

from pytest_mock import MockerFixture

from agent_foundation.prompt import return_global_instruction


class TestReturnGlobalInstruction:
    """Tests for the return_global_instruction InstructionProvider."""

    def test_includes_current_date_day_and_user_id(
        self, mocker: MockerFixture, mock_readonly_context
    ) -> None:
        """Test the instruction carries the UTC date, day name and user ID."""
        mock_datetime = mocker.patch("agent_foundation.prompt.datetime")
        mock_datetime.now.return_value = datetime(2026, 11, 6, 23, 59, tzinfo=UTC)

        result = return_global_instruction(mock_readonly_context)

        mock_datetime.now.assert_called_once_with(UTC)
        assert "Current date: 2026-11-06 (Friday)" in result
        assert "Current User's ID: test_user_123" in result

    def test_omits_clock_time(
        self, mocker: MockerFixture, mock_readonly_context
    ) -> None:
        """Test the instruction has date precision only, so the prefix caches."""
        mock_datetime = mocker.patch("agent_foundation.prompt.datetime")
        mock_datetime.now.return_value = datetime(2026, 11, 6, 23, 59, tzinfo=UTC)

        result = return_global_instruction(mock_readonly_context)

        assert "23:59" not in result
