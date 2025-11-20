"""Unit tests for environment variable parsing utilities."""

import os
from unittest.mock import patch

import pytest

from adk_docker_uv.utils.env_parser import parse_json_list_env


class TestParseJsonListEnv:
    """Tests for parse_json_list_env function."""

    def test_parse_valid_json_list_from_env(self) -> None:
        """Test parsing valid JSON list from environment variable."""
        with patch.dict(os.environ, {"TEST_ORIGINS": '["https://example.com"]'}):
            result = parse_json_list_env("TEST_ORIGINS", '["http://127.0.0.1"]')
            assert result == ["https://example.com"]

    def test_parse_uses_default_when_env_not_set(self) -> None:
        """Test that default is used when environment variable not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = parse_json_list_env("MISSING_VAR", '["http://127.0.0.1"]')
            assert result == ["http://127.0.0.1"]

    def test_parse_falls_back_on_invalid_json(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test fallback to default on invalid JSON."""
        with patch.dict(os.environ, {"BAD_JSON": "not valid json"}):
            result = parse_json_list_env("BAD_JSON", '["http://127.0.0.1"]')
            assert result == ["http://127.0.0.1"]

            # Verify warning was printed
            captured = capsys.readouterr()
            assert "WARNING: Invalid BAD_JSON" in captured.out
            assert "Using default" in captured.out

    def test_parse_falls_back_on_non_list_json(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test fallback to default when JSON is not a list."""
        with patch.dict(os.environ, {"NOT_LIST": '{"key": "value"}'}):
            result = parse_json_list_env("NOT_LIST", '["http://127.0.0.1"]')
            assert result == ["http://127.0.0.1"]

            # Verify warning was printed
            captured = capsys.readouterr()
            assert "WARNING: Invalid NOT_LIST" in captured.out
            assert "must be a JSON array" in captured.out

    def test_parse_raises_on_invalid_default(self) -> None:
        """Test that invalid default value raises ValueError."""
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_json_list_env("ANY_VAR", "not valid json")

    def test_parse_raises_on_non_list_default(self) -> None:
        """Test that non-list default value raises ValueError."""
        with pytest.raises(ValueError, match="must be a JSON array"):
            parse_json_list_env("ANY_VAR", '{"key": "value"}')

    def test_parse_empty_list(self) -> None:
        """Test parsing empty JSON list."""
        with patch.dict(os.environ, {"EMPTY_LIST": "[]"}):
            result = parse_json_list_env("EMPTY_LIST", '["default"]')
            assert result == []

    def test_parse_complex_list(self) -> None:
        """Test parsing complex JSON list with multiple origins."""
        origins = (
            '["http://127.0.0.1", "https://example.com", "http://192.168.1.1:3000"]'
        )
        with patch.dict(os.environ, {"COMPLEX_ORIGINS": origins}):
            result = parse_json_list_env("COMPLEX_ORIGINS", '["http://127.0.0.1"]')
            assert result == [
                "http://127.0.0.1",
                "https://example.com",
                "http://192.168.1.1:3000",
            ]
