"""Brain LangChain integration — failover-aware chat model."""

from .brain_types import ToolSpec, MemoryItem, ToolCall, BrainRequest
from .brain import brain, brain_with_retry, BrainConfig, BrainResponse
from .langchain_wrapper import BrainChatModel
from .api_manager.api_handler.data_store import APIStore
from .api_manager.sqlite_logger import (
    init_logging_schema,
    create_conversation,
    update_conversation,
    create_interactive,
    update_interactive,
    create_api_call,
    update_api_call,
    next_iteration_id,
    log_decide,
    log_wait,
    conversation_scope,
    interactive_scope,
)

__all__ = [
    "ToolSpec",
    "MemoryItem",
    "ToolCall",
    "BrainRequest",
    "brain",
    "brain_with_retry",
    "BrainConfig",
    "BrainResponse",
    "BrainChatModel",
    "APIStore",
    "init_logging_schema",
    "create_conversation",
    "update_conversation",
    "create_interactive",
    "update_interactive",
    "create_api_call",
    "update_api_call",
    "next_iteration_id",
    "log_decide",
    "log_wait",
    "conversation_scope",
    "interactive_scope",
]
