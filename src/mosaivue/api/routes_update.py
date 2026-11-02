from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException

from .. import __version__
from ..config import load_settings
from .dependencies import CSRF, Auth

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
    try:
        parsed = urlsplit(api_url)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Update check requires an HTTPS release API URL") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=502, detail="Update check requires an HTTPS release API URL")
    try:
        response = httpx.get(
            api_url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"mosaivue/{__version__}"},
            timeout=5,
            follow_redirects=False,
        )
        response.raise_for_status()
        document = response.json()
        if not isinstance(document, dict):
            raise ValueError("Release API did not return an object")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Update check failed: {type(exc).__name__}") from exc
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
