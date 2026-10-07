from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import Layout
from ..renderer.rpc import RendererRPCError
from ..schemas import LayoutCreate, LayoutData, LayoutOut, LayoutRevisionOut, LayoutUpdate
from ..services.layouts import LayoutService, LayoutValidationError
from .dependencies import Auth, CSRF, DB

router = APIRouter(prefix="/layouts", tags=["layouts"])


@router.get("", response_model=list[LayoutOut])
def list_layouts(db: DB, _: Auth) -> list[LayoutOut]:
    service = LayoutService(db)
    return [service.output(layout) for layout in service.list()]


@router.post("", response_model=LayoutOut, status_code=201)
async def create_layout(payload: LayoutCreate, request: Request, db: DB, auth: CSRF) -> LayoutOut:
    service = LayoutService(db)
    try:
        layout = service.create(payload, user_id=auth.user.id)
    except LayoutValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors, "warnings": exc.warnings}) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A layout with this name already exists") from exc
    result = service.output(layout)
    await request.app.state.events.publish("layout.changed", result.model_dump(mode="json"))
    return result


@router.get("/templates")
def layout_templates(_: Auth) -> list[dict[str, object]]:
    def slot(name: str, x: float, y: float, w: float, h: float) -> dict[str, object]:
        return {"name": name, "x": x, "y": y, "width": w, "height": h}

    return [
        {"id": "2x2", "name": "2 × 2", "slots": [slot(str(i + 1), (i % 2) / 2, (i // 2) / 2, 0.5, 0.5) for i in range(4)]},
        {"id": "3x3", "name": "3 × 3", "slots": [slot(str(i + 1), (i % 3) / 3, (i // 3) / 3, 1 / 3, 1 / 3) for i in range(9)]},
        {
            "id": "1+3",
            "name": "1 + 3",
            "slots": [
                slot("Primary", 0, 0, 0.75, 1),
                slot("2", 0.75, 0, 0.25, 1 / 3),
                slot("3", 0.75, 1 / 3, 0.25, 1 / 3),
                slot("4", 0.75, 2 / 3, 0.25, 1 / 3),
            ],
        },
        {
            "id": "1+5",
            "name": "1 + 5",
            "slots": [
                slot("Primary", 0, 0, 2 / 3, 1),
                *[slot(str(i + 2), 2 / 3, i / 5, 1 / 3, 1 / 5) for i in range(5)],
            ],
        },
    ]


@router.post("/validate")
def validate_layout(data: LayoutData, db: DB, _: Auth) -> dict[str, object]:
    errors, warnings = LayoutService(db).validate(data)
    return {"valid": not errors, "errors": errors, "warnings": warnings}


@router.get("/{layout_id}", response_model=LayoutOut)
def get_layout(layout_id: str, db: DB, _: Auth) -> LayoutOut:
    service = LayoutService(db)
    try:
        return service.output(service.get(layout_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{layout_id}", response_model=LayoutOut)
async def update_layout(
    layout_id: str, payload: LayoutUpdate, request: Request, db: DB, auth: CSRF
) -> LayoutOut:
    service = LayoutService(db)
    try:
        layout = service.update(layout_id, payload, user_id=auth.user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LayoutValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors, "warnings": exc.warnings}) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A layout with this name already exists") from exc
    result = service.output(layout)
    await request.app.state.events.publish("layout.changed", result.model_dump(mode="json"))
    return result


@router.delete("/{layout_id}", status_code=204)
async def delete_layout(layout_id: str, request: Request, db: DB, _: CSRF) -> Response:
    try:
        LayoutService(db).delete(layout_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await request.app.state.events.publish("layout.deleted", {"id": layout_id})
    return Response(status_code=204)


@router.get("/{layout_id}/revisions", response_model=list[LayoutRevisionOut])
def list_revisions(layout_id: str, db: DB, _: Auth) -> list[LayoutRevisionOut]:
    try:
        return [LayoutRevisionOut.model_validate(item) for item in LayoutService(db).revisions(layout_id)]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{layout_id}/revisions/{revision}/restore", response_model=LayoutOut)
async def restore_revision(
    layout_id: str, revision: int, request: Request, db: DB, auth: CSRF
) -> LayoutOut:
    service = LayoutService(db)
    try:
        layout = service.restore_revision(layout_id, revision, user_id=auth.user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = service.output(layout)
    await request.app.state.events.publish("layout.changed", result.model_dump(mode="json"))
    return result


@router.post("/{layout_id}/activate")
async def activate_layout(layout_id: str, request: Request, db: DB, _: CSRF) -> dict[str, object]:
    service = LayoutService(db)
    try:
        layout = service.get(layout_id)
        revision = service.current_revision(layout)
        if revision is None:
            raise LayoutValidationError(["Layout has no current revision"])
        data = LayoutData.model_validate(revision.data)
        errors, warnings = service.validate(data)
        if errors:
            raise LayoutValidationError(errors, warnings)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LayoutValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors, "warnings": exc.warnings}) from exc

    previous = db.scalar(select(Layout).where(Layout.active.is_(True)))
    try:
        renderer_status = await request.app.state.renderer.call(
            "apply_layout", layout_id=layout.id, revision=layout.current_revision
        )
    except RendererRPCError as exc:
        if previous and previous.id != layout.id:
            try:
                await request.app.state.renderer.call(
                    "apply_layout", layout_id=previous.id, revision=previous.current_revision
                )
            except RendererRPCError:
                pass
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    service.activate(layout_id)
    await request.app.state.events.publish(
        "layout.activated", {"id": layout.id, "revision": layout.current_revision}
    )
    return {"layout": service.output(layout).model_dump(mode="json"), "renderer": renderer_status}
