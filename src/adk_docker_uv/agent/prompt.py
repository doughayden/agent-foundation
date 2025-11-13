"""Prompt definitions for the LLM agent."""


def return_description_root() -> str:
    description = """\
An agent that helps users answer general questions.\
"""
    return description


def return_instruction_root() -> str:
    instruction = """
Answer the user's question politely and factually.
Remember important facts about the user.
"""
    return instruction
