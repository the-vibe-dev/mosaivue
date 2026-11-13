from __future__ import annotations

import asyncio
import threading

import pytest

from mosaivue.services.stream_work import StreamWorkBusy, StreamWorkPool


async def test_identical_requests_coalesce_and_cache_until_ttl():
    now = [10.0]
    pool = StreamWorkPool(cache_ttl_seconds=2, clock=lambda: now[0])
    calls = 0

    def capture():
        nonlocal calls
        calls += 1
        return f"jpeg-{calls}".encode()

    key = pool.fingerprint(url="rtsp://viewer:secret@camera/live", width=640)
    assert len(key) == 32 and b"secret" not in key
    assert await asyncio.gather(*(
        pool.run(key, capture, cache_image=True) for _ in range(20)
    )) == [b"jpeg-1"] * 20
    assert await pool.run(key, capture, cache_image=True) == b"jpeg-1"
    now[0] += 2
    assert await pool.run(key, capture, cache_image=True) == b"jpeg-2"
    assert calls == 2
    await pool.close()


async def test_cancelled_waiter_does_not_release_a_running_capture_slot():
    pool = StreamWorkPool(queue_timeout_seconds=0.1)
    started, release = threading.Event(), threading.Event()
    second_started = threading.Event()

    def blocked_capture():
        started.set()
        assert release.wait(timeout=3)
        return b"first"

    first = asyncio.create_task(pool.run(b"first", blocked_capture))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        with pytest.raises(StreamWorkBusy):
            await pool.run(b"second", lambda: second_started.set())
        assert not second_started.is_set()
        # A fresh waiter can still join the surviving first capture.
        joined = asyncio.create_task(pool.run(b"first", lambda: pytest.fail("duplicate capture")))
        release.set()
        assert await joined == b"first"
    finally:
        release.set()
        await pool.close()


async def test_concurrency_and_distinct_queue_are_bounded():
    pool = StreamWorkPool(concurrency=2, max_queued=0)
    started = threading.Barrier(3)
    release = threading.Event()
    current = maximum = 0
    lock = threading.Lock()

    def capture():
        nonlocal current, maximum
        with lock:
            current += 1
            maximum = max(maximum, current)
        started.wait(timeout=2)
        try:
            assert release.wait(timeout=3)
            return b"jpeg"
        finally:
            with lock:
                current -= 1

    first = asyncio.create_task(pool.run(b"one", capture))
    second = asyncio.create_task(pool.run(b"two", capture))
    try:
        await asyncio.to_thread(started.wait, 2)
        with pytest.raises(StreamWorkBusy):
            await pool.run(b"three", lambda: pytest.fail("queue overflow started a capture"))
        # Duplicates can join even when the distinct-work budget is full.
        duplicate = asyncio.create_task(pool.run(b"one", lambda: pytest.fail("duplicate")))
        release.set()
        assert await asyncio.gather(first, second, duplicate) == [b"jpeg"] * 3
        assert maximum == 2
    finally:
        release.set()
        await pool.close()


async def test_failures_are_not_cached_and_worker_is_reusable():
    pool = StreamWorkPool()

    def failed():
        raise RuntimeError("capture failed")

    with pytest.raises(RuntimeError, match="capture failed"):
        await pool.run(b"camera", failed, cache_image=True)
    assert await pool.run(b"camera", lambda: b"recovered", cache_image=True) == b"recovered"
    await pool.close()


async def test_cache_respects_byte_budget_entry_limit_and_lru_order():
    pool = StreamWorkPool(max_cache_bytes=6, max_cache_entries=2)
    calls = []

    def image(key):
        calls.append(key)
        return key * 3

    async def request(key):
        return await pool.run(key, lambda: image(key), cache_image=True)

    assert await request(b"a") == b"aaa"
    assert await request(b"b") == b"bbb"
    assert await request(b"a") == b"aaa"
    assert await request(b"c") == b"ccc"
    assert await request(b"b") == b"bbb"
    assert calls == [b"a", b"b", b"c", b"b"]
    assert pool._cache_bytes == 6
    await pool.close()
    assert not pool._cache and pool._cache_bytes == 0


@pytest.mark.parametrize("ttl,size", [(0, 1024), (2, 2)])
async def test_disabled_or_oversized_images_are_not_cached(ttl, size):
    pool = StreamWorkPool(cache_ttl_seconds=ttl, max_cache_bytes=size)
    calls = []

    def image():
        calls.append(True)
        return b"oversized"

    assert await pool.run(b"key", image, cache_image=True) == b"oversized"
    assert await pool.run(b"key", image, cache_image=True) == b"oversized"
    assert len(calls) == 2
    await pool.close()


async def test_close_drains_active_work_and_rejects_new_work():
    pool = StreamWorkPool()
    started, release = threading.Event(), threading.Event()

    def capture():
        started.set()
        assert release.wait(timeout=3)
        return b"jpeg"

    first = asyncio.create_task(pool.run(b"one", capture, cache_image=True))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        closing = asyncio.create_task(pool.close())
        await asyncio.sleep(0)
        assert not closing.done()
        with pytest.raises(StreamWorkBusy):
            await pool.run(b"new", lambda: pytest.fail("closed pool ran new work"))
        release.set()
        assert await first == b"jpeg"
        await closing
        assert not pool._cache and not pool._inflight
    finally:
        release.set()
        await pool.close()


def test_fingerprints_are_private_and_change_for_every_stream_setting():
    pool = StreamWorkPool()
    parameters = {"url": "rtsp://u:private@camera/live", "transport": "tcp", "width": 640, "codec": "h264"}
    original = pool.fingerprint(**parameters)
    for name, value in (("url", "rtsp://u:new-secret@camera/live"), ("transport", "udp"), ("width", 1280), ("codec", "h265")):
        assert pool.fingerprint(**{**parameters, name: value}) != original
    assert StreamWorkPool().fingerprint(**parameters) != original
