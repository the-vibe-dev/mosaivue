from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any


class StreamWorkBusy(RuntimeError):
    """The appliance's bounded preview/probe budget is temporarily occupied."""

    def __init__(self) -> None:
        super().__init__("Camera preview and test workers are busy; retry in a few seconds")


class StreamWorkPool:
    """Share a small decode budget across authenticated HTTP previews and tests.

    A disconnected caller must not release a slot while its synchronous capture
    is still running. Independent tasks own the slots; callers only await them
    through shield(). Identical requests share that task and successful JPEGs
    may be cached briefly. Neither cached nor in-flight keys contain stream URIs.
    Create one instance per application lifespan, on the application's event loop.
    """

    def __init__(
        self,
        *,
        concurrency: int = 1,
        max_queued: int = 8,
        queue_timeout_seconds: float = 2,
        cache_ttl_seconds: float = 2,
        max_cache_entries: int = 64,
        max_cache_bytes: int = 8 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if concurrency < 1 or max_queued < 0 or queue_timeout_seconds <= 0:
            raise ValueError("Stream worker concurrency and queue limits must be positive")
        if cache_ttl_seconds < 0 or max_cache_entries < 1 or max_cache_bytes < 1:
            raise ValueError("Stream cache limits must be positive and its TTL nonnegative")
        self._slots = asyncio.Semaphore(concurrency)
        self._max_pending = concurrency + max_queued
        self._queue_timeout = queue_timeout_seconds
        self._cache_ttl = cache_ttl_seconds
        self._max_cache_entries = max_cache_entries
        self._max_cache_bytes = max_cache_bytes
        self._clock = clock
        self._key_secret = secrets.token_bytes(32)
        self._inflight: dict[bytes, asyncio.Task[Any]] = {}
        self._cache: OrderedDict[bytes, tuple[float, bytes]] = OrderedDict()
        self._cache_bytes = 0
        self._closed = False

    def fingerprint(self, **parameters: Any) -> bytes:
        # A process-local keyed digest also prevents offline guessing of a
        # camera password from a low-entropy stream URL found in a memory key.
        encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.blake2b(encoded, key=self._key_secret, digest_size=32).digest()

    async def run(
        self, key: bytes, producer: Callable[[], Any], *, cache_image: bool = False
    ) -> Any:
        if self._closed:
            raise StreamWorkBusy()
        self._expire_cache()
        if cache_image and key in self._cache:
            _, image = self._cache[key]
            self._cache.move_to_end(key)
            return image
        task = self._inflight.get(key)
        if task is None:
            if len(self._inflight) >= self._max_pending:
                raise StreamWorkBusy()
            task = asyncio.create_task(self._produce(key, producer, cache_image))
            self._inflight[key] = task
            # The last HTTP waiter may disconnect before a failed capture
            # finishes. Retrieve the exception even when nobody still awaits it.
            task.add_done_callback(self._consume_exception)
        return await asyncio.shield(task)

    @staticmethod
    def _consume_exception(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()

    async def _produce(self, key: bytes, producer: Callable[[], Any], cache_image: bool) -> Any:
        acquired = False
        try:
            try:
                await asyncio.wait_for(self._slots.acquire(), timeout=self._queue_timeout)
            except TimeoutError as exc:
                raise StreamWorkBusy() from exc
            acquired = True
            if self._closed:
                raise StreamWorkBusy()
            result = await asyncio.to_thread(producer)
            if cache_image and isinstance(result, bytes) and self._cache_ttl > 0 and not self._closed:
                self._remember(key, result)
            return result
        finally:
            if acquired:
                self._slots.release()
            self._inflight.pop(key, None)

    def _expire_cache(self) -> None:
        now = self._clock()
        for key, (expires, image) in list(self._cache.items()):
            if expires <= now:
                self._cache.pop(key)
                self._cache_bytes -= len(image)

    def _remember(self, key: bytes, image: bytes) -> None:
        self._expire_cache()
        if len(image) > self._max_cache_bytes:
            return
        previous = self._cache.pop(key, None)
        if previous is not None:
            self._cache_bytes -= len(previous[1])
        while self._cache and (
            len(self._cache) >= self._max_cache_entries
            or self._cache_bytes + len(image) > self._max_cache_bytes
        ):
            _, (_, discarded) = self._cache.popitem(last=False)
            self._cache_bytes -= len(discarded)
        self._cache[key] = (self._clock() + self._cache_ttl, image)
        self._cache_bytes += len(image)

    async def close(self) -> None:
        self._closed = True
        # Capture/probe functions have their own bounded media timeouts. Drain
        # active work before disposing of the pool instead of losing its slots.
        if self._inflight:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tuple(self._inflight.values())),
                return_exceptions=True,
            )
        self._cache.clear()
        self._cache_bytes = 0
