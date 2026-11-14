from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mosaivue.db import get_session_factory
from mosaivue.models import DisplayProfile, Layout, LayoutRevision
from mosaivue.schemas import LayoutCreate, LayoutData, LayoutRevisionGuard, LayoutUpdate, Slot
from mosaivue.services.backup import export_configuration, import_configuration
from mosaivue.services.layouts import LayoutRevisionConflict, LayoutService, LayoutValidationError


def _saved_wall(db):
    service = LayoutService(db)
    wall = service.create(LayoutCreate(name="Wall", data=LayoutData(output_width=1920)))
    revision_id = service.current_revision(wall).id
    db.commit()
    return wall.id, revision_id


@pytest.mark.parametrize("revision", [0, -1, True, 1.5, "1", 2**63])
def test_revision_precondition_rejects_ambiguous_or_unsupported_values(revision):
    with pytest.raises(ValidationError):
        LayoutRevisionGuard(expected_revision=revision)


def test_stale_save_does_not_mutate_metadata_or_insert_history(db):
    layout_id, original_id = _saved_wall(db)
    service = LayoutService(db)
    latest = service.update(layout_id, LayoutUpdate(
        description="Newer description", data=LayoutData(output_width=1280),
        expected_revision=1, expected_revision_id=original_id,
    ))
    db.commit()
    latest_id = service.current_revision(latest).id

    with pytest.raises(LayoutRevisionConflict) as conflict:
        service.update(layout_id, LayoutUpdate(
            name="Stale name", description="Stale description", data=LayoutData(output_width=640),
            expected_revision=1, expected_revision_id=original_id,
        ))
    db.commit()  # Even if a caller commits after handling the conflict, no edit leaked.
    assert conflict.value.detail() == {
        "code": "layout_revision_conflict",
        "message": str(conflict.value),
        "expected_revision": 1,
        "current_revision": 2,
        "expected_revision_id": original_id,
        "current_revision_id": latest_id,
    }
    db.refresh(latest)
    assert latest.name == "Wall"
    assert latest.description == "Newer description"
    assert latest.current_revision == 2
    assert service.current_revision(latest).data["output_width"] == 1280
    assert len(service.revisions(layout_id)) == 2


@pytest.mark.parametrize("kind", ["name", "description", "display_profile_id"])
def test_metadata_only_save_consumes_token_and_clones_geometry(db, kind):
    layout_id, revision_id = _saved_wall(db)
    profile = DisplayProfile(name="Small display", width=1280, height=720)
    db.add(profile)
    db.commit()
    value = profile.id if kind == "display_profile_id" else "New metadata"
    service = LayoutService(db)
    wall = service.update(layout_id, LayoutUpdate(
        **{kind: value}, expected_revision=1, expected_revision_id=revision_id,
    ))
    db.commit()
    assert wall.current_revision == 2
    assert getattr(wall, kind) == value
    assert service.current_revision(wall).data["output_width"] == 1920
    assert service.current_revision(wall).id != revision_id
    with pytest.raises(LayoutRevisionConflict):
        service.update(layout_id, LayoutUpdate(description="Stale", expected_revision=1))


def test_revision_id_rejects_same_number_replaced_by_merge_import(db, cipher):
    layout_id, revision_id = _saved_wall(db)
    document = export_configuration(db, cipher)
    document["layouts"][0]["revisions"][0]["data"]["output_width"] = 1280
    import_configuration(db, cipher, document, merge=True)
    db.commit()
    service = LayoutService(db)
    wall = service.get(layout_id)
    current_id = service.current_revision(wall).id
    assert wall.current_revision == 1
    assert current_id != revision_id
    with pytest.raises(LayoutRevisionConflict) as conflict:
        service.update(layout_id, LayoutUpdate(
            description="Stale import editor", expected_revision=1, expected_revision_id=revision_id,
        ))
    db.commit()
    assert conflict.value.current_revision_id == current_id
    assert len(service.revisions(layout_id)) == 1
    assert service.current_revision(wall).data["output_width"] == 1280
    assert wall.description == ""


def test_id_only_precondition_and_noop_guards_remain_supported(db):
    layout_id, revision_id = _saved_wall(db)
    service = LayoutService(db)
    unchanged = service.update(layout_id, LayoutUpdate(expected_revision_id=revision_id))
    assert unchanged.current_revision == 1
    updated = service.update(layout_id, LayoutUpdate(description="Changed", expected_revision_id=revision_id))
    db.commit()
    assert updated.current_revision == 2
    with pytest.raises(LayoutRevisionConflict):
        service.update(layout_id, LayoutUpdate(expected_revision_id=revision_id))
    assert len(service.revisions(layout_id)) == 2


@pytest.mark.parametrize("invalid", ["display", "camera"])
def test_invalid_save_does_not_leak_partial_metadata_or_history(db, invalid):
    layout_id, revision_id = _saved_wall(db)
    service = LayoutService(db)
    changes = {"display_profile_id": "missing"} if invalid == "display" else {
        "data": LayoutData(slots=[Slot(
            id="missing", name="Missing camera", camera_id="missing", x=0, y=0, width=1, height=1,
        )]),
    }
    with pytest.raises(LayoutValidationError):
        service.update(layout_id, LayoutUpdate(
            name="Must not leak", description="Must not leak",
            expected_revision=1, expected_revision_id=revision_id, **changes,
        ))
    db.commit()
    wall = service.get(layout_id)
    assert wall.name == "Wall"
    assert wall.description == ""
    assert wall.current_revision == 1
    assert len(service.revisions(layout_id)) == 1


def test_name_conflict_rollback_keeps_token_available_for_retry(db):
    layout_id, revision_id = _saved_wall(db)
    service = LayoutService(db)
    service.create(LayoutCreate(name="Taken"))
    db.commit()
    with pytest.raises(IntegrityError):
        service.update(layout_id, LayoutUpdate(name="Taken", expected_revision=1))
    db.rollback()
    assert service.get(layout_id).current_revision == 1
    assert service.current_revision(service.get(layout_id)).id == revision_id
    updated = service.update(layout_id, LayoutUpdate(name="Available", expected_revision=1))
    db.commit()
    assert updated.current_revision == 2
    assert len(service.revisions(layout_id)) == 2


@pytest.mark.parametrize("guarded", [True, False])
def test_simultaneous_writers_serialize_token_check_and_history_allocation(db, guarded):
    layout_id, revision_id = _saved_wall(db)
    ready = Barrier(2)
    factory = get_session_factory()

    def save(index):
        with factory() as writer:
            service = LayoutService(writer)
            loaded = service.get(layout_id)
            assert loaded.current_revision == 1
            ready.wait(timeout=5)
            try:
                wall = service.update(layout_id, LayoutUpdate(
                    description=f"Writer {index}", data=LayoutData(output_width=640 * index),
                    expected_revision=1 if guarded else None,
                    expected_revision_id=revision_id if guarded else None,
                ))
                revision = wall.current_revision
                writer.commit()
                return "saved", revision, index
            except LayoutRevisionConflict as exc:
                writer.rollback()
                return "conflict", exc.current_revision, index

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, (1, 2)))
    db.expire_all()
    service = LayoutService(db)
    saved = sorted((number, index) for status, number, index in results if status == "saved")
    assert [number for number, _ in saved] == ([2] if guarded else [2, 3])
    assert sum(status == "conflict" for status, _, _ in results) == (1 if guarded else 0)
    latest_number, latest_writer = saved[-1]
    wall = service.get(layout_id)
    assert wall.current_revision == latest_number
    assert wall.description == f"Writer {latest_writer}"
    assert service.current_revision(wall).data["output_width"] == 640 * latest_writer
    assert db.scalar(select(func.count()).select_from(LayoutRevision)) == latest_number


def test_legacy_metadata_save_uses_latest_geometry_despite_cached_layout(db):
    layout_id, _ = _saved_wall(db)
    service = LayoutService(db)
    cached = service.get(layout_id)
    with get_session_factory()() as other:
        LayoutService(other).update(layout_id, LayoutUpdate(data=LayoutData(output_width=1280)))
        other.commit()
    assert cached.current_revision == 1
    updated = service.update(layout_id, LayoutUpdate(description="Keep newer geometry"))
    db.commit()
    assert updated.current_revision == 3
    assert service.current_revision(updated).data["output_width"] == 1280


def test_guarded_history_restore_keeps_metadata_and_adds_one_revision(db):
    layout_id, original_id = _saved_wall(db)
    service = LayoutService(db)
    wall = service.update(layout_id, LayoutUpdate(
        name="Latest name", description="Latest description", data=LayoutData(output_width=1280),
    ))
    db.commit()
    with pytest.raises(LayoutRevisionConflict):
        service.restore_revision(layout_id, 1, expected_revision=1, expected_revision_id=original_id)
    db.rollback()
    restored = service.restore_revision(
        layout_id, 1, expected_revision=2, expected_revision_id=service.current_revision(wall).id,
    )
    db.commit()
    assert restored.current_revision == 3
    assert restored.name == "Latest name"
    assert restored.description == "Latest description"
    assert service.current_revision(restored).data["output_width"] == 1920
    assert len(service.revisions(layout_id)) == 3


def test_activate_pinned_revision_retains_newer_edit_as_current(db):
    layout_id, original_id = _saved_wall(db)
    service = LayoutService(db)
    service.update(layout_id, LayoutUpdate(data=LayoutData(output_width=1280)))
    db.commit()
    activated = service.activate(layout_id, revision_number=1, revision_id=original_id)
    db.commit()
    assert activated.active
    assert activated.current_revision == 2
    assert [(r.revision, r.status) for r in service.revisions(layout_id)] == [(2, "draft"), (1, "active")]


def test_activate_wrong_history_identity_does_not_change_active_wall(db):
    layout_id, _ = _saved_wall(db)
    service = LayoutService(db)
    active = service.create(LayoutCreate(name="Existing active wall"))
    service.activate(active.id)
    db.commit()
    with pytest.raises(LayoutRevisionConflict):
        service.activate(layout_id, revision_number=1, revision_id="old-history-id")
    db.commit()
    assert db.get(Layout, active.id).active
    assert not db.get(Layout, layout_id).active
