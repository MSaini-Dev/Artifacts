"""
langchain_wrapper.py — production BaseChatModel that routes every call through
Brain / call_api so you get automatic provider → model → key failover.

Usage with LangChain agents:

    from backend.agent.brain_langchain import BrainChatModel
    from langchain.agents import create_agent   # or create_react_agent / create_tool_calling_agent

    llm = BrainChatModel(temperature=0.7, buffer=0, max_tokens=4096)
    agent = create_agent(model=llm, tools=[...])
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field, PrivateAttr

from .api_manager.api_handler.data_store import APIStore
from .brain import brain
from .brain_types import ToolSpec

logger = logging.getLogger(__name__)


def _tool_args_schema_to_parameters(args_schema: Any) -> Dict[str, Any]:
    """Convert a Pydantic args schema into the OpenAI-style parameter map."""
    if args_schema is None:
        return {"type": "object", "properties": {}}

    schema = None
    if hasattr(args_schema, "model_json_schema"):
        try:
            schema = args_schema.model_json_schema()
        except TypeError:
            schema = None
    if schema is None and hasattr(args_schema, "schema"):
        try:
            schema = args_schema.schema()
        except TypeError:
            schema = None
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    parameters: Dict[str, Any] = {
        "type": schema.get("type", "object"),
        "properties": schema.get("properties", {}),
    }
    if "required" in schema:
        parameters["required"] = schema["required"]
    return parameters


def _lc_tools_to_specs(
    tools: Optional[Sequence[Union[BaseTool, ToolSpec, Dict[str, Any]]]]
) -> Optional[List[ToolSpec]]:
    """Convert LangChain tools / dicts / ToolSpec into our ToolSpec list."""
    if not tools:
        return None
    out: List[ToolSpec] = []
    for t in tools:
        if isinstance(t, ToolSpec):
            out.append(t)
            continue
        if isinstance(t, BaseTool):
            params = getattr(t, "args_schema", None)
            parameters = _tool_args_schema_to_parameters(params)
            out.append(
                ToolSpec(
                    name=t.name,
                    description=t.description or "",
                    parameters=parameters,
                )
            )
            continue
        if isinstance(t, dict):
            # Already OpenAI-style or raw ToolSpec-like
            if t.get("type") == "function" and "function" in t:
                fn = t["function"]
                out.append(
                    ToolSpec(
                        name=fn.get("name", ""),
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters") or {"type": "object", "properties": {}},
                    )
                )
            else:
                out.append(
                    ToolSpec(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        parameters=t.get("parameters") or {"type": "object", "properties": {}},
                    )
                )
            continue
        raise TypeError(f"Unsupported tool type: {type(t)}")
    return out


def _messages_to_prompts(messages: Sequence[BaseMessage]) -> tuple[str, str]:
    """
    Collapse a LangChain message list into (system_prompt, user_prompt).

    Strategy:
      - Concatenate all SystemMessage contents into system_prompt.
      - Everything else (Human / AI / Tool) is serialised into a single
        user_prompt so multi-turn history is preserved for providers that
        only accept a flat system+user pair (our current HTTP layer).
    """
    system_parts: List[str] = []
    transcript: List[str] = []

    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_parts.append(str(msg.content or ""))
        elif isinstance(msg, HumanMessage):
            transcript.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            content = msg.content or ""
            # Surface prior tool calls so the model can continue the loop
            tool_calls = getattr(msg, "tool_calls", None) or msg.additional_kwargs.get(
                "tool_calls"
            )
            if tool_calls:
                transcript.append(
                    f"Assistant: {content}\n[tool_calls]: {json.dumps(tool_calls, default=str)}"
                )
            else:
                transcript.append(f"Assistant: {content}")
        elif isinstance(msg, ToolMessage):
            transcript.append(
                f"Tool({getattr(msg, 'name', '') or msg.tool_call_id}): {msg.content}"
            )
        else:
            transcript.append(f"User: {getattr(msg, 'content', str(msg))}")

    system_prompt = "\n\n".join(p for p in system_parts if p).strip() or (
        "You are a helpful assistant."
    )
    user_prompt = "\n\n".join(transcript).strip()
    if not user_prompt:
        # Degenerate case: only system messages were supplied
        user_prompt = system_prompt
        system_prompt = "You are a helpful assistant."
    return system_prompt, user_prompt


def _lc_messages_to_openai_messages(messages: Sequence[BaseMessage]) -> List[Dict[str, Any]]:
    """
    Convert LangChain message objects into structured OpenAI chat completions messages,
    preserving separate roles: system, user, assistant (with tool_calls), and tool.
    """
    formatted: List[Dict[str, Any]] = []
    seen_non_system = False

    for msg in messages:
        if isinstance(msg, SystemMessage):
            content = str(msg.content or "")
            if not seen_non_system:
                formatted.append({"role": "system", "content": content})
            else:
                formatted.append({"role": "user", "content": f"[System]: {content}"})
        elif isinstance(msg, HumanMessage):
            seen_non_system = True
            formatted.append({"role": "user", "content": str(msg.content or "")})
        elif isinstance(msg, AIMessage):
            seen_non_system = True
            m: Dict[str, Any] = {
                "role": "assistant",
                "content": str(msg.content) if msg.content else None,
            }
            raw_tc = getattr(msg, "tool_calls", None) or msg.additional_kwargs.get("tool_calls") or []
            if raw_tc:
                formatted_tc = []
                for i, tc in enumerate(raw_tc):
                    if isinstance(tc, dict):
                        tc_id = tc.get("id") or f"call_{i}"
                        fn_obj = tc.get("function")
                        if isinstance(fn_obj, dict):
                            fn_name = fn_obj.get("name") or tc.get("name") or ""
                            fn_args = fn_obj.get("arguments") or tc.get("args") or {}
                        else:
                            fn_name = tc.get("name") or ""
                            fn_args = tc.get("args") or {}
                    else:
                        tc_id = getattr(tc, "id", f"call_{i}")
                        fn_name = getattr(tc, "name", "")
                        fn_args = getattr(tc, "args", {}) or {}

                    if isinstance(fn_args, (dict, list)):
                        args_str = json.dumps(fn_args, ensure_ascii=False)
                    elif isinstance(fn_args, str):
                        args_str = fn_args
                    else:
                        args_str = str(fn_args)

                    formatted_tc.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": args_str,
                        },
                    })
                    tool_call_extras = msg.additional_kwargs.get("tool_call_extras") or {}
                    if tc_id in tool_call_extras:
                        formatted_tc[-1]["extra_content"] = tool_call_extras[tc_id]
                m["tool_calls"] = formatted_tc
            formatted.append(m)
        elif isinstance(msg, ToolMessage):
            seen_non_system = True
            tool_msg: Dict[str, Any] = {
                "role": "tool",
                "tool_call_id": str(msg.tool_call_id or getattr(msg, "id", "") or f"call_{len(formatted)}"),
                "content": str(msg.content or ""),
            }
            if getattr(msg, "name", None):
                tool_msg["name"] = msg.name
            formatted.append(tool_msg)
        else:
            seen_non_system = True
            role = getattr(msg, "type", "user")
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            formatted.append({
                "role": role,
                "content": str(getattr(msg, "content", "")),
            })

    return formatted


def _tool_calls_to_lc(raw: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Normalise provider tool_calls into the modern LangChain / OpenAI shape:

        [{"id": "...", "name": "...", "args": {...}}]
    """
    if not raw:
        return []
    normalised: List[Dict[str, Any]] = []
    for tc in raw:
        if not isinstance(tc, dict):
            continue
        name = tc.get("name") or (tc.get("function") or {}).get("name") or ""
        args = tc.get("arguments")
        if args is None:
            args = tc.get("args")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"_raw": args}
        normalised.append(
            {
                "id": tc.get("id") or "",
                "name": name,
                "args": args,
            }
        )
    return normalised


class BrainChatModel(BaseChatModel):
    """
    LangChain chat model backed by the Brain failover stack.

    Every invocation runs through ``brain()`` / ``call_api()`` which:
      * ranks active (provider, model, key) by model size (+ soft TPM fit)
      * fails over on rate-limit / 401 / 402 / 404 / 413 / 5xx / timeout
      * persists cooldowns & disables into api_data.json

    Parameters
    ----------
    temperature, max_tokens
        Forwarded to the underlying provider.
    buffer
        Seconds we are willing to *wait* for a rate-limited key before
        switching. 0 = never wait (always switch). Matches ``call_api``.
    provider / model / key_name
        Optional hard pin for the first attempt; failover still applies
        if that target is unavailable.
    store
        Optional shared ``APIStore`` instance (useful for tests / multi-tenant).
    """

    temperature: float = 0.7
    max_tokens: Optional[int] = None
    buffer: int = 0
    provider: Optional[str] = None
    model: Optional[str] = None
    key_name: Optional[str] = None

    # Private / non-serialised state
    _store: Optional[APIStore] = PrivateAttr(default=None)
    _bound_tools: Optional[List[Any]] = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        buffer: int = 0,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        key_name: Optional[str] = None,
        store: Optional[APIStore] = None,
        **kwargs: Any,
    ):
        super().__init__(
            temperature=temperature,
            max_tokens=max_tokens,
            buffer=buffer,
            provider=provider,
            model=model,
            key_name=key_name,
            **kwargs,
        )
        self._store = store
        self._bound_tools = None

    # ------------------------------------------------------------------ identity

    @property
    def _llm_type(self) -> str:
        return "brain-failover-chat"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "buffer": self.buffer,
            "provider": self.provider,
            "model": self.model,
            "key_name": self.key_name,
        }

    # ------------------------------------------------------------------ tools

    def bind_tools(
        self,
        tools: Sequence[Union[BaseTool, ToolSpec, Dict[str, Any]]],
        **kwargs: Any,
    ) -> "BrainChatModel":
        """
        Return a *new* instance with tools bound (LangChain convention).
        Does not mutate ``self``.
        """
        clone = self.__class__(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            buffer=self.buffer,
            provider=self.provider,
            model=self.model,
            key_name=self.key_name,
            store=self._store,
        )
        clone._bound_tools = list(tools)
        return clone

    # ------------------------------------------------------------------ core

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_prompt, user_prompt = _messages_to_prompts(messages)
        openai_messages = _lc_messages_to_openai_messages(messages)

        tools_raw = kwargs.get("tools") or self._bound_tools
        tool_specs = _lc_tools_to_specs(tools_raw)

        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        buffer = kwargs.get("buffer", self.buffer)
        provider = kwargs.get("provider", self.provider)
        model = kwargs.get("model", self.model)
        key_name = kwargs.get("key_name", self.key_name)

        # stop sequences are not universally supported; we ignore them for now
        # but keep the parameter so LangChain callers don't break.
        if stop:
            logger.debug("stop sequences requested but ignored by BrainChatModel: %s", stop)

        result = brain(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            tools=tool_specs,
            store=self._store,
            provider=provider,
            model=model,
            key_name=key_name,
            temperature=float(temperature),
            max_tokens=max_tokens,
            buffer=int(buffer or 0),
            messages=openai_messages,
        )

        if result.get("error_status") or not result.get("api_success"):
            err = result.get("error_message") or result.get("error") or "Brain call failed"
            # Attach iteration diagnostics so upstream agents / tracers can inspect
            iterations = result.get("api_iterations") or []
            raise ValueError(
                f"BrainChatModel failed after {result.get('total_attempts', 0)} attempt(s): {err}"
                + (f" | last={iterations[-1]}" if iterations else "")
            )

        content = result.get("api_response") or ""
        lc_tool_calls = _tool_calls_to_lc(result.get("tool_calls"))

        additional: Dict[str, Any] = {
            "provider": (result.get("chosen") or {}).get("provider"),
            "model": (result.get("chosen") or {}).get("model"),
            "key_name": (result.get("chosen") or {}).get("key_name"),
            "total_attempts": result.get("total_attempts"),
            "total_duration_ms": result.get("total_duration_ms"),
            "api_iterations": result.get("api_iterations"),
            "conversation_id": result.get("conversation_id"),
            "interactive_id": result.get("interactive_id"),
            "iteration_id": result.get("iteration_id"),
        }
        tool_call_extras = {
            tc.get("id") or "": tc["extra_content"]
            for tc in (result.get("tool_calls") or [])
            if isinstance(tc, dict) and tc.get("extra_content") is not None
        }
        if tool_call_extras:
            additional["tool_call_extras"] = tool_call_extras
        # Keep a legacy key some older LangChain code still inspects
        if lc_tool_calls:
            additional["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in lc_tool_calls
            ]

        message = AIMessage(
            content=content,
            tool_calls=lc_tool_calls,
            additional_kwargs=additional,
        )
        generation = ChatGeneration(message=message)
        return ChatResult(
            generations=[generation],
            llm_output={
                "chosen": result.get("chosen"),
                "total_attempts": result.get("total_attempts"),
                "total_duration_ms": result.get("total_duration_ms"),
            },
        )

    # Optional async path — run the sync implementation in a thread so
    # LangChain async agents don't block the event loop on HTTP.
    async def _agenerate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        import asyncio

        return await asyncio.to_thread(
            self._generate, messages, stop=stop, run_manager=run_manager, **kwargs
        )
