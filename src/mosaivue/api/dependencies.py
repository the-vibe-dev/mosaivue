from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import session_dependency
from ..models import User, WebSession
from ..security import CredentialCipher, KeyManager, get_session

DB = Annotated[Session, Depends(session_dependency)]


@dataclass(slots=True)
class AuthContext:
    user: User
    session: WebSession


_cipher: CredentialCipher | None = None


def get_cipher() -> CredentialCipher:
    global _cipher
    if _cipher is None:
        _cipher = CredentialCipher(KeyManager().load_or_create())
    return _cipher


def require_auth(
    request: Request,
    db: DB,
    mosaivue_session: Annotated[str | None, Cookie()] = None,
) -> AuthContext:
    if not mosaivue_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session = get_session(db, mosaivue_session)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    request.state.auth = AuthContext(user=session.user, session=session)
    return request.state.auth


Auth = Annotated[AuthContext, Depends(require_auth)]


def require_admin(auth: Auth) -> AuthContext:
    if not auth.user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return auth


Admin = Annotated[AuthContext, Depends(require_admin)]


def require_csrf(
    request: Request,
    auth: Auth,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return auth
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, auth.session.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return auth


CSRF = Annotated[AuthContext, Depends(require_csrf)]


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self.attempts[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many attempts; try again later")
        bucket.append(now)


login_limiter = RateLimiter(8, 60)
