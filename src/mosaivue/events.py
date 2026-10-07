from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: str, data: Any) -> None:
        message = {
            "event": event,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield {"event": "keepalive", "data": None}
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    @staticmethod
    def encode_sse(message: dict[str, Any]) -> str:
        # Use the default SSE ``message`` event so EventSource.onmessage receives
        # every update. Preserve the domain event name inside the JSON envelope.
        payload = {
            "type": message.get("event", "message"),
            "data": message.get("data"),
            "timestamp": message.get("timestamp"),
        }
        data = json.dumps(payload, separators=(",", ":"), default=str)
        return f"data: {data}\n\n"
