"""ADK LlmAgent configuration."""

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from .callbacks import LoggingCallbacks, add_session_to_memory
from .prompt import (
    ROOT_AGENT_DESCRIPTION,
    ROOT_AGENT_INSTRUCTION,
    return_global_instruction,
)
from .tools import get_current_time

APP_NAME = "agent_foundation"
ROOT_AGENT_NAME = "agent_foundation"

# Model for LlmAgent. ADK accepts a string or a LiteLlm wrapper:
#   Gemini (string):       "gemini-2.5-flash"
#   Model Garden endpoint: "projects/P/locations/L/endpoints/ENDPOINT_ID"
#   Vertex AI MaaS:        uncomment below and replace ROOT_AGENT_MODEL
# from google.adk.models.lite_llm import LiteLlm
ROOT_AGENT_MODEL = "gemini-2.5-flash"
# ROOT_AGENT_MODEL = LiteLlm(model="vertex_ai/ORG/MODEL_NAME-maas")

logging_callbacks = LoggingCallbacks()

root_agent = LlmAgent(
    name=ROOT_AGENT_NAME,
    description=ROOT_AGENT_DESCRIPTION,
    before_agent_callback=logging_callbacks.before_agent,
    after_agent_callback=[logging_callbacks.after_agent, add_session_to_memory],
    model=ROOT_AGENT_MODEL,
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[PreloadMemoryTool(), get_current_time],
    before_model_callback=logging_callbacks.before_model,
    after_model_callback=logging_callbacks.after_model,
    before_tool_callback=logging_callbacks.before_tool,
    after_tool_callback=logging_callbacks.after_tool,
)

app = App(
    name=APP_NAME,
    root_agent=root_agent,
    plugins=[
        GlobalInstructionPlugin(return_global_instruction),
        LoggingPlugin(),
    ],
)
