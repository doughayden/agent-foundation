"""Unit tests for plugin construction."""

from google.adk.plugins.logging_plugin import LoggingPlugin

from agent_foundation.plugins import K_CONFIGURATION, build_plugins


class TestBuildPlugins:
    """Tests for build_plugins."""

    def test_registers_logging_plugin_off_cloud_run(self, isolated_environ) -> None:
        """Test that LoggingPlugin is the only plugin when K_CONFIGURATION is unset."""
        isolated_environ({})

        plugins = build_plugins()

        assert len(plugins) == 1
        assert isinstance(plugins[0], LoggingPlugin)

    def test_returns_no_plugins_on_cloud_run(self, isolated_environ) -> None:
        """Test that no plugin is registered when K_CONFIGURATION is set."""
        isolated_environ({K_CONFIGURATION: "agent-foundation-dev"})

        assert build_plugins() == []
