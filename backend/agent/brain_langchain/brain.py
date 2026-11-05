"""
Brain — single-shot orchestration: validate → size-rank model → call API → failover.
"""

import os
import logging
from typing import Dict, Any, Optional, List

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional when configuration is supplied by the host
    def load_dotenv() -> bool:
        return False

from .api_manager.call_api import call_api
from .api_manager.api_handler.data_store import APIStore
from .brain_types import ToolSpec, MemoryItem, inject_memories

logger = logging.getLogger(__name__)
load_dotenv()


class BrainConfig:
    def __init__(self):
        self.is_testing = self._parse_bool_env("BRAIN_TESTING_IS", False)
        self.use_llm = self._parse_bool_env("CALL_LLM_IS", True)
        self.use_api = self._parse_bool_env("CALL_API_IS", True)
        self.max_retries = int(os.getenv("BRAIN_MAX_RETRIES", "3"))
        self.timeout = int(os.getenv("BRAIN_TIMEOUT", "60"))

    @staticmethod
    def _parse_bool_env(key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "y")

    @classmethod
    def from_env(cls) -> "BrainConfig":
        return cls()


class BrainResponse:
    def __init__(self):
        self.error_status: bool = False
        self.error_message: Optional[str] = None
        self.test_status: Optional[bool] = None
        self.iteration_status: bool = False
        self.llm_status: Optional[bool] = None
        self.llm_success: Optional[bool] = None
        self.llm_response: Optional[str] = None
        self.api_status: Optional[bool] = None
        self.api_success: Optional[bool] = None
        self.api_response: Optional[str] = None
        self.tool_calls: Optional[List[Dict[str, Any]]] = None
        self.api_iterations: Optional[list] = None
        self.total_attempts: int = 0
        self.total_duration_ms: int = 0
        self.chosen: Optional[Dict[str, str]] = None
        self.conversation_id: Optional[int] = None
        self.interactive_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_status": self.error_status,
            "error_message": self.error_message,
            "test_status": self.test_status,
            "iteration_status": self.iteration_status,
            "llm_status": self.llm_status,
            "llm_success": self.llm_success,
            "llm_response": self.llm_response,
            "api_status": self.api_status,
            "api_success": self.api_success,
            "api_response": self.api_response,
            "tool_calls": self.tool_calls,
            "api_iterations": self.api_iterations,
            "total_attempts": self.total_attempts,
            "total_duration_ms": self.total_duration_ms,
            "chosen": self.chosen,
            "conversation_id": self.conversation_id,
            "interactive_id": self.interactive_id,
        }

    @classmethod
    def error(cls, message: str) -> "BrainResponse":
        r = cls()
        r.error_status = True
        r.error_message = message
        return r

    @classmethod
    def test_mode(cls) -> "BrainResponse":
        r = cls()
        r.test_status = True
        return r


def validate_inputs(
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    tools: Optional[List[ToolSpec]] = None,
    memories: Optional[List[MemoryItem]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if messages is not None:
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list of dicts")
        for i, m in enumerate(messages):
            if not isinstance(m, dict) or "role" not in m:
                raise ValueError(f"messages[{i}] must be a dict with a 'role' field")
    else:
        if not user_prompt or not isinstance(user_prompt, str):
            raise ValueError("user_prompt must be a non-empty string")
        if not system_prompt or not isinstance(system_prompt, str):
            raise ValueError("system_prompt must be a non-empty string")
        if len(user_prompt) > 100000:
            raise ValueError("user_prompt exceeds maximum length of 100000 characters")
        if len(system_prompt) > 50000:
            raise ValueError("system_prompt exceeds maximum length of 50000 characters")
    if tools is not None:
        if not isinstance(tools, list):
            raise ValueError("tools must be a list of ToolSpec or None")
        for i, t in enumerate(tools):
            if not isinstance(t, ToolSpec):
                raise ValueError(f"tools[{i}] must be a ToolSpec instance")
            if not t.name or not isinstance(t.name, str):
                raise ValueError(f"tools[{i}].name must be a non-empty string")
            if not isinstance(t.parameters, dict):
                raise ValueError(f"tools[{i}].parameters must be a dict")
    if memories is not None:
        if not isinstance(memories, list):
            raise ValueError("memories must be a list of MemoryItem or None")
        for i, m in enumerate(memories):
            if not isinstance(m, MemoryItem):
                raise ValueError(f"memories[{i}] must be a MemoryItem instance")
            if not m.content or not isinstance(m.content, str):
                raise ValueError(f"memories[{i}].content must be a non-empty string")


def brain(
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    tools: Optional[List[ToolSpec]] = None,
    memories: Optional[List[MemoryItem]] = None,
    store: Optional[APIStore] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    key_name: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    buffer: int = 0,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    buffer (seconds): max wait for a rate-limited key/provider.
      cooldown <= buffer → wait and retry same key
      cooldown >  buffer → skip key and switch API immediately
    Default 0 = never wait, always switch.
    """
    try:
        validate_inputs(user_prompt, system_prompt, tools, memories, messages=messages)
    except ValueError as e:
        logger.error("Input validation failed: %s", e)
        return BrainResponse.error(str(e)).to_dict()

    config = BrainConfig.from_env()
    logger.info(
        "Brain init testing=%s llm=%s api=%s buffer=%s",
        config.is_testing, config.use_llm, config.use_api, buffer,
    )

    if config.is_testing:
        return BrainResponse.test_mode().to_dict()

    response = BrainResponse()
    response.llm_status = config.use_llm
    response.api_status = config.use_api

    if not config.use_api:
        return BrainResponse.error("API calls are disabled by configuration").to_dict()

    enriched_system = inject_memories(system_prompt, memories) if system_prompt else None

    try:
        result = call_api(
            user_prompt=user_prompt,
            system_prompt=enriched_system,
            tools=tools,
            store=store,
            provider=provider,
            model=model,
            key_name=key_name,
            temperature=temperature,
            max_tokens=max_tokens,
            buffer=buffer,
            messages=messages,
        )


        response.api_success = result.get("status", False)
        response.api_response = result.get("response")
        response.tool_calls = result.get("tool_calls")
        response.api_iterations = result.get("api_iterations", [])
        response.total_attempts = result.get("total_attempts", 0)
        response.total_duration_ms = result.get("total_duration_ms", 0)
        response.chosen = result.get("chosen")
        response.conversation_id = result.get("conversation_id")
        response.interactive_id = result.get("interactive_id")
        response.iteration_status = True

        if response.api_success:
            logger.info("API success after %s attempts", response.total_attempts)
            return response.to_dict()

        error_msg = result.get("error", "All API attempts failed")
        logger.warning("API failed: %s", error_msg)
        response.error_status = True
        response.error_message = error_msg
        return response.to_dict()

    except Exception as e:
        error_msg = f"Unexpected error in brain: {e}"
        logger.error(error_msg, exc_info=True)
        return BrainResponse.error(error_msg).to_dict()


def brain_with_retry(
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    tools: Optional[List[ToolSpec]] = None,
    memories: Optional[List[MemoryItem]] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    messages: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    import time

    last_error = None
    config = BrainConfig.from_env()
    if not config.use_api:
        return brain(user_prompt, system_prompt, tools=tools, memories=memories, messages=messages, **kwargs)

    for attempt in range(max_retries):
        try:
            result = brain(user_prompt, system_prompt, tools=tools, memories=memories, messages=messages, **kwargs)
            if not result.get("error_status", True) and result.get("api_success", False):
                return result
            error_msg = result.get("error_message", "")
            if "disabled by configuration" in error_msg.lower():
                return result
            last_error = error_msg
            logger.warning("Retry %s/%s failed: %s", attempt + 1, max_retries, error_msg)
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))

    return BrainResponse.error(
        f"All {max_retries} retry attempts failed. Last error: {last_error}"
    ).to_dict()
