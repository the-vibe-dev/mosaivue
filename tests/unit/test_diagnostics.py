from __future__ import annotations

import os
from types import SimpleNamespace

from mosaivue import constants
from mosaivue.services import diagnostics


def test_security_audit_accepts_service_group_key_and_rejects_public_files(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "etc"
    data_dir = tmp_path / "data"
    config_dir.mkdir(mode=0o770)
    data_dir.mkdir()
    key = config_dir / "master.key"
    key.write_bytes(b"x" * 32)
    key.chmod(0o640)
    database = data_dir / "mosaivue.db"
    database.write_bytes(b"database")
    database.chmod(0o600)
    monkeypatch.setattr(constants, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(constants, "MASTER_KEY_PATH", key)
    monkeypatch.setattr(diagnostics, "DB_PATH", database)
    monkeypatch.setattr(diagnostics.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getegid()))
    monkeypatch.setattr(diagnostics.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.geteuid()))

    checks = {item["name"]: item for item in diagnostics.security_audit()["checks"]}
    assert checks["master_key_permissions"]["passed"]
    assert checks["database_permissions"]["passed"]

    key.chmod(0o644)
    database.chmod(0o644)
    checks = {item["name"]: item for item in diagnostics.security_audit()["checks"]}
    assert not checks["master_key_permissions"]["passed"]
    assert not checks["database_permissions"]["passed"]
