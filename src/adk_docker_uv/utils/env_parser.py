"""Environment variable parsing utilities."""

import json
import os


def parse_json_list_env(
    env_key: str,
    default: str,
) -> list[str]:
    """Parse a JSON array from environment variable with validation.

    Args:
        env_key: Environment variable name to read.
        default: Default JSON array string to use if parsing fails or env var not set.

    Returns:
        Parsed list of strings.

    Raises:
        ValueError: If default value is not a valid JSON array.

    Note:
        If the environment variable contains invalid JSON, prints a warning
        and falls back to the default value.
    """
    # Parse and validate default
    try:
        default_value = json.loads(default)
    except json.JSONDecodeError as e:
        msg = f"Default value for {env_key} is not valid JSON: {e}"
        raise ValueError(msg) from e

    if not isinstance(default_value, list):
        msg = f"Default value for {env_key} must be a JSON array"
        raise ValueError(msg)

    # Use default if env var not set
    env_value = os.getenv(env_key)
    if env_value is None:
        return default_value  # pyright: ignore[reportUnknownVariableType]

    # Parse and validate env var
    try:
        parsed = json.loads(env_value)
        if not isinstance(parsed, list):
            msg = f"{env_key} must be a JSON array"
            raise ValueError(msg)
        return parsed  # pyright: ignore[reportUnknownVariableType]
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARNING: Invalid {env_key} value '{env_value}': {e}")
        print(f"Using default: {default}")
        return default_value  # pyright: ignore[reportUnknownVariableType]
