import asyncio

from backend.agent.brain_langchain.api_manager.activity_stream import (
    publish_activity,
    register_client,
    unregister_client,
)


class FakeWebSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


def test_publish_activity_delivers_event_to_subscribed_client():
    async def run_test():
        websocket = FakeWebSocket()
        await register_client(918273, websocket)
        try:
            event = {"type": "tool_update", "interaction_id": 1, "tool": {"ID": 3}}
            publish_activity(918273, event)
            for _ in range(10):
                if websocket.events:
                    break
                await asyncio.sleep(0.001)
            assert websocket.events == [event]
        finally:
            await unregister_client(918273, websocket)

    asyncio.run(run_test())
