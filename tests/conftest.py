from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

# Constants are intentionally environment-derived at import time. Set an isolated
# root before importing any Mosaivue module.
TEST_ROOT = Path(tempfile.gettempdir()) / f"mosaivue-tests-{os.getpid()}"
shutil.rmtree(TEST_ROOT, ignore_errors=True)
for name in ("data", "etc", "cache", "log", "run"):
    (TEST_ROOT / name).mkdir(parents=True, exist_ok=True)
os.environ.update(
    {
        "MOSAIVUE_DATA_DIR": str(TEST_ROOT / "data"),
        "MOSAIVUE_CONFIG_DIR": str(TEST_ROOT / "etc"),
        "MOSAIVUE_CACHE_DIR": str(TEST_ROOT / "cache"),
        "MOSAIVUE_LOG_DIR": str(TEST_ROOT / "log"),
        "MOSAIVUE_RUN_DIR": str(TEST_ROOT / "run"),
        "MOSAIVUE_DB_PATH": str(TEST_ROOT / "data" / "mosaivue.db"),
        "MOSAIVUE_MASTER_KEY_PATH": str(TEST_ROOT / "etc" / "master.key"),
        "MOSAIVUE_SETUP_TOKEN_PATH": str(TEST_ROOT / "etc" / "setup-token"),
        "MOSAIVUE_CAPABILITIES_PATH": str(TEST_ROOT / "data" / "capabilities.json"),
        "MOSAIVUE_RENDERER_SOCKET": str(TEST_ROOT / "run" / "renderer.sock"),
        "MOSAIVUE_TESTING": "1",
        "MOSAIVUE_BIND": "127.0.0.1",
    }
)

import pytest
from sqlalchemy.orm import Session

from mosaivue.db import Base, configure_database, get_session_factory
from mosaivue.security import CredentialCipher, KeyManager


@pytest.fixture()
def db(tmp_path: Path) -> Session:
    engine = configure_database(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def cipher(tmp_path: Path) -> CredentialCipher:
    return CredentialCipher(KeyManager(tmp_path / "master.key").load_or_create())
