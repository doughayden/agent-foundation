"""ADK LlmAgent configuration."""

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.load_memory_tool import load_memory_tool
from google.genai import types

from .callbacks import LoggingCallbacks, add_session_to_memory
from .plugins import build_plugins
from .prompt import ROOT_AGENT_DESCRIPTION, ROOT_AGENT_INSTRUCTION
from .tools import get_current_time

APP_NAME = "agent_foundation"
ROOT_AGENT_NAME = "agent_foundation"
ROOT_AGENT_MODEL = "gemini-3.5-flash"
ROOT_AGENT_MODEL_TIMEOUT_MS = 120_000

logging_callbacks = LoggingCallbacks()

root_agent = LlmAgent(
    name=ROOT_AGENT_NAME,
    description=ROOT_AGENT_DESCRIPTION,
    before_agent_callback=logging_callbacks.before_agent,
    after_agent_callback=[logging_callbacks.after_agent, add_session_to_memory],
    model=ROOT_AGENT_MODEL,
    generate_content_config=types.GenerateContentConfig(
        http_options=types.HttpOptions(timeout=ROOT_AGENT_MODEL_TIMEOUT_MS)
    ),
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[FunctionTool(get_current_time), load_memory_tool],
    before_model_callback=logging_callbacks.before_model,
    after_model_callback=logging_callbacks.after_model,
    before_tool_callback=logging_callbacks.before_tool,
    after_tool_callback=logging_callbacks.after_tool,
)

app = App(
    name=APP_NAME,
    root_agent=root_agent,
    plugins=build_plugins(),
)
