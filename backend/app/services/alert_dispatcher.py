"""
Real-time WebSocket alert dispatcher.
Maintains a pool of connected dashboard clients (WS /ws/alerts) and
broadcasts alert JSON payloads to all of them the instant an alert
record is created — target end-to-end latency < 100ms.
"""
import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger("sentinel.ws")


class ConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, *, subprotocol: str | None = None) -> None:
        # Chromium fails the handshake when the client offered a subprotocol
        # (`new WebSocket(url, [ticket])`) but the 101 response omits
        # Sec-WebSocket-Protocol -- so echo back the exact value the client
        # offered. The ticket was already consumed for auth and the client
        # already holds it; echoing it in the response header leaks nothing
        # new (it is a ~60s, purpose-scoped, single-use ticket).
        await websocket.accept(subprotocol=subprotocol)
        async with self._lock:
            self._connections.add(websocket)
        logger.info("WS client connected; total=%d", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        logger.info("WS client disconnected; total=%d", len(self._connections))

    async def broadcast(self, payload: dict) -> None:
        message = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 — client vanished mid-broadcast
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)


connection_manager = ConnectionManager()
