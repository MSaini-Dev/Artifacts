import asyncio

from aiohttp.test_utils import TestClient, TestServer

from mesh.mesh.api import make_app


def test_prompt_endpoint_requires_bearer_token(monkeypatch):
    async def run_test():
        monkeypatch.setenv("MESH_PROMPT_TOKEN", "test-token")
        client = TestClient(TestServer(make_app(None, None)))
        await client.start_server()
        try:
            response = await client.post("/prompt", json={"prompt": "Run a task"})
            assert response.status == 401
            assert await response.json() == {"error": "Unauthorized"}
        finally:
            await client.close()

    asyncio.run(run_test())


def test_prompt_endpoint_runs_agent_in_process(monkeypatch):
    async def run_test():
        monkeypatch.setenv("MESH_PROMPT_TOKEN", "test-token")
        calls = []

        def fake_call_agent(**kwargs):
            calls.append(kwargs)
            return "Task completed"

        monkeypatch.setattr("backend.agent.single_agent.call_agent", fake_call_agent)
        client = TestClient(TestServer(make_app(None, None)))
        await client.start_server()
        try:
            response = await client.post(
                "/prompt",
                json={"prompt": "  Run a safe task  "},
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status == 200
            assert await response.json() == {
                "success": True,
                "response": "Task completed",
            }
            assert calls == [{"user_prompt": "Run a safe task", "verbose": False}]
        finally:
            await client.close()

    asyncio.run(run_test())


def test_prompt_endpoint_validates_prompt(monkeypatch):
    async def run_test():
        monkeypatch.setenv("MESH_PROMPT_TOKEN", "test-token")
        client = TestClient(TestServer(make_app(None, None)))
        await client.start_server()
        try:
            response = await client.post(
                "/prompt",
                json={"prompt": "  "},
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status == 400
            assert await response.json() == {"error": "A non-empty 'prompt' is required"}
        finally:
            await client.close()

    asyncio.run(run_test())
