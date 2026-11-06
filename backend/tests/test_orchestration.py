import json
import math
import sqlite3
from backend.agent.brain_langchain.brain_types import ToolSpec
from backend.agent.brain_langchain.orchestration.agents import (
    AgentRegistry,
    AgentSpec,
    register_core_tools,
)
from backend.agent.brain_langchain.orchestration.config import OrchestrationConfig
from backend.agent.brain_langchain.orchestration.orchestrator import (
    Orchestrator,
    PlanError,
    PlanStep,
)
from backend.agent.brain_langchain.orchestration.registry import (
    FaissFlatVectorStore,
    HashingEmbedder,
    ToolRegistry,
    tool_spec,
)
from backend.agent.brain_langchain.orchestration.runner import AgentResult, SubAgentRunner


class KeywordEmbedder:
    dimension = 2

    def __init__(self):
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        lower = text.lower()
        vector = [float("drive" in lower or "google" in lower), float("file" in lower or "shell" in lower)]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class MemoryStore:
    def __init__(self):
        self.rows = {}

    def get_description_hash(self, name, agent):
        row = self.rows.get((agent, name))
        return row[0] if row else None

    def get_vector(self, name, agent):
        return self.rows[(agent, name)][2]

    def upsert(self, name, agent, description_hash, metadata, vector):
        self.rows[(agent, name)] = (description_hash, metadata, vector)

    def search(self, vector, agent, k):
        results = []
        for (scope, _), (_, metadata, candidate) in self.rows.items():
            if scope == agent:
                score = sum(left * right for left, right in zip(vector, candidate))
                results.append((metadata, score))
        return sorted(results, key=lambda row: row[1], reverse=True)[:k]


def _config(**kwargs):
    values = {
        "retrieval_k": 6,
        "retrieval_threshold": 0.0,
        "max_steps": 3,
        "max_replans": 1,
        "parallelism": 2,
        "max_total_steps": 6,
        "shell_timeout": 5,
    }
    values.update(kwargs)
    return OrchestrationConfig(**values)


def test_registry_filters_scope_and_reuses_description_embedding():
    embedder = KeywordEmbedder()
    registry = ToolRegistry(embedder, MemoryStore())
    drive = tool_spec("drive_search", "Search files stored in Google Drive.", {}, [])
    local = tool_spec("read_file", "Read a local workspace file.", {}, [])
    registry.register(drive, "google_cloud", lambda: None, service="drive")
    registry.register(local, "coder", lambda: None)
    calls_after_register = embedder.calls

    registry.register(drive, "google_cloud", lambda: None, service="drive")
    assert embedder.calls == calls_after_register
    assert [item.name for item in registry.search("Google Drive", "coder", 6, 0.0)] == [
        "read_file"
    ]
    assert [item.name for item in registry.search("workspace file", "google_cloud", 6, 0.0)] == [
        "drive_search"
    ]


def test_faiss_registry_persists_vectors_and_reembeds_only_changed_descriptions(tmp_path):
    class CountedEmbedder(HashingEmbedder):
        def __init__(self):
            super().__init__(dimension=32)
            self.calls = 0

        def embed(self, text):
            self.calls += 1
            return super().embed(text)

    database = str(tmp_path / "vectors.sqlite3")
    embedder = CountedEmbedder()
    spec = tool_spec("search_drive", "Search files stored in Google Drive.", {}, [])
    first = ToolRegistry(embedder, FaissFlatVectorStore(database, embedder.dimension))
    first.register(spec, "google_cloud", lambda: None, service="drive")
    assert embedder.calls == 1

    restarted = ToolRegistry(embedder, FaissFlatVectorStore(database, embedder.dimension))
    restarted.register(spec, "google_cloud", lambda: None, service="drive")
    assert embedder.calls == 1
    results = restarted.search("find a Google Drive file", "google_cloud", 3, 0.0)
    assert results[0].name == "search_drive"
    assert embedder.calls == 2

    changed = tool_spec("search_drive", "Search Google Drive and filter files by date.", {}, [])
    restarted.register(changed, "google_cloud", lambda: None, service="drive")
    assert embedder.calls == 3


def test_plan_parser_and_dependency_validation():
    agents = AgentRegistry()
    agents.register(AgentSpec("coder", "Local files", "Coder.", 2, "coder"))
    orchestrator = Orchestrator(agents, runner=None, config=_config(), brain_callable=lambda **_: {})
    valid = orchestrator._parse_plan(
        '[{"id":"s1","agent":"coder","prompt":"Read a file.","depends_on":[]}]'
    )
    orchestrator._validate_plan(valid)
    assert valid[0].agent == "coder"
    orchestrator._validate_plan(
        [PlanStep("s2", "coder", "Use the prior file.", ["s1"])],
        {"s1"},
    )

    cyclic = orchestrator._parse_plan(
        '[{"id":"s1","agent":"coder","prompt":"one","depends_on":["s2"]},'
        '{"id":"s2","agent":"coder","prompt":"two","depends_on":["s1"]}]'
    )
    try:
        orchestrator._validate_plan(cyclic)
    except PlanError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("Cyclic dependencies must be rejected.")

    try:
        orchestrator._parse_plan('{"id":"s1"}')
    except PlanError as exc:
        assert "array" in str(exc)
    else:
        raise AssertionError("A plan root must be an array.")


def test_runner_executes_retrieved_tools_and_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "brain.sqlite3"))
    registry = ToolRegistry(KeywordEmbedder(), MemoryStore())
    register_core_tools(registry, "coder", _config())
    calls = []

    registry.register(
        tool_spec("read_file", "Read a local workspace file.", {"path": {"type": "string"}}, ["path"]),
        "coder",
        lambda path: calls.append(path) or {"content": "report text"},
    )
    responses = [
        {
            "api_success": True,
            "tool_calls": [{"id": "c1", "name": "read_file", "arguments": {"path": "report.txt"}}],
        },
        {
            "api_success": True,
            "tool_calls": [{
                "id": "c2",
                "name": "finish",
                "arguments": {"summary": "Read report.", "artifacts": [{"type": "text", "value": "report text"}]},
            }],
        },
    ]

    def fake_brain(**kwargs):
        return responses.pop(0)

    agent = AgentSpec("coder", "Local files", "Coder.", 3, "coder")
    result = SubAgentRunner(registry, _config(), fake_brain).run(
        "Goal: read a local file and return its text.", agent
    )
    assert result.status == "ok"
    assert result.summary == "Read report."
    assert result.artifacts[0]["value"] == "report text"
    assert calls == ["report.txt"]
    connection = sqlite3.connect(str(tmp_path / "brain.sqlite3"))
    try:
        event_types = {
            row[0]
            for row in connection.execute("SELECT Event_Type FROM Orchestration_Event")
        }
    finally:
        connection.close()
    assert {"brain_call", "subagent_tools"}.issubset(event_types)


def test_failed_step_retries_then_replans(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "brain.sqlite3"))
    agents = AgentRegistry()
    agents.register(AgentSpec("coder", "Local files", "Coder.", 2, "coder"))

    class FakeRunner:
        def __init__(self):
            self.calls = 0

        def run(self, prompt, agent):
            self.calls += 1
            if self.calls < 3:
                return AgentResult("error", "", error="script failed")
            return AgentResult("ok", "replanned work completed")

    plan_calls = 0

    def fake_brain(**kwargs):
        nonlocal plan_calls
        system = kwargs["system_prompt"]
        if "precise task planner" in system:
            plan_calls += 1
            step_id = "s1" if plan_calls == 1 else "s2"
            step = {
                "id": step_id,
                "agent": "coder",
                "prompt": "Run the local report summarizer.",
                "depends_on": [],
            }
            return {"api_success": True, "api_response": json.dumps([step])}
        if "final response writer" in system:
            return {"api_success": True, "api_response": "The workflow was retried and replanned."}
        raise AssertionError("Unexpected Brain call.")

    runner = FakeRunner()
    orchestrator = Orchestrator(agents, runner, _config(), fake_brain)
    result = orchestrator.run("Download from Drive and summarize a local report.")
    assert runner.calls == 3
    assert result["replans_used"] == 1
    assert plan_calls == 2
    assert "s2" in result["results"]
    assert result["status"] == "error"


def test_shell_requires_explicit_approval(tmp_path):
    registry = ToolRegistry(KeywordEmbedder(), MemoryStore())
    registry.register(
        ToolSpec(
            "run_shell",
            "Run a shell command.",
            {"type": "object", "properties": {"command": {"type": "string"}}},
        ),
        "coder",
        lambda command: {"command": command},
    )
    agent = AgentSpec("coder", "Local files", "Coder.", 1, "coder")
    runner = SubAgentRunner(registry, _config(), lambda **_: {})
    try:
        runner._dispatch(agent, "run_shell", {"command": "echo unsafe"})
    except PermissionError as exc:
        assert "Approval denied" in str(exc)
    else:
        raise AssertionError("Shell execution must be denied without an approval callback.")
