from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from ..config import load_settings
from ..constants import SETUP_TOKEN_PATH
from ..models import User
from ..schemas import LoginRequest, PasswordChangeRequest, SetupRequest
from ..security import (
    consume_setup_token,
    create_session,
    hash_password,
    revoke_session,
    verify_password,
    verify_setup_token,
)
from ..services.renderer_config import renderer_config, request_renderer_restart, select_renderer_backend
from .dependencies import Auth, CSRF, DB, login_limiter

router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_session_cookie(response: Response, token: str, max_age: int, *, secure: bool) -> None:
    response.set_cookie(
        "mosaivue_session",
        token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


@router.get("/setup/status")
def setup_status(db: DB) -> dict[str, object]:
    count = db.scalar(select(func.count()).select_from(User)) or 0
    return {"setup_required": count == 0, "token_file_exists": SETUP_TOKEN_PATH.exists(),
            "renderer": renderer_config()}


@router.post("/setup", status_code=201)
def setup(payload: SetupRequest, request: Request, response: Response, db: DB) -> dict[str, object]:
    login_limiter.check(request.client.host if request.client else "unknown")
    count = db.scalar(select(func.count()).select_from(User)) or 0
    if count:
        raise HTTPException(status_code=409, detail="Initial setup is already complete")
    if not verify_setup_token(payload.setup_token):
        raise HTTPException(status_code=403, detail="Invalid setup token")
    backend_changed = False
    if payload.renderer_backend is not None:
        try:
            backend_changed = select_renderer_backend(payload.renderer_backend)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = User(username=payload.username, password_hash=hash_password(payload.password), is_admin=True)
    db.add(user)
    db.flush()
    settings = load_settings()
    created = create_session(
        db,
        user,
        hours=settings.session_hours,
        remote_addr=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    # Persist the administrator and session before deleting the one-time token.
    # This prevents a late database failure from leaving the appliance without
    # either a usable account or a setup token.
    db.commit()
    consume_setup_token()
    renderer_restart_requested = request_renderer_restart() if backend_changed else False
    _set_session_cookie(response, created.token, settings.session_hours * 3600, secure=settings.secure_cookies)
    return {
        "user": {"id": user.id, "username": user.username, "is_admin": user.is_admin},
        "csrf_token": created.csrf_token,
        "expires_at": created.expires_at,
        "renderer_restart_requested": renderer_restart_requested,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: DB) -> dict[str, object]:
    remote = request.client.host if request.client else "unknown"
    login_limiter.check(remote)
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.enabled or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    settings = load_settings()
    created = create_session(
        db,
        user,
        hours=settings.session_hours,
        remote_addr=remote,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, created.token, settings.session_hours * 3600, secure=settings.secure_cookies)
    return {
        "user": {"id": user.id, "username": user.username, "is_admin": user.is_admin},
        "csrf_token": created.csrf_token,
        "expires_at": created.expires_at,
    }


@router.post("/logout")
def logout(response: Response, request: Request, db: DB, _: CSRF) -> dict[str, bool]:
    token = request.cookies.get("mosaivue_session")
    if token:
        revoke_session(db, token)
    response.delete_cookie("mosaivue_session", path="/")
    return {"ok": True}


@router.get("/me")
def me(auth: Auth) -> dict[str, object]:
    return {
        "user": {"id": auth.user.id, "username": auth.user.username, "is_admin": auth.user.is_admin},
        "csrf_token": auth.session.csrf_token,
        "expires_at": auth.session.expires_at,
    }


@router.post("/password")
def change_password(payload: PasswordChangeRequest, auth: CSRF, db: DB) -> dict[str, bool]:
    if not verify_password(payload.current_password, auth.user.password_hash):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    auth.user.password_hash = hash_password(payload.new_password)
    return {"ok": True}
