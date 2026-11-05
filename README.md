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

## Development checks

```powershell
python -m pytest backend\tests
Set-Location frontend
npm run lint
npm run build
```
