# Brain orchestration

The package composes the existing `brain()` function; it does not change its
provider or failover behavior. All planner, specialist, and final-merge LLM
calls go through `brain()`.

## Modules

```text
orchestration/
├── agents.py          # AgentSpec, AgentRegistry, core tools
├── config.py          # Environment-backed orchestration settings
├── demo.py            # Offline three-step demo
├── example_tools.py   # Drive/Gmail and restricted local tools
├── observability.py   # Orchestration_Event SQLite records
├── orchestrator.py    # Planning, DAG execution, retry/replan, final merge
├── registry.py        # Tool metadata, embedder interface, FAISS flat search
└── runner.py          # Scoped tool-RAG agent loop
```

`HashingEmbedder` is a deterministic offline embedder behind the `Embedder`
interface. `FaissFlatVectorStore` persists vectors and metadata in a local
SQLite file and builds an exact FAISS flat index after first filtering on the
agent scope. Descriptions are embedded again only when their SHA-256 changes.
An alternative embedder/store can be injected into `build_default_orchestrator`.
Service metadata is stored, but service-tag retrieval is intentionally not
implemented.

## Use

```python
from backend.agent.brain_langchain.orchestration import build_default_orchestrator

def approve(tool, arguments):
    # Replace with the application's interactive approval flow.
    return False

orchestrator = build_default_orchestrator(
    working_directory=r"C:\path\to\workspace",
    approval_callback=approve,
)
result = orchestrator.run("Find a report in Drive and summarize it locally.")
print(result["answer"])
```

The default examples register `drive_download_latest`, `gmail_send`, `read_file`,
and `run_shell`. Google tools reuse the existing Drive and Gmail integrations.
Drive downloads and local reads/writes are restricted to the configured
workspace. Shell commands and email sends require a positive approval callback;
the shell is also bounded by its timeout and working directory. Applications
should implement the callback as an explicit user confirmation UI.

Install the requirements in `backend/agent/brain_langchain/requirements.txt`
to provide FAISS. The local vector database defaults to
`.brain_tool_vectors.sqlite3` in the selected workspace and is git-ignored.
Set `ORCHESTRATION_VECTOR_DB` to choose another path.

## Runnable demo

From the repository root:

```powershell
python -m backend.agent.brain_langchain.orchestration.demo
```

The demo prints a three-step plan spanning `google_cloud`, `coder`, and
`google_cloud`. It runs a local summarization script for real, but uses an
offline mock planner/Brain response and fake Drive/Gmail handlers. It does not
access Google accounts or send email.

## Settings

| Environment variable | Default | Meaning |
|---|---:|---|
| `ORCHESTRATION_K` | `6` | Maximum retrieved tools per specialist |
| `ORCHESTRATION_THRESHOLD` | `0.12` | Minimum cosine score |
| `ORCHESTRATION_MAX_STEPS` | `6` | Brain calls per specialist |
| `ORCHESTRATION_MAX_REPLANS` | `2` | Planner retries after planning/step errors |
| `ORCHESTRATION_PARALLELISM` | `3` | Independent steps per executor batch |
| `ORCHESTRATION_MAX_TOTAL_STEPS` | `12` | Maximum planned step executions |
| `ORCHESTRATION_SHELL_TIMEOUT` | `30` | Maximum command runtime in seconds |
| `ORCHESTRATION_VECTOR_DB` | workspace DB | FAISS metadata/vector database path |

## Test plan

1. **Retrieval precision/scope:** test relevant matches against labeled
   descriptions and assert a coder query never returns Google tools (and vice
   versa); compare top-k results and threshold behavior.
2. **Plan JSON:** test valid plans, malformed JSON, unknown agents, duplicate
   IDs, missing dependencies, cycles, and max-step limits.
3. **Tool loop and approvals:** mock `brain()` and handlers; verify retrieval
   refresh, `finish`, `ask_user`, handler error feedback, and that shell/delete
   handlers are blocked unless approval returns true.
4. **Failure/replan:** simulate a failed step, one refined retry, a new plan,
   and exhausted replans; assert the final result does not claim unverified
   work.
5. **Observability:** assert plans, chosen agents, retrieved/called tools,
   Brain attempts/latency, and final status are written to the configured
   SQLite database.
