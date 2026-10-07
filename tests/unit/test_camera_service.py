from __future__ import annotations

from sqlalchemy.orm import Session

from mosaivue.schemas import CameraCreate, CameraUpdate, StreamProfileIn
from mosaivue.security import CredentialCipher
from mosaivue.services.cameras import CameraService


def test_camera_credentials_are_separated_from_stream_url(
    db: Session, cipher: CredentialCipher
) -> None:
    service = CameraService(db, cipher)
    camera = service.create(
        CameraCreate(
            name="Front Door",
            tags=["Door", "outside", "door"],
            stream_profiles=[
                StreamProfileIn(
                    name="Main", url="rtsp://viewer:s3cret@192.0.2.9:8554/live"
                )
            ],
        )
    )
    db.flush()
    output = service.output(camera).model_dump()
    assert output["username"] == "viewer"
    assert output["has_password"] is True
    assert output["stream_profiles"][0]["url"] == "rtsp://192.0.2.9:8554/live"
    assert "s3cret" not in str(output)
    _, _, resolved = service.resolve_stream_url(camera.id)
    assert resolved == "rtsp://viewer:s3cret@192.0.2.9:8554/live"


def test_camera_password_can_be_replaced_without_returning_it(
    db: Session, cipher: CredentialCipher
) -> None:
    service = CameraService(db, cipher)
    camera = service.create(
        CameraCreate(
            name="Garage",
            username="one",
            password="old",
            stream_profiles=[StreamProfileIn(name="Main", url="rtsp://192.0.2.10/live")],
        )
    )
    service.update(camera.id, CameraUpdate(password="new"))
    _, _, resolved = service.resolve_stream_url(camera.id)
    assert "one:new@" in resolved
    assert "new" not in service.output(camera).model_dump_json()


def test_rtsps_credentials_are_stored_separately(
    db: Session, cipher: CredentialCipher
) -> None:
    service = CameraService(db, cipher)
    camera = service.create(
        CameraCreate(
            name="UniFi",
            stream_profiles=[StreamProfileIn(url="rtsps://viewer:secret@192.0.2.50:7441/live")],
        )
    )
    db.flush()
    output = service.output(camera).model_dump()
    assert output["stream_profiles"][0]["url"] == "rtsps://192.0.2.50:7441/live"
    assert "secret" not in str(output)
    assert service.resolve_stream_url(camera.id)[2] == "rtsps://viewer:secret@192.0.2.50:7441/live"
