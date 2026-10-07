from __future__ import annotations

from pathlib import Path

import pytest

from mosaivue.security import (
    CredentialCipher,
    KeyManager,
    hash_password,
    inject_url_credentials,
    strip_url_credentials,
    verify_password,
)


def test_credential_cipher_uses_context(tmp_path: Path) -> None:
    cipher = CredentialCipher(KeyManager(tmp_path / "key").load_or_create())
    token = cipher.encrypt("camera-secret", context="credential-1")
    assert "camera-secret" not in token
    assert cipher.decrypt(token, context="credential-1") == "camera-secret"
    with pytest.raises(Exception):
        cipher.decrypt(token, context="credential-2")


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("scrypt$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)


def test_url_credentials_are_removed_and_reinjected() -> None:
    clean, username, password = strip_url_credentials(
        "rtsp://cam%20user:p%40ss@192.0.2.3:8554/live?profile=1"
    )
    assert clean == "rtsp://192.0.2.3:8554/live?profile=1"
    assert username == "cam user"
    assert password == "p@ss"
    rebuilt = inject_url_credentials(clean, username, password)
    assert rebuilt.startswith("rtsp://cam%20user:p%40ss@192.0.2.3:8554/")
