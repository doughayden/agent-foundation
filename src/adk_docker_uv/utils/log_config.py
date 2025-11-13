"""Logging configuration utilities."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_file_logging(
    log_level: str,
    log_format: str | None = None,
    log_dir: str = ".log",
    log_filename: str = "app.log",
    max_bytes: int = 1024 * 1024,  # 1 MB
    encoding: str = "utf-8",
    backup_count: int = 5,
) -> None:
    """Configure rotating file logging for the application.

    Args:
        log_level: Logging level
        log_format: Custom log format string using '{' style formatting
            (default: standard format with time, level, name, message)
        log_dir: Directory for log files (default: .log)
        log_filename: Name of the log file (default: app.log)
        max_bytes: Maximum size in bytes before rotation
            (default: 1 MB)
        encoding: File encoding (default: utf-8)
        backup_count: Number of backup files to keep (default: 5)
    """
    # Validate log_level with fallback
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        print(f"WARNING: Received log_level: '{log_level}'. Defaulting to 'INFO'.")
        log_level = "INFO"

    if log_format is None:
        log_format = (
            "[{asctime}] [{process}] [{levelname:>8}] "
            "[{name}.{funcName}:{lineno:>5}] {message}"
        )

    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_path = log_dir_path / log_filename

    formatter = logging.Formatter(
        log_format,
        style="{",
    )

    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding=encoding,
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(handler)
