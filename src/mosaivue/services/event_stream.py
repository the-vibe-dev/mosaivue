"""Session-scoped events without holding a SQLite transaction for an SSE socket."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing

from ..db import get_session_factory
from ..events import EventBus
from ..security import get_session


def event_session_valid(token: str | None) -> bool:
    if not token:
        return False
    with get_session_factory()() as db:
        return get_session(db, token) is not None


async def authenticated_events(
    events: EventBus, token: str, disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    async with aclosing(events.subscribe()) as messages:
        async for message in messages:
            if await disconnected() or not await asyncio.to_thread(event_session_valid, token):
                return
            yield EventBus.encode_sse(message)
