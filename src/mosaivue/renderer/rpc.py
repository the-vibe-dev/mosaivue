from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..constants import RENDERER_SOCKET_PATH

LOGGER = logging.getLogger(__name__)
RPC_MESSAGE_LIMIT = 1024 * 1024


class RendererRPCError(RuntimeError):
    pass


class RendererRPCClient:
    def __init__(self, socket_path: Path = RENDERER_SOCKET_PATH, timeout: float = 10.0):
        self.socket_path = socket_path
        self.timeout = timeout

    async def call(self, action: str, **params: Any) -> Any:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(self.socket_path), limit=RPC_MESSAGE_LIMIT),
                timeout=self.timeout,
            )
        except (OSError, TimeoutError) as exc:
            raise RendererRPCError(f"Renderer service is unavailable: {exc}") from exc
        try:
            request = json.dumps({"action": action, "params": params}, separators=(",", ":")) + "\n"
            writer.write(request.encode("utf-8"))
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
            raw = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
            if not raw:
                raise RendererRPCError("Renderer closed the connection without a response")
            response = json.loads(raw)
            if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
                raise RendererRPCError("Renderer returned an invalid response")
            if not response.get("ok"):
                raise RendererRPCError(response.get("error", "Unknown renderer error"))
            return response.get("result")
        except TimeoutError as exc:
            raise RendererRPCError("Renderer request timed out") from exc
        except (OSError, ValueError) as exc:
            raise RendererRPCError("Renderer returned an unreadable response") from exc
        finally:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), timeout=self.timeout)

    def call_sync(self, action: str, **params: Any) -> Any:
        return asyncio.run(self.call(action, **params))


class RendererRPCServer:
    def __init__(
        self,
        handlers: dict[str, Callable[..., Any] | Callable[..., Awaitable[Any]]],
        socket_path: Path = RENDERER_SOCKET_PATH,
    ) -> None:
        self.handlers = handlers
        self.socket_path = socket_path
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(
            self._handle, path=str(self.socket_path), limit=RPC_MESSAGE_LIMIT
        )
        os.chmod(self.socket_path, 0o600)

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.socket_path.unlink(missing_ok=True)

    async def serve_forever(self) -> None:
        if self.server is None:
            await self.start()
        assert self.server is not None
        async with self.server:
            await self.server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=15)
            request = json.loads(raw)
            if not isinstance(request, dict) or not isinstance(request.get("action"), str):
                raise ValueError("Renderer request must contain an action string")
            action = request.get("action")
            params = request.get("params", {})
            if params is None:
                params = {}
            if not isinstance(params, dict):
                raise ValueError("Renderer request params must be an object")
            handler = self.handlers.get(action)
            if handler is None:
                raise KeyError(f"Unknown renderer action: {action}")
            result = handler(**params)
            if asyncio.iscoroutine(result):
                result = await result
            response = {"ok": True, "result": result}
        except Exception as exc:
            LOGGER.exception("Renderer RPC request failed")
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            writer.write((json.dumps(response, separators=(",", ":"), default=str) + "\n").encode("utf-8"))
            await asyncio.wait_for(writer.drain(), timeout=15)
        except (OSError, TimeoutError):
            LOGGER.debug("Renderer RPC client disconnected before receiving the response")
        finally:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), timeout=15)
