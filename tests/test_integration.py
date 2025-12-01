"""Integration tests for agent configuration and component wiring.

This module contains integration tests that verify how components work together.
Unlike unit tests, these tests validate end-to-end behavior and configuration.

Future: Container-based smoke tests for CI/CD will be added here.
"""

from datetime import date

from conftest import MockReadonlyContext

from adk_docker_uv import root_agent
from adk_docker_uv.prompt import return_global_instruction


class TestInstructionProviderIntegration:
    """Integration tests for InstructionProvider pattern wiring."""

    def test_agent_uses_instruction_provider_callable(self) -> None:
        """Verify agent is configured with callable InstructionProvider, not string."""
        # Agent should have callable global_instruction (not static string)
        assert callable(root_agent.global_instruction)
        assert root_agent.global_instruction == return_global_instruction

    def test_instruction_provider_works_with_agent_context(self) -> None:
        """Verify InstructionProvider can be invoked with ReadonlyContext."""
        # Create context matching what ADK would pass
        ctx = MockReadonlyContext(
            agent_name=root_agent.name,
            invocation_id="integration-test-123",
            state={"test": "integration"},
        )

        # Invoke the provider (simulating ADK's call)
        instruction = root_agent.global_instruction(ctx)

        # Verify it returns valid instruction
        assert isinstance(instruction, str)
        assert len(instruction) > 0

    def test_instruction_includes_dynamic_date(self) -> None:
        """Verify InstructionProvider generates instructions with current date."""
        ctx = MockReadonlyContext(agent_name=root_agent.name)

        instruction = root_agent.global_instruction(ctx)

        # Verify dynamic date injection
        today = str(date.today())
        assert today in instruction
        assert "Today's date:" in instruction

    def test_instruction_includes_expected_content(self) -> None:
        """Verify InstructionProvider generates expected base instruction."""
        ctx = MockReadonlyContext(agent_name=root_agent.name)

        instruction = root_agent.global_instruction(ctx)

        # Verify expected content
        assert "helpful Assistant" in instruction
        assert "Today's date:" in instruction

    def test_agent_configuration_completeness(self) -> None:
        """Verify agent has all expected configuration elements."""
        # Verify agent has name (should be non-empty string)
        assert root_agent.name is not None
        assert isinstance(root_agent.name, str)
        assert len(root_agent.name) > 0

        # Verify agent has model configured
        assert root_agent.model is not None
        assert "gemini" in root_agent.model.lower()

        # Verify agent has tools
        assert root_agent.tools is not None
        assert len(root_agent.tools) > 0

        # Verify agent has instruction provider
        assert callable(root_agent.global_instruction)
