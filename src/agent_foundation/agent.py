"""ADK LlmAgent configuration."""

import os

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from google.adk.plugins.logging_plugin import LoggingPlugin
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
    tools=[PreloadMemoryTool(), example_tool],
    before_model_callback=logging_callbacks.before_model,
    after_model_callback=logging_callbacks.after_model,
    before_tool_callback=logging_callbacks.before_tool,
    after_tool_callback=logging_callbacks.after_tool,
)

# Optional App configs explicitly set to None for template documentation
app = App(
    name="agent_foundation",
    root_agent=root_agent,
    plugins=[
        GlobalInstructionPlugin(return_global_instruction),
        LoggingPlugin(),
    ],
    events_compaction_config=None,
    context_cache_config=None,
    resumability_config=None,
)
