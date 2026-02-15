"""Unit tests for custom tools."""

import logging

import pytest

from agent_foundation.tools import example_tool


class TestExampleTool:
    """Tests for the example_tool function."""

    def test_example_tool_returns_success(
        self, mock_tool_context, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that example_tool returns success status and message."""
        caplog.set_level(logging.INFO)

        result = example_tool(mock_tool_context)

        assert result["status"] == "success"
        assert result["message"] == "Successfully used example_tool."

    def test_example_tool_logs_state_keys(
        self, mock_tool_context, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that example_tool logs session state keys."""
        caplog.set_level(logging.INFO)

        example_tool(mock_tool_context)

        assert "Session state keys:" in caplog.text
        assert "Successfully used example_tool." in caplog.text

        # Verify INFO level was used
        info_records = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_records) == 2

    def test_example_tool_with_empty_state(
        self, mock_tool_context_empty_state, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that example_tool handles empty state correctly."""
        caplog.set_level(logging.INFO)

        result = example_tool(mock_tool_context_empty_state)

        assert result["status"] == "success"
        assert result["message"] == "Successfully used example_tool."
        assert "Session state keys:" in caplog.text
