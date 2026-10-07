from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..constants import MAX_LAYOUT_REVISIONS
from ..models import Camera, Layout, LayoutRevision, RotationGroup
from ..schemas import LayoutCreate, LayoutData, LayoutOut, LayoutRevisionOut, LayoutUpdate

LOGGER = logging.getLogger(__name__)


class LayoutValidationError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []


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
        layout = self.get(layout_id)
        if payload.name is not None:
            layout.name = payload.name
        if payload.description is not None:
            layout.description = payload.description
        if "display_profile_id" in payload.model_fields_set:
            layout.display_profile_id = payload.display_profile_id
        if payload.data is not None:
            errors, warnings = self.validate(payload.data)
            if errors:
                raise LayoutValidationError(errors, warnings)
            next_revision = layout.current_revision + 1
            revision = LayoutRevision(
                layout_id=layout.id,
                revision=next_revision,
                status=payload.status,
                data=payload.data.model_dump(mode="json"),
                created_by=user_id,
            )
            self.db.add(revision)
            layout.current_revision = next_revision
            self.db.flush()
            self._prune(layout.id)
        self.db.flush()
        return layout

    def restore_revision(self, layout_id: str, revision_number: int, user_id: str | None = None) -> Layout:
        layout = self.get(layout_id)
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
            LayoutUpdate(data=data, status="draft"),
            user_id=user_id,
        )

    def activate(self, layout_id: str) -> Layout:
        layout = self.get(layout_id)
        revision = self.current_revision(layout)
        if revision is None:
            raise LayoutValidationError(["Layout has no revision"])
        data = LayoutData.model_validate(revision.data)
        errors, warnings = self.validate(data)
        if errors:
            raise LayoutValidationError(errors, warnings)
        self.db.execute(update(Layout).values(active=False))
        layout.active = True
        revision.status = "active"
        self.db.flush()
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
        for slot in data.slots:
            if slot.type.value in {"fixed", "manual"}:
                camera_id = slot.camera_id or slot.selected_camera_id
                if camera_id not in camera_ids:
                    errors.append(f"Slot {slot.name} references missing camera {camera_id}")
            if slot.type.value == "rotation" and slot.rotation_group_id not in rotation_ids:
                errors.append(f"Slot {slot.name} references missing rotation group {slot.rotation_group_id}")
        for index, first in enumerate(data.slots):
            for second in data.slots[index + 1 :]:
                if first.z_index != second.z_index:
                    continue
                if _overlaps(first.model_dump(), second.model_dump()):
                    warnings.append(f"Slots {first.name} and {second.name} overlap at the same z-index")
        return errors, warnings

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
