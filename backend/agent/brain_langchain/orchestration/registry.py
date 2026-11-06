"""Agent-scoped tool registration and local FAISS retrieval."""

import hashlib
import json
import math
import re
import sqlite3
import struct
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from ..brain_types import ToolSpec

ToolHandler = Callable[..., Any]


@contextmanager
def _sqlite_connection(path: str):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@dataclass
class RegisteredTool:
    spec: ToolSpec
    agent: str
    handler: ToolHandler
    service: Optional[str] = None
    requires_approval: bool = False


@dataclass
class ToolMatch:
    name: str
    agent: str
    service: Optional[str]
    spec: ToolSpec
    score: float


class Embedder(Protocol):
    dimension: int

    def embed(self, text: str) -> Sequence[float]:
        """Return a normalized dense vector."""


class VectorStore(Protocol):
    def get_description_hash(self, name: str, agent: str) -> Optional[str]:
        """Return the persisted description hash for a tool."""

    def get_vector(self, name: str, agent: str) -> Sequence[float]:
        """Return the persisted embedding for a tool."""

    def upsert(
        self, name: str, agent: str, description_hash: str, metadata: Dict[str, Any],
        vector: Sequence[float],
    ) -> None:
        """Insert or update one vector and its metadata."""

    def search(self, vector: Sequence[float], agent: str, k: int) -> List[Tuple[Dict[str, Any], float]]:
        """Search a flat index restricted to one agent."""


class HashingEmbedder:
    """Small deterministic local embedder; replaceable with a model-backed embedder."""

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def embed(self, text: str) -> Sequence[float]:
        vector = [0.0] * self.dimension
        words = re.findall(r"[a-z0-9_]+", text.lower())
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


class FaissFlatVectorStore:
    """Persistent metadata store with exact, agent-filtered FAISS flat search."""

    def __init__(self, path: str, dimension: int):
        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError(
                "FAISS is required for tool retrieval; install faiss-cpu from "
                "backend/agent/brain_langchain/requirements.txt."
            ) from exc
        self._faiss = faiss
        self.dimension = dimension
        self.path = str(Path(path).expanduser().resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with _sqlite_connection(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_vectors (
                    name TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    description_hash TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    PRIMARY KEY (agent, name)
                )
                """
            )

    def get_description_hash(self, name: str, agent: str) -> Optional[str]:
        with _sqlite_connection(self.path) as conn:
            row = conn.execute(
                "SELECT description_hash FROM tool_vectors WHERE agent = ? AND name = ?",
                (agent, name),
            ).fetchone()
        return str(row[0]) if row else None

    def get_vector(self, name: str, agent: str) -> Sequence[float]:
        with _sqlite_connection(self.path) as conn:
            row = conn.execute(
                "SELECT vector FROM tool_vectors WHERE agent = ? AND name = ?",
                (agent, name),
            ).fetchone()
        if row is None:
            raise KeyError((agent, name))
        return struct.unpack(f"{self.dimension}f", row[0])

    def upsert(
        self, name: str, agent: str, description_hash: str, metadata: Dict[str, Any],
        vector: Sequence[float],
    ) -> None:
        packed = struct.pack(f"{len(vector)}f", *vector)
        with _sqlite_connection(self.path) as conn:
            conn.execute(
                """
                INSERT INTO tool_vectors (name, agent, description_hash, metadata, vector)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent, name) DO UPDATE SET
                    description_hash = excluded.description_hash,
                    metadata = excluded.metadata,
                    vector = excluded.vector
                """,
                (name, agent, description_hash, json.dumps(metadata), packed),
            )

    def search(
        self, vector: Sequence[float], agent: str, k: int
    ) -> List[Tuple[Dict[str, Any], float]]:
        with _sqlite_connection(self.path) as conn:
            rows = conn.execute(
                "SELECT metadata, vector FROM tool_vectors WHERE agent = ?",
                (agent,),
            ).fetchall()
        if not rows:
            return []

        # Scope filtering happens in SQLite before vectors enter the FAISS index.
        index = self._faiss.IndexFlatIP(self.dimension)
        vectors = [struct.unpack(f"{self.dimension}f", row[1]) for row in rows]
        import numpy

        matrix = numpy.asarray(vectors, dtype="float32")
        query = numpy.asarray([vector], dtype="float32")
        index.add(matrix)
        scores, positions = index.search(query, min(k, len(rows)))
        return [
            (json.loads(rows[int(position)][0]), float(score))
            for position, score in zip(positions[0], scores[0])
            if int(position) >= 0
        ]


class ToolRegistry:
    """Stores callable tools and retrieves specs within an agent's scope."""

    def __init__(self, embedder: Embedder, vector_store: VectorStore):
        self.embedder = embedder
        self.vector_store = vector_store
        self._tools: Dict[Tuple[str, str], RegisteredTool] = {}

    def register(
        self,
        spec: ToolSpec,
        agent: str,
        handler: ToolHandler,
        service: Optional[str] = None,
        requires_approval: bool = False,
    ) -> None:
        key = (agent, spec.name)
        if key in self._tools and spec.name in {"finish", "ask_user", "search_tools"}:
            raise ValueError(f"{spec.name} is a reserved core tool name.")
        name_lower = spec.name.lower()
        requires_approval = requires_approval or (
            "delete" in name_lower
            or name_lower in {"shell", "run_shell", "execute_command"}
        )
        registered = RegisteredTool(spec, agent, handler, service, requires_approval)
        self._tools[key] = registered
        description_hash = hashlib.sha256(spec.description.encode("utf-8")).hexdigest()
        if self.vector_store.get_description_hash(spec.name, agent) != description_hash:
            vector = self.embedder.embed(spec.description)
        else:
            vector = self.vector_store.get_vector(spec.name, agent)
        self.vector_store.upsert(
            spec.name,
            agent,
            description_hash,
            {
                "name": spec.name,
                "agent": agent,
                "service": service,
                "spec": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            },
            vector,
        )

    def handler(self, name: str, agent: str) -> RegisteredTool:
        try:
            return self._tools[(agent, name)]
        except KeyError as exc:
            raise KeyError(f"Tool {name!r} is not registered for agent {agent!r}.") from exc

    def search(
        self,
        query: str,
        agent: str,
        k: int = 6,
        threshold: float = 0.12,
    ) -> List[ToolSpec]:
        matches = self.search_matches(query, agent, k, threshold)
        return [match.spec for match in matches]

    def search_matches(
        self,
        query: str,
        agent: str,
        k: int = 6,
        threshold: float = 0.12,
    ) -> List[ToolMatch]:
        query_vector = self.embedder.embed(query)
        results = self.vector_store.search(query_vector, agent, k)
        matches = []
        for metadata, score in results:
            if score < threshold:
                continue
            tool_data = metadata["spec"]
            matches.append(
                ToolMatch(
                    name=tool_data["name"],
                    agent=agent,
                    service=metadata.get("service"),
                    spec=ToolSpec(**tool_data),
                    score=score,
                )
            )
        return matches

    def tools_for_agent(self, agent: str) -> List[RegisteredTool]:
        return [
            tool for (scope, _), tool in self._tools.items()
            if scope == agent
        ]


def tool_spec(
    name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None
) -> ToolSpec:
    """Build the JSON schema expected by the existing Brain API."""
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return ToolSpec(name=name, description=description, parameters=schema)
