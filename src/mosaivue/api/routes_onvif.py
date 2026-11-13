from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from ..schemas import CameraOut
from ..schemas_onvif import OnvifConnection, OnvifImport, OnvifProfiles
from ..services.cameras import CameraService
from ..services.onvif import OnvifError, camera_payload, inspect_profiles
from .dependencies import CSRF, DB, Admin, get_cipher

router = APIRouter(prefix="/onvif", tags=["ONVIF onboarding"])


@router.post("/profiles", response_model=OnvifProfiles)
async def inspect_onvif(payload: OnvifConnection, _: CSRF, _admin: Admin) -> OnvifProfiles:
    try:
        return await inspect_profiles(payload)
    except OnvifError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import", response_model=CameraOut, status_code=201)
async def import_onvif(
    payload: OnvifImport, request: Request, db: DB, _: CSRF, _admin: Admin,
) -> CameraOut:
    try:
        configuration = await camera_payload(payload)
        service = CameraService(db, get_cipher())
        camera = service.create(configuration)
        db.flush()
        result = service.output(camera)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A camera with this name already exists") from exc
    except ValueError as exc:
        # Exceptions in the network service are sanitized at their source.
        detail = str(exc) if isinstance(exc, OnvifError) else "The camera returned incompatible stream profiles or credentials"
        raise HTTPException(status_code=422, detail=detail) from exc
    db.commit()
    await request.app.state.events.publish("camera.changed", result.model_dump(mode="json"))
    return result
