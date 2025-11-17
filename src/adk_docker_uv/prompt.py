"""Prompt definitions for the LLM agent."""

from datetime import date

from google.adk.agents.readonly_context import ReadonlyContext


def return_description_root() -> str:
    description = "An agent that helps users answer general questions"
    return description


def return_instruction_root() -> str:
    instruction = """
Answer the user's question politely and factually.
Remember important facts about the user.
"""
    return instruction


def return_global_instruction(ctx: ReadonlyContext) -> str:
    """Generate global instruction with current date.

    Uses InstructionProvider pattern to ensure date updates at request time.
    LlmAgent.global_instruction expects signature: (ReadonlyContext) -> str

    Args:
        ctx: ReadonlyContext required by LlmAgent.global_instruction signature.
             Provides access to session state and metadata for future customization.

    Returns:
        str: Global instruction string with dynamically generated current date.
    """
    # ctx parameter required by LlmAgent.global_instruction interface
    # Currently unused but available for session-aware customization
    return f"You are a helpful Assistant.\nToday's date: {date.today()}"
