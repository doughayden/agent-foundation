"""Unit tests for custom tools."""

import re

from agent_foundation.tools import (
    DEFAULT_TIMEZONE_NAME,
    ERROR_STATUS,
    INVALID_TIMEZONE_CODE,
    SUCCESS_CODE,
    SUCCESS_STATUS,
    get_current_time,
)


class TestGetCurrentTime:
    """Tests for the get_current_time function."""

    def test_get_current_time_returns_default_timezone_success(
        self, mock_tool_context
    ) -> None:
        """Test that get_current_time defaults to UTC."""
        result = get_current_time(tool_context=mock_tool_context)

        assert result["status"] == SUCCESS_STATUS
        assert result["code"] == SUCCESS_CODE
        assert result["timezone_name"] == DEFAULT_TIMEZONE_NAME
        assert result["utc_offset"] == "+00:00"
        assert result["message"] == "Retrieved current time for UTC."
        assert result["day_of_week"]
        assert result["current_date"]
        assert result["utc_time"]
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00",
            result["current_time"],
        )

    def test_get_current_time_uses_requested_timezone(self, mock_tool_context) -> None:
        """Test that get_current_time returns data for a valid timezone."""
        result = get_current_time(
            tool_context=mock_tool_context, timezone_name="America/New_York"
        )

        assert result["status"] == SUCCESS_STATUS
        assert result["code"] == SUCCESS_CODE
        assert result["timezone_name"] == "America/New_York"
        assert result["message"] == "Retrieved current time for America/New_York."
        assert result["utc_offset"] in {"-05:00", "-04:00"}

    def test_get_current_time_uses_default_timezone_for_blank_input(
        self, mock_tool_context
    ) -> None:
        """Test that blank timezone input falls back to UTC."""
        result = get_current_time(tool_context=mock_tool_context, timezone_name="   ")

        assert result["status"] == SUCCESS_STATUS
        assert result["timezone_name"] == DEFAULT_TIMEZONE_NAME
        assert result["message"] == "Retrieved current time for UTC."

    def test_get_current_time_returns_error_for_invalid_timezone(
        self, mock_tool_context_empty_state
    ) -> None:
        """Test that invalid timezone input returns a clear error response."""
        result = get_current_time(
            tool_context=mock_tool_context_empty_state,
            timezone_name="Mars/Olympus_Mons",
        )

        assert result == {
            "status": ERROR_STATUS,
            "code": INVALID_TIMEZONE_CODE,
            "message": (
                "Unsupported timezone 'Mars/Olympus_Mons'. "
                "Use an IANA timezone name such as 'UTC' or "
                "'America/New_York'."
            ),
            "requested_timezone": "Mars/Olympus_Mons",
        }
