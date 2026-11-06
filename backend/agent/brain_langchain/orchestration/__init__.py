"""Tool-RAG orchestration built on the existing Brain call path."""

from pathlib import Path
from typing import Any, Optional

from .agents import AgentRegistry, AgentSpec, ApprovalCallback, initial_agents, register_core_tools
from .config import OrchestrationConfig
from .example_tools import build_default_registry, register_example_tools
from .orchestrator import Orchestrator, PlanError, PlanStep
from .registry import (
    Embedder,
    FaissFlatVectorStore,
    HashingEmbedder,
    RegisteredTool,
    ToolMatch,
    ToolRegistry,
    VectorStore,
)
from .runner import AgentResult, SubAgentRunner


def build_default_orchestrator(
    working_directory: Optional[str] = None,
    config: Optional[OrchestrationConfig] = None,
    approval_callback: Optional[ApprovalCallback] = None,
    vector_store_path: Optional[str] = None,
    embedder: Optional[Embedder] = None,
    vector_store: Optional[VectorStore] = None,
) -> Orchestrator:
    """Create the initial specialists and scoped example tools."""
    root = str(Path(working_directory or Path.cwd()).resolve())
    settings = config or OrchestrationConfig.from_env()
    registry = build_default_registry(
        root,
        settings,
        vector_store_path=vector_store_path,
        embedder=embedder,
        vector_store=vector_store,
    )
    agents = initial_agents(
        root,
        max_steps=settings.max_steps,
        approval_callback=approval_callback,
    )
    runner = SubAgentRunner(registry, settings)
    return Orchestrator(agents, runner, settings)


__all__ = [
    "AgentRegistry",
    "AgentResult",
    "AgentSpec",
    "ApprovalCallback",
    "Embedder",
    "FaissFlatVectorStore",
    "HashingEmbedder",
    "OrchestrationConfig",
    "Orchestrator",
    "PlanError",
    "PlanStep",
    "RegisteredTool",
    "SubAgentRunner",
    "ToolMatch",
    "ToolRegistry",
    "VectorStore",
    "build_default_orchestrator",
    "build_default_registry",
    "initial_agents",
    "register_core_tools",
    "register_example_tools",
]
