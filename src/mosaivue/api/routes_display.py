from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import DisplayProfile
from ..schemas import DisplayProfileIn, DisplayProfileOut
from ..services.capabilities import detect_drm_outputs
from .dependencies import Auth, CSRF, DB

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
    result = DisplayProfileOut.model_validate(profile)
    await request.app.state.events.publish("display.changed", result.model_dump(mode="json"))
    return result


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: str, db: DB, _: CSRF) -> Response:
    profile = db.get(DisplayProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Display profile not found")
    db.delete(profile)
    return Response(status_code=204)
