from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import func, select

from .. import __version__
from ..config import load_settings
from ..models import Camera, Layout, RotationGroup
from ..renderer.rpc import RendererRPCError
from ..schemas import LayoutData
from ..services.benchmark import BenchmarkUnavailable, synthetic_benchmark
from ..services.capabilities import detect_capabilities, live_metrics, write_capabilities
from ..services.diagnostics import build_support_bundle, security_audit
from ..services.layouts import LayoutService
from .dependencies import Auth, CSRF, DB

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(request: Request, db: DB, _: Auth) -> dict[str, object]:
    renderer: dict[str, object]
    try:
        renderer = await request.app.state.renderer.call("status")
    except RendererRPCError as exc:
        renderer = {"state": "UNAVAILABLE", "error": str(exc), "streams": {}}
    streams = renderer.get("streams", {}) if isinstance(renderer, dict) else {}
    failed = 0
    if isinstance(streams, dict):
        failed = sum(
            1
            for item in streams.values()
            if isinstance(item, dict) and item.get("state") not in {"LIVE", "CONNECTING"}
        )
    return {
        "version": __version__,
        "time": datetime.now(UTC).isoformat(),
        "metrics": live_metrics(),
        "counts": {
            "cameras": db.scalar(select(func.count()).select_from(Camera)) or 0,
            "layouts": db.scalar(select(func.count()).select_from(Layout)) or 0,
            "rotation_groups": db.scalar(select(func.count()).select_from(RotationGroup)) or 0,
            "active_streams": len(streams) if isinstance(streams, dict) else 0,
            "failed_streams": failed,
        },
        "renderer": renderer,
        "settings": {
            "bind": load_settings().bind,
            "port": load_settings().port,
            "profile": load_settings().profile,
        },
    }


@router.get("/doctor")
def doctor(_: Auth, refresh: bool = False) -> dict[str, object]:
    return write_capabilities() if refresh else detect_capabilities()


@router.get("/security-audit")
def audit(_: Auth) -> dict[str, object]:
    return security_audit()


@router.get("/support-bundle")
def support_bundle(db: DB, _: Auth) -> Response:
    content = build_support_bundle(db)
    filename = f"mosaivue-support-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/benchmark")
async def benchmark(
    _: CSRF,
    streams: int = Query(default=6, ge=1, le=16),
    width: int = Query(default=1920, ge=320, le=3840),
    height: int = Query(default=1080, ge=240, le=2160),
    duration: int = Query(default=5, ge=2, le=30),
) -> dict[str, object]:
    try:
        return await asyncio.to_thread(
            synthetic_benchmark,
            streams=streams,
            width=width,
            height=height,
            duration_seconds=duration,
        )
    except BenchmarkUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/optimize")
def optimize(_: Auth) -> dict[str, object]:
    capabilities = detect_capabilities()
    plugins = capabilities.get("gstreamer", {}).get("plugins", {})
    sink = capabilities.get("recommended_sink")
    decoders = capabilities.get("gstreamer", {}).get("decoders", [])
    return {
        "recommended_profile": capabilities.get("recommended_profile"),
        "renderer_backend": capabilities.get("recommended_backend"),
        "renderer_sink": sink,
        "hardware_decoders": [name for name in decoders if str(name).startswith("v4l2")],
        "apply_automatically": False,
        "reason": "Recommendations are based on detected local capabilities; camera settings are never changed.",
    }


@router.post("/config/validate")
def validate_config(db: DB, _: CSRF) -> dict[str, object]:
    service = LayoutService(db)
    results = []
    valid = True
    for layout in service.list():
        revision = service.current_revision(layout)
        if not revision:
            results.append({"layout_id": layout.id, "valid": False, "errors": ["No revision"]})
            valid = False
            continue
        try:
            data = LayoutData.model_validate(revision.data)
            errors, warnings = service.validate(data)
        except Exception as exc:
            errors, warnings = [str(exc)], []
        results.append({"layout_id": layout.id, "valid": not errors, "errors": errors, "warnings": warnings})
        valid = valid and not errors
    return {"valid": valid, "layouts": results}
