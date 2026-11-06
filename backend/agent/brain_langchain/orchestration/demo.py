"""Offline demo of a three-step Drive -> local script -> Gmail workflow."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple

from .agents import initial_agents
from .config import OrchestrationConfig
from .orchestrator import Orchestrator
from .registry import HashingEmbedder, ToolRegistry, tool_spec
from .runner import SubAgentRunner


class DemoVectorStore:
    """Tiny in-memory flat store used only by the offline demo."""

    def __init__(self) -> None:
        self.rows: Dict[Tuple[str, str], Tuple[str, Dict[str, Any], Sequence[float]]] = {}

    def get_description_hash(self, name: str, agent: str):
        row = self.rows.get((agent, name))
        return row[0] if row else None

    def get_vector(self, name: str, agent: str):
        return self.rows[(agent, name)][2]

    def upsert(self, name, agent, description_hash, metadata, vector):
        self.rows[(agent, name)] = (description_hash, metadata, vector)

    def search(self, vector, agent, k):
        results = []
        for (scope, _), (_, metadata, candidate) in self.rows.items():
            if scope != agent:
                continue
            score = sum(left * right for left, right in zip(vector, candidate))
            results.append((metadata, score))
        return sorted(results, key=lambda item: item[1], reverse=True)[:k]


def _tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": "demo-call", "name": name, "arguments": args}


def _demo_brain(**kwargs) -> Dict[str, Any]:
    system = kwargs.get("system_prompt", "")
    messages = kwargs.get("messages") or []
    tools = kwargs.get("tools") or []
    tool_names = {item.name for item in tools}
    last_message = messages[-1].get("content", "") if messages else ""

    if "precise task planner" in system:
        plan = [
            {
                "id": "s1",
                "agent": "google_cloud",
                "prompt": (
                    "Download the latest report from Drive into the workspace reports folder. "
                    "Return its local path and Drive file ID."
                ),
                "depends_on": [],
            },
            {
                "id": "s2",
                "agent": "coder",
                "prompt": (
                    "Run the local summarize_report.py script on the downloaded report. "
                    "Return the summary text as an artifact."
                ),
                "depends_on": ["s1"],
            },
            {
                "id": "s3",
                "agent": "google_cloud",
                "prompt": (
                    "Email the summary artifact to demo@example.com with subject "
                    "'Latest report summary'. Return a confirmation artifact."
                ),
                "depends_on": ["s2"],
            },
        ]
        return {"api_success": True, "api_response": json.dumps(plan), "total_attempts": 1}
    if "final response writer" in system:
        return {
            "api_success": True,
            "api_response": (
                "Demo complete: the latest report was downloaded, summarized by the local "
                "script, and a simulated email was sent to demo@example.com."
            ),
            "total_attempts": 1,
        }

    if "drive_download_latest" in tool_names and "goal" in last_message.lower():
        return {
            "api_success": True,
            "tool_calls": [_tool_call(
                "drive_download_latest",
                {"query": "latest report", "download_dir": "."},
            )],
            "total_attempts": 1,
        }
    if "run_shell" in tool_names and "goal" in last_message.lower():
        return {
            "api_success": True,
            "tool_calls": [_tool_call(
                "run_shell",
                {"command": "summarize_report.py report.txt", "cwd": ".", "timeout": 10},
            )],
            "total_attempts": 1,
        }
    if "gmail_send" in tool_names and "goal" in last_message.lower():
        return {
            "api_success": True,
            "tool_calls": [_tool_call(
                "gmail_send",
                {
                    "to": "demo@example.com",
                    "subject": "Latest report summary",
                    "body": "Revenue increased 12 percent; costs were stable.",
                },
            )],
            "total_attempts": 1,
        }
    if any(item.get("role") == "tool" for item in messages):
        return {
            "api_success": True,
            "tool_calls": [_tool_call(
                "finish",
                {
                    "summary": "Sub-task completed with the simulated tool result.",
                    "artifacts": [{"type": "demo_result", "value": last_message}],
                },
            )],
            "total_attempts": 1,
        }
    return {"api_success": True, "api_response": "No demo action requested.", "total_attempts": 1}


def run_demo() -> Dict[str, Any]:
    """Run the workflow without Google credentials or external side effects."""
    with tempfile.TemporaryDirectory(prefix="brain-orchestration-demo-") as temp_dir:
        root = Path(temp_dir)
        report_path = root / "report.txt"
        report_path.write_text(
            "Quarterly report: revenue increased 12 percent. Costs were stable.\n",
            encoding="utf-8",
        )
        script_path = root / "summarize_report.py"
        script_path.write_text(
            "import pathlib, sys\n"
            "text = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')\n"
            "print('Revenue increased 12 percent; costs were stable.')\n",
            encoding="utf-8",
        )
        embedder = HashingEmbedder()
        registry = ToolRegistry(embedder, DemoVectorStore())

        def fake_drive_download_latest(query: str, download_dir: str = ".") -> Dict[str, Any]:
            return {"path": str(report_path), "file_id": "demo-drive-file-1", "query": query}

        def fake_read_file(file_path: str) -> Dict[str, Any]:
            return {"path": file_path, "content": Path(file_path).read_text(encoding="utf-8")}

        def local_script(command: str, cwd: str = ".", timeout: int = 10) -> Dict[str, Any]:
            completed = subprocess.run(
                [sys.executable, str(script_path), str(report_path)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            return {"success": True, "stdout": completed.stdout.strip()}

        def fake_gmail_send(to: str, subject: str, body: str) -> Dict[str, str]:
            return {"status": "simulated", "to": to, "subject": subject, "body": body}

        registry.register(
            tool_spec(
                "drive_download_latest",
                "Find the newest Google Drive report and download it to the workspace.",
                {"query": {"type": "string"}, "download_dir": {"type": "string"}},
                ["query"],
            ),
            "google_cloud",
            fake_drive_download_latest,
            service="drive",
        )
        registry.register(
            tool_spec(
                "gmail_send",
                "Send an email using the authenticated Gmail account.",
                {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                ["to", "subject", "body"],
            ),
            "google_cloud",
            fake_gmail_send,
            service="gmail",
            requires_approval=True,
        )
        registry.register(
            tool_spec("read_file", "Read a workspace text file.", {"file_path": {"type": "string"}}, ["file_path"]),
            "coder",
            fake_read_file,
        )
        registry.register(
            tool_spec(
                "run_shell",
                "Run an approved local summarization script with a timeout.",
                {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                ["command"],
            ),
            "coder",
            local_script,
            requires_approval=True,
        )
        config = OrchestrationConfig(
            retrieval_k=6,
            retrieval_threshold=0.0,
            max_steps=4,
            max_replans=2,
            parallelism=2,
            max_total_steps=8,
            shell_timeout=10,
        )
        agents = initial_agents(
            str(root),
            max_steps=config.max_steps,
            approval_callback=lambda _tool, _args: True,
        )
        runner = SubAgentRunner(registry, config, brain_callable=_demo_brain)
        orchestrator = Orchestrator(
            agents,
            runner,
            config,
            brain_callable=_demo_brain,
        )
        result = orchestrator.run(
            "Download the latest report from Drive, summarize it with a local script, "
            "and email me the summary."
        )
        if result["status"] != "ok":
            raise RuntimeError(f"Offline demo failed: {result}")
        print("Plan:")
        for step in result["plan"]:
            print(f"  {step['id']} [{step['agent']}] depends_on={step['depends_on']}: {step['prompt']}")
        print("\n" + result["answer"])
        print("\nExternal Google actions are simulated; the local summarization script ran for real.")
        return result


if __name__ == "__main__":
    run_demo()
