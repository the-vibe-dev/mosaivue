from __future__ import annotations

import json

from mosaivue.events import EventBus


def test_sse_uses_default_message_event_and_preserves_type() -> None:
    encoded = EventBus.encode_sse(
        {"event": "layout.activated", "data": {"id": "main"}, "timestamp": "now"}
    )
    assert encoded.startswith("data: ")
    assert "event:" not in encoded
    payload = json.loads(encoded.removeprefix("data: ").strip())
    assert payload == {
        "type": "layout.activated",
        "data": {"id": "main"},
        "timestamp": "now",
    }
