"""In-process WebSocket delivery for tool activity events."""

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any, Dict, Set, Tuple

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_clients: Dict[int, Set[Tuple[asyncio.AbstractEventLoop, WebSocket]]] = {}
_clients_lock = threading.Lock()


async def register_client(conversation_id: int, websocket: WebSocket) -> None:
    loop = asyncio.get_running_loop()
    with _clients_lock:
        _clients.setdefault(conversation_id, set()).add((loop, websocket))


async def unregister_client(conversation_id: int, websocket: WebSocket) -> None:
    with _clients_lock:
        clients = _clients.get(conversation_id)
        if clients is None:
            return
        disconnected = {entry for entry in clients if entry[1] is websocket}
        clients.difference_update(disconnected)
        if not clients:
            _clients.pop(conversation_id, None)


async def send_activity(websocket: WebSocket, event: Dict[str, Any]) -> None:
    await websocket.send_json(event)


def publish_activity(conversation_id: int, event: Dict[str, Any]) -> None:
    """Schedule an event on each subscribed WebSocket's event loop."""
    with _clients_lock:
        clients = tuple(_clients.get(conversation_id, ()))

    for loop, websocket in clients:
        if loop.is_closed():
            continue
        future = asyncio.run_coroutine_threadsafe(send_activity(websocket, event), loop)
        future.add_done_callback(
            lambda completed, cid=conversation_id, client=websocket: _discard_failed_client(
                cid, client, completed
            )
        )


def _discard_failed_client(
    conversation_id: int,
    websocket: WebSocket,
    future: Future[None],
) -> None:
    try:
        future.result()
    except Exception:
        logger.debug("Removing disconnected activity WebSocket for conversation %s.", conversation_id)
        with _clients_lock:
            clients = _clients.get(conversation_id)
            if clients is None:
                return
            disconnected = {entry for entry in clients if entry[1] is websocket}
            clients.difference_update(disconnected)
            if not clients:
                _clients.pop(conversation_id, None)
