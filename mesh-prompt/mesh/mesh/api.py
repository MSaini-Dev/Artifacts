import asyncio
import hmac
import json
import os
import sys
import time
from pathlib import Path
from aiohttp import web

from .network import NetworkManager
from .node import MeshNode

# Ensure repository root is on sys.path for in-process agent imports
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_environment():
    """Load variables from .env in project root or current working directory into os.environ if not already set."""
    search_paths = [
        Path.cwd() / ".env",
        REPO_ROOT / ".env",
        REPO_ROOT.parent / ".env",
        REPO_ROOT / "mesh" / ".env",
    ]
    for env_path in search_paths:
        if env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass


# Pre-load environment at module import
load_environment()


def make_app(node: MeshNode, net: NetworkManager):
    app = web.Application()

    async def connection_info(request):
        return web.json_response(node.snapshot())

    async def peers(request):
        return web.json_response({
            "direct": node.peer_addrs,
            "known_beacons": list(node.known_beacons.keys()),
            "persistent_peers": list(node.persistent_peers),
        })

    async def connect_peer(request):
        data = await request.json()
        target_url = data.get("url")
        if not target_url:
            return web.json_response({"error": "Missing 'url'"}, status=400)
        node.save_persistent_peer(target_url)
        asyncio.create_task(net.dial(target_url))
        return web.json_response({"status": "dialing", "target": target_url})

    async def send_msg(request):
        """Standard Mesh text messaging endpoint - does not execute prompts."""
        data = await request.json()
        dest = data.get("dest")
        msg = data.get("msg")

        if not dest or not msg:
            return web.json_response({"error": "Missing 'dest' or 'msg'"}, status=400)

        envelope = {
            "type": "MSG",
            "src": node.id,
            "dest": dest,
            "msg": msg,
            "path": [node.id],
            "ts": time.time(),
        }

        if dest == node.id:
            node.inbox.append({"from": node.id, "msg": msg, "ts": time.time(), "path": [node.id]})
            node.sent.append({"to": dest, "msg": msg, "ts": time.time()})
            return web.json_response({"status": "delivered_locally"})

        next_hop = node.bfs_next_hop(dest)
        if not next_hop or next_hop not in node.connections:
            return web.json_response({"error": f"No route to destination '{dest}'"}, status=404)

        try:
            await node.connections[next_hop].send(json.dumps(envelope))
            node.sent.append({"to": dest, "msg": msg, "ts": time.time()})
            return web.json_response({"status": "sent", "next_hop": next_hop, "dest": dest})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def execute_prompt(request):
        """
        Execute an autonomous agent prompt in-process on the local laptop.
        Requires Authorization: Bearer <token> matching MESH_PROMPT_TOKEN.
        Note: MESH_PROMPT_TOKEN is distinct from MESH_AGENT_TOKEN (which is for peer agent RPC).
        """
        load_environment()
        # 1. Bearer Token Verification - strictly check MESH_PROMPT_TOKEN
        expected_token = os.environ.get("MESH_PROMPT_TOKEN")
        if not expected_token:
            return web.json_response(
                {
                    "success": False,
                    "error": "MESH_PROMPT_TOKEN is not configured on the laptop. Please set MESH_PROMPT_TOKEN in your .env file or environment before executing remote prompts (note: distinct from MESH_AGENT_TOKEN).",
                },
                status=503,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response(
                {
                    "success": False,
                    "error": "Missing or malformed Authorization header. Expected 'Authorization: Bearer <token>'",
                },
                status=401,
            )

        token = auth_header[7:].strip()
        if not hmac.compare_digest(token, expected_token):
            return web.json_response(
                {
                    "success": False,
                    "error": "Unauthorized: Invalid bearer token. Ensure the token in your phone app matches MESH_PROMPT_TOKEN on your laptop.",
                },
                status=403,
            )

        # 2. Validate Prompt Payload
        try:
            data = await request.json()
        except Exception as e:
            return web.json_response(
                {"success": False, "error": f"Invalid JSON payload: {str(e)}"},
                status=400,
            )

        prompt = data.get("prompt")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            return web.json_response(
                {"success": False, "error": "Missing or empty 'prompt' in request body."},
                status=400,
            )

        # 3. Import local agent in-process
        try:
            from backend.agent.single_agent import call_agent
        except ImportError:
            try:
                from agent.single_agent import call_agent
            except ImportError as err:
                return web.json_response(
                    {
                        "success": False,
                        "error": f"Agent module not found: {str(err)}",
                    },
                    status=500,
                )

        # 4. Invoke agent in a background thread to prevent blocking aiohttp event loop
        try:
            loop = asyncio.get_running_loop()
            agent_result = await loop.run_in_executor(
                None,
                lambda: call_agent(user_prompt=prompt.strip(), verbose=False),
            )
            return web.json_response({
                "success": True,
                "response": agent_result,
            })
        except Exception as e:
            return web.json_response(
                {
                    "success": False,
                    "error": f"Agent execution error: {str(e)}",
                },
                status=500,
            )

    async def index(request):
        return web.FileResponse(os.path.join(os.path.dirname(__file__), "ui.html"))

    async def set_name(request):
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return web.json_response({"error": "Missing 'name'"}, status=400)
        node.set_name(name)
        await net.broadcast_graph()
        return web.json_response({"status": "ok", "name": node.name})

    async def get_sent(request):
        return web.json_response(node.sent)

    async def get_inbox(request):
        return web.json_response(node.inbox)

    async def refresh_route(request):
        res = await net.refresh_connections()
        return web.json_response(res)

    # REST Routes
    app.router.add_get("/", index)
    app.router.add_post("/name", set_name)
    app.router.add_get("/sent", get_sent)
    app.router.add_get("/status", connection_info)
    app.router.add_get("/connection_info", connection_info)
    app.router.add_get("/peers", peers)
    app.router.add_post("/connect", connect_peer)
    app.router.add_post("/send", send_msg)
    app.router.add_post("/prompt", execute_prompt)  # Remote prompt execution
    app.router.add_get("/inbox", get_inbox)
    app.router.add_route("*", "/refresh", refresh_route)
    return app
