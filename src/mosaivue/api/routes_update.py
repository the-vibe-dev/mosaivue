from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

from .. import __version__
from ..config import load_settings
from .dependencies import Auth, CSRF

router = APIRouter(prefix="/update", tags=["updates"])


@router.get("/check")
def check_update(_: Auth) -> dict[str, object]:
    settings = load_settings()
    if not settings.update_checks_enabled:
        return {"enabled": False, "current_version": __version__, "update_available": False}
    api_url = os.environ.get("MOSAIVUE_RELEASE_API")
    if not api_url:
        return {
            "enabled": True,
            "configured": False,
            "current_version": __version__,
            "update_available": False,
            "message": "Set MOSAIVUE_RELEASE_API to the project's GitHub latest-release API URL after publication.",
        }
    request = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"mosaivue/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            document = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"Update check failed: {exc}") from exc
    latest = str(document.get("tag_name", "")).lstrip("v")
    return {
        "enabled": True,
        "configured": True,
        "current_version": __version__,
        "latest_version": latest,
        "update_available": bool(latest and latest != __version__),
        "release_name": document.get("name"),
        "published_at": document.get("published_at"),
    }


@router.post("/apply")
def apply_update(_: CSRF) -> dict[str, object]:
    return {
        "started": False,
        "message": "Use `sudo mosaivue update` for a transactional update with backup and service control.",
    }
