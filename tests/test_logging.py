"""Tests for logging configuration."""

import logging
from pathlib import Path

import pytest


class TestLoggingConfiguration:
    """Tests for logging configuration."""

    async def test_logging_setup_creates_log_file(self, tmp_path: Path) -> None:
        """Verify logging setup creates log file and captures messages."""
        from adk_docker_uv.utils.log_config import setup_file_logging

        log_dir = tmp_path / "logs"
        log_filename = "test.log"

        setup_file_logging("INFO", log_dir=str(log_dir), log_filename=log_filename)

        # Emit test messages
        logger = logging.getLogger("test_logging")
        logger.info("Test info message")
        logger.warning("Test warning message")

        # Verify log file exists and contains messages
        log_file = log_dir / log_filename
        assert log_file.exists()

        log_content = log_file.read_text()
        assert "Test info message" in log_content
        assert "Test warning message" in log_content
        assert "test_logging" in log_content

    async def test_logging_setup_respects_log_level(self, tmp_path: Path) -> None:
        """Verify logging setup respects configured log level."""
        from adk_docker_uv.utils.log_config import setup_file_logging

        log_dir = tmp_path / "logs"
        log_filename = "level_test.log"

        # Configure at WARNING level
        setup_file_logging("WARNING", log_dir=str(log_dir), log_filename=log_filename)

        logger = logging.getLogger("test_level")
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        log_file = log_dir / log_filename
        log_content = log_file.read_text()

        # Should NOT contain debug/info
        assert "Debug message" not in log_content
        assert "Info message" not in log_content

        # Should contain warning/error
        assert "Warning message" in log_content
        assert "Error message" in log_content

    async def test_logging_setup_with_invalid_log_level(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Verify invalid log level falls back to INFO with warning to stderr."""
        from adk_docker_uv.utils.log_config import setup_file_logging

        log_dir = tmp_path / "logs"
        log_filename = "invalid_level.log"

        # Pass invalid log level
        setup_file_logging("INVALID", log_dir=str(log_dir), log_filename=log_filename)

        # Should print warning to stdout (captured by capsys)
        captured = capsys.readouterr()
        assert "Received log_level: 'INVALID'" in captured.out
        assert "Defaulting to 'INFO'" in captured.out

    async def test_logging_setup_with_custom_format(self, tmp_path: Path) -> None:
        """Verify custom log format is used."""
        from adk_docker_uv.utils.log_config import setup_file_logging

        log_dir = tmp_path / "logs"
        log_filename = "custom_format.log"
        custom_format = "CUSTOM: {message}"

        setup_file_logging(
            "INFO",
            log_format=custom_format,
            log_dir=str(log_dir),
            log_filename=log_filename,
        )

        logger = logging.getLogger("test_custom")
        logger.info("Test message")

        log_file = log_dir / log_filename
        log_content = log_file.read_text()

        assert "CUSTOM: Test message" in log_content
