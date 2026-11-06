"""Tool-RAG sub-agent loop using the existing Brain function."""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..brain import brain
from ..brain_types import ToolSpec
from .agents import AgentSpec, core_tool_names
from .config import OrchestrationConfig
from .observability import log_event
from .registry import RegisteredTool, ToolRegistry

logger = logging.getLogger(__name__)
BrainCallable = Callable[..., Dict[str, Any]]


@dataclass
class AgentResult:
    status: str
    summary: str
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    steps_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "artifacts": self.artifacts,
            "error": self.error,
            "steps_used": self.steps_used,
        }


class SubAgentRunner:
    def __init__(
        self,
        registry: ToolRegistry,
        config: Optional[OrchestrationConfig] = None,
        brain_callable: Optional[BrainCallable] = None,
    ):
        self.registry = registry
        self.config = config or OrchestrationConfig.from_env()
        self.brain = brain_callable or brain

    def run(self, sub_prompt: str, agent: AgentSpec) -> AgentResult:
        history: List[Dict[str, Any]] = [{"role": "user", "content": sub_prompt}]
        active_specs: Dict[str, ToolSpec] = {}
        requested_specs: Dict[str, ToolSpec] = {}
        called_tools: List[str] = []
        latest_retrieval: List[str] = []
        total_tool_steps = 0

        for call_number in range(1, agent.max_steps + 1):
            query = sub_prompt
            if history and len(history) > 1:
                query += "\nRecent tool result:\n" + str(history[-1].get("content", ""))
            matches = self.registry.search_matches(
                query,
                agent.tool_scope,
                k=self.config.retrieval_k,
                threshold=self.config.retrieval_threshold,
            )
            latest_retrieval = [item.name for item in matches]
            active_specs = {
                item.name: item.spec for item in matches
                if item.name not in core_tool_names()
            }
            active_specs.update(requested_specs)
            core_specs = [
                item.spec for item in self.registry.tools_for_agent(agent.tool_scope)
                if item.spec.name in core_tool_names()
            ]
            tools = core_specs + list(active_specs.values())
            visible_names = {tool.name for tool in tools}
            result = self._brain_call(
                agent=agent.name,
                phase="subagent",
                call_number=call_number,
                system_prompt=agent.system_prompt,
                tools=tools,
                messages=history,
            )
            if result.get("error_status") or result.get("api_success") is False:
                message = str(
                    result.get("error_message")
                    or result.get("api_response")
                    or "Brain call failed."
                )
                return AgentResult("error", "", error=message, steps_used=call_number)

            calls = result.get("tool_calls") or []
            if not calls:
                text = result.get("api_response")
                if text is None:
                    return AgentResult(
                        "error", "", error="Brain returned neither text nor tool calls.",
                        steps_used=call_number,
                    )
                return AgentResult("ok", str(text), steps_used=call_number)

            history.append(
                {
                    "role": "assistant",
                    "content": result.get("api_response") or "",
                    "tool_calls": [self._assistant_tool_call(item) for item in calls],
                }
            )
            for call in calls:
                name = str(call.get("name", ""))
                call_id = str(call.get("id") or f"call_{total_tool_steps}")
                arguments = call.get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {"_raw": arguments}
                called_tools.append(name)
                total_tool_steps += 1

                if name == "finish":
                    summary = str(arguments.get("summary", ""))
                    artifacts = arguments.get("artifacts") or []
                    log_event(
                        "subagent_tools",
                        {
                            "agent": agent.name,
                            "retrieved_tools": latest_retrieval,
                            "called_tools": called_tools,
                        },
                    )
                    return AgentResult(
                        "ok",
                        summary,
                        artifacts if isinstance(artifacts, list) else [],
                        steps_used=call_number,
                    )
                if name == "ask_user":
                    question = str(arguments.get("question", ""))
                    return AgentResult(
                        "needs_input",
                        question,
                        error=None,
                        steps_used=call_number,
                    )

                try:
                    if name not in visible_names:
                        raise PermissionError(f"Tool {name!r} was not retrieved for this agent.")
                    tool_result = self._dispatch(agent, name, arguments)
                    is_search = name == "search_tools"
                    if is_search:
                        for item in self.registry.search_matches(
                            str(arguments.get("query", "")),
                            agent.tool_scope,
                            k=self.config.retrieval_k,
                            threshold=self.config.retrieval_threshold,
                        ):
                            requested_specs[item.name] = item.spec
                    content = json.dumps(tool_result, ensure_ascii=False, default=str)
                except Exception as exc:
                    logger.exception("Tool %s failed for agent %s.", name, agent.name)
                    content = json.dumps({"error": str(exc)}, ensure_ascii=False)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": content,
                    }
                )

            log_event(
                "subagent_tools",
                {
                    "agent": agent.name,
                    "retrieved_tools": latest_retrieval,
                    "called_tools": called_tools,
                },
            )

        return AgentResult(
            "error",
            "",
            error=f"Agent exceeded max_steps={agent.max_steps}.",
            steps_used=agent.max_steps,
        )

    def _dispatch(self, agent: AgentSpec, name: str, arguments: Dict[str, Any]) -> Any:
        registered = self.registry.handler(name, agent.tool_scope)
        if self._requires_approval(registered):
            if agent.approval_callback is None or not agent.approval_callback(registered, arguments):
                raise PermissionError(f"Approval denied or unavailable for tool {name!r}.")
        return registered.handler(**arguments)

    @staticmethod
    def _requires_approval(tool: RegisteredTool) -> bool:
        name = tool.spec.name.lower()
        return (
            tool.requires_approval
            or "delete" in name
            or "shell" in name
            or "execute" in name
            or name.startswith("exec")
        )

    def _brain_call(
        self,
        agent: str,
        phase: str,
        call_number: int,
        system_prompt: str,
        tools: Sequence[ToolSpec],
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = self.brain(
                system_prompt=system_prompt,
                tools=list(tools),
                messages=messages,
            )
        except Exception as exc:
            response = {"error_status": True, "error_message": str(exc)}
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            "brain_call",
            {
                "phase": phase,
                "agent": agent,
                "call_number": call_number,
                "latency_ms": latency_ms,
                "attempts": response.get("total_attempts", 0),
                "retrieved_tools": [tool.name for tool in tools],
                "error": response.get("error_message"),
            },
        )
        return response

    @staticmethod
    def _assistant_tool_call(call: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(call.get("id", "")),
            "type": "function",
            "function": {
                "name": str(call.get("name", "")),
                "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
            },
        }
