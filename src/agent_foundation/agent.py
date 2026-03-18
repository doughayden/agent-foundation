"""ADK LlmAgent configuration."""

import os

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from .callbacks import LoggingCallbacks, add_session_to_memory
from .prompt import (
    DESCRIPTION_ROOT,
    INSTRUCTION_ROOT,
    return_global_instruction,
)
from .tools import example_tool

APP_NAME = "example_agent"
logging_callbacks = LoggingCallbacks()

root_agent = LlmAgent(
    name=APP_NAME,
    description=DESCRIPTION_ROOT,
    before_agent_callback=logging_callbacks.before_agent,
    after_agent_callback=[logging_callbacks.after_agent, add_session_to_memory],
    model=os.getenv("ROOT_AGENT_MODEL", "gemini-2.5-flash"),
    instruction=INSTRUCTION_ROOT,
    tools=[PreloadMemoryTool(), example_tool],
    before_model_callback=logging_callbacks.before_model,
    after_model_callback=logging_callbacks.after_model,
    before_tool_callback=logging_callbacks.before_tool,
    after_tool_callback=logging_callbacks.after_tool,
)

app = App(
    name="agent_foundation",
    root_agent=root_agent,
    plugins=[
        GlobalInstructionPlugin(return_global_instruction),
        LoggingPlugin(),
    ],
)
