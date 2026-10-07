from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .constants import MASTER_KEY_PATH, SETUP_TOKEN_PATH
from .models import User, WebSession, uuid4

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1


def secure_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(temporary, flags, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


class KeyManager:
    def __init__(self, path: Path = MASTER_KEY_PATH):
        self.path = path

    def load_or_create(self) -> bytes:
        if self.path.exists():
            key = self.path.read_bytes()
            if len(key) != 32:
                raise RuntimeError(f"Invalid Mosaivue master key length at {self.path}")
            return key
        key = secrets.token_bytes(32)
        secure_write(self.path, key, 0o600)
        return key

    def load(self) -> bytes:
        key = self.path.read_bytes()
        if len(key) != 32:
            raise RuntimeError(f"Invalid Mosaivue master key length at {self.path}")
        return key


class CredentialCipher:
    VERSION = 1

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: str, *, context: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))
        payload = bytes([self.VERSION]) + nonce + ciphertext
        return base64.urlsafe_b64encode(payload).decode("ascii")

    def decrypt(self, token: str, *, context: str) -> str:
        payload = base64.urlsafe_b64decode(token.encode("ascii"))
        if not payload or payload[0] != self.VERSION:
            raise ValueError("Unsupported encrypted credential format")
        nonce = payload[1:13]
        ciphertext = payload[13:]
        return self._cipher.decrypt(nonce, ciphertext, context.encode("utf-8")).decode("utf-8")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32, maxmem=128 * 1024 * 1024
    )
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected), maxmem=128 * 1024 * 1024
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def generate_setup_token(path: Path = SETUP_TOKEN_PATH) -> str:
    token = "MV-" + "-".join(secrets.token_hex(3).upper() for _ in range(3))
    secure_write(path, (token + "\n").encode("utf-8"), 0o600)
    return token


def verify_setup_token(candidate: str, path: Path = SETUP_TOKEN_PATH) -> bool:
    if not path.exists():
        return False
    expected = path.read_text(encoding="utf-8").strip()
    return hmac.compare_digest(candidate.strip(), expected)


def consume_setup_token(path: Path = SETUP_TOKEN_PATH) -> None:
    path.unlink(missing_ok=True)


def strip_url_credentials(url: str) -> tuple[str, str | None, str | None]:
    parts = urlsplit(url)
    username = unquote(parts.username) if parts.username is not None else None
    password = unquote(parts.password) if parts.password is not None else None
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    clean = urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return clean, username, password


def inject_url_credentials(url: str, username: str | None, password: str | None) -> str:
    if not username:
        return url
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    userinfo = quote(username, safe="")
    if password is not None:
        userinfo += ":" + quote(password, safe="")
    netloc = f"{userinfo}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


@dataclass(slots=True)
class CreatedSession:
    token: str
    csrf_token: str
    expires_at: datetime


def create_session(
    db: Session,
    user: User,
    *,
    hours: int = 12,
    remote_addr: str | None = None,
    user_agent: str | None = None,
) -> CreatedSession:
    # Expired-session cleanup belongs on the already-write-oriented login path.
    # Authentication checks must remain read-only so parallel dashboard requests
    # do not contend for SQLite's single writer lock.
    db.execute(delete(WebSession).where(WebSession.expires_at <= datetime.now(UTC)))
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(hours=hours)
    db.add(
        WebSession(
            id=uuid4(),
            user_id=user.id,
            token_hash=session_token_hash(token),
            csrf_token=csrf,
            expires_at=expires_at,
            remote_addr=remote_addr,
            user_agent=(user_agent or "")[:512],
        )
    )
    return CreatedSession(token=token, csrf_token=csrf, expires_at=expires_at)


def get_session(db: Session, token: str) -> WebSession | None:
    """Resolve a session without writing to the database.

    The browser deliberately issues several authenticated GET requests in
    parallel. A DELETE or last-seen UPDATE here would turn every read into a
    writer and can produce ``database is locked`` failures on SQLite.
    Expired rows are ignored here and pruned when a new session is created.
    """
    now = datetime.now(UTC)
    web_session = db.scalar(
        select(WebSession).where(WebSession.token_hash == session_token_hash(token))
    )
    if web_session is None:
        return None
    expires_at = web_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now or not web_session.user.enabled:
        return None
    return web_session


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(WebSession).where(WebSession.token_hash == session_token_hash(token)))
