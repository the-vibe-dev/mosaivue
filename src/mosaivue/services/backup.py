from __future__ import annotations

import io
import json
import secrets
import zipfile
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidTag
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
    uuid4,
)
from ..security import CredentialCipher
from .backup_validation import BackupValidationError, normalized_export

FORMAT_VERSION = 1
ENCRYPTED_HEADER = b"CWBACKUP1\n"
MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_EXPORT_BYTES = 32 * 1024 * 1024


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
    if include_credentials and (not passphrase or len(passphrase) < 12):
        raise ValueError("A passphrase of at least 12 characters is required to include credentials")
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
    if len(payload) > MAX_BACKUP_BYTES:
        raise BackupValidationError("Backup exceeds the 100 MiB limit")
    if payload.startswith(ENCRYPTED_HEADER):
        if not passphrase:
            raise BackupValidationError("This backup is encrypted; provide its passphrase")
        if len(payload) < len(ENCRYPTED_HEADER) + 16 + 12 + 16:
            raise BackupValidationError("Encrypted backup is truncated")
        offset = len(ENCRYPTED_HEADER)
        salt = payload[offset : offset + 16]
        nonce = payload[offset + 16 : offset + 28]
        encrypted = payload[offset + 28 :]
        key = _derive_backup_key(passphrase, salt)
        try:
            payload = AESGCM(key).decrypt(nonce, encrypted, ENCRYPTED_HEADER)
        except InvalidTag as exc:
            raise BackupValidationError("Incorrect passphrase or damaged encrypted backup") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            entries = archive.infolist()
            matches = [entry for entry in entries if entry.filename == "mosaivue-export.json"]
            if len(entries) > 16 or len(matches) != 1:
                raise BackupValidationError("Backup must contain exactly one configuration document")
            entry = matches[0]
            if entry.file_size > MAX_EXPORT_BYTES:
                raise BackupValidationError("Expanded configuration exceeds the 32 MiB limit")
            with archive.open(entry) as handle:
                data = handle.read(MAX_EXPORT_BYTES + 1)
            if len(data) > MAX_EXPORT_BYTES:
                raise BackupValidationError("Expanded configuration exceeds the 32 MiB limit")
            document = json.loads(data)
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupValidationError("Backup does not contain a readable configuration document") from exc
    return normalized_export(document, FORMAT_VERSION)


def validate_export(document: dict[str, Any]) -> None:
    normalized_export(document, FORMAT_VERSION)


def import_configuration(
    db: Session,
    cipher: CredentialCipher,
    document: dict[str, Any],
    *,
    merge: bool = True,
) -> dict[str, int]:
    document = normalized_export(document, FORMAT_VERSION)
    # SQLite's legacy transaction mode does not begin a transaction for a
    # SAVEPOINT. Start one explicitly so releasing our savepoint cannot commit
    # the caller's surrounding unit of work.
    connection = db.connection()
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")
    with db.begin_nested():
        return _import_validated_configuration(db, cipher, document, merge=merge)


def _import_validated_configuration(
    db: Session, cipher: CredentialCipher, document: dict[str, Any], *, merge: bool
) -> dict[str, int]:
    previous_active = db.scalar(select(Layout).where(Layout.active.is_(True)).order_by(Layout.name)) if merge else None
    active_id = previous_active.id if previous_active else None
    if not merge:
        for model in (
            Schedule, LayoutRevision, Layout, RotationGroup, StreamProfile,
            Camera, Credential, DisplayProfile, Setting,
        ):
            db.execute(delete(model))
        db.flush()
        db.expire_all()

    counts = {"cameras": 0, "layouts": 0, "rotation_groups": 0, "display_profiles": 0, "schedules": 0}
    camera_map: dict[str, str] = {}
    profile_map: dict[str, str] = {}
    display_map: dict[str, str] = {}
    rotation_map: dict[str, str] = {}
    layout_map: dict[str, str] = {}

    for raw in document["display_profiles"]:
        existing = db.scalar(select(DisplayProfile).where(DisplayProfile.name == raw["name"])) if merge else None
        item = existing or DisplayProfile(name=raw["name"])
        for field in ("output_name", "width", "height", "refresh_rate", "rotation", "prevent_blanking"):
            setattr(item, field, raw[field])
        if existing is None:
            db.add(item)
        db.flush()
        display_map[raw["id"]] = item.id
        counts["display_profiles"] += 1

    for raw in document["cameras"]:
        existing = db.scalar(select(Camera).where(Camera.name == raw["name"])) if merge else None
        camera = existing or Camera(name=raw["name"])
        if existing is None:
            db.add(camera)
        for field in ("description", "enabled", "vendor", "model", "host", "tags", "location"):
            setattr(camera, field, raw[field])
        credential_raw = raw["credential"]
        # A sanitized export deliberately omits secrets; merging it must not
        # erase the working local credential. A replacement has no old secret.
        if credential_raw.get("included"):
            credential = camera.credential or Credential(encrypted_secret="")
            credential.username = credential_raw.get("username")
            db.add(credential)
            db.flush()
            credential.encrypted_secret = cipher.encrypt(
                credential_raw.get("password") or "", context=credential.id
            )
            camera.credential = credential
        db.flush()
        by_id = {profile.id: profile for profile in camera.stream_profiles}
        by_name = {profile.name: profile for profile in camera.stream_profiles}
        pairs = [(stream, by_id.get(stream["id"]) or by_name.get(stream["name"])) for stream in raw["stream_profiles"]]
        retained = [profile for _, profile in pairs if profile is not None]
        if len({profile.id for profile in retained}) != len(retained):
            raise BackupValidationError("Imported profile identities conflict with existing profile names")
        for profile in list(camera.stream_profiles):
            if profile not in retained:
                camera.stream_profiles.remove(profile)
            else:
                profile.name = f"__restore_{uuid4()}"
        db.flush()
        for stream, profile in pairs:
            if profile is None:
                profile = StreamProfile()
                camera.stream_profiles.append(profile)
            for field in ("name", "url", "transport", "codec", "width", "height", "fps", "bitrate", "latency_profile", "priority"):
                setattr(profile, field, stream[field])
            db.flush()
            profile_map[stream["id"]] = profile.id
        camera_map[raw["id"]] = camera.id
        counts["cameras"] += 1

    for raw in document["rotation_groups"]:
        existing = db.scalar(select(RotationGroup).where(RotationGroup.name == raw["name"])) if merge else None
        item = existing or RotationGroup(name=raw["name"])
        item.camera_entries = [
            {**entry, "camera_id": camera_map[entry["camera_id"]],
             "stream_profile_id": profile_map.get(entry.get("stream_profile_id"))}
            for entry in raw["camera_entries"]
        ]
        for field in ("interval_seconds", "order_mode", "enabled", "preconnect", "failure_behavior", "rotate_together_group", "start_position"):
            setattr(item, field, raw[field])
        if existing is None:
            db.add(item)
        db.flush()
        rotation_map[raw["id"]] = item.id
        counts["rotation_groups"] += 1

    for raw in document["layouts"]:
        existing = db.scalar(select(Layout).where(Layout.name == raw["name"])) if merge else None
        layout = existing or Layout(name=raw["name"])
        if existing:
            layout.revisions.clear()
            # Delete the old (layout_id, revision) pairs before inserting their
            # replacements. Unit-of-work inserts otherwise precede deletions.
            db.flush()
        layout.description = raw["description"]
        layout.display_profile_id = display_map.get(raw["display_profile_id"])
        if existing is None:
            db.add(layout)
        db.flush()
        for revision_raw in raw["revisions"]:
            layout.revisions.append(LayoutRevision(
                revision=revision_raw["revision"],
                status=revision_raw.get("status", "draft"),
                data=_remap_layout_data(revision_raw["data"], camera_map, rotation_map, profile_map),
            ))
        layout.current_revision = raw["current_revision"]
        if active_id is None and raw.get("active", False):
            active_id = layout.id
        db.flush()
        layout_map[raw["id"]] = layout.id
        counts["layouts"] += 1

    for raw in document["schedules"]:
        existing = db.scalar(select(Schedule).where(Schedule.name == raw["name"])) if merge else None
        item = existing or Schedule(name=raw["name"])
        item.layout_id = layout_map[raw["layout_id"]]
        for field in ("enabled", "days", "start_time", "end_time", "priority"):
            setattr(item, field, raw[field])
        if existing is None:
            db.add(item)
        counts["schedules"] += 1
    for key, value in document["settings"].items():
        setting = db.get(Setting, key) or Setting(key=key, value=value)
        setting.value = value
        db.add(setting)
    db.flush()
    from ..schemas import LayoutData
    from .layouts import LayoutService

    service = LayoutService(db)
    for layout in service.list():
        layout.active = layout.id == active_id
        revision = service.current_revision(layout)
        if revision is None:
            raise BackupValidationError("Merged configuration contains a layout with no current revision")
        errors, _ = service.validate(LayoutData.model_validate(revision.data))
        if errors:
            raise BackupValidationError("Merged configuration leaves a layout with missing camera, stream profile, or rotation references")
        if layout.active:
            revision.status = "active"
    # Validate untouched groups as well: merging a camera must not leave an
    # unrelated rotation pointing to one of its removed profiles.
    owners = dict(db.execute(select(StreamProfile.id, StreamProfile.camera_id)).all())
    for group in db.scalars(select(RotationGroup)):
        for entry in group.camera_entries:
            if entry.get("stream_profile_id") is not None and owners.get(entry["stream_profile_id"]) != entry.get("camera_id"):
                raise BackupValidationError("Merged configuration leaves a rotation group with a missing stream profile")
    db.flush()
    return counts


def _remap_layout_data(
    data: dict[str, Any], camera_map: dict[str, str], rotation_map: dict[str, str],
    profile_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    copied = json.loads(json.dumps(data))
    for slot in copied.get("slots", []):
        for key in ("camera_id", "selected_camera_id"):
            if slot.get(key) in camera_map:
                slot[key] = camera_map[slot[key]]
        if slot.get("rotation_group_id") in rotation_map:
            slot["rotation_group_id"] = rotation_map[slot["rotation_group_id"]]
        if profile_map and slot.get("stream_profile_id") in profile_map:
            slot["stream_profile_id"] = profile_map[slot["stream_profile_id"]]
    return copied
