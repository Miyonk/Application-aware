"""Request client (Figure 7.3 send_request) and control-port helper."""
from __future__ import annotations

import asyncio
import json
import socket
import struct
import time
from typing import Any

_LINGER_ABORT = struct.pack("hh", 1, 0)  # SO_LINGER on, 0 s -> abortive close, no TIME_WAIT


async def send_request(host: str, port: int, payload: dict[str, Any], timeout_s: float) -> dict:
    """Send one JSON request on a new TCP connection; return client-measured outcome.

    Same logic as send_request in Figure 7.3, but on a raw non-blocking socket
    (loop.sock_* API) instead of asyncio streams. Reason: the Windows proactor
    stream transport calls shutdown(SHUT_RDWR) before closesocket(), which sends a
    FIN and puts every client socket into TIME_WAIT even with SO_LINGER(1, 0)
    (measured: 1000/1000 connections). With a raw socket we call close() directly,
    so SO_LINGER(1, 0) yields an abortive close (RST) and no TIME_WAIT.
    """
    if timeout_s <= 0:
        raise ValueError("timeout_s must be greater than zero")
    loop = asyncio.get_running_loop()
    started = time.perf_counter()
    sock: socket.socket | None = None
    result: dict
    try:
        async with asyncio.timeout(timeout_s):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, _LINGER_ABORT)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # as asyncio streams do
            await loop.sock_connect(sock, (host, port))
            await loop.sock_sendall(sock, json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
            buf = b""
            while b"\n" not in buf:
                chunk = await loop.sock_recv(sock, 65536)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n", 1)[0] if b"\n" in buf else b""
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not line:
            result = {"ok": False, "latency_ms": elapsed_ms, "server_load": None, "error": "connection_error"}
        else:
            response = json.loads(line)
            if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
                result = {"ok": False, "latency_ms": elapsed_ms, "server_load": None, "error": "connection_error"}
            else:
                raw_load = response.get("load")
                server_load = (
                    float(raw_load)
                    if isinstance(raw_load, (int, float)) and not isinstance(raw_load, bool)
                    else None
                )
                success = response["ok"]
                result = {
                    "ok": success,
                    "latency_ms": elapsed_ms,
                    "server_load": server_load,
                    "error": None if success else "simulated_failure",
                }
    except TimeoutError:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result = {"ok": False, "latency_ms": elapsed_ms, "server_load": None, "error": "timeout"}
    except (OSError, asyncio.IncompleteReadError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result = {
            "ok": False,
            "latency_ms": elapsed_ms,
            "server_load": None,
            "error": "connection_error",
            "detail": repr(exc),
        }
    finally:
        if sock is not None:
            sock.close()  # abortive (RST) because of SO_LINGER(1, 0)
    return result


async def control(host: str, port: int, msg: dict, timeout_s: float = 5.0) -> dict:
    async with asyncio.timeout(timeout_s):
        reader, writer = await asyncio.open_connection(host, port)
        try:
            writer.write(json.dumps(msg).encode("utf-8") + b"\n")
            await writer.drain()
            line = await reader.readline()
            if not line:
                raise ConnectionError("empty control reply")
            return json.loads(line)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


def make_payload(request_id: int, app: str, size: int) -> dict:
    """Request JSON with padding so the encoded line is about `size` bytes."""
    base = {"request_id": request_id, "app": app, "pad": ""}
    n = len(json.dumps(base, separators=(",", ":"))) + 1  # + newline
    base["pad"] = "x" * max(0, size - n)
    return base
