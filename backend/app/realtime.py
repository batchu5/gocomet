"""WebSocket fan-out. Clients get a small 'something changed' message and refetch over REST."""

import asyncio
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        clients = list(self._clients)
        results = await asyncio.gather(*(c.send_json(message) for c in clients), return_exceptions=True)
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                log.debug("Dropping websocket client: %s", result)
                self.disconnect(client)

    async def rfq_changed(self, rfq_id: int, reason: str) -> None:
        await self.broadcast({"type": "rfq_updated", "rfq_id": rfq_id, "reason": reason})


manager = ConnectionManager()
