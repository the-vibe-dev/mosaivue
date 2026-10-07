from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile

from ..schemas import BackupRequest, ImportRequest
from ..services.backup import (
    create_backup,
    export_configuration,
    import_configuration,
    read_backup,
    validate_export,
)
from .dependencies import Auth, CSRF, DB, get_cipher

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
    file: UploadFile = File(...),
    passphrase: str | None = Form(default=None),
    merge: bool = Form(default=True),
) -> dict[str, object]:
    payload = await file.read()
    if len(payload) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup exceeds the 100 MiB limit")
    try:
        document = read_backup(payload, passphrase=passphrase)
        counts = import_configuration(db, get_cipher(), document, merge=merge)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Restore failed: {exc}") from exc
    await request.app.state.events.publish("configuration.restored", counts)
    return {"ok": True, "imported": counts}


@router.post("/import")
async def import_config(payload: ImportRequest, request: Request, db: DB, _: CSRF) -> dict[str, object]:
    try:
        validate_export(payload.document)
        counts = import_configuration(db, get_cipher(), payload.document, merge=payload.merge)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Import failed: {exc}") from exc
    await request.app.state.events.publish("configuration.imported", counts)
    return {"ok": True, "imported": counts}
