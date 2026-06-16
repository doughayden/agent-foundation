"""Prompt definitions for the LLM agent."""

from datetime import UTC, datetime

from google.adk.agents.readonly_context import ReadonlyContext


def return_global_instruction(ctx: ReadonlyContext) -> str:
    """Generate global instruction with current date, day of week, and user ID.

    Uses the InstructionProvider pattern so the date is evaluated at request
    time. GlobalInstructionPlugin expects signature: (ReadonlyContext) -> str.

    Date precision only (no clock time): a per-turn value here would bust
    prompt caching, since this string is the cached instruction prefix.

    Args:
        ctx: ReadonlyContext providing access to session metadata including
             user_id for queries and memory operations.

    Returns:
        str: Global instruction with the current date, day name for work-week
             calculations (Sunday-Saturday timecard periods), and user ID.
    """
    now_utc = datetime.now(UTC)
    today = now_utc.strftime("%Y-%m-%d")
    day_name = now_utc.strftime("%A")
    return (
        "\n\nYou are a helpful Assistant.\n"
        f"Current date: {today} ({day_name})\n"
        f"Current User's ID: {ctx.user_id}"
    )


ROOT_AGENT_DESCRIPTION: str = "An agent that helps users answer general questions"

ROOT_AGENT_INSTRUCTION: str = """## Core Behaviors
- Greet the user by name if you know it or ask for their name
- Answer the user's question politely and factually
"""
