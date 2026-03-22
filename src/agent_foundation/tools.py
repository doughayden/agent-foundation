"""Custom tools for the LLM agent."""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)


def get_current_time(
    timezone: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Get the current time in a specified timezone.

    Returns the current date and time in the requested timezone, formatted
    for readability. Use this tool when the user asks about the current time
    in a specific location or timezone.

    Args:
        timezone: IANA timezone name (e.g., 'America/New_York', 'Europe/London',
                  'Asia/Tokyo', 'UTC'). Case-sensitive.
        tool_context: ADK ToolContext with access to session state.

    Returns:
        A dictionary containing:
        - status: 'success' or 'error'
        - timezone: The requested timezone (on success)
        - datetime: ISO format datetime string (on success)
        - formatted: Human-readable datetime string (on success)
        - message: Error description (on error)
        - available_timezones: List of example timezones (on error)
    """
    logger.info(f"Getting current time for timezone: {timezone}")

    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)

        result = {
            "status": "success",
            "timezone": timezone,
            "datetime": now.isoformat(),
            "formatted": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
        logger.info(f"Current time in {timezone}: {result['formatted']}")
        return result

    except Exception:
        logger.warning(f"Invalid timezone requested: {timezone}")
        # Provide helpful examples for common timezones
        example_timezones = sorted(
            [
                "UTC",
                "America/New_York",
                "America/Chicago",
                "America/Denver",
                "America/Los_Angeles",
                "Europe/London",
                "Europe/Paris",
                "Europe/Berlin",
                "Asia/Tokyo",
                "Asia/Shanghai",
                "Asia/Dubai",
                "Australia/Sydney",
            ]
        )
        return {
            "status": "error",
            "message": f"Unknown timezone: '{timezone}'. Use IANA timezone names.",
            "available_timezones": example_timezones,
        }


def list_timezones(
    tool_context: ToolContext,
) -> dict[str, Any]:
    """List available IANA timezone names.

    Returns a list of all valid IANA timezone names that can be used with
    get_current_time. Use this tool when the user wants to know what
    timezones are available or when a timezone lookup fails.

    Args:
        tool_context: ADK ToolContext with access to session state.

    Returns:
        A dictionary containing:
        - status: 'success'
        - count: Total number of available timezones
        - timezones: Sorted list of all IANA timezone names
    """
    logger.info("Listing available timezones")

    all_timezones = sorted(available_timezones())
    result = {
        "status": "success",
        "count": len(all_timezones),
        "timezones": all_timezones,
    }

    logger.info(f"Found {len(all_timezones)} available timezones")
    return result
