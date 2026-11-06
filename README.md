# Brain Studio

Brain Studio combines a FastAPI agent backend, a React/Vite interface, and a
peer-to-peer Mesh service.

## Project layout

```text
artifacts/
├── backend/
│   ├── server.py
│   ├── run_server.py
│   ├── agent/
│   │   ├── brain_langchain/
│   │   ├── single_agent.py
│   │   └── multi_agent.py
│   ├── tools/
│   ├── tests/
│   ├── data/
│   └── static/          # Legacy UI assets
├── mesh/
│   ├── server.py
│   └── mesh/
├── frontend/            # React/Vite app
├── .env
├── setup.bat
└── start.bat
```

## Windows setup and launch

1. Install Python 3 and Node.js.
2. Run `setup.bat` once from this directory.
3. Configure provider keys and Mesh settings in the root `.env`.
4. Run `start.bat`.

The script opens separate terminals for the Mesh node, Brain API, and Vite UI.
Open the UI at `http://127.0.0.1:5173`.

## Mesh agent calls

Set the same private `MESH_AGENT_TOKEN` on each laptop in its root `.env`.
The Brain API binds to LAN interfaces when that token is configured. On a
trusted Windows LAN, run `allow_mesh_firewall.bat` as Administrator on each
laptop to permit Mesh traffic from the local subnet. Do not expose these ports
on public networks.

## Tool-RAG orchestration

The Brain stack includes an agent-scoped tool-RAG orchestrator under
`backend/agent/brain_langchain/orchestration/`. It uses the existing `brain()`
path for planning, specialist tool loops, and final response composition. See
the [orchestration README](backend/agent/brain_langchain/orchestration/README.md)
for configuration, approval requirements, the offline demo, and the test plan.

## Google Workspace tools

The tool registry exposes 31 purpose-specific Google tools for Drive, Gmail,
Sheets, and Tasks, including email search/read/send, Drive file operations,
spreadsheet reads/writes, and task/task-list management. Set
`GOOGLE_OAUTH_CLIENT_SECRETS` to the path of a Google OAuth desktop-client JSON
file before using them. The first call opens Google's local consent flow and
saves its token to `backend/tools/google_workspace_token.json`; set
`GOOGLE_WORKSPACE_TOKEN_PATH` to choose another token path. The OAuth grant
includes Drive, Gmail, Sheets, and Tasks access so the tools can perform the
documented read/write operations.

## Development checks

```powershell
python -m pytest backend\tests
Set-Location frontend
npm run lint
npm run build
```
