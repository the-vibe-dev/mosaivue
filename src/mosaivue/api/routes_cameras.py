from __future__ import annotations

from functools import partial
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy.exc import IntegrityError

from ..config import load_settings
from ..logging_utils import redact
from ..models import Camera, StreamProfile
from ..schemas import CameraCreate, CameraOut, CameraUpdate
from ..services.cameras import CameraService
from ..services.stream_probe import StreamProbeUnavailable, capture_thumbnail, probe_stream
from ..services.stream_work import StreamWorkBusy, StreamWorkPool
from .dependencies import CSRF, DB, Auth, get_cipher

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _service(db: DB) -> CameraService:
    return CameraService(db, get_cipher())


def _work_key(
    pool: StreamWorkPool, camera: Camera, profile: StreamProfile, url: str,
    operation: str, width: int | None = None,
) -> bytes:
    return pool.fingerprint(
        operation=operation, width=width, camera_id=camera.id,
        camera_updated_at=camera.updated_at.isoformat(), url=url,
        credential=camera.credential.encrypted_secret if camera.credential else None,
        profile={
            name: getattr(profile, name) for name in (
                "id", "name", "transport", "latency_profile", "codec", "width",
                "height", "fps", "bitrate", "priority",
            )
        },
        profile_updated_at=profile.updated_at.isoformat(),
    )


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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = service.output(camera)
    db.commit()
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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = service.output(camera)
    db.commit()
    await request.app.state.events.publish("camera.changed", result.model_dump(mode="json"))
    return result


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: str, request: Request, db: DB, _: CSRF) -> Response:
    try:
        _service(db).delete(camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
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
    db.commit()
    await request.app.state.events.publish("camera.changed", result.model_dump(mode="json"))
    return result


@router.post("/{camera_id}/test")
async def test_camera(
    camera_id: str,
    request: Request,
    db: DB,
    _: CSRF,
    stream_profile_id: str | None = None,
) -> dict[str, object]:
    service = _service(db)
    try:
        camera, profile, url = service.resolve_stream_url(camera_id, stream_profile_id)
        pool = request.app.state.stream_work
        key = _work_key(pool, camera, profile, url, "probe")
        result = await pool.run(key, partial(probe_stream, url, transport=profile.transport))
        return {**result, "profile_id": profile.id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StreamProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StreamWorkBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "2"}) from exc
    except Exception as exc:
        return {"success": False, "error": str(redact(str(exc)))}


@router.get("/{camera_id}/preview")
async def camera_preview(
    camera_id: str,
    request: Request,
    db: DB,
    _: Auth,
    stream_profile_id: str | None = None,
    width: Annotated[int, Query(ge=160, le=1920)] = 640,
) -> Response:
    if not load_settings().web_preview_enabled:
        raise HTTPException(status_code=403, detail="Web camera previews are disabled on this appliance")
    service = _service(db)
    try:
        camera, profile, url = service.resolve_stream_url(camera_id, stream_profile_id)
        pool = request.app.state.stream_work
        key = _work_key(pool, camera, profile, url, "preview", width)
        image = await pool.run(
            key, partial(capture_thumbnail, url, width=width, transport=profile.transport),
            cache_image=True,
        )
        return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StreamProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StreamWorkBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "2"}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to capture preview") from exc
