from __future__ import annotations

import json
from sqlalchemy.orm import Session

from mosaivue.schemas import CameraCreate, StreamProfileIn
from mosaivue.security import CredentialCipher
from mosaivue.services.backup import create_backup, export_configuration, read_backup
from mosaivue.services.cameras import CameraService


def test_sanitized_export_never_contains_credentials(db: Session, cipher: CredentialCipher) -> None:
    CameraService(db, cipher).create(
        CameraCreate(
            name="Driveway",
            username="viewer",
            password="super-secret",
            stream_profiles=[StreamProfileIn(name="Main", url="rtsp://192.0.2.11/live")],
        )
    )
    db.flush()
    document = export_configuration(db, cipher, include_credentials=False)
    encoded = json.dumps(document)
    assert "super-secret" not in encoded
    assert "viewer" not in encoded
    assert document["credentials_included"] is False


def test_encrypted_backup_requires_passphrase(db: Session, cipher: CredentialCipher) -> None:
    CameraService(db, cipher).create(
        CameraCreate(
            name="Back Yard",
            username="viewer",
            password="secret-two",
            stream_profiles=[StreamProfileIn(name="Main", url="rtsp://192.0.2.12/live")],
        )
    )
    db.flush()
    payload = create_backup(db, cipher, include_credentials=True, passphrase="long-passphrase")
    assert b"secret-two" not in payload
    restored = read_backup(payload, passphrase="long-passphrase")
    assert restored["credentials_included"] is True
    assert restored["cameras"][0]["credential"]["password"] == "secret-two"
