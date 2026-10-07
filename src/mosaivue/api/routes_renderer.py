from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import load_settings
from ..renderer.factory import available_backends
from ..renderer.rpc import RendererRPCError
from ..schemas import FocusRequest, RendererConfigRequest
from ..services.renderer_config import renderer_config, request_renderer_restart, select_renderer_backend
from .dependencies import Auth, CSRF

router = APIRouter(prefix="/renderer", tags=["renderer"])


@router.get("/backends")
def backends(_: Auth) -> list[dict[str, object]]:
    return available_backends(load_settings())


@router.get("/config")
def get_renderer_config(auth: Auth) -> dict[str, object]:
    return {**renderer_config(), "can_change": auth.user.is_admin}


@router.put("/config")
def set_renderer_config(payload: RendererConfigRequest, auth: CSRF) -> dict[str, object]:
    if not auth.user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    try:
        changed = select_renderer_backend(payload.renderer_backend)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    restarted = request_renderer_restart() if changed else False
    return {**renderer_config(), "restart_requested": restarted, "changed": changed}


@router.get("/status")
async def status(request: Request, _: Auth) -> dict[str, object]:
    try:
        return await request.app.state.renderer.call("status")
    except RendererRPCError as exc:
        return {"state": "UNAVAILABLE", "error": str(exc), "streams": {}}


@router.post("/focus")
async def focus(payload: FocusRequest, request: Request, _: CSRF) -> dict[str, object]:
    try:
        return await request.app.state.renderer.call(
            "focus_camera",
            camera_id=payload.camera_id,
            stream_profile_id=payload.stream_profile_id,
            aspect_mode=payload.aspect_mode.value,
            duration_seconds=payload.duration_seconds,
        )
    except RendererRPCError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/restore")
async def restore(request: Request, _: CSRF) -> dict[str, object]:
    try:
        return await request.app.state.renderer.call("restore_layout")
    except RendererRPCError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/streams/{slot_id}/restart")
async def restart_stream(slot_id: str, request: Request, _: CSRF) -> dict[str, object]:
    try:
        return await request.app.state.renderer.call("restart_stream", slot_id=slot_id)
    except RendererRPCError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
