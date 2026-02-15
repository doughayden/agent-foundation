"""Shared pytest fixtures for all tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pytest_mock import MockerFixture, MockType


def pytest_configure(config: pytest.Config) -> None:
    """Pytest hook to set up environment before test collection.

    IMPORTANT: This hook runs BEFORE pytest's plugin system is fully initialized,
    including pytest-mock. We must use unittest.mock.patch here because:

    1. This hook runs before test collection
    2. Test collection imports test modules, which imports agent_foundation modules
    3. Agent modules may trigger API calls during import (auth, config loading)
    4. pytest-mock's mocker/session_mocker fixtures aren't available until AFTER
       test collection completes

    Pytest execution order:
    - pytest_configure() ← We are here (only stdlib available)
    - Test collection (imports happen, triggers API calls if not mocked)
    - Session setup (fixtures become available)
    - Test execution

    Therefore, unittest.mock is the ONLY tool available at this stage. This is
    the only place in the codebase where unittest.mock is used - all other mocking
    (fixtures and tests) uses pytest-mock's mocker fixture.
    """
    from unittest.mock import Mock, patch

    # Patch load_dotenv to prevent loading real .env file during module imports
    load_dotenv_patcher = patch("dotenv.load_dotenv")
    load_dotenv_patcher.start()

    # Patch google.auth.default to prevent Application Default Credentials lookup
    mock_credentials = Mock()
    mock_credentials.token = "test-mock-token-totally-not-real"  # noqa: S105
    mock_credentials.valid = True
    mock_credentials.expired = False
    mock_credentials.refresh = Mock()
    mock_credentials.universe_domain = "googleapis.com"

    # Patch both public and private auth paths (ADK uses private path internally)
    auth_patcher = patch(
        "google.auth.default", return_value=(mock_credentials, "test-project")
    )
    auth_patcher.start()

    auth_private_patcher = patch(
        "google.auth._default.default", return_value=(mock_credentials, "test-project")
    )
    auth_private_patcher.start()

    # Set test environment variables before any imports occur
    # Use direct assignment (not setdefault) since we're preventing .env loading
    import os

    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
    os.environ["AGENT_NAME"] = "test-agent"
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"


# ADK Callback Mock Objects for testing callbacks
class MockState:
    """Mock State object for ADK callback testing.

    Supports both dictionary-style access and to_dict() method
    to match ADK's state interface.
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Initialize mock state with optional data."""
        self._data = data if data is not None else {}

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        """Get item from state with optional default."""
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        """Get item using dictionary syntax."""
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Set item using dictionary syntax."""
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        """Check if key exists in state."""
        return key in self._data


class MockContent:
    """Mock Content object for ADK callback testing.

    Used for user_content and llm_content in callbacks.
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Initialize mock content with optional data."""
        self._data = data if data is not None else {"text": "test content"}

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        """Serialize content to dictionary."""
        return self._data


class MockSession:
    """Mock ADK Session for testing.

    Minimal mock used by MockReadonlyContext.
    """

    def __init__(self, user_id: str = "test_user_123") -> None:
        """Initialize mock session with user_id."""
        self.user_id = user_id


class MockMemoryCallbackContext:
    """Minimal mock CallbackContext for add_session_to_memory callback testing.

    Controls behavior through constructor parameters instead of rebuilding
    ADK's internal logic. This keeps tests independent of ADK implementation.
    """

    def __init__(
        self,
        should_raise: type[Exception] | None = None,
        error_message: str = "",
    ) -> None:
        """Initialize mock callback context with controlled behavior.

        Args:
            should_raise: Exception type to raise when add_session_to_memory is called.
                         None means the call succeeds.
            error_message: Message for the exception if should_raise is set.
        """
        self._should_raise = should_raise
        self._error_message = error_message
        self.add_session_to_memory_called = False

    async def add_session_to_memory(self) -> None:
        """Mock implementation that either succeeds or raises controlled exception.

        Raises:
            Exception: The exception type configured in __init__ if should_raise is set.
        """
        self.add_session_to_memory_called = True
        if self._should_raise:
            raise self._should_raise(self._error_message)


class MockLoggingCallbackContext:
    """Mock CallbackContext for LoggingCallbacks testing.

    Used for agent and model callbacks testing.
    """

    def __init__(
        self,
        agent_name: str = "test_agent",
        invocation_id: str = "test-invocation-123",
        state: MockState | None = None,
        user_content: MockContent | None = None,
    ) -> None:
        """Initialize mock callback context for logging callbacks."""
        self.agent_name = agent_name
        self.invocation_id = invocation_id
        self.state = state if state is not None else MockState()
        self.user_content = user_content


class MockLlmRequest:
    """Mock LlmRequest for model callbacks."""

    def __init__(self, contents: list[MockContent] | None = None) -> None:
        """Initialize mock LLM request."""
        if contents is None:
            contents = [
                MockContent({"text": "system prompt"}),
                MockContent({"text": "user message"}),
            ]
        self.contents = contents


class MockLlmResponse:
    """Mock LlmResponse for model callbacks."""

    def __init__(self, content: MockContent | None = None) -> None:
        """Initialize mock LLM response."""
        self.content = content


class MockEventActions:
    """Mock EventActions for tool callbacks."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Initialize mock event actions."""
        self._data = data if data is not None else {"action": "execute"}

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        """Serialize actions to dictionary."""
        return self._data


class MockToolContext:
    """Mock ToolContext for tool callbacks."""

    def __init__(
        self,
        agent_name: str = "test_agent",
        invocation_id: str = "test-invocation-456",
        state: MockState | None = None,
        user_content: MockContent | None = None,
        actions: MockEventActions | None = None,
    ) -> None:
        """Initialize mock tool context."""
        self.agent_name = agent_name
        self.invocation_id = invocation_id
        self.state = state if state is not None else MockState()
        self.user_content = user_content
        self.actions = actions if actions is not None else MockEventActions()


class MockBaseTool:
    """Mock BaseTool for tool callbacks."""

    def __init__(self, name: str = "test_tool") -> None:
        """Initialize mock tool."""
        self.name = name


class MockReadonlyContext:
    """Mock ReadonlyContext for testing InstructionProvider functions.

    Provides read-only access to invocation metadata and session state,
    matching the interface of google.adk.agents.readonly_context.ReadonlyContext.

    To customize user_id, pass a MockSession with the desired user_id:
        MockReadonlyContext(session=MockSession(user_id="custom_user"))
    """

    def __init__(
        self,
        agent_name: str = "test_agent",
        invocation_id: str = "test-inv-readonly",
        state: dict[str, Any] | None = None,
        user_content: MockContent | None = None,
        session: MockSession | None = None,
    ) -> None:
        """Initialize mock readonly context.

        Args:
            agent_name: Name of the agent.
            invocation_id: ID of the current invocation.
            state: Session state dictionary (read-only).
            user_content: Optional user content that started the invocation.
            session: Optional session object. If not provided, creates MockSession
                     with default user_id.
        """
        self._agent_name = agent_name
        self._invocation_id = invocation_id
        self._state = state if state is not None else {}
        self._user_content = user_content
        self._session = session if session is not None else MockSession()

    @property
    def agent_name(self) -> str:
        """The name of the agent that is currently running."""
        return self._agent_name

    @property
    def invocation_id(self) -> str:
        """The current invocation id."""
        return self._invocation_id

    @property
    def state(self) -> dict[str, Any]:
        """The state of the current session (read-only)."""
        return self._state.copy()  # Return a copy to enforce read-only

    @property
    def user_content(self) -> MockContent | None:
        """The user content that started this invocation."""
        return self._user_content

    @property
    def session(self) -> MockSession:
        """The current session for this invocation."""
        return self._session

    @property
    def user_id(self) -> str:
        """The user ID from the current session."""
        return self._session.user_id


# Fixtures for ADK callback testing
@pytest.fixture
def mock_state() -> MockState:
    """Create a mock state with test data."""
    return MockState({"user_id": "user123", "session_data": {"key": "value"}})


@pytest.fixture
def mock_content() -> MockContent:
    """Create a mock content with test data."""
    return MockContent({"text": "Hello, agent!"})


@pytest.fixture
def mock_logging_callback_context(
    mock_state: MockState, mock_content: MockContent
) -> MockLoggingCallbackContext:
    """Create a mock logging callback context with full data."""
    return MockLoggingCallbackContext(
        agent_name="my_agent",
        invocation_id="inv-789",
        state=mock_state,
        user_content=mock_content,
    )


@pytest.fixture
def mock_llm_request() -> MockLlmRequest:
    """Create a mock LLM request with default messages."""
    return MockLlmRequest(
        contents=[
            MockContent({"text": "system prompt"}),
            MockContent({"text": "user message"}),
        ]
    )


@pytest.fixture
def mock_llm_response() -> MockLlmResponse:
    """Create a mock LLM response with content."""
    return MockLlmResponse(
        content=MockContent({"text": "The answer is 42", "confidence": 0.95})
    )


@pytest.fixture
def mock_event_actions() -> MockEventActions:
    """Create mock event actions with test data."""
    return MockEventActions({"action": "run", "params": ["arg1", "arg2"]})


@pytest.fixture
def mock_tool_context(
    mock_event_actions: MockEventActions,
) -> MockToolContext:
    """Create a mock tool context with full data."""
    return MockToolContext(
        agent_name="tool_agent",
        invocation_id="tool-inv-123",
        state=MockState({"tool_state": "active"}),
        user_content=MockContent({"text": "Execute tool"}),
        actions=mock_event_actions,
    )


@pytest.fixture
def mock_tool_context_empty_state(
    mock_event_actions: MockEventActions,
) -> MockToolContext:
    """Create a mock tool context with empty state."""
    return MockToolContext(
        agent_name="tool_agent",
        invocation_id="tool-inv-empty",
        state=MockState({}),
        user_content=MockContent({"text": "Execute tool"}),
        actions=mock_event_actions,
    )


@pytest.fixture
def mock_base_tool() -> MockBaseTool:
    """Create a mock tool with default name."""
    return MockBaseTool(name="test_tool")


@pytest.fixture
def mock_memory_callback_context() -> MockMemoryCallbackContext:
    """Create a mock callback context that succeeds."""
    return MockMemoryCallbackContext()


@pytest.fixture
def mock_memory_callback_context_no_service() -> MockMemoryCallbackContext:
    """Create a mock callback context that raises ValueError (no service)."""
    return MockMemoryCallbackContext(
        should_raise=ValueError,
        error_message="Cannot add session to memory: memory service is not available.",
    )


@pytest.fixture
def mock_memory_callback_context_with_runtime_error() -> MockMemoryCallbackContext:
    """Create a mock callback context that raises RuntimeError."""
    return MockMemoryCallbackContext(
        should_raise=RuntimeError,
        error_message="Memory service connection failed",
    )


@pytest.fixture
def mock_memory_callback_context_with_attribute_error() -> MockMemoryCallbackContext:
    """Create a mock callback context that raises AttributeError."""
    return MockMemoryCallbackContext(
        should_raise=AttributeError,
        error_message="'MockMemoryCallbackContext' has no invocation context",
    )


@pytest.fixture
def mock_readonly_context() -> MockReadonlyContext:
    """Create a mock readonly context for InstructionProvider testing."""
    return MockReadonlyContext(
        agent_name="instruction_test_agent",
        invocation_id="readonly-inv-123",
        state={"user_tier": "premium", "language": "en"},
    )


# Config testing fixtures
@pytest.fixture
def valid_server_env() -> dict[str, str]:
    """Valid environment variables for ServerEnv model.

    Returns:
        Dictionary with minimal required fields for ServerEnv.
    """
    return {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "AGENT_NAME": "test-agent",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
    }


# Note: clean_environment fixture removed because pytest_configure now sets
# all test environment variables and prevents .env loading. Test isolation is
# achieved by explicit test values set at session start.


@pytest.fixture
def mock_load_dotenv(mocker: MockerFixture) -> MockType:
    """Mock load_dotenv function for testing.

    Returns:
        Mock object for load_dotenv function.
    """
    return mocker.patch("agent_foundation.utils.config.load_dotenv")


@pytest.fixture
def mock_sys_exit(mocker: MockerFixture) -> MockType:
    """Mock sys.exit with SystemExit side effect for testing validation failures.

    Returns:
        Mock object for sys.exit that raises SystemExit(1).
    """
    return mocker.patch("sys.exit", side_effect=SystemExit(1))


@pytest.fixture
def mock_print_config(mocker: MockerFixture) -> Callable[[type], MockType]:
    """Factory fixture for mocking print_config on any model class.

    Returns:
        Function that patches print_config on a given model class.
    """

    def _mock_print_config(model_class: type) -> MockType:
        """Patch print_config on a model class.

        Args:
            model_class: The Pydantic model class to mock print_config on.

        Returns:
            Mock object for the print_config method.
        """
        return mocker.patch.object(model_class, "print_config", autospec=True)

    return _mock_print_config
