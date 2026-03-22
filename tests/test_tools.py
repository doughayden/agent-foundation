"""Unit tests for custom tools."""

import logging
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from agent_foundation.tools import get_current_time, list_timezones


class TestGetCurrentTime:
    """Tests for the get_current_time function."""

    def test_get_current_time_utc_success(
        self, mock_tool_context, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test getting current time in UTC timezone."""
        caplog.set_level(logging.INFO)

        result = get_current_time("UTC", mock_tool_context)

        assert result["status"] == "success"
        assert result["timezone"] == "UTC"
        assert "datetime" in result
        assert "formatted" in result
        # Verify the datetime is parseable
        parsed = datetime.fromisoformat(result["datetime"])
        assert parsed is not None
        # Verify logging
        assert "Getting current time for timezone: UTC" in caplog.text

    def test_get_current_time_america_new_york(
        self, mock_tool_context, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test getting current time in America/New_York timezone."""
        caplog.set_level(logging.INFO)

        result = get_current_time("America/New_York", mock_tool_context)

        assert result["status"] == "success"
        assert result["timezone"] == "America/New_York"
        assert "datetime" in result
        assert "formatted" in result

    def test_get_current_time_asia_tokyo(
        self, mock_tool_context, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test getting current time in Asia/Tokyo timezone."""
        caplog.set_level(logging.INFO)

        result = get_current_time("Asia/Tokyo", mock_tool_context)

        assert result["status"] == "success"
        assert result["timezone"] == "Asia/Tokyo"
        # Tokyo is typically UTC+9
        parsed = datetime.fromisoformat(result["datetime"])
        assert parsed is not None

    def test_get_current_time_invalid_timezone(
        self, mock_tool_context, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test error handling for invalid timezone."""
        caplog.set_level(logging.INFO)

        result = get_current_time("Invalid/Timezone", mock_tool_context)

        assert result["status"] == "error"
        assert "Unknown timezone" in result["message"]
        assert "Invalid/Timezone" in result["message"]
        assert "available_timezones" in result
        # Verify helpful timezones are returned
        assert "UTC" in result["available_timezones"]
        assert "America/New_York" in result["available_timezones"]
        # Verify warning was logged
        assert "Invalid timezone requested: Invalid/Timezone" in caplog.text

    def test_get_current_time_lowercase_timezone(self, mock_tool_context) -> None:
        """Test that lowercase timezone names work (ZoneInfo is case-insensitive)."""
        result = get_current_time("america/new_york", mock_tool_context)

        # ZoneInfo accepts lowercase timezone names
        assert result["status"] == "success"
        assert result["timezone"] == "america/new_york"

    def test_get_current_time_formatted_output(self, mock_tool_context) -> None:
        """Test that formatted output contains expected components."""
        result = get_current_time("UTC", mock_tool_context)

        assert result["status"] == "success"
        formatted = result["formatted"]
        # Should contain date in YYYY-MM-DD format
        assert len(formatted.split()[0]) == 10  # "2024-01-15" = 10 chars
        # Should contain time in HH:MM:SS format
        assert ":" in formatted

    def test_get_current_time_returns_correct_timezone(self, mock_tool_context) -> None:
        """Test that the returned datetime is in the correct timezone."""
        with (
            patch("agent_foundation.tools.datetime") as mock_datetime,
        ):
            # Create a fixed datetime for testing
            fixed_time = datetime(2024, 6, 15, 14, 30, 45, tzinfo=ZoneInfo("UTC"))
            mock_datetime.now.return_value = fixed_time

            result = get_current_time("UTC", mock_tool_context)

            assert result["status"] == "success"
            assert result["datetime"] == "2024-06-15T14:30:45+00:00"

    def test_get_current_time_europe_london(self, mock_tool_context) -> None:
        """Test getting current time in Europe/London timezone."""
        result = get_current_time("Europe/London", mock_tool_context)

        assert result["status"] == "success"
        assert result["timezone"] == "Europe/London"


class TestListTimezones:
    """Tests for the list_timezones function."""

    def test_list_timezones_returns_success(
        self, mock_tool_context, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that list_timezones returns success status."""
        caplog.set_level(logging.INFO)

        result = list_timezones(mock_tool_context)

        assert result["status"] == "success"
        assert "Listing available timezones" in caplog.text

    def test_list_timezones_returns_count(self, mock_tool_context) -> None:
        """Test that list_timezones returns timezone count."""
        result = list_timezones(mock_tool_context)

        assert "count" in result
        assert isinstance(result["count"], int)
        assert result["count"] > 0

    def test_list_timezones_returns_sorted_list(self, mock_tool_context) -> None:
        """Test that timezones are returned as a sorted list."""
        result = list_timezones(mock_tool_context)

        assert "timezones" in result
        assert isinstance(result["timezones"], list)
        # Verify sorted
        assert result["timezones"] == sorted(result["timezones"])

    def test_list_timezones_contains_common_zones(self, mock_tool_context) -> None:
        """Test that common timezones are included in the list."""
        result = list_timezones(mock_tool_context)

        timezones = result["timezones"]
        assert "UTC" in timezones
        assert "America/New_York" in timezones
        assert "Europe/London" in timezones
        assert "Asia/Tokyo" in timezones

    def test_list_timezones_count_matches_list(self, mock_tool_context) -> None:
        """Test that count matches the actual list length."""
        result = list_timezones(mock_tool_context)

        assert result["count"] == len(result["timezones"])
