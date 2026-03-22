"""ADK LlmAgent configuration."""

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .callbacks import LoggingCallbacks, add_session_to_memory
from .prompt import (
    ROOT_AGENT_DESCRIPTION,
    ROOT_AGENT_INSTRUCTION,
    return_global_instruction,
)
from .tools import example_tool

APP_NAME = "agent_foundation"
ROOT_AGENT_NAME = "agent_foundation"
ROOT_AGENT_MODEL = "gemini-2.5-flash"
ROOT_AGENT_RETRIES = 3

logging_callbacks = LoggingCallbacks()

root_agent = LlmAgent(
    name=ROOT_AGENT_NAME,
    description=ROOT_AGENT_DESCRIPTION,
    before_agent_callback=logging_callbacks.before_agent,
    after_agent_callback=[logging_callbacks.after_agent, add_session_to_memory],
    model=Gemini(
        model=ROOT_AGENT_MODEL,
        retry_options=types.HttpRetryOptions(attempts=ROOT_AGENT_RETRIES),
    ),
    instruction=ROOT_AGENT_INSTRUCTION,
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
