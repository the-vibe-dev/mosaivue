from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ..models import DisplayProfile, Layout
from ..schemas import DisplayProfileIn, DisplayProfileOut
from ..services.capabilities import detect_drm_outputs
from .dependencies import CSRF, DB, Auth

router = APIRouter(prefix="/display", tags=["display"])


@router.get("/outputs")
def outputs(_: Auth) -> list[dict[str, object]]:
    return detect_drm_outputs()


@router.get("/profiles", response_model=list[DisplayProfileOut])
def list_profiles(db: DB, _: Auth) -> list[DisplayProfileOut]:
    return [
        DisplayProfileOut.model_validate(item)
        for item in db.scalars(select(DisplayProfile).order_by(DisplayProfile.name))
    ]


@router.post("/profiles", response_model=DisplayProfileOut, status_code=201)
async def create_profile(
    payload: DisplayProfileIn, request: Request, db: DB, _: CSRF
) -> DisplayProfileOut:
    profile = DisplayProfile(**payload.model_dump())
    db.add(profile)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A display profile with this name already exists") from exc
    result = DisplayProfileOut.model_validate(profile)
    db.commit()
    await request.app.state.events.publish("display.changed", result.model_dump(mode="json"))
    return result


@router.put("/profiles/{profile_id}", response_model=DisplayProfileOut)
async def update_profile(
    profile_id: str, payload: DisplayProfileIn, request: Request, db: DB, _: CSRF
) -> DisplayProfileOut:
    profile = db.get(DisplayProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Display profile not found")
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A display profile with this name already exists") from exc
    result = DisplayProfileOut.model_validate(profile)
    db.commit()
    await request.app.state.events.publish("display.changed", result.model_dump(mode="json"))
    return result


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, request: Request, db: DB, _: CSRF) -> Response:
    # Check the relationship in the DELETE itself so a racing association cannot
    # slip between a preflight SELECT and an FK SET NULL deletion.
    associated = select(Layout.id).where(Layout.display_profile_id == profile_id).exists()
    result = db.execute(delete(DisplayProfile).where(
        DisplayProfile.id == profile_id, ~associated,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        if db.get(DisplayProfile, profile_id) is None:
            raise HTTPException(status_code=404, detail="Display profile not found")
        names = list(db.scalars(select(Layout.name).where(
            Layout.display_profile_id == profile_id,
        ).order_by(Layout.name)))
        raise HTTPException(
            status_code=409,
            detail="Display profile is still used by layouts: " + ", ".join(names)
            + ". Detach it from those layouts before deleting.",
        )
    db.commit()
    await request.app.state.events.publish("display.deleted", {"id": profile_id})
    return Response(status_code=204)
