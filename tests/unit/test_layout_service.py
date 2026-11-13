from __future__ import annotations

from sqlalchemy.orm import Session

from mosaivue.models import Camera
from mosaivue.schemas import LayoutCreate, LayoutData, LayoutUpdate, Slot
from mosaivue.services.layouts import LayoutService


def test_layout_revisions_preserve_last_known_data(db: Session) -> None:
    camera = Camera(name="A", enabled=True)
    db.add(camera)
    db.flush()
    service = LayoutService(db)
    layout = service.create(
        LayoutCreate(
            name="Main",
            data=LayoutData(
                slots=[
                    Slot(
                        id="slot-a",
                        name="A",
                        type="fixed",
                        camera_id=camera.id,
                        x=0,
                        y=0,
                        width=1,
                        height=1,
                    )
                ]
            ),
        )
    )
    assert layout.current_revision == 1
    updated = service.update(
        layout.id,
        LayoutUpdate(
            data=LayoutData(
                slots=[
                    Slot(
                        id="slot-a",
                        name="A",
                        type="fixed",
                        camera_id=camera.id,
                        x=0,
                        y=0,
                        width=.75,
                        height=1,
                    )
                ]
            )
        ),
    )
    assert updated.current_revision == 2
    revisions = service.revisions(layout.id)
    assert [item.revision for item in revisions] == [2, 1]
    restored = service.restore_revision(layout.id, 1)
    assert restored.current_revision == 3
    restored_revision = service.current_revision(restored)
    assert restored_revision is not None
    assert restored_revision.data["slots"][0]["width"] == 1.0


def test_validation_reports_missing_camera_and_overlap(db: Session) -> None:
    data = LayoutData(
        slots=[
            Slot(id="a", name="A", type="fixed", camera_id="missing-a", x=0, y=0, width=.7, height=1),
            Slot(id="b", name="B", type="fixed", camera_id="missing-b", x=.5, y=0, width=.5, height=1),
        ]
    )
    errors, warnings = LayoutService(db).validate(data)
    assert any("missing-a" in item for item in errors)
    assert any("overlap" in item.lower() for item in warnings)


def test_manual_slot_validates_selected_camera_profile(db):
    from mosaivue.models import StreamProfile

    first, selected = Camera(name="Default"), Camera(name="Selected")
    db.add_all([first, selected])
    db.flush()
    first_profile = StreamProfile(camera_id=first.id, name="Main", url="rtsp://192.0.2.1/live")
    selected_profile = StreamProfile(camera_id=selected.id, name="Main", url="rtsp://192.0.2.2/live")
    db.add_all([first_profile, selected_profile])
    db.flush()
    data = LayoutData(slots=[Slot(
        id="manual", name="Selected", type="manual", camera_id=first.id,
        selected_camera_id=selected.id, stream_profile_id=selected_profile.id,
        x=0, y=0, width=1, height=1,
    )])
    assert LayoutService(db).validate(data)[0] == []
    data.slots[0].stream_profile_id = first_profile.id
    assert any("does not belong" in error for error in LayoutService(db).validate(data)[0])


def test_missing_display_profile_fails_validation_not_database_insert(db):
    import pytest

    from mosaivue.services.layouts import LayoutValidationError

    with pytest.raises(LayoutValidationError, match="Display profile"):
        LayoutService(db).create(LayoutCreate(name="Missing display", display_profile_id="missing"))
