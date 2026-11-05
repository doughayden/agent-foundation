"""Comprehensive unit tests for config module."""

import os

import pytest
from pydantic import ValidationError

from agent_foundation.config import (
    TELEMETRY_API_ENDPOINT,
    ServerEnv,
    TelemetryEnv,
    initialize_environment,
)


class TestServerEnv:
    """Tests for ServerEnv model."""

    def test_valid_server_env_creation(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test creating ServerEnv with valid required fields."""
        isolated_environ(valid_server_env)
        env = ServerEnv()

        assert env.google_cloud_project == "test-project"
        assert env.agent_name == "test-agent"

    def test_server_env_missing_required_field_raises_validation_error(
        self, isolated_environ
    ) -> None:
        """Test that missing required fields raise ValidationError."""
        data: dict[str, str] = {
            # Missing GOOGLE_CLOUD_PROJECT, AGENT_NAME,
            # and OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
        }

        isolated_environ(data)
        with pytest.raises(ValidationError) as exc_info:
            ServerEnv()

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("google_cloud_project",) for error in errors)
        assert any(error["loc"] == ("agent_name",) for error in errors)
        assert any(
            error["loc"] == ("otel_instrumentation_genai_capture_message_content",)
            for error in errors
        )

    def test_server_env_optional_fields_use_defaults(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that optional fields use default values when not provided."""
        isolated_environ(valid_server_env)
        env = ServerEnv()

        # Check defaults
        assert env.google_cloud_location == "global"
        assert env.log_level == "INFO"
        assert env.serve_web_interface is False
        assert env.reload_agents is False
        assert env.session_service_uri is None
        assert env.memory_service_uri is None
        assert env.artifact_service_uri is None
        assert env.allow_origins == '["http://127.0.0.1:8000", "http://localhost:8000"]'
        assert env.host == "127.0.0.1"
        assert env.port == 8000

    def test_server_env_optional_fields_with_values(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test setting optional fields with actual values."""
        data = {
            **valid_server_env,
            "GOOGLE_CLOUD_LOCATION": "us-west1",
            "AGENT_NAME": "custom-agent",
            "LOG_LEVEL": "DEBUG",
            "SERVE_WEB_INTERFACE": "true",
            "RELOAD_AGENTS": "true",
            "SESSION_SERVICE_URI": "postgresql+asyncpg://user@host:5432/db",
            "MEMORY_SERVICE_URI": "agentengine://projects/p/locations/l/reasoningEngines/123",
            "ARTIFACT_SERVICE_URI": "gs://test-bucket",
            "ALLOW_ORIGINS": '["http://localhost:3000"]',
            "HOST": "0.0.0.0",  # noqa: S104
            "PORT": "9000",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "NO_CONTENT",
        }

        isolated_environ(data)
        env = ServerEnv()

        assert env.google_cloud_location == "us-west1"
        assert env.agent_name == "custom-agent"
        assert env.log_level == "DEBUG"
        assert env.serve_web_interface is True
        assert env.reload_agents is True
        assert env.session_service_uri == "postgresql+asyncpg://user@host:5432/db"
        assert (
            env.memory_service_uri
            == "agentengine://projects/p/locations/l/reasoningEngines/123"
        )
        assert env.artifact_service_uri == "gs://test-bucket"
        assert env.allow_origins == '["http://localhost:3000"]'
        assert env.host == "0.0.0.0"  # noqa: S104
        assert env.port == 9000
        assert env.otel_instrumentation_genai_capture_message_content == "NO_CONTENT"

    @pytest.mark.parametrize(
        "value", ["NO_CONTENT", "EVENT_ONLY", "SPAN_ONLY", "SPAN_AND_EVENT"]
    )
    def test_content_capture_accepts_adk_modes(
        self, value: str, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that each ADK capture mode passes."""
        data = {
            **valid_server_env,
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": value,
        }
        isolated_environ(data)

        env = ServerEnv()

        assert env.otel_instrumentation_genai_capture_message_content == value

    @pytest.mark.parametrize("value", ["TRUE", "false", "event_only", ""])
    def test_content_capture_rejects_other_values(
        self, value: str, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that booleans and non-exact mode names fail validation."""
        data = {
            **valid_server_env,
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": value,
        }
        isolated_environ(data)

        with pytest.raises(ValidationError) as exc_info:
            ServerEnv()

        assert exc_info.value.errors()[0]["type"] == "literal_error"

    def test_allow_origins_list_property(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that allow_origins_list property parses JSON correctly."""
        data = {
            **valid_server_env,
            "ALLOW_ORIGINS": '["http://localhost:3000", "http://localhost:8080"]',
        }
        isolated_environ(data)
        env = ServerEnv()

        origins = env.allow_origins_list
        assert origins == ["http://localhost:3000", "http://localhost:8080"]

    def test_allow_origins_list_invalid_json_raises_error(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that invalid JSON raises ValidationError at model creation."""
        data = {**valid_server_env, "ALLOW_ORIGINS": "not valid json"}

        isolated_environ(data)
        with pytest.raises(ValidationError, match="ALLOW_ORIGINS must be valid JSON"):
            ServerEnv()

    def test_allow_origins_list_not_array_raises_error(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that non-array JSON raises ValidationError at model creation."""
        data = {**valid_server_env, "ALLOW_ORIGINS": '{"key": "value"}'}

        isolated_environ(data)
        with pytest.raises(ValidationError, match="ALLOW_ORIGINS must be a JSON array"):
            ServerEnv()

    def test_allow_origins_list_non_string_array_raises_error(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that array with non-strings raises ValidationError at model creation."""
        data = {**valid_server_env, "ALLOW_ORIGINS": "[123, 456]"}

        isolated_environ(data)
        with pytest.raises(
            ValidationError, match="ALLOW_ORIGINS must be an array of strings"
        ):
            ServerEnv()

    def test_allow_origins_list_empty_array_raises_error(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that empty array raises ValidationError at model creation."""
        data = {**valid_server_env, "ALLOW_ORIGINS": "[]"}

        isolated_environ(data)
        with pytest.raises(
            ValidationError, match="ALLOW_ORIGINS must contain at least one origin"
        ):
            ServerEnv()

    def test_allow_origins_array_with_empty_strings_raises_error(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that array containing empty strings raises ValidationError."""
        data = {**valid_server_env, "ALLOW_ORIGINS": '["", "http://localhost"]'}

        isolated_environ(data)
        with pytest.raises(
            ValidationError, match="ALLOW_ORIGINS must be an array of non-empty strings"
        ):
            ServerEnv()

    def test_allow_origins_array_with_mixed_types_raises_error(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that array with mixed types raises ValidationError."""
        data = {**valid_server_env, "ALLOW_ORIGINS": '["http://localhost", 123, null]'}

        isolated_environ(data)
        with pytest.raises(
            ValidationError, match="ALLOW_ORIGINS must be an array of strings"
        ):
            ServerEnv()

    def test_allow_origins_nested_arrays_raises_error(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that nested arrays raise ValidationError."""
        data = {**valid_server_env, "ALLOW_ORIGINS": '[["http://localhost"]]'}

        isolated_environ(data)
        with pytest.raises(
            ValidationError, match="ALLOW_ORIGINS must be an array of strings"
        ):
            ServerEnv()

    def test_server_env_print_config(
        self,
        valid_server_env: dict[str, str],
        isolated_environ,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that print_config outputs expected information."""
        isolated_environ(valid_server_env)
        env = ServerEnv()
        env.print_config()

        captured = capsys.readouterr()
        output = captured.out

        # Check key information is printed
        assert "test-project" in output
        assert "test-agent" in output
        assert "GOOGLE_CLOUD_PROJECT" in output
        assert "AGENT_NAME" in output
        assert "LOG_LEVEL" in output

    def test_server_env_ignores_extra_fields(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that extra environment variables are ignored."""
        data = {**valid_server_env, "EXTRA_VAR": "extra-value", "PATH": "/usr/bin"}

        isolated_environ(data)
        env = ServerEnv()
        assert env.google_cloud_project == "test-project"
        # Extra fields should not be included
        assert not hasattr(env, "EXTRA_VAR")
        assert not hasattr(env, "PATH")


COLLECTOR = "http://localhost:4317"
SIGNAL_COLLECTOR = "http://collector:4317"


class TestTelemetryEnv:
    """Tests for telemetry endpoint resolution and Cloud Run identity."""

    def test_defaults(self, isolated_environ) -> None:
        """Test local defaults: Google for traces and logs, no metrics."""
        isolated_environ({})

        env = TelemetryEnv()

        assert env.traces_endpoint == TELEMETRY_API_ENDPOINT
        assert env.logs_endpoint == TELEMETRY_API_ENDPOINT
        assert env.metrics_endpoint is None
        assert env.k_revision == "local"
        assert env.k_service is None

    @pytest.mark.parametrize("signal", ["TRACES", "LOGS", "METRICS"])
    @pytest.mark.parametrize(
        ("generic", "specific", "expected"),
        [
            (None, SIGNAL_COLLECTOR, SIGNAL_COLLECTOR),
            (COLLECTOR, None, COLLECTOR),
            (COLLECTOR, SIGNAL_COLLECTOR, SIGNAL_COLLECTOR),
            ("", "", None),
            (None, None, None),
        ],
    )
    def test_endpoint_resolution(
        self,
        signal: str,
        generic: str | None,
        specific: str | None,
        expected: str | None,
        isolated_environ,
    ) -> None:
        """Test signal var, then generic var, then the per-signal fallback."""
        variables = {}
        if generic is not None:
            variables["OTEL_EXPORTER_OTLP_ENDPOINT"] = generic
        if specific is not None:
            variables[f"OTEL_EXPORTER_OTLP_{signal}_ENDPOINT"] = specific
        isolated_environ(variables)

        env = TelemetryEnv()

        resolved = getattr(env, f"{signal.lower()}_endpoint")
        fallback = None if signal == "METRICS" else TELEMETRY_API_ENDPOINT
        assert resolved == (expected or fallback)

    def test_telemetry_api_endpoint_is_configurable(self, isolated_environ) -> None:
        """Test that TELEMETRY_API_ENDPOINT replaces the Google fallback."""
        isolated_environ({"TELEMETRY_API_ENDPOINT": "https://telemetry.example:443"})

        env = TelemetryEnv()

        assert env.traces_endpoint == "https://telemetry.example:443"
        assert env.logs_endpoint == "https://telemetry.example:443"

    def test_cloud_run_identity(self, isolated_environ) -> None:
        """Test that a complete Cloud Run environment validates."""
        isolated_environ(
            {
                "K_SERVICE": "svc",
                "K_REVISION": "svc-00001-abc",
                "K_CONFIGURATION": "svc",
                "CLOUD_RUN_REGION": "us-central1",
            }
        )

        env = TelemetryEnv()

        assert env.k_service == "svc"
        assert env.cloud_run_region == "us-central1"

    @pytest.mark.parametrize(
        "variables",
        [
            {"K_SERVICE": "svc", "CLOUD_RUN_REGION": "us-central1"},
            {"K_SERVICE": "svc", "K_CONFIGURATION": "svc"},
            {"K_SERVICE": "svc", "K_CONFIGURATION": "", "CLOUD_RUN_REGION": ""},
        ],
    )
    def test_partial_cloud_run_identity_fails(
        self, variables: dict[str, str], isolated_environ
    ) -> None:
        """Test that K_SERVICE without its labels fails fast."""
        isolated_environ(variables)

        with pytest.raises(
            ValidationError, match="K_CONFIGURATION and CLOUD_RUN_REGION"
        ):
            TelemetryEnv()

    def test_print_config(
        self, isolated_environ, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that each signal's destination and the identity are printed."""
        isolated_environ(
            {
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": COLLECTOR,
                "OTEL_RESOURCE_ATTRIBUTES": "service.namespace=alice-local",
            }
        )

        TelemetryEnv().print_config()

        output = capsys.readouterr().out
        assert "OTEL_RESOURCE_ATTRIBUTES: service.namespace=alice-local" in output
        assert f"TRACES ENDPOINT:       {COLLECTOR}" in output
        assert f"LOGS ENDPOINT:         {TELEMETRY_API_ENDPOINT}" in output
        assert (
            f"METRICS ENDPOINT:      {TELEMETRY_API_ENDPOINT} when cloud.region is set"
            in output
        )
        assert "K_SERVICE:             None" in output

    def test_print_config_when_disabled(
        self, isolated_environ, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that a disabled SDK prints no per-signal destinations."""
        isolated_environ(
            {"OTEL_SDK_DISABLED": "true", "OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR}
        )

        env = TelemetryEnv()
        env.print_config()

        output = capsys.readouterr().out
        assert env.otel_sdk_disabled is True
        assert "OTEL_SDK_DISABLED:     true (no telemetry export)" in output
        assert "TRACES ENDPOINT" not in output


class TestInitializeEnvironment:
    """Tests for the initialize_environment startup wrapper."""

    def test_initialize_environment_success(
        self, valid_server_env: dict[str, str], isolated_environ, mock_print_config
    ) -> None:
        """Test that both validated settings are returned and printed."""
        isolated_environ(valid_server_env)
        mock_print = mock_print_config(ServerEnv)
        mock_telemetry_print = mock_print_config(TelemetryEnv)

        env, telemetry_env = initialize_environment()

        assert env.google_cloud_project == "test-project"
        assert env.agent_name == "test-agent"
        assert telemetry_env.traces_endpoint == TELEMETRY_API_ENDPOINT
        mock_print.assert_called_once()
        mock_telemetry_print.assert_called_once()

    def test_initialize_environment_invalid_telemetry_exits(
        self,
        valid_server_env: dict[str, str],
        isolated_environ,
        mock_print_config,
        mock_sys_exit,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that an invalid telemetry environment exits 1 like ServerEnv does."""
        isolated_environ({**valid_server_env, "K_SERVICE": "svc"})
        mock_print_config(ServerEnv)

        with pytest.raises(SystemExit):
            initialize_environment()

        mock_sys_exit.assert_called_once_with(1)
        assert "CLOUD_RUN_REGION" in capsys.readouterr().out

    def test_initialize_environment_validation_failure_exits(
        self,
        isolated_environ,
        mock_sys_exit,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that invalid configuration prints the errors and exits 1."""
        isolated_environ({"AGENT_NAME": "test-agent"})

        with pytest.raises(SystemExit):
            initialize_environment()

        mock_sys_exit.assert_called_once_with(1)
        output = capsys.readouterr().out
        assert "Environment validation failed" in output
        assert "google_cloud_project" in output


class TestDotEnv:
    """Tests for .env loading and its precedence below the environment."""

    def test_env_file_supplies_values_absent_from_environment(
        self, isolated_environ, create_dotenv, mock_print_config
    ) -> None:
        """Test that .env fills in variables the environment does not set."""
        isolated_environ({})
        create_dotenv(
            "GOOGLE_CLOUD_PROJECT=dotenv-project\n"
            "AGENT_NAME=dotenv-agent\n"
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY\n"
        )
        mock_print_config(ServerEnv)

        env, _ = initialize_environment()

        assert env.google_cloud_project == "dotenv-project"
        assert env.agent_name == "dotenv-agent"
        assert env.otel_instrumentation_genai_capture_message_content == "SPAN_ONLY"

    def test_environment_wins_over_env_file(
        self,
        valid_server_env: dict[str, str],
        isolated_environ,
        create_dotenv,
        mock_print_config,
    ) -> None:
        """Test that a variable set in the shell beats the same key in .env."""
        isolated_environ({**valid_server_env, "LOG_LEVEL": "DEBUG"})
        create_dotenv("LOG_LEVEL=WARNING\nGOOGLE_CLOUD_PROJECT=dotenv-project\n")
        mock_print_config(ServerEnv)

        env, _ = initialize_environment()

        assert env.log_level == "DEBUG"
        assert env.google_cloud_project == "test-project"

    def test_env_file_values_reach_os_environ(
        self,
        valid_server_env: dict[str, str],
        isolated_environ,
        create_dotenv,
        mock_print_config,
    ) -> None:
        """Test that keys other readers own (ADK, the OTel SDK) land in os.environ."""
        isolated_environ(valid_server_env)
        create_dotenv("OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317\n")
        mock_print_config(ServerEnv)

        env, _ = initialize_environment()

        assert env.google_cloud_project == "test-project"
        assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4317"

    def test_env_file_reaches_telemetry_settings(
        self,
        valid_server_env: dict[str, str],
        isolated_environ,
        create_dotenv,
        mock_print_config,
    ) -> None:
        """Test that an OTLP endpoint set only in .env routes telemetry."""
        isolated_environ(valid_server_env)
        create_dotenv("OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317\n")
        mock_print_config(ServerEnv)
        mock_print_config(TelemetryEnv)

        _, telemetry_env = initialize_environment()

        assert telemetry_env.traces_endpoint == "http://localhost:4317"
        assert telemetry_env.metrics_endpoint == "http://localhost:4317"


class TestEdgeCases:
    """Tests for edge cases and field parsing."""

    def test_boolean_field_parsing(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that boolean fields parse correctly from strings.

        Pydantic accepts multiple truthy/falsy string representations for bool fields.
        This test documents all accepted patterns.
        """
        # Test truthy values
        for truthy in ["true", "True", "TRUE"]:
            data = {**valid_server_env, "SERVE_WEB_INTERFACE": truthy}
            isolated_environ(data)
            env = ServerEnv()
            assert env.serve_web_interface is True, f"Failed for: {truthy}"

        # Test more truthy values
        for truthy in ["1", "yes", "Yes", "on", "On", "t", "y", "Y"]:
            data = {**valid_server_env, "RELOAD_AGENTS": truthy}
            isolated_environ(data)
            env = ServerEnv()
            assert env.reload_agents is True, f"Failed for: {truthy}"

        # Test falsy values
        for falsy in ["false", "False", "FALSE"]:
            data = {**valid_server_env, "SERVE_WEB_INTERFACE": falsy}
            isolated_environ(data)
            env = ServerEnv()
            assert env.serve_web_interface is False, f"Failed for: {falsy}"

        # Test more falsy values
        for falsy in ["0", "no", "No", "off", "Off", "f", "n", "N"]:
            data = {**valid_server_env, "RELOAD_AGENTS": falsy}
            isolated_environ(data)
            env = ServerEnv()
            assert env.reload_agents is False, f"Failed for: {falsy}"

    def test_boolean_field_invalid_values_raise_errors(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that invalid boolean values raise ValidationError.

        Documents what string values are NOT accepted for bool fields.
        """
        # Test invalid values that should raise ValidationError
        invalid_values = [
            "",  # Empty string
            "maybe",  # Invalid word
            "2",  # Invalid number (only "0" and "1" work)
            "yep",  # Similar to "yes" but not accepted
            "nope",  # Similar to "no" but not accepted
            "enabled",  # Descriptive but not accepted
            "disabled",  # Descriptive but not accepted
            "ok",  # Common but not accepted
            "sure",  # Informal affirmative
            "nah",  # Informal negative
        ]

        for invalid in invalid_values:
            data = {**valid_server_env, "SERVE_WEB_INTERFACE": invalid}
            isolated_environ(data)
            with pytest.raises(ValidationError) as exc_info:
                ServerEnv()

            # Verify the error is about bool parsing
            errors = exc_info.value.errors()
            assert any(error["type"] == "bool_parsing" for error in errors), (
                f"Expected bool_parsing error for: {invalid}"
            )

    def test_port_field_parsing(
        self, valid_server_env: dict[str, str], isolated_environ
    ) -> None:
        """Test that port field parses integers from strings."""
        data = {**valid_server_env, "PORT": "9000"}

        isolated_environ(data)
        env = ServerEnv()
        assert env.port == 9000
        assert isinstance(env.port, int)
