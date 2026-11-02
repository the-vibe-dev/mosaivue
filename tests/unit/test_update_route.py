from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mosaivue.api import routes_update


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://example.com/latest", "https://user:password@example.com/latest"])
def test_update_check_rejects_unsafe_api_urls(monkeypatch, url: str) -> None:
    monkeypatch.setenv("MOSAIVUE_RELEASE_API", url)
    monkeypatch.setattr(routes_update, "load_settings", lambda: SimpleNamespace(update_checks_enabled=True))
    monkeypatch.setattr(routes_update.httpx, "get", lambda *args, **kwargs: pytest.fail("URL was fetched"))
    with pytest.raises(HTTPException) as exc:
        routes_update.check_update(None)
    assert exc.value.status_code == 502


def test_update_check_fetches_https_without_redirects(monkeypatch) -> None:
    monkeypatch.setenv("MOSAIVUE_RELEASE_API", "https://api.example.com/latest")
    monkeypatch.setattr(routes_update, "load_settings", lambda: SimpleNamespace(update_checks_enabled=True))
    calls: list[tuple[str, bool]] = []

    def fetch(url: str, **kwargs):
        calls.append((url, kwargs["follow_redirects"]))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"tag_name": "v0.2.0b1"})

    monkeypatch.setattr(routes_update.httpx, "get", fetch)
    result = routes_update.check_update(None)
    assert result["latest_version"] == "0.2.0b1"
    assert calls == [("https://api.example.com/latest", False)]
