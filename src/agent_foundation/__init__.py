"""Agent implementation public package interface.

ADK agent discovery (google.adk.cli.utils.agent_loader.AgentLoader._perform_load)
tries in order, looking for `app` then `root_agent` at each step:
1. {agent_name}/__init__.py exports (method: _load_from_module_or_package)
2. {agent_name}/agent.py exports (method: _load_from_submodule)
3. {agent_name}/root_agent.yaml (method: _load_from_yaml_config)

ADK eval (google.adk.cli.cli_eval.get_root_agent, AgentEvaluator) reads the
`agent` attribute, then `app` or `root_agent` on it:
  agent_module.agent.app

This module uses __getattr__ for true lazy loading to support both eval CLI
and web server requirements while allowing .env file to load before agent.py
reads module-level environment variables. ADK's agent loader loads .env into
os.environ (variables already set win) before it imports the agent module.

ref: https://peps.python.org/pep-0562/

Lazy loading workflow:
1. Package import does NOT trigger agent.py execution
2. server.py validates ServerEnv and TelemetryEnv via initialize_environment()
3. server.py creates FastAPI app (does not access agent attribute)
4. ADK's agent loader loads .env into os.environ, finds no `app` or `root_agent`
   on the package (step 1 above), then imports agent.py as a submodule (step 2)
5. agent.py executes with all .env variables set
"""

import importlib
from types import ModuleType

__all__ = ["agent"]


def __getattr__(name: str) -> ModuleType:
    """Lazy load agent module when accessed.

    This defers agent.py import until the agent attribute is actually accessed,
    allowing ADK's agent loader to load .env first.
    """
    if name in __all__:
        return importlib.import_module("." + name, __package__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
