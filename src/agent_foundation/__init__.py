"""Agent implementation public package interface.

ADK recommends this export pattern for agent and app discovery:

    from . import agent

ADK agent discovery (google.adk.cli.utils.agent_loader.AgentLoader._perform_load)
tries in order:
1. {agent_name}/__init__.py exports (method: _load_from_module_or_package)
2. {agent_name}/agent.py exports (method: _load_from_submodule) ← fallback
3. {agent_name}/root_agent.yaml (method: _load_from_yaml_config)

This module intentionally does NOT import agent at all, keeping __init__.py
empty, forcing ADK to use fallback pattern #2.

Rationale: Any import of agent.py executes all module-level code (globals),
including statements that construct root_agent and app, which read ROOT_AGENT_MODEL
from the environment - but during local development, .env hasn't loaded yet at
package import time.

By not exporting `agent` from __init__.py, we enable lazy loading:
the package imports without importing agent.py or executing its globals.
Our custom server.py first loads a local .env file and then starts the FastAPI server.
When a session is initiated, ADK also loads .env (AdkWebServer.get_runner_async) and
imports agent.py (fallback pattern #2), executing its module-level code.
At that point, all .env variables like ROOT_AGENT_MODEL are available.
"""
