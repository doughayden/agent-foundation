"""ADK LlmAgent configuration.

This module defines the main ADK agent.
"""

import os
from datetime import date

from google.adk.agents import LlmAgent
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from adk_docker_uv.agent.callbacks import (
    LoggingCallbacks,
    add_session_to_memory,
)
from adk_docker_uv.agent.prompt import (
    return_description_root,
    return_instruction_root,
)
from adk_docker_uv.agent.tools import example_tool

logging_callbacks = LoggingCallbacks()

root_agent = LlmAgent(
    name="example_agent",
    model=os.getenv("ROOT_AGENT_MODEL", "gemini-2.5-flash"),
    global_instruction=(f"You are a helpful Assistant.\nTodays date: {date.today()}"),
    description=return_description_root(),
    instruction=return_instruction_root(),
    before_agent_callback=logging_callbacks.before_agent,
    after_agent_callback=[logging_callbacks.after_agent, add_session_to_memory],
    before_model_callback=logging_callbacks.before_model,
    after_model_callback=logging_callbacks.after_model,
    before_tool_callback=logging_callbacks.before_tool,
    after_tool_callback=logging_callbacks.after_tool,
    tools=[example_tool, PreloadMemoryTool()],
)
