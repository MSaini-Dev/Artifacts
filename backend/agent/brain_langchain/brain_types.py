"""Shared types for Brain requests / responses."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]

    def to_openai(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class MemoryItem:
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        src = self.metadata.get("source")
        if src:
            return f"[Memory | {src}] {self.content}"
        return f"[Memory] {self.content}"


@dataclass
class BrainRequest:
    user_prompt: str
    system_prompt: str
    tools: Optional[List[ToolSpec]] = None
    memories: Optional[List[MemoryItem]] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    key_name: Optional[str] = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


def tool_specs_to_openai(tools: Optional[List[ToolSpec]]) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None
    return [t.to_openai() for t in tools]


def inject_memories(system_prompt: str, memories: Optional[List[MemoryItem]]) -> str:
    if not memories:
        return system_prompt
    block = "\n\n".join(m.format() for m in memories)
    return f"{system_prompt.rstrip()}\n\n--- Retrieved Memories ---\n{block}"
