from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from ..renderer.rpc import RendererRPCError
from ..schemas import RotationGroupIn, RotationGroupOut
from ..services.rotations import RotationService
from .dependencies import Auth, CSRF, DB

router = APIRouter(prefix="/rotation-groups", tags=["rotation groups"])


@router.get("", response_model=list[RotationGroupOut])
def list_groups(db: DB, _: Auth) -> list[RotationGroupOut]:
    return [RotationGroupOut.model_validate(item) for item in RotationService(db).list()]


@router.post("", response_model=RotationGroupOut, status_code=201)
async def create_group(payload: RotationGroupIn, request: Request, db: DB, _: CSRF) -> RotationGroupOut:
    try:
        group = RotationService(db).create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A rotation group with this name already exists") from exc
    result = RotationGroupOut.model_validate(group)
    await request.app.state.events.publish("rotation.changed", result.model_dump(mode="json"))
    return result


@router.get("/{group_id}", response_model=RotationGroupOut)
def get_group(group_id: str, db: DB, _: Auth) -> RotationGroupOut:
    try:
        return RotationGroupOut.model_validate(RotationService(db).get(group_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{group_id}", response_model=RotationGroupOut)
async def update_group(
    group_id: str, payload: RotationGroupIn, request: Request, db: DB, _: CSRF
) -> RotationGroupOut:
    try:
        group = RotationService(db).update(group_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = RotationGroupOut.model_validate(group)
    await request.app.state.events.publish("rotation.changed", result.model_dump(mode="json"))
    return result


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: str, request: Request, db: DB, _: CSRF) -> Response:
    try:
        RotationService(db).delete(group_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await request.app.state.events.publish("rotation.deleted", {"id": group_id})
    return Response(status_code=204)


@router.post("/{group_id}/pause")
async def pause_group(group_id: str, request: Request, db: DB, _: CSRF) -> dict[str, bool]:
    try:
        RotationService(db).get(group_id)
        await request.app.state.renderer.call("rotation_pause", group_id=group_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RendererRPCError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{group_id}/resume")
async def resume_group(group_id: str, request: Request, db: DB, _: CSRF) -> dict[str, bool]:
    try:
        RotationService(db).get(group_id)
        await request.app.state.renderer.call("rotation_resume", group_id=group_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RendererRPCError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/slots/{slot_id}/next")
async def next_camera(slot_id: str, request: Request, _: CSRF) -> dict[str, object]:
    try:
        return await request.app.state.renderer.call("rotation_next", slot_id=slot_id)
    except RendererRPCError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/slots/{slot_id}/previous")
async def previous_camera(slot_id: str, request: Request, _: CSRF) -> dict[str, object]:
    try:
        return await request.app.state.renderer.call("rotation_previous", slot_id=slot_id)
    except RendererRPCError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
