from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from mosaivue.models import User, WebSession
from mosaivue.security import create_session, hash_password, revoke_session
from mosaivue.services.event_stream import authenticated_events, event_session_valid


class Messages:
    def __init__(self):
        self.closed = False

    async def subscribe(self):
        try:
            for number in range(3):
                yield {"event": "camera.changed", "data": {"number": number}}
        finally:
            self.closed = True


async def connected():
    return False


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["logout", "expire", "disable"])
async def test_event_stream_stops_after_session_changes_without_leaking_next_event(db, change) -> None:
    user = User(username="event-user", password_hash=hash_password("fixture password"), is_admin=True)
    db.add(user)
    db.flush()
    session = create_session(db, user)
    db.commit()
    messages = Messages()
    stream = authenticated_events(messages, session.token, connected)
    assert '"number":0' in await anext(stream)
    if change == "logout":
        revoke_session(db, session.token)
    elif change == "expire":
        row = db.scalar(select(WebSession))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    else:
        user.enabled = False
    db.commit()
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert messages.closed


def test_missing_or_unknown_event_session_is_not_valid(db) -> None:
    assert not event_session_valid(None)
    assert not event_session_valid("unknown")
