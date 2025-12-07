"""ADK LlmAgent configuration."""

import os

from google.adk.agents import LlmAgent
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from .callbacks import LoggingCallbacks, add_session_to_memory
from .prompt import (
    return_description_root,
    return_global_instruction,
    return_instruction_root,
)
from .tools import example_tool

logging_callbacks = LoggingCallbacks()

root_agent = LlmAgent(
    name="example_agent",
    description=return_description_root(),
    before_agent_callback=logging_callbacks.before_agent,
    after_agent_callback=[logging_callbacks.after_agent, add_session_to_memory],
    model=os.getenv("ROOT_AGENT_MODEL", "gemini-2.5-flash"),
    instruction=return_instruction_root(),
    global_instruction=return_global_instruction,
    tools=[PreloadMemoryTool(), example_tool],
    before_model_callback=logging_callbacks.before_model,
    after_model_callback=logging_callbacks.after_model,
    before_tool_callback=logging_callbacks.before_tool,
    after_tool_callback=logging_callbacks.after_tool,
)
