"""Unit tests for the callbacks module."""

import logging

import pytest

# Import mock classes from conftest
from conftest import (
    MockInvocationContext,
    MockMemoryCallbackContext,
    MockMemoryService,
    MockSession,
)

from adk_docker_uv.callbacks import (
    add_session_to_memory,
)


class TestAddSessionToMemory:
    """Tests for the add_session_to_memory callback function."""

    @pytest.mark.asyncio
    async def test_add_session_to_memory_saves_session(
        self,
        mock_memory_callback_context: MockMemoryCallbackContext,
        mock_memory_service: MockMemoryService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback saves session when memory service exists."""
        # Setup logging to capture DEBUG level
        caplog.set_level(logging.DEBUG)

        # Execute callback
        result = await add_session_to_memory(mock_memory_callback_context)

        # Verify callback returns None (proceeds normally)
        assert result is None

        # Verify add_session_to_memory was called on the memory service
        assert len(mock_memory_service.add_session_calls) == 1
        saved_session = mock_memory_service.add_session_calls[0]
        assert saved_session.user_id == "test_user_456"

        # Verify logging
        assert "*** Started add_session_to_memory callback ***" in caplog.text
        assert "Adding session to memory using MockMemoryService" in caplog.text

    @pytest.mark.asyncio
    async def test_add_session_to_memory_no_service(
        self,
        mock_memory_callback_context_no_service: MockMemoryCallbackContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback handles missing memory service gracefully."""
        # Setup logging to capture WARNING level
        caplog.set_level(logging.WARNING)

        # Execute callback - should not raise
        result = await add_session_to_memory(mock_memory_callback_context_no_service)

        # Verify callback returns None
        assert result is None

        # Verify warning was logged
        assert "No memory_service found in _invocation_context" in caplog.text

    @pytest.mark.asyncio
    async def test_add_session_to_memory_no_invocation_context(
        self,
        mock_memory_callback_context_no_invocation: MockMemoryCallbackContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback handles missing invocation context gracefully."""
        # Setup logging to capture DEBUG level
        caplog.set_level(logging.DEBUG)

        # Execute callback - should not raise AttributeError
        result = await add_session_to_memory(mock_memory_callback_context_no_invocation)

        # Verify callback returns None
        assert result is None

        # Verify debug log was created (callback started)
        assert "*** Started add_session_to_memory callback ***" in caplog.text

        # Verify no warning about missing service (hasattr check prevents this path)
        assert "No memory_service found" not in caplog.text

    @pytest.mark.asyncio
    async def test_add_session_to_memory_with_different_sessions(
        self,
        mock_memory_service: MockMemoryService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback correctly handles different sessions."""
        # Setup logging
        caplog.set_level(logging.DEBUG)

        # Create callback contexts with different sessions
        session1 = MockSession(user_id="user_001")
        session2 = MockSession(user_id="user_002")

        invocation_context1 = MockInvocationContext(
            session=session1, memory_service=mock_memory_service
        )
        invocation_context2 = MockInvocationContext(
            session=session2, memory_service=mock_memory_service
        )

        callback_context1 = MockMemoryCallbackContext(
            invocation_context=invocation_context1
        )
        callback_context2 = MockMemoryCallbackContext(
            invocation_context=invocation_context2
        )

        # Execute callbacks
        await add_session_to_memory(callback_context1)
        await add_session_to_memory(callback_context2)

        # Verify both sessions were saved
        assert len(mock_memory_service.add_session_calls) == 2
        assert mock_memory_service.add_session_calls[0].user_id == "user_001"
        assert mock_memory_service.add_session_calls[1].user_id == "user_002"

    @pytest.mark.asyncio
    async def test_add_session_to_memory_logging_levels(
        self,
        mock_memory_callback_context: MockMemoryCallbackContext,
        mock_memory_callback_context_no_service: MockMemoryCallbackContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback uses appropriate logging levels."""
        # Test case 1: Saving session (DEBUG level)
        caplog.set_level(logging.DEBUG)
        caplog.clear()

        await add_session_to_memory(mock_memory_callback_context)

        # Check for DEBUG logs
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(debug_records) == 2  # Started and adding messages
        assert any("Started add_session_to_memory" in r.message for r in debug_records)
        assert any("Adding session to memory" in r.message for r in debug_records)

        # Test case 2: No service (WARNING level)
        caplog.set_level(logging.WARNING)
        caplog.clear()

        await add_session_to_memory(mock_memory_callback_context_no_service)

        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) == 1
        assert "No memory_service found" in warning_records[0].message

    @pytest.mark.asyncio
    async def test_add_session_to_memory_returns_none(
        self,
        mock_memory_callback_context: MockMemoryCallbackContext,
    ) -> None:
        """Test that callback always returns None."""
        # Execute callback
        result = await add_session_to_memory(mock_memory_callback_context)

        # Verify callback returns None (doesn't short-circuit)
        assert result is None

    @pytest.mark.asyncio
    async def test_add_session_to_memory_handles_async_call(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that callback properly awaits async memory service call."""
        # Setup logging
        caplog.set_level(logging.DEBUG)

        # Create a real async mock for the memory service
        mock_service = MockMemoryService()
        session = MockSession(user_id="async_user")
        invocation_context = MockInvocationContext(
            session=session, memory_service=mock_service
        )
        callback_context = MockMemoryCallbackContext(
            invocation_context=invocation_context
        )

        # Execute callback (await completes successfully)
        result = await add_session_to_memory(callback_context)

        # Verify callback completed successfully
        assert result is None
        assert len(mock_service.add_session_calls) == 1
        assert mock_service.add_session_calls[0].user_id == "async_user"

    @pytest.mark.asyncio
    async def test_add_session_to_memory_handles_service_exceptions(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that callback handles exceptions from memory service gracefully."""
        # Setup logging to capture WARNING level
        caplog.set_level(logging.WARNING)

        # Create a mock memory service that raises an exception
        class FailingMockMemoryService:
            """Mock memory service that always fails."""

            async def add_session_to_memory(self, session: MockSession) -> None:
                """Raise an exception when called."""
                raise RuntimeError("Memory service connection failed")

        failing_service = FailingMockMemoryService()
        session = MockSession(user_id="test_user_fail")
        invocation_context = MockInvocationContext(
            session=session,
            memory_service=failing_service,
        )
        callback_context = MockMemoryCallbackContext(
            invocation_context=invocation_context
        )

        # Execute callback - should not raise
        result = await add_session_to_memory(callback_context)

        # Verify callback returns None (doesn't propagate exception)
        assert result is None

        # Verify warning was logged with exception details
        assert "Failed to add session to memory" in caplog.text
        assert "RuntimeError" in caplog.text
        assert "Memory service connection failed" in caplog.text

        # Verify WARNING level was used
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) == 1
