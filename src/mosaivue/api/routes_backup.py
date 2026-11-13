from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Layout
from ..renderer.rpc import RendererRPCError
from ..schemas import BackupRequest, ImportRequest
from ..services.backup import (
    MAX_BACKUP_BYTES,
    create_backup,
    export_configuration,
    import_configuration,
    read_backup,
)
from ..services.backup_validation import BackupValidationError
from .dependencies import CSRF, DB, Auth, get_cipher

router = APIRouter(prefix="/backup", tags=["backup and restore"])


@router.get("/export")
def export_config(db: DB, _: Auth) -> Response:
    document = export_configuration(db, get_cipher(), include_credentials=False)
    filename = f"mosaivue-export-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        content=json.dumps(document, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/create")
def backup(payload: BackupRequest, db: DB, _: CSRF) -> Response:
    try:
        content = create_backup(
            db,
            get_cipher(),
            include_credentials=payload.include_credentials,
            passphrase=payload.passphrase,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    extension = "cwbackup" if payload.include_credentials else "zip"
    filename = f"mosaivue-backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.{extension}"
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore(
    request: Request,
    db: DB,
    _: CSRF,
    file: Annotated[UploadFile, File()],
    passphrase: Annotated[str | None, Form()] = None,
    merge: Annotated[bool, Form()] = True,
) -> dict[str, object]:
    try:
        payload = await file.read(MAX_BACKUP_BYTES + 1)
    finally:
        await file.close()
    if len(payload) > MAX_BACKUP_BYTES:
        raise HTTPException(status_code=413, detail="Backup exceeds the 100 MiB limit")
    try:
        document = read_backup(payload, passphrase=passphrase)
        counts = import_configuration(db, get_cipher(), document, merge=merge)
    except BackupValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Restore failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Restore failed. No configuration changes were applied; check the backup and its configuration references.") from exc
    state = await _finish_import(request, db)
    await request.app.state.events.publish("configuration.restored", counts)
    return {"ok": True, "imported": counts, **state}


@router.post("/import")
async def import_config(payload: ImportRequest, request: Request, db: DB, _: CSRF) -> dict[str, object]:
    try:
        counts = import_configuration(db, get_cipher(), payload.document, merge=payload.merge)
    except BackupValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Import failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Import failed. No configuration changes were applied; check the configuration format and references.") from exc
    state = await _finish_import(request, db)
    await request.app.state.events.publish("configuration.imported", counts)
    return {"ok": True, "imported": counts, **state}


async def _finish_import(request: Request, db: Session) -> dict[str, object]:
    # The renderer uses its own database connection and must observe the
    # committed replacement before attempting to apply it.
    db.commit()
    active = db.scalar(select(Layout).where(Layout.active.is_(True)))
    if active is None:
        return {
            "renderer_applied": False,
            "renderer_warning": "No active layout is selected. Restart the renderer to clear any old output, then choose a layout.",
        }
    try:
        await request.app.state.renderer.call(
            "apply_layout", layout_id=active.id, revision=active.current_revision
        )
    except RendererRPCError:
        return {
            "renderer_applied": False,
            "renderer_warning": "Configuration was saved, but the renderer could not apply it. Restart the renderer or apply the layout again.",
        }
    return {"renderer_applied": True, "renderer_warning": None}
