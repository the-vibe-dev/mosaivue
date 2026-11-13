import pytest

from mosaivue.models import Camera, Layout, LayoutRevision, RotationGroup, StreamProfile
from mosaivue.schemas import RotationGroupIn
from mosaivue.services.rotations import RotationService


def test_rotation_rejects_another_cameras_profile(db):
    camera = Camera(name="One")
    other = Camera(name="Two")
    other.stream_profiles.append(StreamProfile(name="Main", url="rtsp://192.0.2.2/live"))
    db.add_all([camera, other])
    db.flush()
    payload = RotationGroupIn(name="Group", camera_entries=[{
        "camera_id": camera.id, "stream_profile_id": other.stream_profiles[0].id,
    }])
    with pytest.raises(ValueError, match="belong to the selected camera"):
        RotationService(db).create(payload)


def test_rotation_group_in_current_layout_cannot_be_deleted(db):
    group = RotationGroup(name="Group")
    layout = Layout(name="Main", current_revision=1)
    db.add_all([group, layout])
    db.flush()
    db.add(LayoutRevision(layout_id=layout.id, revision=1, data={
        "slots": [{"id": "tile", "rotation_group_id": group.id}],
    }))
    db.flush()
    with pytest.raises(ValueError, match="used by layouts: Main"):
        RotationService(db).delete(group.id)
    assert db.get(RotationGroup, group.id) is group


def test_unused_rotation_group_can_be_deleted(db):
    group = RotationGroup(name="Unused")
    db.add(group)
    db.flush()
    group_id = group.id
    RotationService(db).delete(group_id)
    db.flush()
    assert db.get(RotationGroup, group_id) is None
