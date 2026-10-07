from __future__ import annotations

import grp
import io
import json
import os
import pwd
import stat
import subprocess
import zipfile
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_settings
from ..constants import CAPABILITIES_PATH, DB_PATH
from ..logging_utils import redact
from ..models import Camera, Layout, RotationGroup
from .capabilities import detect_capabilities


def security_audit() -> dict[str, Any]:
    settings = load_settings()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str, severity: str = "warning") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail, "severity": severity})

    from ..constants import CONFIG_DIR, MASTER_KEY_PATH

    try:
        service_gid = grp.getgrnam("mosaivue").gr_gid
        service_uid = pwd.getpwnam("mosaivue").pw_uid
    except KeyError:
        service_gid = os.getegid()
        service_uid = os.geteuid()
    add("master_key_exists", MASTER_KEY_PATH.is_file(), f"Credential key at {MASTER_KEY_PATH}", "critical")
    if MASTER_KEY_PATH.exists():
        key = MASTER_KEY_PATH.lstat()
        mode = stat.S_IMODE(key.st_mode)
        owner_ok = key.st_uid in {0, service_uid}
        group_read_ok = not (mode & 0o070) or (key.st_gid == service_gid and mode & 0o070 == 0o040)
        permissions_ok = stat.S_ISREG(key.st_mode) and owner_ok and group_read_ok and mode & 0o007 == 0
        add(
            "master_key_permissions", permissions_ok,
            f"{oct(mode)}; owner uid {key.st_uid}, group gid {key.st_gid}. Expected 0600 or root:mosaivue 0640; no other access.",
            "critical",
        )
    add(
        "web_bind_explicit",
        settings.bind in {"127.0.0.1", "localhost", "::1"} or bool(settings.bind),
        f"Listening on {settings.bind}; 0.0.0.0 exposes the web UI on all IPv4 interfaces.",
    )
    add(
        "lan_http_warning",
        settings.bind in {"127.0.0.1", "localhost", "::1"},
        "LAN HTTP is acceptable on a trusted network. Use a TLS reverse proxy for access beyond it.",
    )
    config_mode_ok = True
    if CONFIG_DIR.exists():
        config_mode_ok = (CONFIG_DIR.stat().st_mode & 0o007) == 0
    add("config_directory_permissions", config_mode_ok, f"{CONFIG_DIR}; no access for other users")
    add("database_exists", DB_PATH.is_file(), f"Configuration database at {DB_PATH}")
    if DB_PATH.exists():
        database = DB_PATH.lstat()
        mode = stat.S_IMODE(database.st_mode)
        add(
            "database_permissions",
            stat.S_ISREG(database.st_mode) and database.st_uid in {service_uid, os.geteuid()} and mode & 0o007 == 0,
            f"{oct(mode)}; owner uid {database.st_uid}. The service user must own the database and other users must have no access.",
            "critical",
        )
    return {
        "passed": all(item["passed"] or item["severity"] != "critical" for item in checks),
        "checks": checks,
    }


def sanitized_configuration(db: Session) -> dict[str, Any]:
    cameras = []
    for camera in db.scalars(select(Camera).order_by(Camera.name)).unique():
        cameras.append(
            {
                "id": camera.id,
                "name": camera.name,
                "enabled": camera.enabled,
                "vendor": camera.vendor,
                "model": camera.model,
                "host": camera.host,
                "tags": camera.tags,
                "location": camera.location,
                "has_credentials": camera.credential is not None,
                "stream_profiles": [
                    {
                        "id": profile.id,
                        "name": profile.name,
                        "url": redact(profile.url),
                        "transport": profile.transport,
                        "codec": profile.codec,
                        "width": profile.width,
                        "height": profile.height,
                    }
                    for profile in camera.stream_profiles
                ],
            }
        )
    return {
        "settings": redact(load_settings().to_mapping()),
        "cameras": cameras,
        "layouts": [
            {"id": item.id, "name": item.name, "active": item.active, "revision": item.current_revision}
            for item in db.scalars(select(Layout).order_by(Layout.name))
        ],
        "rotation_groups": [
            {
                "id": item.id,
                "name": item.name,
                "camera_count": len(item.camera_entries),
                "interval_seconds": item.interval_seconds,
                "enabled": item.enabled,
            }
            for item in db.scalars(select(RotationGroup).order_by(RotationGroup.name))
        ],
    }


def recent_journal(lines: int = 500) -> str:
    try:
        completed = subprocess.run(
            ["journalctl", "-u", "mosaivue*", "--no-pager", "-n", str(lines), "-o", "short-iso"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return str(redact(completed.stdout[-250_000:]))
    except (OSError, subprocess.TimeoutExpired):
        return "journald unavailable\n"


def build_support_bundle(db: Session) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "type": "mosaivue-support-bundle",
                    "sanitized": True,
                },
                indent=2,
            ),
        )
        archive.writestr("capabilities.json", json.dumps(detect_capabilities(), indent=2))
        archive.writestr("configuration-sanitized.json", json.dumps(sanitized_configuration(db), indent=2))
        archive.writestr("security-audit.json", json.dumps(security_audit(), indent=2))
        archive.writestr("journal.log", recent_journal())
        if CAPABILITIES_PATH.exists():
            archive.writestr("capabilities-install-time.json", CAPABILITIES_PATH.read_text(encoding="utf-8"))
    return stream.getvalue()
