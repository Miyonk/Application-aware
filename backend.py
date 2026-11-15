"""One backend server process: asyncio TCP data port + control port.

Usage: python backend.py --index 0     (S1 on 9001/9101)

Data protocol and _process_request follow Figure 7.3 of the paper.
Control protocol (JSON line in, JSON line out):
  {"cmd":"ping"}
  {"cmd":"set","config":{...}}      merge values into the live config
  {"cmd":"reset","seed":N}          restore original config, reseed RNG
  {"cmd":"get"}                     return live config
  {"cmd":"sleeptest"}               measure asyncio.sleep accuracy in this process
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from typing import Any

import common


class Backend:
    def __init__(self, index: int):
        self.index = index
        self.original = common.default_server_config(index)
        self.config = dict(self.original)
        self.server_id = self.config["server_id"]
        self._random = random.Random(common.server_seed(0, index))
        self._active_connections = 0

    # ---------------- data path (Figure 7.3) ----------------
    async def _write_json(self, writer: asyncio.StreamWriter, obj: dict) -> None:
        writer.write(json.dumps(obj, separators=(",", ":")).encode("utf-8") + b"\n")
        await writer.drain()

    async def _sleep_ms(self, ms: float) -> None:
        await asyncio.sleep(ms / 1000.0)

    async def handle_data_client(self, reader, writer) -> None:
        self._active_connections += 1
        try:
            while line := await reader.readline():
                try:
                    request = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    await self._write_json(writer, {"ok": False, "error": "invalid_json"})
                    continue
                if not isinstance(request, dict):
                    await self._write_json(writer, {"ok": False, "error": "request_must_be_object"})
                    continue
                await self._process_request(request, writer)
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass  # client reset (abortive close) or timeout: tolerated
        finally:
            self._active_connections -= 1
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _process_request(self, request: dict[str, Any], writer) -> None:
        config = self.config
        load = self._active_connections / config["capacity"]
        latency_ms = max(
            0.0,
            config["base_latency_ms"]
            + self._random.uniform(-config["jitter"], config["jitter"])
            + config["load_factor"] * load,
        )
        if self._random.random() < config["packet_loss_prob"]:
            await self._sleep_ms(config["timeout_ms"])
            return
        await self._sleep_ms(latency_ms)
        success = self._random.random() >= config["failure_prob"]
        response: dict[str, Any] = {
            "ok": success,
            "server_id": self.server_id,
            "latency_ms": round(latency_ms, 3),
            "load": round(load, 6),
        }
        if not success:
            response["error"] = "simulated_failure"
        if "request_id" in request:
            response["request_id"] = request["request_id"]
        await self._write_json(writer, response)

    # ---------------- control path ----------------
    async def handle_control_client(self, reader, writer) -> None:
        try:
            while line := await reader.readline():
                try:
                    msg = json.loads(line)
                    reply = await self._control(msg)
                except Exception as exc:  # noqa: BLE001
                    reply = {"ok": False, "error": repr(exc)}
                await self._write_json(writer, reply)
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _control(self, msg: dict) -> dict:
        cmd = msg.get("cmd")
        if cmd == "ping":
            return {"ok": True, "server_id": self.server_id}
        if cmd == "set":
            new = dict(self.config)
            for k, v in msg.get("config", {}).items():
                if k not in self.original or k == "server_id":
                    return {"ok": False, "error": f"unknown key {k}"}
                new[k] = v
            self.config = new  # atomic swap
            return {"ok": True, "config": self.config}
        if cmd == "reset":
            self.config = dict(self.original)
            self._random = random.Random(common.server_seed(int(msg["seed"]), self.index))
            return {"ok": True, "config": self.config, "active": self._active_connections}
        if cmd == "get":
            return {"ok": True, "config": self.config, "active": self._active_connections}
        if cmd == "sleeptest":
            res = await common.measure_sleep_accuracy()
            return {"ok": True, "server_id": self.server_id, "sleep": res}
        return {"ok": False, "error": f"unknown cmd {cmd}"}


async def main(index: int) -> None:
    common.enable_hires_timer()
    common.install_quiet_exception_handler()
    b = Backend(index)
    data = await asyncio.start_server(b.handle_data_client, common.HOST, common.DATA_PORTS[index], backlog=1024)
    ctrl = await asyncio.start_server(b.handle_control_client, common.HOST, common.CONTROL_PORTS[index])
    async with data, ctrl:
        await asyncio.gather(data.serve_forever(), ctrl.serve_forever())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, required=True)
    args = ap.parse_args()
    try:
        asyncio.run(main(args.index))
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"backend {args.index}: {exc}", file=sys.stderr)
        sys.exit(2)
