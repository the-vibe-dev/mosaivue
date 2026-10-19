from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from ..config import load_settings
from ..constants import SETUP_TOKEN_PATH, STATIC_DIR
from ..db import get_session_factory, init_db
from ..events import EventBus
from ..logging_utils import configure_logging
from ..models import User
from ..renderer.rpc import RendererRPCClient
from ..security import KeyManager, generate_setup_token
from ..services.capabilities import write_capabilities
from ..version import __version__
from .dependencies import AuthContext, require_auth
from .routes_auth import router as auth_router
from .routes_backup import router as backup_router
from .routes_cameras import router as cameras_router
from .routes_display import router as display_router
from .routes_layouts import router as layouts_router
from .routes_logs import router as logs_router
from .routes_renderer import router as renderer_router
from .routes_rotations import router as rotations_router
from .routes_schedules import router as schedules_router
from .routes_system import router as system_router
from .routes_update import router as update_router

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    configure_logging(settings.log_level)
    init_db()
    KeyManager().load_or_create()
    with get_session_factory()() as db:
        user_count = db.scalar(select(func.count()).select_from(User)) or 0
    if user_count == 0 and not SETUP_TOKEN_PATH.exists():
        generate_setup_token()
        LOGGER.warning("Initial setup is required; the one-time token is stored at %s", SETUP_TOKEN_PATH)
    app.state.events = EventBus()
    app.state.renderer = RendererRPCClient()

    async def refresh_capabilities() -> None:
        try:
            await asyncio.to_thread(write_capabilities)
        except Exception:
            LOGGER.exception("Unable to write initial capabilities report")

    # The installer already saved a capability report. Probing every GStreamer
    # plugin again can take over a minute on a Pi 3, so serve HTTP first.
    refresh_task = asyncio.create_task(refresh_capabilities())
    try:
        yield
    finally:
        refresh_task.cancel()
        with suppress(asyncio.CancelledError):
            await refresh_task


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mosaivue API",
        description="Local-first RTSP camera wall control plane",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; style-src-attr 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix="/api/v1")
    for router in (
        auth_router,
        cameras_router,
        layouts_router,
        rotations_router,
        display_router,
        renderer_router,
        schedules_router,
        system_router,
        logs_router,
        backup_router,
        update_router,
    ):
        api.include_router(router)

    @api.get("/status", tags=["system"])
    async def status_alias(_: AuthContext = Depends(require_auth)) -> dict[str, object]:
        """Compatibility status endpoint matching the documented API root."""
        try:
            renderer = await app.state.renderer.call("status")
        except Exception as exc:
            renderer = {"state": "UNAVAILABLE", "error": str(exc), "streams": {}}
        return {"status": "ok", "renderer": renderer}

    @api.get("/events", tags=["events"])
    async def events(
        request: Request, _: AuthContext = Depends(require_auth)
    ) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            async for message in request.app.state.events.subscribe():
                if await request.is_disconnected():
                    break
                yield EventBus.encode_sse(message)

        return StreamingResponse(stream(), media_type="text/event-stream")

    app.include_router(api)

    static_path = Path(STATIC_DIR)
    if static_path.exists():
        assets = static_path / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False, response_model=None)
        async def frontend(path: str) -> FileResponse | JSONResponse:
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            candidate = static_path / path
            if path and candidate.is_file() and static_path in candidate.resolve().parents:
                return FileResponse(candidate)
            index = static_path / "index.html"
            if index.exists():
                return FileResponse(index)
            return JSONResponse({"detail": "Frontend assets are not installed"}, status_code=503)

    return app


app = create_app()


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "mosaivue.api.app:app",
        host=settings.bind,
        port=settings.port,
        log_config=None,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1,::1",
    )


if __name__ == "__main__":
    main()
