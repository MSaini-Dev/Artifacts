# Brain Studio React frontend

This Vite app is the React replacement for the legacy UI in `backend/static`.
It keeps the existing Python API and provides Chat, Tools, Database, and Logs
screens with shadcn/ui components.

The appearance toggle in the top-right switches between light and dark themes.
The app follows the operating system theme by default and remembers an explicit
selection in the browser.

## Run locally

From the repository root, run `setup.bat` once to install backend and frontend
dependencies, then `start.bat` to start Mesh, the Brain API, and Vite in
separate terminals.

To start services manually, start the Python API from the repository root in
one terminal:

```powershell
python -m backend.run_server
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

The Vite development server proxies `/api` requests to the Python service at
`http://127.0.0.1:8000`. Keep the Python API running while using the React app.
After backend code changes, restart the Python API so it loads the updated log
schema and records each API request payload and actual tool execution. On
startup, existing interaction, iteration, recovery, and wait rows are migrated
into `API_Call_Log`; the legacy detail tables are removed after the migration
succeeds. Conversation metadata
remains in `Conversation`. Old records are marked as legacy, and timestamps are
approximated from their interaction time. The migration preserves payloads only
where an old per-call request payload was actually stored; missing payloads are
left empty rather than reconstructed.

## Mesh between laptops

The Mesh tab connects to the MeshOS node running on the same laptop (REST port
8766 by default). Start a node on each laptop from the project root:

The Mesh source is included in the repository under `mesh`. `start.bat` starts
it on port 8765; to run it separately or choose a node name, use:

```powershell
python mesh\server.py --port 8765 --name "Laptop 1"
```

In the Mesh tab, connect peers using their WebSocket addresses, for example
`ws://192.168.1.23:8765`. MeshOS uses UDP port 3848 for automatic discovery;
allow UDP 3848 and TCP 8765 through the LAN firewall, or use the connect field
when discovery is unavailable. Remote agent calls also need inbound TCP port
8000 allowed on each laptop.

On Windows, mark the trusted Wi-Fi/Ethernet network as **Private**, then run
`allow_mesh_firewall.bat` as Administrator on each laptop. It adds inbound
rules limited to the local subnet for TCP 8000 (agent API), TCP 8765 (Mesh
WebSocket), and UDP 3848 (discovery). Do not expose these ports on a public
network.

To call a peer's agent, both laptops must run the Brain API on port 8000 and
share the same private token. On each laptop, set these environment variables
before starting the API:

```powershell
$env:MESH_AGENT_TOKEN = "use-the-same-long-random-secret-on-each-laptop"
$env:MESH_API_URL = "http://127.0.0.1:8766"
python -m backend.run_server
```

When `MESH_AGENT_TOKEN` is set, the Brain API listens on network interfaces by
default so peers can reach it. Without a token, it listens on loopback only.
Set `HOST` explicitly to override either default.

If an agent call times out, check that the target laptop's Brain API says it is
listening on `0.0.0.0:8000`, then run
`Test-NetConnection <peer-ip> -Port 8000` from the calling laptop. A timeout
means the port is unreachable (often firewall or network isolation); an HTTP
403 means the request reached the API but the shared `MESH_AGENT_TOKEN` is
missing or different. Confirm both laptops use the same token and restart the
API.

Remote requests to the Brain API require `MESH_AGENT_TOKEN`; the token is not
needed for the local browser UI. Keep it private and use this only on a trusted
network. The Mesh tab supports human-to-human messages and explicit calls to a
selected peer's agent; tools are executed only by that peer's own agent, not
shared or invoked across the Mesh directly.

The Logs screen defaults to **Full trace**, where each interaction's chronological
LLM tasks and actual tool executions are shown. Choose **Simple** for just the
first API payload and final response. Each task groups provider failover attempts
for one model invocation, shows its common request and last successful response,
and expands to individual API attempts. Tool executions are persisted separately
in `Tool_Execution` with their arguments, output or error, status, timestamp, and
duration. Legacy tool activity is not reconstructed from prompts; it appears only
when the execution was actually recorded. Failed API calls have no final-response
flag, tool-call responses are marked non-final, and the final user-facing
response is marked final.

## Checks

```powershell
npm run lint
npm run build
```
