"""Unit tests for plugin construction."""

import pytest
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from google.adk.plugins.logging_plugin import LoggingPlugin

from agent_foundation.plugins import K_CONFIGURATION, build_plugins
from agent_foundation.prompt import return_global_instruction


class TestBuildPlugins:
    """Tests for build_plugins."""

    def test_build_plugins_off_cloud_run_orders_global_instruction_first(
        self, isolated_environ
    ) -> None:
        """Test GlobalInstructionPlugin, then LoggingPlugin, off Cloud Run."""
        isolated_environ({})

        plugins = build_plugins()

        assert [type(plugin) for plugin in plugins] == [
            GlobalInstructionPlugin,
            LoggingPlugin,
        ]

    def test_build_plugins_global_instruction_uses_provider(
        self, isolated_environ
    ) -> None:
        """Test that GlobalInstructionPlugin wraps the template's provider."""
        isolated_environ({})

        plugin = build_plugins()[0]

        assert isinstance(plugin, GlobalInstructionPlugin)
        assert plugin.global_instruction is return_global_instruction

    @pytest.mark.parametrize("value", ["agent-foundation-dev", ""])
    def test_build_plugins_on_cloud_run_omits_logging_plugin(
        self, value, isolated_environ
    ) -> None:
        """Test that a set K_CONFIGURATION, even empty, leaves out LoggingPlugin."""
        isolated_environ({K_CONFIGURATION: value})

        plugins = build_plugins()

        assert [type(plugin) for plugin in plugins] == [GlobalInstructionPlugin]
