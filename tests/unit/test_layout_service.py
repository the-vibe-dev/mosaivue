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
