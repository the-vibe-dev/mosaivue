from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError

from ..schemas import CameraCreate, CameraOut, CameraUpdate
from ..services.cameras import CameraService
from ..services.stream_probe import StreamProbeUnavailable, capture_thumbnail, probe_stream
from .dependencies import Auth, CSRF, DB, get_cipher

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _service(db: DB) -> CameraService:
    return CameraService(db, get_cipher())


@router.get("", response_model=list[CameraOut])
def list_cameras(
    db: DB,
    _: Auth,
    search: str | None = None,
    tag: str | None = None,
) -> list[CameraOut]:
    service = _service(db)
    return [service.output(camera) for camera in service.list(search=search, tag=tag)]


@router.post("", response_model=CameraOut, status_code=201)
async def create_camera(payload: CameraCreate, request: Request, db: DB, _: CSRF) -> CameraOut:
    service = _service(db)
    try:
        camera = service.create(payload)
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A camera with this name already exists") from exc
    result = service.output(camera)
    await request.app.state.events.publish("camera.changed", result.model_dump(mode="json"))
    return result


@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: str, db: DB, _: Auth) -> CameraOut:
    service = _service(db)
    try:
        return service.output(service.get(camera_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: str, payload: CameraUpdate, request: Request, db: DB, _: CSRF
) -> CameraOut:
    service = _service(db)
    try:
        camera = service.update(camera_id, payload)
        db.flush()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A camera with this name already exists") from exc
    result = service.output(camera)
    await request.app.state.events.publish("camera.changed", result.model_dump(mode="json"))
    return result


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: str, request: Request, db: DB, _: CSRF) -> Response:
    try:
        _service(db).delete(camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await request.app.state.events.publish("camera.deleted", {"id": camera_id})
    return Response(status_code=204)


@router.post("/{camera_id}/duplicate", response_model=CameraOut, status_code=201)
async def duplicate_camera(camera_id: str, request: Request, db: DB, _: CSRF) -> CameraOut:
    service = _service(db)
    try:
        camera = service.duplicate(camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = service.output(camera)
    await request.app.state.events.publish("camera.changed", result.model_dump(mode="json"))
    return result


@router.post("/{camera_id}/test")
async def test_camera(
    camera_id: str,
    db: DB,
    _: CSRF,
    stream_profile_id: str | None = None,
) -> dict[str, object]:
    service = _service(db)
    try:
        _, profile, url = service.resolve_stream_url(camera_id, stream_profile_id)
        result = await asyncio.to_thread(probe_stream, url)
        result["profile_id"] = profile.id
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StreamProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/{camera_id}/preview")
async def camera_preview(
    camera_id: str,
    db: DB,
    _: Auth,
    stream_profile_id: str | None = None,
    width: Annotated[int, Query(ge=160, le=1920)] = 640,
) -> Response:
    service = _service(db)
    try:
        _, _, url = service.resolve_stream_url(camera_id, stream_profile_id)
        image = await asyncio.to_thread(capture_thumbnail, url, width=width)
        return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StreamProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to capture preview") from exc
