from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from concurrent.futures import Future
from contextlib import suppress
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import load_settings
from ..db import get_session_factory, init_db
from ..logging_utils import configure_logging
from ..models import DisplayProfile, Layout
from ..security import CredentialCipher, KeyManager
from ..services.schedules import select_scheduled_layout
from .controller import RendererController
from .factory import create_backend
from .gstreamer import GStreamerRenderer
from .rpc import RendererRPCServer

LOGGER = logging.getLogger(__name__)


async def watch_schedules(
    controller: RendererController, session_factory: sessionmaker[Session],
    stop_event: asyncio.Event, *,
    enabled: bool = True, interval_seconds: float = 30,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("Schedule poll interval must be positive")
    while not stop_event.is_set():
        try:
            if enabled and not controller.focused:
                with session_factory() as db:
                    scheduled = select_scheduled_layout(db, datetime.now().astimezone())
                if scheduled and scheduled != controller.active_layout_id:
                    await controller.apply_layout(scheduled)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Temporary SQLite/read errors need the same retry behavior as an
            # unavailable renderer. They must not silently kill scheduling.
            LOGGER.exception("Scheduled layout check failed; retrying on the next poll")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)


async def wait_for_daemon_stop(
    stop_event: asyncio.Event, tasks: list[asyncio.Task[None]]
) -> None:
    """Exit on a failed/stopped essential task so systemd can recover it."""
    stop_task = asyncio.create_task(stop_event.wait(), name="renderer-stop")
    try:
        done, _ = await asyncio.wait([stop_task, *tasks], return_when=asyncio.FIRST_COMPLETED)
        if not stop_event.is_set():
            ended = next(task for task in tasks if task in done)
            if ended.cancelled():
                raise RuntimeError(f"Renderer background task {ended.get_name()} was cancelled")
            raise RuntimeError(f"Renderer background task {ended.get_name()} stopped") from ended.exception()
    finally:
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)


async def run_daemon() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    init_db()
    session_factory = get_session_factory()
    cipher = CredentialCipher(KeyManager().load_or_create())
    width, height = 1920, 1080
    active_layout_id: str | None = None
    with session_factory() as db:
        active = db.scalar(select(Layout).where(Layout.active.is_(True)))
        if active:
            active_layout_id = active.id
            if active.display_profile_id:
                profile = db.get(DisplayProfile, active.display_profile_id)
                if profile:
                    width, height = profile.width, profile.height
    backend = create_backend(settings)
    backend.initialize(width=width, height=height, sink=settings.renderer_sink)
    controller = RendererController(
        backend,
        session_factory,
        cipher,
        output_width=width,
        output_height=height,
    )
    loop = asyncio.get_running_loop()
    if isinstance(backend, GStreamerRenderer):
        def request_failover(slot_id: str) -> None:
            future = asyncio.run_coroutine_threadsafe(controller.rotate(slot_id), loop)

            def report(result: Future[object]) -> None:
                try:
                    result.result()
                except Exception:
                    LOGGER.exception("Prepared rotation failover failed", extra={"slot_id": slot_id})

            future.add_done_callback(report)

        backend.set_failure_callback(request_failover)
    if active_layout_id:
        try:
            await controller.apply_layout(active_layout_id)
        except Exception:
            LOGGER.exception("Unable to render the active layout at startup")

    server = RendererRPCServer(
        {
            "ping": lambda: {"pong": True},
            "status": controller.status,
            "apply_layout": controller.apply_layout,
            "focus_camera": controller.focus_camera,
            "restore_layout": controller.restore_layout,
            "restart_stream": controller.restart_stream,
            "rotation_next": lambda slot_id: controller.rotate(slot_id, direction=1, manual=True),
            "rotation_previous": lambda slot_id: controller.rotate(slot_id, direction=-1, manual=True),
            "rotation_pause": lambda group_id: controller.pause_rotation(group_id),
            "rotation_resume": lambda group_id: controller.resume_rotation(group_id),
        }
    )
    await server.start()
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    tasks = [
        asyncio.create_task(server.serve_forever(), name="renderer-rpc"),
        asyncio.create_task(
            watch_schedules(controller, session_factory, stop_event, enabled=settings.schedule_enabled),
            name="layout-scheduler",
        ),
    ]
    try:
        await wait_for_daemon_stop(stop_event, tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await server.close()
        finally:
            await controller.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Mosaivue renderer service")
    parser.parse_args()
    asyncio.run(run_daemon())


if __name__ == "__main__":
    main()
