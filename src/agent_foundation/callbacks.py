"""Agent lifecycle callback functions for monitoring and memory.

This module provides callback functions that execute at various stages of the
agent lifecycle. These callbacks enable comprehensive logging and session
memory persistence.
"""

import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import ToolContext
from google.adk.tools.base_tool import BaseTool
from opentelemetry import trace

logger = logging.getLogger(__name__)


async def add_session_to_memory(callback_context: CallbackContext) -> None:
    """Automatically save completed sessions to memory bank.

    This callback checks if the invocation context has a memory service.
    If so, it saves the session to memory for future retrieval.

    Args:
        callback_context: The callback context with access to invocation context
    """
    logger.info("*** Starting add_session_to_memory callback ***")
    try:
        await callback_context.add_session_to_memory()
    except ValueError as e:
        logger.warning(e)
    except Exception as e:
        logger.warning(f"Failed to add session to memory: {type(e).__name__}: {e}")

    return


class LoggingCallbacks:
    """Provides observability callbacks for ADK agent lifecycle events.

    This class groups all agent lifecycle callback methods together and supports
    logger injection following the strategy pattern. Covers both logging
    and trace enrichment (e.g., token usage span attributes). All
    callbacks are non-intrusive and return None.

    Attributes:
        logger: Logger instance for recording agent lifecycle events.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize logging callbacks with optional logger.

        Args:
            logger: Optional logger instance. If not provided, creates one
                   using the module name.
        """
        if logger is None:
            logger = logging.getLogger(self.__class__.__module__)
        self.logger = logger

    def before_agent(self, callback_context: CallbackContext) -> None:
        """Callback executed before agent processing begins.

        Args:
            callback_context (CallbackContext): Context containing agent name,
                invocation ID, state, and user content.
        """
        self.logger.info(
            f"*** Starting agent '{callback_context.agent_name}' "
            f"with invocation_id '{callback_context.invocation_id}' ***"
        )
        self.logger.debug(f"State keys: {callback_context.state.to_dict().keys()}")

        if user_content := callback_context.user_content:
            content_data = user_content.model_dump(exclude_none=True, mode="json")
            self.logger.debug(f"User Content: {content_data}")

        return

    def after_agent(self, callback_context: CallbackContext) -> None:
        """Callback executed after agent processing completes.

        Args:
            callback_context (CallbackContext): Context containing agent name,
                invocation ID, state, and user content.
        """
        self.logger.info(
            f"*** Leaving agent '{callback_context.agent_name}' "
            f"with invocation_id '{callback_context.invocation_id}' ***"
        )
        self.logger.debug(f"State keys: {callback_context.state.to_dict().keys()}")

        if user_content := callback_context.user_content:
            content_data = user_content.model_dump(exclude_none=True, mode="json")
            self.logger.debug(f"User Content: {content_data}")

        return

    def before_model(
        self,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> None:
        """Callback executed before LLM model invocation.

        Args:
            callback_context (CallbackContext): Context containing agent name,
                invocation ID, state, and user content.
            llm_request (LlmRequest): The request being sent to the LLM model
                containing message contents.
        """
        self.logger.info(
            f"*** Before LLM call for agent '{callback_context.agent_name}' "
            f"with invocation_id '{callback_context.invocation_id}' ***"
        )
        self.logger.debug(f"State keys: {callback_context.state.to_dict().keys()}")

        if user_content := callback_context.user_content:
            content_data = user_content.model_dump(exclude_none=True, mode="json")
            self.logger.debug(f"User Content: {content_data}")

        self.logger.debug(f"LLM request contains {len(llm_request.contents)} messages:")
        for i, content in enumerate(llm_request.contents, start=1):
            self.logger.debug(
                f"Content {i}: {content.model_dump(exclude_none=True, mode='json')}"
            )

        return

    def after_model(
        self,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> None:
        """Callback executed after LLM model responds.

        Args:
            callback_context (CallbackContext): Context containing agent name,
                invocation ID, state, and user content.
            llm_response (LlmResponse): The response received from the LLM model.
        """
        self.logger.info(
            f"*** After LLM call for agent '{callback_context.agent_name}' "
            f"with invocation_id '{callback_context.invocation_id}' ***"
        )
        self.logger.debug(f"State keys: {callback_context.state.to_dict().keys()}")

        if user_content := callback_context.user_content:
            content_data = user_content.model_dump(exclude_none=True, mode="json")
            self.logger.debug(f"User Content: {content_data}")

        if llm_content := llm_response.content:
            response_data = llm_content.model_dump(exclude_none=True, mode="json")
            self.logger.debug(f"LLM response: {response_data}")

        if usage := llm_response.usage_metadata:
            token_info: dict[str, int] = {
                key: value
                for key, value in {
                    "prompt_tokens": usage.prompt_token_count,
                    "response_tokens": usage.candidates_token_count,
                    "total_tokens": usage.total_token_count,
                    "cached_tokens": usage.cached_content_token_count,
                }.items()
                if value is not None
            }
            if token_info:
                self.logger.info(f"Token usage: {token_info}")

            span = trace.get_current_span()
            if usage.cached_content_token_count is not None:
                span.set_attribute(
                    "gen_ai.usage.experimental.cached_tokens",
                    usage.cached_content_token_count,
                )
            if usage.total_token_count is not None:
                span.set_attribute(
                    "gen_ai.usage.experimental.total_tokens",
                    usage.total_token_count,
                )

        return

    def before_tool(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> None:
        """Callback executed before tool invocation.

        Args:
            tool (BaseTool): The tool being invoked.
            args (dict[str, Any]): Arguments being passed to the tool.
            tool_context (ToolContext): Context containing agent name, invocation ID,
                state, user content, and event actions.
        """
        self.logger.info(
            f"*** Before invoking tool '{tool.name}' in agent "
            f"'{tool_context.agent_name}' with invocation_id "
            f"'{tool_context.invocation_id}' ***"
        )
        self.logger.debug(f"State keys: {tool_context.state.to_dict().keys()}")

        if content := tool_context.user_content:
            self.logger.debug(
                f"User Content: {content.model_dump(exclude_none=True, mode='json')}"
            )

        actions_data = tool_context.actions.model_dump(exclude_none=True, mode="json")
        self.logger.debug(f"EventActions: {actions_data}")
        self.logger.debug(f"args: {args}")

        return

    def after_tool(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
        tool_response: dict[str, Any],
    ) -> None:
        """Callback executed after tool invocation completes.

        Args:
            tool (BaseTool): The tool that was invoked.
            args (dict[str, Any]): Arguments that were passed to the tool.
            tool_context (ToolContext): Context containing agent name, invocation ID,
                state, user content, and event actions.
            tool_response (dict[str, Any]): The response returned by the tool.
        """
        self.logger.info(
            f"*** After invoking tool '{tool.name}' in agent "
            f"'{tool_context.agent_name}' with invocation_id "
            f"'{tool_context.invocation_id}' ***"
        )
        self.logger.debug(f"State keys: {tool_context.state.to_dict().keys()}")

        if content := tool_context.user_content:
            self.logger.debug(
                f"User Content: {content.model_dump(exclude_none=True, mode='json')}"
            )

        actions_data = tool_context.actions.model_dump(exclude_none=True, mode="json")
        self.logger.debug(f"EventActions: {actions_data}")
        self.logger.debug(f"args: {args}")
        self.logger.debug(f"Tool response: {tool_response}")

        return
