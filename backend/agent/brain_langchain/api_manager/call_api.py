"""
call_api.py — SQLite DB-backed size-ranked failover across providers/models/keys.
"""

import logging
import socket
from typing import Dict, Any, Optional, List

from .api_caller import api_caller
from ..brain_types import ToolSpec, tool_specs_to_openai

logger = logging.getLogger(__name__)


def _check_internet_connection() -> bool:
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=2) as sock:
            return sock is not None
    except OSError:
        return False


def call_api(
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    tools: Optional[List[ToolSpec]] = None,
    store: Optional[Any] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    key_name: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    buffer: int = 0,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Main entry point for API calls backed by SQLite database API_Store.db.
    """
    if not _check_internet_connection():
        logger.error("No internet connection")
        error_msg = "No internet connection available"
        return {
            "status": False,
            "success": False,
            "response": None,
            "tool_calls": None,
            "error": error_msg,
            "api_iterations": [],
            "total_duration_ms": 0,
            "total_attempts": 0,
            "chosen": None,
        }

    tools_openai = tool_specs_to_openai(tools) if tools else None

    data: Dict[str, Any] = {
        "user_prompt": user_prompt,
        "system_prompt": system_prompt,
        "tools": tools_openai,
        "temperature": temperature,
        "max_tokens": max_tokens or 4096,
    }
    if messages:
        data["messages"] = messages

    result = api_caller(
        data=data,
        target_provider=provider,
        target_model=model,
        target_key_name=key_name,
    )

    return result
