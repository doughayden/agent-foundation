"""Shared pytest fixtures for all tests."""

from typing import Any

import pytest


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

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize content to dictionary."""
        return self._data


class MockSession:
    """Mock ADK Session for testing."""

    def __init__(self, user_id: str = "test_user_123") -> None:
        """Initialize mock session with user_id."""
        self.user_id = user_id


class MockMemoryService:
    """Mock ADK MemoryService for testing."""

    def __init__(self) -> None:
        """Initialize mock memory service."""
        self.add_session_calls: list[MockSession] = []  # Track calls for testing

    async def add_session_to_memory(self, session: MockSession) -> None:
        """Mock adding session to memory.

        Args:
            session: The session to add to memory.
        """
        self.add_session_calls.append(session)


class MockInvocationContext:
    """Mock ADK InvocationContext for testing."""

    def __init__(
        self,
        session: MockSession | None = None,
        memory_service: MockMemoryService | None = None,
    ) -> None:
        """Initialize mock invocation context with optional session and memory service.

        Args:
            session: Optional mock session.
            memory_service: Optional mock memory service.
        """
        self.session = session
        self.memory_service = memory_service


class MockLocationCallbackContext:
    """Mock CallbackContext for location context loading.

    Used by load_location_context callback for testing.
    """

    def __init__(
        self,
        state: dict[str, Any] | None = None,
        invocation_context: MockInvocationContext | None = None,
    ) -> None:
        """Initialize mock callback context for location loading.

        Args:
            state: Initial state dictionary (defaults to empty dict).
            invocation_context: Optional invocation context with session.
        """
        self.state = state if state is not None else {}
        self._invocation_context = invocation_context


class MockMemoryCallbackContext:
    """Mock CallbackContext for memory service callbacks.

    Used by add_session_to_memory callback for testing.
    """

    def __init__(self, invocation_context: MockInvocationContext | None = None) -> None:
        """Initialize mock callback context for memory callbacks.

        Args:
            invocation_context: Optional invocation context with memory service.
        """
        self._invocation_context = invocation_context


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

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
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
            session: Optional session object.
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
def mock_location_callback_context() -> MockLocationCallbackContext:
    """Create a mock location callback context with session for testing."""
    session = MockSession(user_id="test_user_123")
    invocation_context = MockInvocationContext(session=session)
    return MockLocationCallbackContext(state={}, invocation_context=invocation_context)


@pytest.fixture
def mock_location_callback_context_no_session() -> MockLocationCallbackContext:
    """Create a mock location callback context without session for testing."""
    return MockLocationCallbackContext(state={})


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
    mock_state: MockState,
    mock_content: MockContent,
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
def mock_base_tool() -> MockBaseTool:
    """Create a mock tool with default name."""
    return MockBaseTool(name="test_tool")


@pytest.fixture
def mock_memory_service() -> MockMemoryService:
    """Create a mock memory service for testing."""
    return MockMemoryService()


@pytest.fixture
def mock_memory_callback_context(
    mock_memory_service: MockMemoryService,
) -> MockMemoryCallbackContext:
    """Create a mock memory callback context with memory service."""
    session = MockSession(user_id="test_user_456")
    invocation_context = MockInvocationContext(
        session=session, memory_service=mock_memory_service
    )
    return MockMemoryCallbackContext(invocation_context=invocation_context)


@pytest.fixture
def mock_memory_callback_context_no_service() -> MockMemoryCallbackContext:
    """Create a mock memory callback context without memory service."""
    session = MockSession(user_id="test_user_789")
    invocation_context = MockInvocationContext(session=session, memory_service=None)
    return MockMemoryCallbackContext(invocation_context=invocation_context)


@pytest.fixture
def mock_memory_callback_context_no_invocation() -> MockMemoryCallbackContext:
    """Create a mock memory callback context without invocation context."""
    return MockMemoryCallbackContext(invocation_context=None)


@pytest.fixture
def mock_readonly_context() -> MockReadonlyContext:
    """Create a mock readonly context for InstructionProvider testing."""
    return MockReadonlyContext(
        agent_name="instruction_test_agent",
        invocation_id="readonly-inv-123",
        state={"user_tier": "premium", "language": "en"},
    )
