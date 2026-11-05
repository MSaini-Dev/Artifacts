import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from backend import server


def test_api_bind_host_requires_token_for_network_access(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("MESH_AGENT_TOKEN", raising=False)
    assert server._api_bind_host() == "127.0.0.1"

    monkeypatch.setenv("MESH_AGENT_TOKEN", "test-shared-token")
    assert server._api_bind_host() == "0.0.0.0"

    monkeypatch.setenv("HOST", "192.168.1.10")
    assert server._api_bind_host() == "192.168.1.10"


def test_mesh_snapshot_combines_local_node_data(monkeypatch):
    results = {
        "/status": {"self_id": "node-a", "graph": {"node-a": {}}},
        "/inbox": [{"from": "node-b", "msg": "hello", "ts": 1}],
        "/sent": [],
    }
    monkeypatch.setattr(server, "_mesh_request", lambda path, *_args, **_kwargs: results[path])

    snapshot = server.get_mesh_snapshot()

    assert snapshot["status"]["self_id"] == "node-a"
    assert snapshot["inbox"][0]["msg"] == "hello"
    assert snapshot["mesh_api_url"] == "http://127.0.0.1:8766"


def test_mesh_message_proxies_to_local_mesh_node(monkeypatch):
    captured = {}

    def fake_request(path, method, payload):
        captured.update(path=path, method=method, payload=payload)
        return {"success": True}

    monkeypatch.setattr(server, "_mesh_request", fake_request)

    result = server.send_mesh_message(server.MeshMessageRequest(dest="node-b", msg="hello"))

    assert result == {"success": True}
    assert captured == {
        "path": "/send",
        "method": "POST",
        "payload": {"dest": "node-b", "msg": "hello"},
    }


def test_mesh_agent_calls_selected_peer_agent_with_shared_token(monkeypatch):
    monkeypatch.setenv("MESH_AGENT_TOKEN", "test-shared-token")
    monkeypatch.setattr(
        server,
        "_mesh_request",
        lambda *_args, **_kwargs: {
            "self_id": "node-a",
            "graph": {
                "node-a": {"addr": "ws://10.0.0.1:8765"},
                "node-b": {"addr": "ws://10.0.0.3:8765"},
            },
        },
    )
    outgoing = {}

    def fake_post(url, **kwargs):
        outgoing["url"] = url
        outgoing.update(kwargs)
        return SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: {"success": True, "response": "Remote agent response", "conversation_id": 45},
        )

    monkeypatch.setattr(server.requests, "post", fake_post)
    request = server.MeshAgentRequest(
        peer_id="node-b",
        message="List the files",
        temperature=0.3,
        max_turns=7,
        conversation_id=44,
    )

    response = server.call_peer_agent(request)

    assert response["response"] == "Remote agent response"
    assert outgoing["url"] == "http://10.0.0.3:8000/api/chat"
    assert outgoing["headers"] == {"X-Mesh-Agent-Token": "test-shared-token"}
    assert outgoing["json"] == {
        "message": "List the files",
        "mode": "agent",
        "temperature": 0.3,
        "max_turns": 7,
        "conversation_id": 44,
    }


def test_mesh_agent_rejects_peer_not_in_mesh(monkeypatch):
    monkeypatch.setenv("MESH_AGENT_TOKEN", "test-shared-token")
    monkeypatch.setattr(
        server,
        "_mesh_request",
        lambda *_args, **_kwargs: {"self_id": "node-a", "graph": {"node-a": {}}},
    )

    with pytest.raises(HTTPException) as error:
        server.call_peer_agent(server.MeshAgentRequest(peer_id="unknown", message="Run a task"))

    assert error.value.status_code == 404
    assert error.value.detail == "Selected peer is not in the Mesh network"


def _remote_request(headers=()):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/mesh/snapshot",
        "raw_path": b"/api/mesh/snapshot",
        "query_string": b"",
        "headers": list(headers),
        "client": ("10.0.0.5", 12345),
        "server": ("localhost", 8000),
    })


def test_remote_api_requires_mesh_token(monkeypatch):
    monkeypatch.setenv("MESH_AGENT_TOKEN", "test-shared-token")

    async def call_next(_request):
        return Response(status_code=204)

    response = asyncio.run(server.protect_remote_api(_remote_request(), call_next))

    assert response.status_code == 403
    assert json.loads(response.body) == {
        "detail": "Remote API access requires a valid MESH_AGENT_TOKEN"
    }


def test_remote_api_accepts_valid_mesh_token(monkeypatch):
    monkeypatch.setenv("MESH_AGENT_TOKEN", "test-shared-token")
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return Response(status_code=204)

    response = asyncio.run(
        server.protect_remote_api(
            _remote_request([(b"x-mesh-agent-token", b"test-shared-token")]),
            call_next,
        )
    )

    assert response.status_code == 204
    assert called
