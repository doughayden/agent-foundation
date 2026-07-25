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
CONVERSION_SUCCESS_CODE = "timestamp_converted"


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


def convert_timestamp(
    tool_context: ToolContext,
    timestamp: str,
    target_timezone_name: str,
    source_timezone_name: str = DEFAULT_TIMEZONE_NAME,
) -> dict[str, Any]:
    """Convert an ISO 8601 timestamp from one timezone to another.

    Args:
        timestamp: ISO 8601 timestamp such as ``2026-07-25T14:30:00``. A
            timestamp without an offset is read in the source timezone.
        target_timezone_name: IANA timezone name to convert into.
        source_timezone_name: IANA timezone name the timestamp is expressed
            in when it carries no offset.

    Returns:
        A dictionary describing either the conversion result or the
        validation error for an unsupported timezone.
    """
    # tool_context: ToolContext injected by ADK for session state access.
    # Not included in the docstring to avoid confusing the LlmAgent.
    normalized_target = target_timezone_name.strip() or DEFAULT_TIMEZONE_NAME
    normalized_source = source_timezone_name.strip() or DEFAULT_TIMEZONE_NAME

    try:
        target_timezone = ZoneInfo(normalized_target)
        source_timezone = ZoneInfo(normalized_source)
    except ZoneInfoNotFoundError:
        error_message = (
            f"Unsupported timezone '{normalized_target}' or "
            f"'{normalized_source}'. Use an IANA timezone name such as "
            "'UTC' or 'America/New_York'."
        )
        return {
            "status": ERROR_STATUS,
            "code": INVALID_TIMEZONE_CODE,
            "message": error_message,
            "requested_timezone": normalized_target,
        }

    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_timezone)

    converted = parsed.astimezone(target_timezone)
    utc_offset = converted.strftime("%z")
    formatted_utc_offset = f"{utc_offset[:3]}:{utc_offset[3:]}"

    return {
        "status": SUCCESS_STATUS,
        "code": CONVERSION_SUCCESS_CODE,
        "message": f"Converted timestamp to {normalized_target}.",
        "timezone_name": normalized_target,
        "source_timezone_name": normalized_source,
        "converted_time": converted.isoformat(timespec="seconds"),
        "day_of_week": converted.strftime("%A"),
        "utc_offset": formatted_utc_offset,
        "utc_time": parsed.astimezone(UTC).isoformat(timespec="seconds"),
    }
