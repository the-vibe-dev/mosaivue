import asyncio
import json

import pytest

from mosaivue.renderer.rpc import (
    RPC_MESSAGE_LIMIT,
    RendererRPCClient,
    RendererRPCError,
    RendererRPCServer,
)


class MemoryWriter:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def response_reader(response):
    reader = asyncio.StreamReader(limit=RPC_MESSAGE_LIMIT)
    reader.feed_data(response)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_rpc_real_socket_roundtrip_and_permissions(tmp_path):
    socket = tmp_path / "r.sock"
    server = RendererRPCServer({"status": lambda: {"state": "RUNNING"}}, socket)
    try:
        await server.start()
    except PermissionError:
        pytest.skip("Execution environment prohibits creating Unix sockets")
    try:
        client = RendererRPCClient(socket)
        assert await client.call("status") == {"state": "RUNNING"}
        with pytest.raises(RendererRPCError, match="Unknown renderer action"):
            await client.call("unknown")
        assert socket.stat().st_mode & 0o777 == 0o600
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_rpc_supports_status_larger_than_default_stream_limit(monkeypatch, tmp_path):
    payload = {f"slot-{index}": {"detail": "x" * 700} for index in range(128)}
    response = (json.dumps({"ok": True, "result": payload}) + "\n").encode()
    assert len(response) > 65536
    writer = MemoryWriter()

    async def connect(path, *, limit):
        assert limit == RPC_MESSAGE_LIMIT
        return response_reader(response), writer

    monkeypatch.setattr(asyncio, "open_unix_connection", connect)
    assert await RendererRPCClient(tmp_path / "r.sock").call("status") == payload
    assert writer.closed
    assert json.loads(writer.data)["action"] == "status"


@pytest.mark.asyncio
async def test_rpc_timeout_is_an_availability_error(monkeypatch, tmp_path):
    writer = MemoryWriter()

    async def connect(path, *, limit):
        return asyncio.StreamReader(limit=limit), writer

    monkeypatch.setattr(asyncio, "open_unix_connection", connect)
    with pytest.raises(RendererRPCError, match="timed out"):
        await RendererRPCClient(tmp_path / "r.sock", timeout=0.01).call("slow")
    assert writer.closed


@pytest.mark.parametrize("response", [b"not-json\n", b"[]\n", b'{"ok":"yes"}\n'])
@pytest.mark.asyncio
async def test_rpc_malformed_response_is_normalized(monkeypatch, tmp_path, response):
    writer = MemoryWriter()

    async def connect(path, *, limit):
        return response_reader(response), writer

    monkeypatch.setattr(asyncio, "open_unix_connection", connect)
    with pytest.raises(RendererRPCError):
        await RendererRPCClient(tmp_path / "r.sock").call("status")
    assert writer.closed


@pytest.mark.parametrize("payload", [[], {"action": "status", "params": []}, {"action": 123}])
@pytest.mark.asyncio
async def test_rpc_rejects_nonobject_requests_and_params(tmp_path, payload):
    server = RendererRPCServer({"status": lambda: pytest.fail("Unexpected handler call")}, tmp_path / "r.sock")
    reader = response_reader((json.dumps(payload) + "\n").encode())
    writer = MemoryWriter()
    await server._handle(reader, writer)
    response = json.loads(writer.data)
    assert response["ok"] is False
    assert "ValueError" in response["error"]
    assert writer.closed
