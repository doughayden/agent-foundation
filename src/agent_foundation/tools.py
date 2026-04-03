"""Custom tools for the LLM agent."""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.adk.tools import ToolContext

DEFAULT_TIMEZONE_NAME = "UTC"
SUCCESS_STATUS = "success"
ERROR_STATUS = "error"
SUCCESS_CODE = "current_time_retrieved"
INVALID_TIMEZONE_CODE = "invalid_timezone"


def get_current_time(
    tool_context: ToolContext,
    timezone_name: str = DEFAULT_TIMEZONE_NAME,
) -> dict[str, Any]:
    """Return the current time for a requested timezone.

    Args:
        timezone_name: IANA timezone name such as ``UTC`` or
            ``America/New_York``.

    Returns:
        A dictionary describing either the current time lookup result or the
        validation error for an unsupported timezone.
    """
    # tool_context: ToolContext injected by ADK for session state access.
    # Not included in the docstring to avoid confusing the LlmAgent.
    normalized_timezone_name = timezone_name.strip() or DEFAULT_TIMEZONE_NAME

    try:
        timezone = ZoneInfo(normalized_timezone_name)
    except ZoneInfoNotFoundError:
        error_message = (
            f"Unsupported timezone '{normalized_timezone_name}'. "
            "Use an IANA timezone name such as 'UTC' or "
            "'America/New_York'."
        )
        return {
            "status": ERROR_STATUS,
            "code": INVALID_TIMEZONE_CODE,
            "message": error_message,
            "requested_timezone": normalized_timezone_name,
        }

    current_time = datetime.now(timezone)
    utc_offset = current_time.strftime("%z")
    formatted_utc_offset = f"{utc_offset[:3]}:{utc_offset[3:]}"
    utc_time = current_time.astimezone(UTC)

    message = f"Retrieved current time for {normalized_timezone_name}."
    return {
        "status": SUCCESS_STATUS,
        "code": SUCCESS_CODE,
        "message": message,
        "timezone_name": normalized_timezone_name,
        "current_time": current_time.isoformat(timespec="seconds"),
        "current_date": current_time.date().isoformat(),
        "day_of_week": current_time.strftime("%A"),
        "utc_offset": formatted_utc_offset,
        "utc_time": utc_time.isoformat(timespec="seconds"),
    }
