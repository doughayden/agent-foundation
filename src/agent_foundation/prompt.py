"""Prompt definitions for the LLM agent."""

from datetime import UTC, datetime

from google.adk.agents.readonly_context import ReadonlyContext


def return_global_instruction(ctx: ReadonlyContext) -> str:
    """Generate global instruction with current date, day of week, and user ID.

    Uses InstructionProvider pattern to ensure date updates at request time.
    GlobalInstructionPlugin expects signature: (ReadonlyContext) -> str

    Args:
        ctx: ReadonlyContext providing access to session metadata including
             user_id for queries and memory operations.

    Returns:
        str: Global instruction with UTC timestamp, day name for work week
             calculations (Sunday-Saturday timecard periods), and user ID.
    """
    now_utc = datetime.now(UTC)
    day_name = now_utc.strftime("%A")
    return (
        "\n\nYou are a helpful Assistant.\n"
        f"Current UTC timestamp: {now_utc} ({day_name})\n"
        f"Current User's ID: {ctx.user_id}"
    )


def return_description_root() -> str:
    description = "An agent that helps users answer general questions"
    return description


def return_instruction_root() -> str:
    instruction = """
Answer the user's question politely and factually.
Remember important facts about the user.
"""
    return instruction
