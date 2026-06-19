"""Unit tests for the callbacks module."""

import logging

import pytest

from agent_foundation.callbacks import add_session_to_memory


class TestAddSessionToMemory:
    """Tests for the add_session_to_memory callback function."""

    async def test_add_session_to_memory_success(
        self,
        mock_memory_callback_context,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback succeeds when context.add_session_to_memory succeeds."""
        caplog.set_level(logging.INFO)

        # Execute callback
        result = await add_session_to_memory(mock_memory_callback_context)

        # Verify callback returns None
        assert result is None

        # Verify add_session_to_memory was called on the context
        assert mock_memory_callback_context.add_session_to_memory_called

        # Verify logging
        assert "*** Starting add_session_to_memory callback ***" in caplog.text

    async def test_add_session_to_memory_handles_value_error(
        self,
        create_mock_memory_callback_context,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback handles ValueError (e.g., no memory service)."""
        caplog.set_level(logging.WARNING)
        ctx = create_mock_memory_callback_context(
            should_raise=ValueError,
            error_message=(
                "Cannot add session to memory: memory service is not available."
            ),
        )

        # Execute callback - should not raise
        result = await add_session_to_memory(ctx)

        # Verify callback returns None (doesn't propagate exception)
        assert result is None

        # Verify the method was attempted
        assert ctx.add_session_to_memory_called

        # Verify warning was logged
        assert (
            "Cannot add session to memory: memory service is not available."
            in caplog.text
        )

    async def test_add_session_to_memory_handles_attribute_error(
        self,
        create_mock_memory_callback_context,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback handles AttributeError gracefully."""
        caplog.set_level(logging.WARNING)
        ctx = create_mock_memory_callback_context(
            should_raise=AttributeError,
            error_message="'MockMemoryCallbackContext' has no invocation context",
        )

        # Execute callback - should not raise
        result = await add_session_to_memory(ctx)

        # Verify callback returns None
        assert result is None

        # Verify the method was attempted
        assert ctx.add_session_to_memory_called

        # Verify warning was logged with exception details
        assert "Failed to add session to memory" in caplog.text
        assert "AttributeError" in caplog.text

    async def test_add_session_to_memory_handles_runtime_error(
        self,
        create_mock_memory_callback_context,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback handles RuntimeError gracefully."""
        caplog.set_level(logging.WARNING)
        ctx = create_mock_memory_callback_context(
            should_raise=RuntimeError,
            error_message="Memory service connection failed",
        )

        # Execute callback - should not raise
        result = await add_session_to_memory(ctx)

        # Verify callback returns None (doesn't propagate exception)
        assert result is None

        # Verify the method was attempted
        assert ctx.add_session_to_memory_called

        # Verify warning was logged with exception details
        assert "Failed to add session to memory" in caplog.text
        assert "RuntimeError" in caplog.text
        assert "Memory service connection failed" in caplog.text

    async def test_add_session_to_memory_logging_levels(
        self,
        mock_memory_callback_context,
        create_mock_memory_callback_context,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback uses appropriate logging levels."""
        # Test case 1: Success (INFO level)
        caplog.set_level(logging.INFO)
        caplog.clear()

        await add_session_to_memory(mock_memory_callback_context)

        # Check for INFO log (starting callback)
        info_records = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_records) == 1
        assert "Starting add_session_to_memory" in info_records[0].message

        # Test case 2: ValueError (WARNING level)
        caplog.set_level(logging.WARNING)
        caplog.clear()

        await add_session_to_memory(
            create_mock_memory_callback_context(
                should_raise=ValueError,
                error_message=(
                    "Cannot add session to memory: memory service is not available."
                ),
            )
        )

        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) == 1
        assert (
            "Cannot add session to memory: memory service is not available."
            in warning_records[0].message
        )

    async def test_add_session_to_memory_returns_none(
        self,
        mock_memory_callback_context,
    ) -> None:
        """Test that callback always returns None."""
        # Execute callback
        result = await add_session_to_memory(mock_memory_callback_context)

        # Verify callback returns None (doesn't short-circuit)
        assert result is None

    async def test_add_session_to_memory_multiple_calls(
        self,
        create_mock_memory_callback_context,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback can be called multiple times."""
        caplog.set_level(logging.INFO)

        # Create multiple contexts
        ctx1 = create_mock_memory_callback_context()
        ctx2 = create_mock_memory_callback_context()

        # Execute callbacks
        result1 = await add_session_to_memory(ctx1)
        result2 = await add_session_to_memory(ctx2)

        # Verify both completed successfully
        assert result1 is None
        assert result2 is None
        assert ctx1.add_session_to_memory_called
        assert ctx2.add_session_to_memory_called

        # Verify both were logged
        info_records = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_records) == 2
