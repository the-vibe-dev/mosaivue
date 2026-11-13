import asyncio
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from mosaivue.renderer import daemon
from mosaivue.renderer.controller import RendererController
from mosaivue.renderer.testing import TestRenderer as MemoryRenderer


@pytest.mark.parametrize("failure_stage", ["open", "query", "apply"])
@pytest.mark.asyncio
async def test_scheduler_retries_transient_failure_then_applies_layout(monkeypatch, failure_stage):
    stop = asyncio.Event()
    calls = {"open": 0, "query": 0, "apply": 0}

    def attempt(stage):
        calls[stage] += 1
        if stage == failure_stage and calls[stage] == 1:
            raise OSError("Temporary appliance failure")

    def session_factory():
        attempt("open")
        return nullcontext(object())

    def select_schedule(db, moment):
        attempt("query")
        assert moment.tzinfo is not None
        return "scheduled-wall"

    async def apply_layout(layout_id):
        attempt("apply")
        controller.active_layout_id = layout_id
        stop.set()

    controller = SimpleNamespace(focused=False, active_layout_id="old-wall", apply_layout=apply_layout)
    monkeypatch.setattr(daemon, "select_scheduled_layout", select_schedule)
    await asyncio.wait_for(daemon.watch_schedules(controller, session_factory, stop, interval_seconds=0.001), 1)
    assert controller.active_layout_id == "scheduled-wall"
    assert calls[failure_stage] == 2


@pytest.mark.asyncio
async def test_scheduler_propagates_cancellation(monkeypatch):
    def cancelled(*_):
        raise asyncio.CancelledError

    monkeypatch.setattr(daemon, "select_scheduled_layout", cancelled)
    controller = SimpleNamespace(focused=False, active_layout_id=None)
    with pytest.raises(asyncio.CancelledError):
        await daemon.watch_schedules(controller, lambda: nullcontext(object()), asyncio.Event())


@pytest.mark.parametrize("focused,enabled", [(True, True), (False, False)])
@pytest.mark.asyncio
async def test_scheduler_does_not_override_focus_or_disabled_scheduling(focused, enabled):
    stop = asyncio.Event()
    controller = SimpleNamespace(focused=focused, active_layout_id=None)

    def session_factory():
        pytest.fail("Schedule read while scheduling is suspended")

    task = asyncio.create_task(daemon.watch_schedules(controller, session_factory, stop, enabled=enabled))
    await asyncio.sleep(0)
    stop.set()
    await asyncio.wait_for(task, 1)


@pytest.mark.parametrize("outcome", ["exception", "return", "cancel"])
@pytest.mark.asyncio
async def test_supervisor_fails_when_essential_task_stops(outcome):
    async def background():
        if outcome == "exception":
            raise OSError("RPC listener failed")
        if outcome == "cancel":
            raise asyncio.CancelledError

    task = asyncio.create_task(background(), name="essential-task")
    with pytest.raises(RuntimeError, match="essential-task") as caught:
        await asyncio.wait_for(daemon.wait_for_daemon_stop(asyncio.Event(), [task]), 1)
    if outcome == "exception":
        assert isinstance(caught.value.__cause__, OSError)
    assert task.done()


@pytest.mark.asyncio
async def test_supervisor_accepts_requested_stop_without_cancelling_background_task():
    stop = asyncio.Event()
    stop.set()
    task = asyncio.create_task(asyncio.Event().wait(), name="still-running")
    try:
        await daemon.wait_for_daemon_stop(stop, [task])
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_rotation_timer_recovers_from_database_read_failure(monkeypatch):
    reads = 0
    steps = []
    waits = []

    def session_factory():
        nonlocal reads
        reads += 1
        if reads == 1:
            raise OSError("Temporary database failure")
        return nullcontext(SimpleNamespace(get=lambda *_: SimpleNamespace(interval_seconds=10)))

    async def rotate(slot_id, *, direction, prepare_only=False):
        steps.append(prepare_only)
        if not prepare_only:
            raise asyncio.CancelledError

    async def sleep(seconds):
        waits.append(seconds)

    controller = RendererController(MemoryRenderer(), session_factory, None)
    monkeypatch.setattr(controller, "rotate", rotate)
    monkeypatch.setattr("mosaivue.renderer.controller.asyncio.sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await controller._rotation_loop("tile", "group")
    assert reads == 2
    assert steps == [True, False]
    assert waits[0] == 5
    assert controller.rotation_failures["tile"] == 1
