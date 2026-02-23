"""Agent implementation public package interface.

ADK agent discovery (google.adk.cli.utils.agent_loader.AgentLoader._perform_load)
tries in order:
1. {agent_name}/__init__.py exports (method: _load_from_module_or_package)
2. {agent_name}/agent.py exports (method: _load_from_submodule)
3. {agent_name}/root_agent.yaml (method: _load_from_yaml_config)

ADK eval command (google.adk.cli.utils.cli_eval.get_root_agent) requires:
  agent_module.agent.root_agent

This module uses __getattr__ for true lazy loading to support both eval CLI
and web server requirements while allowing .env file to load before agent.py
reads module-level environment variables.

ref: https://peps.python.org/pep-0562/

Lazy loading workflow:
1. Package import does NOT trigger agent.py execution
2. server.py loads .env file via initialize_environment()
3. server.py creates FastAPI app (does not access agent attribute)
4. First access to agent attribute → agent.py imports and executes
5. At that point, all .env variables like FAQ_DATA_STORE are available
"""

import importlib
from types import ModuleType

__all__ = ["agent"]


def __getattr__(name: str) -> ModuleType:
    """Lazy load agent module when accessed.

    This defers agent.py import until the agent attribute is actually accessed,
    allowing .env file to load first in server.py.
    """
    if name in __all__:
        return importlib.import_module("." + name, __package__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
