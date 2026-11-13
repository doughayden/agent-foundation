"""ADK plugin construction for the App."""

import os

from google.adk.plugins.base_plugin import BasePlugin
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from google.adk.plugins.logging_plugin import LoggingPlugin

from .prompt import return_global_instruction

# Cloud Run sets it in every service container
K_CONFIGURATION = "K_CONFIGURATION"


def build_plugins() -> list[BasePlugin]:
    """Return the App's plugins, in the order ADK runs them.

    ``GlobalInstructionPlugin`` comes first, so later plugins and the agent's
    callbacks see the final instruction. ``LoggingPlugin`` prints every callback,
    including user content, with ``print()``, outside ``LOG_LEVEL`` and the
    content-capture settings. It runs locally and in eval runs, where its readable
    trace helps, and stays off on Cloud Run, detected by ``K_CONFIGURATION``. A
    deployment on any other platform registers it and prints there.

    Returns:
        ``GlobalInstructionPlugin``, then ``LoggingPlugin`` off Cloud Run.
    """
    plugins: list[BasePlugin] = [GlobalInstructionPlugin(return_global_instruction)]
    if os.environ.get(K_CONFIGURATION) is None:
        plugins.append(LoggingPlugin())
    return plugins
