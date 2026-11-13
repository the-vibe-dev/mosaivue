from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Camera, Layout, LayoutRevision, RotationGroup, StreamProfile
from ..schemas import RotationGroupIn


class RotationService:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[RotationGroup]:
        return list(self.db.scalars(select(RotationGroup).order_by(RotationGroup.name)))

    def get(self, group_id: str) -> RotationGroup:
        group = self.db.get(RotationGroup, group_id)
        if group is None:
            raise KeyError("Rotation group not found")
        return group

    def create(self, payload: RotationGroupIn) -> RotationGroup:
        self._validate_cameras(payload)
        group = RotationGroup(**payload.model_dump(mode="json"))
        self.db.add(group)
        self.db.flush()
        return group

    def update(self, group_id: str, payload: RotationGroupIn) -> RotationGroup:
        self._validate_cameras(payload)
        group = self.get(group_id)
        for key, value in payload.model_dump(mode="json").items():
            setattr(group, key, value)
        self.db.flush()
        return group

    def delete(self, group_id: str) -> None:
        group = self.get(group_id)
        revisions = self.db.execute(
            select(Layout.name, LayoutRevision.data).join(
                LayoutRevision,
                (LayoutRevision.layout_id == Layout.id)
                & (LayoutRevision.revision == Layout.current_revision),
            )
        )
        used_by = [
            name for name, data in revisions
            if any(slot.get("rotation_group_id") == group_id for slot in data.get("slots", []))
        ]
        if used_by:
            raise ValueError(f"Rotation group is used by layouts: {', '.join(used_by)}")
        self.db.delete(group)

    def _validate_cameras(self, payload: RotationGroupIn) -> None:
        available = set(self.db.scalars(select(Camera.id)))
        missing = [entry.camera_id for entry in payload.camera_entries if entry.camera_id not in available]
        if missing:
            raise ValueError(f"Rotation group references missing cameras: {', '.join(missing)}")
        for entry in payload.camera_entries:
            if entry.stream_profile_id:
                profile = self.db.get(StreamProfile, entry.stream_profile_id)
                if profile is None or profile.camera_id != entry.camera_id:
                    raise ValueError("Rotation stream profile must belong to the selected camera")
