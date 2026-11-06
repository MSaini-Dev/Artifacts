"""Specialist agent definitions and always-available control tools."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import OrchestrationConfig
from .registry import RegisteredTool, ToolRegistry, tool_spec

ApprovalCallback = Callable[[RegisteredTool, Dict[str, Any]], bool]


@dataclass
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    max_steps: int
    tool_scope: str
    sandbox_root: Optional[str] = None
    approval_callback: Optional[ApprovalCallback] = None


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, AgentSpec] = {}

    def register(self, agent: AgentSpec) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Agent {agent.name!r} is already registered.")
        if agent.max_steps < 1:
            raise ValueError("Agent max_steps must be at least one.")
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentSpec:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"Unknown agent: {name}") from exc

    def all(self) -> List[AgentSpec]:
        return list(self._agents.values())


def register_core_tools(
    registry: ToolRegistry,
    agent_name: str,
    config: Optional[OrchestrationConfig] = None,
) -> None:
    """Register finish, ask_user, and a scoped tool-search meta-tool."""
    settings = config or OrchestrationConfig.from_env()

    def finish(summary: str, artifacts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return {"summary": summary, "artifacts": artifacts or []}

    def ask_user(question: str) -> Dict[str, str]:
        return {"question": question}

    def search_tools(query: str) -> List[Dict[str, Any]]:
        matches = registry.search_matches(
            query,
            agent_name,
            k=settings.retrieval_k,
            threshold=settings.retrieval_threshold,
        )
        return [
            {
                "name": item.name,
                "description": item.spec.description,
                "parameters": item.spec.parameters,
                "score": item.score,
            }
            for item in matches
        ]

    registered_names = {
        item.spec.name for item in registry.tools_for_agent(agent_name)
    }
    if "finish" not in registered_names:
        registry.register(
            tool_spec(
                "finish",
                "Finish this sub-task. Provide a concise summary and any typed artifacts.",
                {
                    "summary": {"type": "string"},
                    "artifacts": {"type": "array", "items": {"type": "object"}},
                },
                ["summary"],
            ),
            agent_name,
            finish,
        )
    if "ask_user" not in registered_names:
        registry.register(
            tool_spec(
                "ask_user",
                "Ask the user for missing information required to continue.",
                {"question": {"type": "string"}},
                ["question"],
            ),
            agent_name,
            ask_user,
        )
    if "search_tools" not in registered_names:
        registry.register(
            tool_spec(
                "search_tools",
                "Search for additional tools available within your own specialist scope.",
                {"query": {"type": "string"}},
                ["query"],
            ),
            agent_name,
            search_tools,
        )


def initial_agents(
    working_directory: str,
    max_steps: int = 6,
    approval_callback: Optional[ApprovalCallback] = None,
) -> AgentRegistry:
    """Return the initial Google and local-coder agent definitions."""
    root = str(Path(working_directory).resolve())
    agents = AgentRegistry()
    agents.register(
        AgentSpec(
            name="google_cloud",
            description="Google services: search and download Drive files, Gmail, Calendar, and Google Cloud Storage.",
            system_prompt=(
                "You are the Google Cloud specialist. Use only supplied tools and only the task prompt. "
                "Do not invent file IDs or claim external actions succeeded without tool evidence. "
                "Use finish with typed artifacts when complete; use ask_user if required information is missing."
            ),
            max_steps=max_steps,
            tool_scope="google_cloud",
            sandbox_root=root,
            approval_callback=approval_callback,
        )
    )
    agents.register(
        AgentSpec(
            name="coder",
            description="Local coding and file tasks: read files and run approved scripts within the workspace.",
            system_prompt=(
                "You are the local coder specialist. Use only supplied tools and only the task prompt. "
                "Respect the workspace restriction. Report concrete outputs and use finish with typed artifacts."
            ),
            max_steps=max_steps,
            tool_scope="coder",
            sandbox_root=root,
            approval_callback=approval_callback,
        )
    )
    return agents


def core_tool_names() -> set:
    return {"finish", "ask_user", "search_tools"}
