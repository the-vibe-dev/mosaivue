from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

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
    with pytest.raises(InvalidTag):
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


@pytest.mark.parametrize("scheme", ["rtsp", "rtsps"])
def test_ipv6_url_credentials_round_trip(scheme: str) -> None:
    original = f"{scheme}://cam%20user:p%40ss@[2001:db8::10]:8554/live?profile=1"
    clean, user, password = strip_url_credentials(original)
    assert clean == f"{scheme}://[2001:db8::10]:8554/live?profile=1"
    assert inject_url_credentials(clean, user, password) == original


def test_concurrent_master_key_creation_uses_one_complete_key(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    manager = KeyManager(tmp_path / "key")
    with ThreadPoolExecutor(max_workers=12) as pool:
        keys = list(pool.map(lambda _: manager.load_or_create(), range(24)))
    assert len(set(keys)) == 1
    assert manager.load() == keys[0]
    assert manager.path.stat().st_mode & 0o777 == 0o600


def test_consumed_setup_token_can_be_cleared_in_protected_directory(tmp_path: Path, monkeypatch) -> None:
    from mosaivue.security import consume_setup_token, generate_setup_token, verify_setup_token

    path = tmp_path / "setup-token"
    token = generate_setup_token(path)
    real_unlink = Path.unlink

    def deny_unlink(self, *args, **kwargs):
        if self == path:
            raise PermissionError("directory is protected")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_unlink)
    consume_setup_token(path)
    assert path.read_bytes() == b""
    assert not verify_setup_token(token, path)
    assert not verify_setup_token("", path)


def test_non_ascii_session_cookie_is_invalid_not_a_server_error(db) -> None:
    from mosaivue.security import get_session

    assert get_session(db, "malformed-\u2603-cookie") is None


def test_diagnostics_redact_query_secrets_and_ipv6_userinfo() -> None:
    from mosaivue.logging_utils import redact

    message = "Discovery failed for rtsps://viewer:hidden@[2001:db8::3]:7441/live?token=abc123&profile=main"
    sanitized = redact(message)
    assert "hidden" not in sanitized
    assert "viewer" not in sanitized
    assert "abc123" not in sanitized
    assert "[2001:db8::3]:7441" in sanitized
    assert "profile=main" in sanitized
