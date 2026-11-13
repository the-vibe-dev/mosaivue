from __future__ import annotations

import copy
import io
import json
import zipfile

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mosaivue.models import Camera, DisplayProfile, Layout, RotationGroup, Schedule, StreamProfile
from mosaivue.schemas import (
    CameraCreate,
    CameraUpdate,
    LayoutCreate,
    LayoutData,
    RotationGroupIn,
    Slot,
    StreamProfileIn,
)
from mosaivue.security import CredentialCipher
from mosaivue.services import backup
from mosaivue.services.backup import (
    create_backup,
    export_configuration,
    import_configuration,
    read_backup,
)
from mosaivue.services.cameras import CameraService
from mosaivue.services.layouts import LayoutService
from mosaivue.services.rotations import RotationService


def _wall(db: Session, cipher: CredentialCipher):
    camera = CameraService(db, cipher).create(CameraCreate(
        name="Garden", username="viewer", password="preserve this secret",
        stream_profiles=[
            StreamProfileIn(name="Main", url="rtsps://[2001:db8::5]:7441/live", width=1920, height=1080),
            StreamProfileIn(name="Sub", url="rtsp://192.0.2.5/sub", width=640, height=360),
        ],
    ))
    profile = camera.stream_profiles[1]
    group = RotationService(db).create(RotationGroupIn(
        name="Patrol", camera_entries=[{"camera_id": camera.id, "stream_profile_id": profile.id}],
    ))
    display = DisplayProfile(name="HDMI", width=1920, height=1080)
    db.add(display)
    db.flush()
    layout = LayoutService(db).create(LayoutCreate(
        name="Wall", display_profile_id=display.id,
        data=LayoutData(slots=[
            Slot(id="fixed", name="Garden", type="fixed", camera_id=camera.id,
                 stream_profile_id=profile.id, stream_selection="manual", x=0, y=0, width=.5, height=1),
            Slot(id="rotate", name="Patrol", type="rotation", rotation_group_id=group.id,
                 x=.5, y=0, width=.5, height=1),
        ]),
    ))
    LayoutService(db).activate(layout.id)
    db.add(Schedule(name="Morning", layout_id=layout.id, start_time="08:00", end_time="17:00"))
    db.commit()
    return camera, profile, group, layout


def test_sanitized_merge_keeps_credentials_profiles_and_revisions(db, cipher):
    camera, profile, _, layout = _wall(db, cipher)
    document = export_configuration(db, cipher)
    original_profile_id, original_layout_id = profile.id, layout.id
    result = import_configuration(db, cipher, document, merge=True)
    db.commit()
    assert result["cameras"] == result["layouts"] == 1
    current = db.scalar(select(Camera).where(Camera.name == "Garden"))
    assert current.id == camera.id
    assert current.credential is not None
    assert cipher.decrypt(current.credential.encrypted_secret, context=current.credential.id) == "preserve this secret"
    assert next(p for p in current.stream_profiles if p.name == "Sub").id == original_profile_id
    restored = db.get(Layout, original_layout_id)
    assert len(restored.revisions) == 1
    assert restored.revisions[0].data["slots"][0]["stream_profile_id"] == original_profile_id


def test_complete_replace_remaps_every_profile_and_resource_reference(db, cipher):
    _wall(db, cipher)
    document = read_backup(create_backup(db, cipher, include_credentials=True, passphrase="complete backup secret"), passphrase="complete backup secret")
    old_camera_id = document["cameras"][0]["id"]
    result = import_configuration(db, cipher, document, merge=False)
    db.commit()
    assert result == {"cameras": 1, "layouts": 1, "rotation_groups": 1, "display_profiles": 1, "schedules": 1}
    camera = db.scalar(select(Camera))
    layout = db.scalar(select(Layout))
    group = db.scalar(select(RotationGroup))
    schedule = db.scalar(select(Schedule))
    profile = next(p for p in camera.stream_profiles if p.name == "Sub")
    assert camera.id != old_camera_id
    slot = layout.revisions[0].data["slots"][0]
    assert slot["camera_id"] == camera.id
    assert slot["stream_profile_id"] == profile.id
    assert group.camera_entries[0]["stream_profile_id"] == profile.id
    assert group.camera_entries[0]["camera_id"] == camera.id
    assert schedule.layout_id == layout.id
    assert db.get(DisplayProfile, layout.display_profile_id) is not None
    assert layout.active
    assert CameraService(db, cipher).resolve_stream_url(camera.id)[2].startswith("rtsps://viewer:preserve%20this%20secret@[2001:db8::5]:7441/")


def test_bad_replace_is_rejected_before_any_live_rows_are_deleted(db, cipher):
    camera, _, _, _ = _wall(db, cipher)
    camera_id = camera.id
    document = export_configuration(db, cipher)
    document["cameras"][0]["stream_profiles"][0]["url"] = "file:///etc/passwd"
    with pytest.raises(ValueError, match="RTSP"):
        import_configuration(db, cipher, document, merge=False)
    db.commit()
    assert db.get(Camera, camera_id) is not None
    assert db.scalar(select(func.count()).select_from(Layout)) == 1


def test_late_merge_conflict_rolls_back_import_but_keeps_session_usable(db, cipher):
    camera, profile, _, _ = _wall(db, cipher)
    camera_id, profile_id = camera.id, profile.id
    document = export_configuration(db, cipher)
    document.update(layouts=[], rotation_groups=[], schedules=[])
    document["cameras"][0]["description"] = "must roll back"
    document["cameras"][0]["stream_profiles"] = document["cameras"][0]["stream_profiles"][:1]
    with pytest.raises(ValueError, match="stream profile"):
        import_configuration(db, cipher, document, merge=True)
    db.commit()
    assert db.get(StreamProfile, profile_id) is not None
    assert db.get(Camera, camera_id).description != "must roll back"


def test_import_participates_in_callers_transaction(db, cipher):
    camera, _, _, _ = _wall(db, cipher)
    camera_id = camera.id
    document = export_configuration(db, cipher)
    document["cameras"][0]["description"] = "not committed"
    import_configuration(db, cipher, document, merge=True)
    db.rollback()
    assert db.get(Camera, camera_id).description != "not committed"


def test_merge_preserves_existing_active_wall(db, cipher):
    _, _, _, layout = _wall(db, cipher)
    original_id = layout.id
    document = export_configuration(db, cipher)
    document["layouts"][0].update(id="new-layout", name="Imported active wall")
    document["schedules"] = []
    import_configuration(db, cipher, document, merge=True)
    db.commit()
    active = list(db.scalars(select(Layout).where(Layout.active.is_(True))))
    assert [item.id for item in active] == [original_id]


def test_current_revision_is_preserved_even_when_not_highest(db, cipher):
    _wall(db, cipher)
    document = export_configuration(db, cipher)
    revision = copy.deepcopy(document["layouts"][0]["revisions"][0])
    revision["revision"] = 2
    revision["data"]["slots"][0]["name"] = "Newer draft"
    document["layouts"][0]["revisions"].append(revision)
    import_configuration(db, cipher, document, merge=False)
    db.commit()
    layout = db.scalar(select(Layout))
    assert layout.current_revision == 1
    assert LayoutService(db).current_revision(layout).data["slots"][0]["name"] == "Garden"


@pytest.mark.parametrize("corruption", ["foreign_profile", "missing_camera", "invalid_geometry", "duplicate_id", "two_active"])
def test_import_checks_graph_and_nested_data_before_writing(db, cipher, corruption):
    _wall(db, cipher)
    document = export_configuration(db, cipher)
    if corruption == "foreign_profile":
        document["layouts"][0]["revisions"][0]["data"]["slots"][0]["stream_profile_id"] = "unknown"
    elif corruption == "missing_camera":
        document["rotation_groups"][0]["camera_entries"][0]["camera_id"] = "unknown"
    elif corruption == "invalid_geometry":
        document["layouts"][0]["revisions"][0]["data"]["slots"][0]["width"] = 2
    elif corruption == "duplicate_id":
        camera = copy.deepcopy(document["cameras"][0])
        camera["name"] = "Same ID"
        document["cameras"].append(camera)
    else:
        layout = copy.deepcopy(document["layouts"][0])
        layout.update(id="another", name="Second active")
        document["layouts"].append(layout)
    with pytest.raises(ValueError):
        import_configuration(db, cipher, document, merge=False)
    assert db.scalar(select(func.count()).select_from(Camera)) == 1


def test_backup_read_bounds_uncompressed_document(monkeypatch):
    monkeypatch.setattr(backup, "MAX_EXPORT_BYTES", 1024)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mosaivue-export.json", json.dumps({"padding": "x" * 4096}))
    assert len(stream.getvalue()) < 1024
    with pytest.raises(ValueError, match="Expanded configuration"):
        read_backup(stream.getvalue())


def test_damaged_or_wrong_passphrase_backup_has_useful_error(db, cipher):
    _wall(db, cipher)
    data = create_backup(db, cipher, include_credentials=True, passphrase="complete backup secret")
    with pytest.raises(ValueError, match="Incorrect passphrase"):
        read_backup(data, passphrase="wrong password")
    with pytest.raises(ValueError, match="truncated"):
        read_backup(backup.ENCRYPTED_HEADER + b"short", passphrase="anything")
    with pytest.raises(ValueError, match="readable configuration"):
        read_backup(b"not an archive")


def test_profile_edit_keeps_id_and_refuses_referenced_removal(db, cipher):
    camera, profile, _, layout = _wall(db, cipher)
    original_ids = {p.name: p.id for p in camera.stream_profiles}
    service = CameraService(db, cipher)
    service.update(camera.id, CameraUpdate(stream_profiles=[
        StreamProfileIn(name="Main", url="rtsp://192.0.2.10/main"),
        StreamProfileIn(name="Sub", url="rtsp://192.0.2.10/sub"),
    ]))
    assert {p.name: p.id for p in camera.stream_profiles} == original_ids
    with pytest.raises(ValueError, match="still used"):
        service.update(camera.id, CameraUpdate(stream_profiles=[StreamProfileIn(name="Main", url="rtsp://192.0.2.10/main")]))
    with pytest.raises(ValueError, match="still used"):
        service.delete(camera.id)
    assert LayoutService(db).current_revision(layout).data["slots"][0]["stream_profile_id"] == profile.id


def test_profile_id_cannot_be_taken_from_another_camera(db, cipher):
    camera, profile, _, _ = _wall(db, cipher)
    other = CameraService(db, cipher).create(CameraCreate(name="Other", stream_profiles=[StreamProfileIn(url="rtsp://192.0.2.90/live")]))
    with pytest.raises(ValueError, match="does not belong"):
        CameraService(db, cipher).update(other.id, CameraUpdate(stream_profiles=[StreamProfileIn(id=profile.id, url="rtsp://192.0.2.90/live")]))
    assert db.get(StreamProfile, profile.id).camera_id == camera.id


def test_clear_credentials_wins_over_embedded_url_credentials(db, cipher):
    camera = CameraService(db, cipher).create(CameraCreate(name="Clear", username="old", password="old-secret", stream_profiles=[StreamProfileIn(url="rtsp://192.0.2.70/live")]))
    CameraService(db, cipher).update(camera.id, CameraUpdate(clear_credentials=True, stream_profiles=[StreamProfileIn(id=camera.stream_profiles[0].id, url="rtsp://old:old-secret@192.0.2.70/live")]))
    assert camera.credential is None
    assert camera.stream_profiles[0].url == "rtsp://192.0.2.70/live"


def test_blank_username_edit_does_not_create_a_password(db, cipher):
    service = CameraService(db, cipher)
    camera = service.create(CameraCreate(
        name="No credentials",
        stream_profiles=[StreamProfileIn(url="rtsp://192.0.2.71/live")],
    ))
    assert camera.credential is None

    service.update(camera.id, CameraUpdate(username=None))
    assert camera.credential is None
    assert service.output(camera).has_password is False

    service.update(camera.id, CameraUpdate(username="viewer"))
    assert camera.credential is not None
    assert service.output(camera).has_password is False
