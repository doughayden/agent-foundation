"""Unit tests for the package's lazy-loading interface."""

import pytest
from pytest_mock import MockerFixture

import agent_foundation


class TestLazyLoader:
    """Tests for the PEP 562 module __getattr__."""

    def test_exported_name_imports_submodule(self, mocker: MockerFixture) -> None:
        """Test an attribute in __all__ imports the matching submodule."""
        mock_import = mocker.patch("agent_foundation.importlib.import_module")

        result = agent_foundation.agent

        mock_import.assert_called_once_with(".agent", "agent_foundation")
        assert result is mock_import.return_value

    def test_unknown_name_raises_attribute_error(self, mocker: MockerFixture) -> None:
        """Test an attribute outside __all__ raises AttributeError without importing."""
        mock_import = mocker.patch("agent_foundation.importlib.import_module")

        with pytest.raises(AttributeError, match="has no attribute 'missing'"):
            _ = agent_foundation.missing

        mock_import.assert_not_called()
