from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Camera, RotationGroup
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
        self.db.delete(self.get(group_id))

    def _validate_cameras(self, payload: RotationGroupIn) -> None:
        available = set(self.db.scalars(select(Camera.id)))
        missing = [entry.camera_id for entry in payload.camera_entries if entry.camera_id not in available]
        if missing:
            raise ValueError(f"Rotation group references missing cameras: {', '.join(missing)}")
