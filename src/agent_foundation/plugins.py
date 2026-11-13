"""ADK plugin construction for the App."""

import os

from google.adk.plugins.base_plugin import BasePlugin
from google.adk.plugins.logging_plugin import LoggingPlugin

# Cloud Run sets it in every service container
K_CONFIGURATION = "K_CONFIGURATION"


def build_plugins() -> list[BasePlugin]:
    """Return the environment-dependent plugins for ``App.plugins``.

    ``LoggingPlugin`` prints every callback, including user content, with
    ``print()``, outside ``LOG_LEVEL`` and the content-capture settings. It runs
    locally and in eval runs, where its readable trace helps, and stays off on Cloud
    Run, detected by ``K_CONFIGURATION``. A deployment on any other platform
    registers it and prints there.

    Returns:
        ``[LoggingPlugin()]`` off Cloud Run, an empty list on it.
    """
    if os.environ.get(K_CONFIGURATION) is not None:
        return []
    return [LoggingPlugin()]
