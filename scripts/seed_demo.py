#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from mosaivue.db import get_session_factory, init_db
from mosaivue.models import Layout
from mosaivue.schemas import CameraCreate, LayoutCreate, LayoutData, RotationEntry, RotationGroupIn, Slot, StreamProfileIn
from mosaivue.security import CredentialCipher, KeyManager
from mosaivue.services.cameras import CameraService
from mosaivue.services.layouts import LayoutService
from mosaivue.services.rotations import RotationService


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed non-secret Mosaivue demo data")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    init_db()
    cipher = CredentialCipher(KeyManager().load_or_create())
    with get_session_factory()() as db:
        if db.query(Layout).count() and not args.reset:
            print("Demo seed skipped: layouts already exist")
            return
        names = ["Driveway", "Front Door", "Garage", "Back Yard", "Side Yard", "Workshop"]
        cameras = []
        camera_service = CameraService(db, cipher)
        for index, name in enumerate(names, start=1):
            existing = next((c for c in camera_service.list() if c.name == name), None)
            camera = existing or camera_service.create(
                CameraCreate(
                    name=name,
                    location="Outside" if name != "Workshop" else "Outbuilding",
                    vendor="Demo",
                    tags=["outside", name.lower().replace(" ", "-")],
                    stream_profiles=[
                        StreamProfileIn(
                            name="Low",
                            url=f"rtsp://127.0.0.1:8554/demo{index}",
                            width=640,
                            height=360,
                            fps=15,
                            priority=0,
                        )
                    ],
                )
            )
            cameras.append(camera)
        rotation = RotationService(db).create(
            RotationGroupIn(
                name="Perimeter rotation",
                interval_seconds=15,
                camera_entries=[RotationEntry(camera_id=item.id) for item in cameras[3:]],
            )
        )
        data = LayoutData(
            slots=[
                Slot(id="driveway", name="Driveway", type="fixed", camera_id=cameras[0].id, x=0, y=0, width=.65, height=1, label="Driveway"),
                Slot(id="front", name="Front Door", type="fixed", camera_id=cameras[1].id, x=.65, y=0, width=.35, height=.34, label="Front Door"),
                Slot(id="garage", name="Garage", type="fixed", camera_id=cameras[2].id, x=.65, y=.34, width=.35, height=.33, label="Garage"),
                Slot(id="perimeter", name="Perimeter", type="rotation", rotation_group_id=rotation.id, x=.65, y=.67, width=.35, height=.33, label="Perimeter"),
            ]
        )
        layout = LayoutService(db).create(LayoutCreate(name="Main", description="Demo camera wall", data=data))
        layout.active = True
        db.commit()
        print(f"Seeded {len(cameras)} cameras, rotation {rotation.id}, layout {layout.id}")


if __name__ == "__main__":
    main()
