from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..constants import MAX_LAYOUT_REVISIONS
from ..models import Camera, DisplayProfile, Layout, LayoutRevision, RotationGroup, StreamProfile
from ..schemas import LayoutCreate, LayoutData, LayoutOut, LayoutRevisionOut, LayoutUpdate

LOGGER = logging.getLogger(__name__)


class LayoutValidationError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []


class LayoutRevisionConflict(ValueError):
    def __init__(
        self,
        expected_revision: int | None,
        current_revision: int,
        expected_revision_id: str | None = None,
        current_revision_id: str | None = None,
    ):
        super().__init__(
            "This layout changed after it was loaded. "
            "Reload the latest revision or save your work as a copy."
        )
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        self.expected_revision_id = expected_revision_id
        self.current_revision_id = current_revision_id

    def detail(self) -> dict[str, Any]:
        return {
            "code": "layout_revision_conflict",
            "message": str(self),
            "expected_revision": self.expected_revision,
            "current_revision": self.current_revision,
            "expected_revision_id": self.expected_revision_id,
            "current_revision_id": self.current_revision_id,
        }


class LayoutService:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[Layout]:
        return list(self.db.scalars(select(Layout).order_by(Layout.name)).unique())

    def get(self, layout_id: str) -> Layout:
        layout = self.db.get(Layout, layout_id)
        if layout is None:
            raise KeyError("Layout not found")
        return layout

    def current_revision(self, layout: Layout) -> LayoutRevision | None:
        return self.db.scalar(
            select(LayoutRevision).where(
                LayoutRevision.layout_id == layout.id,
                LayoutRevision.revision == layout.current_revision,
            )
        )

    def create(self, payload: LayoutCreate, user_id: str | None = None) -> Layout:
        self._validate_display_profile(payload.display_profile_id)
        errors, warnings = self.validate(payload.data)
        if errors:
            raise LayoutValidationError(errors, warnings)
        layout = Layout(
            name=payload.name,
            description=payload.description,
            display_profile_id=payload.display_profile_id,
            current_revision=1,
        )
        self.db.add(layout)
        self.db.flush()
        self.db.add(
            LayoutRevision(
                layout_id=layout.id,
                revision=1,
                status="draft",
                data=payload.data.model_dump(mode="json"),
                created_by=user_id,
            )
        )
        self.db.flush()
        LOGGER.info("Layout created: %s", layout.name, extra={"layout_id": layout.id})
        return layout

    def update(self, layout_id: str, payload: LayoutUpdate, user_id: str | None = None) -> Layout:
        layout = self._claim_revision(layout_id, payload.expected_revision, payload.expected_revision_id)
        if "display_profile_id" in payload.model_fields_set:
            self._validate_display_profile(payload.display_profile_id)
        changed = (
            payload.data is not None
            or payload.name is not None
            or payload.description is not None
            or "display_profile_id" in payload.model_fields_set
        )
        if not changed:
            return layout
        data = payload.data
        if data is None:
            current = self.current_revision(layout)
            if current is None:
                raise LayoutValidationError(["Layout has no current revision"])
            data = LayoutData.model_validate(current.data)
        errors, warnings = self.validate(data)
        if errors:
            raise LayoutValidationError(errors, warnings)
        # Even metadata-only saves consume a revision, otherwise a stale editor
        # could miss a renamed/reassigned wall and overwrite its newer metadata.
        # The claim holds the writer lock until the caller commits or rolls back.
        newest_revision = self.db.scalar(
            select(func.max(LayoutRevision.revision)).where(LayoutRevision.layout_id == layout.id)
        ) or 0
        next_revision = newest_revision + 1
        if payload.name is not None:
            layout.name = payload.name
        if payload.description is not None:
            layout.description = payload.description
        if "display_profile_id" in payload.model_fields_set:
            layout.display_profile_id = payload.display_profile_id
        self.db.add(LayoutRevision(
            layout_id=layout.id, revision=next_revision, status=payload.status,
            data=data.model_dump(mode="json"), created_by=user_id,
        ))
        layout.current_revision = next_revision
        self.db.flush()
        self._prune(layout.id)
        return layout

    def _claim_revision(
        self, layout_id: str, expected_revision: int | None, expected_revision_id: str | None = None,
    ) -> Layout:
        # UPDATE is the synchronization point, not a preceding SELECT. On SQLite
        # it reserves the writer before history allocation or metadata changes.
        # A second guarded writer rechecks its predicate after the first commits.
        statement = update(Layout).where(Layout.id == layout_id).values(
            current_revision=Layout.current_revision, updated_at=Layout.updated_at,
        )
        if expected_revision is not None:
            statement = statement.where(Layout.current_revision == expected_revision)
        if expected_revision_id is not None:
            statement = statement.where(select(LayoutRevision.id).where(
                LayoutRevision.layout_id == Layout.id,
                LayoutRevision.revision == Layout.current_revision,
                LayoutRevision.id == expected_revision_id,
            ).exists())
        with self.db.no_autoflush:
            result = self.db.execute(statement.execution_options(synchronize_session=False))
            current = self.db.scalar(select(Layout.current_revision).where(Layout.id == layout_id))
            if current is None:
                raise KeyError("Layout not found")
            if result.rowcount != 1:
                current_id = self.db.scalar(select(LayoutRevision.id).where(
                    LayoutRevision.layout_id == layout_id, LayoutRevision.revision == current,
                ))
                raise LayoutRevisionConflict(expected_revision, current, expected_revision_id, current_id)
            # An earlier request read or service call may have populated the
            # identity map. Reload after the claim so legacy metadata-only saves
            # clone the newest geometry rather than reverting a concurrent edit.
            layout = self.db.get(Layout, layout_id, populate_existing=True)
            if layout is None:
                raise KeyError("Layout not found")
            return layout

    def restore_revision(
        self, layout_id: str, revision_number: int, user_id: str | None = None,
        *, expected_revision: int | None = None, expected_revision_id: str | None = None,
    ) -> Layout:
        self._claim_revision(layout_id, expected_revision, expected_revision_id)
        source = self.db.scalar(
            select(LayoutRevision).where(
                LayoutRevision.layout_id == layout_id,
                LayoutRevision.revision == revision_number,
            )
        )
        if source is None:
            raise KeyError("Layout revision not found")
        data = LayoutData.model_validate(source.data)
        return self.update(
            layout_id,
            LayoutUpdate(
                data=data, status="draft", expected_revision=expected_revision,
                expected_revision_id=expected_revision_id,
            ),
            user_id=user_id,
        )

    def activate(
        self, layout_id: str, *, revision_number: int | None = None, revision_id: str | None = None,
    ) -> Layout:
        # Reserve a writer only after the caller has finished the renderer RPC.
        # Keep the chosen history identity stable while committing active flags;
        # a newer draft is allowed and remains the current editable revision.
        layout = self._claim_revision(layout_id, None)
        revision = self.db.scalar(select(LayoutRevision).where(
            LayoutRevision.layout_id == layout_id,
            LayoutRevision.revision == (revision_number if revision_number is not None else layout.current_revision),
        ))
        if revision is None:
            raise LayoutValidationError(["Layout has no revision"])
        if revision_id is not None and revision.id != revision_id:
            current = self.current_revision(layout)
            raise LayoutRevisionConflict(
                revision_number, layout.current_revision, revision_id, current.id if current else None,
            )
        data = LayoutData.model_validate(revision.data)
        errors, warnings = self.validate(data)
        if errors:
            raise LayoutValidationError(errors, warnings)
        self.db.execute(update(Layout).values(active=False))
        layout.active = True
        revision.status = "active"
        self.db.flush()
        self.db.refresh(layout)
        return layout

    def delete(self, layout_id: str) -> None:
        layout = self.get(layout_id)
        if layout.active:
            raise ValueError("The active layout cannot be deleted")
        self.db.delete(layout)

    def revisions(self, layout_id: str) -> list[LayoutRevision]:
        self.get(layout_id)
        return list(
            self.db.scalars(
                select(LayoutRevision)
                .where(LayoutRevision.layout_id == layout_id)
                .order_by(LayoutRevision.revision.desc())
            )
        )

    def output(self, layout: Layout) -> LayoutOut:
        revision = self.current_revision(layout)
        return LayoutOut(
            id=layout.id,
            name=layout.name,
            description=layout.description,
            current_revision=layout.current_revision,
            active=layout.active,
            display_profile_id=layout.display_profile_id,
            created_at=layout.created_at,
            updated_at=layout.updated_at,
            revision=LayoutRevisionOut.model_validate(revision) if revision else None,
        )

    def validate(self, data: LayoutData) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        camera_ids = set(self.db.scalars(select(Camera.id)))
        rotation_ids = set(self.db.scalars(select(RotationGroup.id)))
        profile_owners = dict(self.db.execute(select(StreamProfile.id, StreamProfile.camera_id)).all())
        disabled_ids = set(self.db.scalars(select(Camera.id).where(Camera.enabled.is_(False))))
        for slot in data.slots:
            if slot.type.value in {"fixed", "manual"}:
                camera_id = (slot.selected_camera_id or slot.camera_id) if slot.type.value == "manual" else slot.camera_id
                if camera_id not in camera_ids:
                    errors.append(f"Slot {slot.name} references missing camera {camera_id}")
                elif camera_id in disabled_ids:
                    warnings.append(f"Slot {slot.name} uses a disabled camera")
                if slot.stream_profile_id is not None and profile_owners.get(slot.stream_profile_id) != camera_id:
                    errors.append(f"Slot {slot.name} references a stream profile that does not belong to its camera")
            if slot.type.value == "rotation" and slot.rotation_group_id not in rotation_ids:
                errors.append(f"Slot {slot.name} references missing rotation group {slot.rotation_group_id}")
        for index, first in enumerate(data.slots):
            for second in data.slots[index + 1 :]:
                if first.z_index != second.z_index:
                    continue
                if _overlaps(first.model_dump(), second.model_dump()):
                    warnings.append(f"Slots {first.name} and {second.name} overlap at the same z-index")
        return errors, warnings

    def _validate_display_profile(self, profile_id: str | None) -> None:
        if profile_id is not None and self.db.get(DisplayProfile, profile_id) is None:
            raise LayoutValidationError(["Display profile not found"])

    def _prune(self, layout_id: str) -> None:
        revisions = list(
            self.db.scalars(
                select(LayoutRevision.id)
                .where(LayoutRevision.layout_id == layout_id)
                .order_by(LayoutRevision.revision.desc())
            )
        )
        stale = revisions[MAX_LAYOUT_REVISIONS:]
        if stale:
            self.db.execute(delete(LayoutRevision).where(LayoutRevision.id.in_(stale)))


def _overlaps(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return not (
        first["x"] + first["width"] <= second["x"]
        or second["x"] + second["width"] <= first["x"]
        or first["y"] + first["height"] <= second["y"]
        or second["y"] + second["height"] <= first["y"]
    )
