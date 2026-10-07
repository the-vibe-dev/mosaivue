from __future__ import annotations

import io
import json
import secrets
import zipfile
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Camera,
    Credential,
    DisplayProfile,
    Layout,
    LayoutRevision,
    RotationGroup,
    Schedule,
    Setting,
    StreamProfile,
)
from ..security import CredentialCipher

FORMAT_VERSION = 1
ENCRYPTED_HEADER = b"CWBACKUP1\n"


def export_configuration(
    db: Session,
    cipher: CredentialCipher,
    *,
    include_credentials: bool = False,
) -> dict[str, Any]:
    cameras: list[dict[str, Any]] = []
    for camera in db.scalars(select(Camera).order_by(Camera.name)).unique():
        item: dict[str, Any] = {
            "id": camera.id,
            "name": camera.name,
            "description": camera.description,
            "enabled": camera.enabled,
            "vendor": camera.vendor,
            "model": camera.model,
            "host": camera.host,
            "tags": camera.tags,
            "location": camera.location,
            "credential": {
                "username": camera.credential.username if include_credentials and camera.credential else None,
                "password": None,
                "included": False,
            },
            "stream_profiles": [
                {
                    "id": profile.id,
                    "name": profile.name,
                    "url": profile.url,
                    "transport": profile.transport,
                    "codec": profile.codec,
                    "width": profile.width,
                    "height": profile.height,
                    "fps": profile.fps,
                    "bitrate": profile.bitrate,
                    "latency_profile": profile.latency_profile,
                    "priority": profile.priority,
                }
                for profile in camera.stream_profiles
            ],
        }
        if include_credentials and camera.credential:
            item["credential"]["password"] = cipher.decrypt(
                camera.credential.encrypted_secret, context=camera.credential.id
            )
            item["credential"]["included"] = True
        cameras.append(item)

    layouts: list[dict[str, Any]] = []
    for layout in db.scalars(select(Layout).order_by(Layout.name)).unique():
        layouts.append(
            {
                "id": layout.id,
                "name": layout.name,
                "description": layout.description,
                "current_revision": layout.current_revision,
                "active": layout.active,
                "display_profile_id": layout.display_profile_id,
                "revisions": [
                    {
                        "id": revision.id,
                        "revision": revision.revision,
                        "status": revision.status,
                        "data": revision.data,
                        "created_at": revision.created_at.isoformat(),
                    }
                    for revision in layout.revisions
                ],
            }
        )

    return {
        "format": "mosaivue-configuration",
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "credentials_included": include_credentials,
        "cameras": cameras,
        "display_profiles": [
            {
                "id": item.id,
                "name": item.name,
                "output_name": item.output_name,
                "width": item.width,
                "height": item.height,
                "refresh_rate": item.refresh_rate,
                "rotation": item.rotation,
                "prevent_blanking": item.prevent_blanking,
            }
            for item in db.scalars(select(DisplayProfile).order_by(DisplayProfile.name))
        ],
        "rotation_groups": [
            {
                "id": item.id,
                "name": item.name,
                "camera_entries": item.camera_entries,
                "interval_seconds": item.interval_seconds,
                "order_mode": item.order_mode,
                "enabled": item.enabled,
                "preconnect": item.preconnect,
                "failure_behavior": item.failure_behavior,
                "rotate_together_group": item.rotate_together_group,
                "start_position": item.start_position,
            }
            for item in db.scalars(select(RotationGroup).order_by(RotationGroup.name))
        ],
        "layouts": layouts,
        "schedules": [
            {
                "id": item.id,
                "name": item.name,
                "enabled": item.enabled,
                "layout_id": item.layout_id,
                "days": item.days,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "priority": item.priority,
            }
            for item in db.scalars(select(Schedule).order_by(Schedule.name))
        ],
        "settings": {item.key: item.value for item in db.scalars(select(Setting))},
    }


def _configuration_zip(document: dict[str, Any]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "mosaivue-backup",
                    "format_version": FORMAT_VERSION,
                    "created_at": document["created_at"],
                    "credentials_included": document["credentials_included"],
                },
                indent=2,
            ),
        )
        archive.writestr("mosaivue-export.json", json.dumps(document, indent=2))
    return output.getvalue()


def _derive_backup_key(passphrase: str, salt: bytes) -> bytes:
    import hashlib

    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024
    )


def create_backup(
    db: Session,
    cipher: CredentialCipher,
    *,
    include_credentials: bool = False,
    passphrase: str | None = None,
) -> bytes:
    if include_credentials and not passphrase:
        raise ValueError("A passphrase is required to include credentials")
    document = export_configuration(db, cipher, include_credentials=include_credentials)
    archive = _configuration_zip(document)
    if not include_credentials:
        return archive
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = _derive_backup_key(passphrase or "", salt)
    encrypted = AESGCM(key).encrypt(nonce, archive, ENCRYPTED_HEADER)
    return ENCRYPTED_HEADER + salt + nonce + encrypted


def read_backup(payload: bytes, *, passphrase: str | None = None) -> dict[str, Any]:
    if payload.startswith(ENCRYPTED_HEADER):
        if not passphrase:
            raise ValueError("This backup is encrypted; provide its passphrase")
        offset = len(ENCRYPTED_HEADER)
        salt = payload[offset : offset + 16]
        nonce = payload[offset + 16 : offset + 28]
        encrypted = payload[offset + 28 :]
        key = _derive_backup_key(passphrase, salt)
        payload = AESGCM(key).decrypt(nonce, encrypted, ENCRYPTED_HEADER)
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        document = json.loads(archive.read("mosaivue-export.json"))
    validate_export(document)
    return document


def validate_export(document: dict[str, Any]) -> None:
    if document.get("format") != "mosaivue-configuration":
        raise ValueError("Not a Mosaivue configuration export")
    if document.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"Unsupported export version: {document.get('format_version')}")
    for key in ("cameras", "layouts", "rotation_groups", "display_profiles", "schedules"):
        if not isinstance(document.get(key, []), list):
            raise ValueError(f"Invalid {key} section")


def import_configuration(
    db: Session,
    cipher: CredentialCipher,
    document: dict[str, Any],
    *,
    merge: bool = True,
) -> dict[str, int]:
    validate_export(document)
    if not merge:
        for model in (
            Schedule,
            LayoutRevision,
            Layout,
            RotationGroup,
            StreamProfile,
            Camera,
            Credential,
            DisplayProfile,
            Setting,
        ):
            db.execute(delete(model))
        db.flush()

    counts = {"cameras": 0, "layouts": 0, "rotation_groups": 0, "display_profiles": 0, "schedules": 0}
    camera_map: dict[str, str] = {}
    display_map: dict[str, str] = {}
    rotation_map: dict[str, str] = {}
    layout_map: dict[str, str] = {}

    for raw in document.get("display_profiles", []):
        existing = db.scalar(select(DisplayProfile).where(DisplayProfile.name == raw["name"])) if merge else None
        item = existing or DisplayProfile(name=raw["name"])
        for field in ("output_name", "width", "height", "refresh_rate", "rotation", "prevent_blanking"):
            setattr(item, field, raw.get(field))
        if existing is None:
            db.add(item)
        db.flush()
        display_map[raw["id"]] = item.id
        counts["display_profiles"] += 1

    for raw in document.get("cameras", []):
        existing = db.scalar(select(Camera).where(Camera.name == raw["name"])) if merge else None
        if existing:
            camera = existing
            camera.stream_profiles.clear()
            if camera.credential:
                db.delete(camera.credential)
                camera.credential = None
        else:
            camera = Camera(name=raw["name"])
            db.add(camera)
        for field in ("description", "enabled", "vendor", "model", "host", "tags", "location"):
            setattr(camera, field, raw.get(field))
        credential_raw = raw.get("credential") or {}
        if credential_raw.get("included"):
            credential = Credential(username=credential_raw.get("username"), encrypted_secret="")
            db.add(credential)
            db.flush()
            credential.encrypted_secret = cipher.encrypt(
                credential_raw.get("password") or "", context=credential.id
            )
            camera.credential = credential
        db.flush()
        for stream in raw.get("stream_profiles", []):
            camera.stream_profiles.append(
                StreamProfile(
                    name=stream["name"],
                    url=stream["url"],
                    transport=stream.get("transport", "tcp"),
                    codec=stream.get("codec"),
                    width=stream.get("width"),
                    height=stream.get("height"),
                    fps=stream.get("fps"),
                    bitrate=stream.get("bitrate"),
                    latency_profile=stream.get("latency_profile", "low"),
                    priority=stream.get("priority", 0),
                )
            )
        db.flush()
        camera_map[raw["id"]] = camera.id
        counts["cameras"] += 1

    for raw in document.get("rotation_groups", []):
        existing = db.scalar(select(RotationGroup).where(RotationGroup.name == raw["name"])) if merge else None
        item = existing or RotationGroup(name=raw["name"])
        entries = []
        for entry in raw.get("camera_entries", []):
            mapped = camera_map.get(entry.get("camera_id"))
            if mapped:
                entries.append({**entry, "camera_id": mapped})
        item.camera_entries = entries
        for field in (
            "interval_seconds",
            "order_mode",
            "enabled",
            "preconnect",
            "failure_behavior",
            "rotate_together_group",
            "start_position",
        ):
            setattr(item, field, raw.get(field))
        if existing is None:
            db.add(item)
        db.flush()
        rotation_map[raw["id"]] = item.id
        counts["rotation_groups"] += 1

    for raw in document.get("layouts", []):
        existing = db.scalar(select(Layout).where(Layout.name == raw["name"])) if merge else None
        layout = existing or Layout(name=raw["name"])
        if existing:
            layout.revisions.clear()
        layout.description = raw.get("description", "")
        layout.active = bool(raw.get("active", False))
        layout.display_profile_id = display_map.get(raw.get("display_profile_id"))
        if existing is None:
            db.add(layout)
        db.flush()
        revisions = raw.get("revisions") or []
        for revision_raw in revisions:
            data = _remap_layout_data(revision_raw["data"], camera_map, rotation_map)
            layout.revisions.append(
                LayoutRevision(
                    revision=int(revision_raw["revision"]),
                    status=revision_raw.get("status", "draft"),
                    data=data,
                )
            )
        layout.current_revision = max((item.revision for item in layout.revisions), default=1)
        db.flush()
        layout_map[raw["id"]] = layout.id
        counts["layouts"] += 1

    for raw in document.get("schedules", []):
        mapped_layout = layout_map.get(raw.get("layout_id"))
        if not mapped_layout:
            continue
        existing = db.scalar(select(Schedule).where(Schedule.name == raw["name"])) if merge else None
        item = existing or Schedule(name=raw["name"], layout_id=mapped_layout)
        item.layout_id = mapped_layout
        for field in ("enabled", "days", "start_time", "end_time", "priority"):
            setattr(item, field, raw.get(field))
        if existing is None:
            db.add(item)
        counts["schedules"] += 1

    for key, value in document.get("settings", {}).items():
        setting = db.get(Setting, key) or Setting(key=key, value=value)
        setting.value = value
        db.merge(setting)
    db.flush()
    return counts


def _remap_layout_data(
    data: dict[str, Any], camera_map: dict[str, str], rotation_map: dict[str, str]
) -> dict[str, Any]:
    copied = json.loads(json.dumps(data))
    for slot in copied.get("slots", []):
        for key in ("camera_id", "selected_camera_id"):
            if slot.get(key) in camera_map:
                slot[key] = camera_map[slot[key]]
        if slot.get("rotation_group_id") in rotation_map:
            slot["rotation_group_id"] = rotation_map[slot["rotation_group_id"]]
    return copied
