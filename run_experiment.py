"""Experiment runner.

python run_experiment.py --mode {smoke,static,drift} [--seeds 501-512] [--rates 50,150]
                         [--n 600] [--strategies a,b,c] [--append]

Starts 8 backend processes, waits for their control ports, runs every
(rate, seed, strategy) combination, writes one CSV row per request, and always
terminates the servers on exit.

Output files (results/):
  smoke -> smoke.csv (overwritten), static -> static.csv, drift -> drift.csv.
  For static/drift an existing CSV is moved to results/old/ unless --append is given.
  run_order.csv is always appended (one row per run, with a session id).
"""
from __future__ import annotations

import argparse
import asyncio
import atexit
import csv
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime

import common
from client import control, make_payload, send_request
from policies import STRATEGIES

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")

ALL_STRATEGIES = list(STRATEGIES.keys())
DRIFT_STRATEGIES = ["random", "p2c_cost", "arms_app_ts", "softmax_cost", "shared_cost_ts_fast"]
REPEAT_STRATEGIES = ["random", "p2c_cost", "shared_cost_ts_fast", "softmax_cost"]

FIELDS = [
    "mode", "rate", "seed", "strategy", "idx", "app", "server", "latency_ms", "ok", "error",
    "cost", "sla_violation", "server_load", "overhead_ms", "drift_idx", "explain", "dispatch_lag_ms", "rep",
]


def parse_seeds(text: str) -> list[int]:
    out = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


# ---------------------------------------------------------------------------
# Server process management
# ---------------------------------------------------------------------------
def check_ports_free() -> None:
    busy = []
    for port in common.DATA_PORTS + common.CONTROL_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((common.HOST, port))
        except OSError:
            busy.append(port)
        finally:
            s.close()
    if busy:
        raise SystemExit(f"ERROR: port(s) already in use: {busy}. Stop the process holding them and retry.")


_ALL_PROCS: list[subprocess.Popen] = []
atexit.register(lambda: stop_servers(_ALL_PROCS))


def start_servers() -> list[subprocess.Popen]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    procs = []
    for i in range(common.N_SERVERS):
        procs.append(
            subprocess.Popen(
                [sys.executable, os.path.join(HERE, "backend.py"), "--index", str(i)],
                cwd=HERE,
                creationflags=flags,
            )
        )
    _ALL_PROCS.extend(procs)
    return procs


def stop_servers(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    deadline = time.time() + 5
    for p in procs:
        try:
            p.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


async def wait_for_servers(procs, timeout_s: float = 15.0) -> None:
    deadline = time.perf_counter() + timeout_s
    pending = set(range(common.N_SERVERS))
    while pending:
        for i, p in enumerate(procs):
            if p.poll() is not None:
                raise RuntimeError(f"server {common.SERVER_IDS[i]} exited early with code {p.returncode}")
        for i in list(pending):
            try:
                r = await control(common.HOST, common.CONTROL_PORTS[i], {"cmd": "ping"}, timeout_s=1.0)
                if r.get("ok"):
                    pending.discard(i)
            except (OSError, TimeoutError, ConnectionError):
                pass
        if pending:
            if time.perf_counter() > deadline:
                raise RuntimeError(f"servers not ready: {[common.SERVER_IDS[i] for i in pending]}")
            await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------
def app_sequence(seed: int, n: int) -> list[str]:
    rng = random.Random(f"apps-{seed}")
    apps = common.APPS
    weights = [common.ASSUMED_APP_MIX[a] for a in apps]
    return rng.choices(apps, weights=weights, k=n)


async def run_one(mode: str, rate: float, seed: int, strategy: str, n: int, drift: bool, rep: int = 0) -> list[dict]:
    # reset all servers: original config + seeded RNG
    for i in range(common.N_SERVERS):
        r = await control(common.HOST, common.CONTROL_PORTS[i], {"cmd": "reset", "seed": seed})
        if not r.get("ok"):
            raise RuntimeError(f"reset failed on {common.SERVER_IDS[i]}: {r}")
        if r.get("active", 0):
            print(f"  warning: {common.SERVER_IDS[i]} still has {r['active']} active connections at reset")

    policy = STRATEGIES[strategy](seed)
    apps = app_sequence(seed, n)
    rows: list[dict] = [None] * n  # type: ignore[list-item]
    interval = 1.0 / rate
    drift_idx = common.ASSUMED_DRIFT_INDEX if drift else None
    perf = time.perf_counter

    async def do_request(idx: int, app: str, s: int, info, sel_ms: float, lag_ms: float) -> None:
        payload = make_payload(idx, app, common.APP_PAYLOAD_BYTES[app])
        res = await send_request(common.HOST, common.DATA_PORTS[s], payload, common.CLIENT_TIMEOUT_S)
        failed = not res["ok"]
        lat = res["latency_ms"]
        cost = common.request_cost(app, lat, failed)
        t0 = perf()
        policy.update(app, s, lat, res["ok"], cost)
        upd_ms = (perf() - t0) * 1000.0
        rows[idx] = {
            "mode": mode,
            "rate": rate,
            "seed": seed,
            "strategy": strategy,
            "idx": idx,
            "app": app,
            "server": common.SERVER_IDS[s],
            "latency_ms": round(lat, 4),
            "ok": int(res["ok"]),
            "error": res["error"] or "",
            "cost": round(cost, 6),
            "sla_violation": int(common.sla_violation(app, lat, failed)),
            "server_load": "" if res["server_load"] is None else res["server_load"],
            "overhead_ms": round(sel_ms + upd_ms, 5),
            "drift_idx": "" if drift_idx is None else drift_idx,
            "explain": policy.explain(app, s, info),  # built outside the timed section
            "dispatch_lag_ms": round(lag_ms, 3),
            "rep": rep,
        }
        if res.get("detail"):
            rows[idx]["explain"] = (rows[idx]["explain"] + " | " + res["detail"]).strip(" |")

    tasks = []
    start = perf() + 0.05
    for idx in range(n):
        target = start + idx * interval
        delay = target - perf()
        if delay > 0:
            await asyncio.sleep(delay)
        if drift_idx is not None and idx == drift_idx:
            i = common.ASSUMED_DRIFT_SERVER
            r = await control(common.HOST, common.CONTROL_PORTS[i], {"cmd": "set", "config": common.ASSUMED_DRIFT_CONFIG})
            if not r.get("ok"):
                raise RuntimeError(f"drift set failed: {r}")
        lag_ms = (perf() - target) * 1000.0
        app = apps[idx]
        t0 = perf()
        s, info = policy.select(app)
        sel_ms = (perf() - t0) * 1000.0
        tasks.append(asyncio.create_task(do_request(idx, app, s, info, sel_ms, lag_ms)))
    await asyncio.gather(*tasks)
    return rows


# ---------------------------------------------------------------------------
async def sleep_check(procs) -> dict:
    # client and all servers measured concurrently (separate processes)
    replies = await asyncio.gather(
        common.measure_sleep_accuracy(),
        *[control(common.HOST, common.CONTROL_PORTS[i], {"cmd": "sleeptest"}, timeout_s=15)
          for i in range(common.N_SERVERS)],
    )
    out = {"client": replies[0]}
    for i, r in enumerate(replies[1:]):
        out[common.SERVER_IDS[i]] = r["sleep"]
    return out


def print_sleep_check(res: dict) -> bool:
    print("Sleep accuracy (asyncio.sleep measured with perf_counter, 20 reps each), ms:")
    print(f"{'process':8} {'target':>6} {'mean':>8} {'median':>8} {'min':>8} {'max':>8}")
    good = True
    for proc, d in res.items():
        for t, v in d.items():
            print(f"{proc:8} {t:>6} {v['mean']:8.3f} {v['median']:8.3f} {v['min']:8.3f} {v['max']:8.3f}")
            if abs(v["mean"] - float(t)) > 2.0:
                good = False
    print("sleep accuracy within 2 ms (mean):", good)
    return good


async def amain(args) -> None:
    common.enable_hires_timer()
    common.install_quiet_exception_handler()
    procs = start_servers()
    try:
        await wait_for_servers(procs)
        print(f"all {common.N_SERVERS} servers ready", flush=True)

        sleep_results = {"before": await sleep_check(procs)}
        print("[before runs]")
        print_sleep_check(sleep_results["before"])
        session = datetime.now().strftime("%Y%m%d-%H%M%S")
        sleep_path = os.path.join(RESULTS, f"sleep_check_{args.mode}_{session}.json")
        with open(sleep_path, "w") as f:  # saved now, so it survives an interrupted session
            json.dump(sleep_results, f, indent=1)

        csv_path = os.path.join(RESULTS, f"{args.mode}.csv")
        new_file = not os.path.exists(csv_path)
        order_path = os.path.join(RESULTS, "run_order.csv")
        order_new = not os.path.exists(order_path)

        runs = []
        ns = len(args.strategies)
        for rate in args.rates:
            for k, seed in enumerate(args.seeds):
                for rep in range(args.reps):
                    # rotate strategy order per seed/repetition so no strategy always runs first/last
                    r = (k + rep) % ns
                    for st in args.strategies[r:] + args.strategies[:r]:
                        runs.append((rate, seed, st, rep))
        print(f"{len(runs)} runs planned", flush=True)

        with open(csv_path, "a", newline="", encoding="utf-8") as fcsv, open(
            order_path, "a", newline="", encoding="utf-8"
        ) as ford:
            w = csv.DictWriter(fcsv, fieldnames=FIELDS)
            wo = csv.writer(ford)
            if new_file:
                w.writeheader()
            if order_new:
                wo.writerow(["session", "order", "mode", "rate", "seed", "strategy", "start_time", "mean_cost", "n_rows", "rep"])
            for order, (rate, seed, st, rep) in enumerate(runs):
                t_start = datetime.now().isoformat(timespec="milliseconds")
                rows = await run_one(args.mode, rate, seed, st, args.n, drift=(args.mode == "drift"), rep=rep)
                w.writerows(rows)
                fcsv.flush()
                mc = sum(r["cost"] for r in rows) / len(rows)
                errs = {}
                for r in rows:
                    if r["error"]:
                        errs[r["error"]] = errs.get(r["error"], 0) + 1
                maxlag = max(r["dispatch_lag_ms"] for r in rows)
                wo.writerow([session, order, args.mode, rate, seed, st, t_start, round(mc, 6), len(rows), rep])
                ford.flush()
                print(
                    f"[{order + 1}/{len(runs)}] mode={args.mode} rate={rate:g} seed={seed} rep={rep} {st:22s} "
                    f"mean_cost={mc:.4f} errors={errs} max_dispatch_lag_ms={maxlag:.1f}",
                    flush=True,
                )
                await asyncio.sleep(common.COOLDOWN_S)
        sleep_results["after"] = await sleep_check(procs)
        print("[after runs]")
        print_sleep_check(sleep_results["after"])
        with open(sleep_path, "w") as f:
            json.dump(sleep_results, f, indent=1)
    finally:
        stop_servers(procs)
        print("servers stopped", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["smoke", "static", "drift", "repeat"], required=True)
    ap.add_argument("--seeds")
    ap.add_argument("--rates")
    ap.add_argument("--n", type=int)
    ap.add_argument("--strategies")
    ap.add_argument("--reps", type=int, help="repetitions per (rate, seed, strategy); default 5 for repeat, else 1")
    ap.add_argument("--append", action="store_true", help="append to an existing static/drift CSV")
    args = ap.parse_args()

    defaults = {
        "smoke": ("501-502", "50", 200, ALL_STRATEGIES),
        "static": ("501-512", "50,150", 600, ALL_STRATEGIES),
        "drift": ("501-512", str(common.ASSUMED_DRIFT_RATE), 600, DRIFT_STRATEGIES),
        "repeat": ("501", "50", 600, REPEAT_STRATEGIES),
    }[args.mode]
    args.reps = args.reps or (5 if args.mode == "repeat" else 1)
    args.seeds = parse_seeds(args.seeds or defaults[0])
    args.rates = [float(x) for x in (args.rates or defaults[1]).split(",")]
    args.n = args.n or defaults[2]
    args.strategies = args.strategies.split(",") if args.strategies else list(defaults[3])
    for s in args.strategies:
        if s not in STRATEGIES:
            raise SystemExit(f"unknown strategy {s}; known: {ALL_STRATEGIES}")
    if args.mode == "drift" and args.n <= common.ASSUMED_DRIFT_INDEX:
        raise SystemExit("drift mode needs --n > drift index")

    check_ports_free()  # before touching any result file
    os.makedirs(RESULTS, exist_ok=True)
    csv_path = os.path.join(RESULTS, f"{args.mode}.csv")
    if os.path.exists(csv_path):
        if args.mode == "smoke":
            os.remove(csv_path)
        elif not args.append:
            old = os.path.join(RESULTS, "old")
            os.makedirs(old, exist_ok=True)
            dst = os.path.join(old, f"{args.mode}.{datetime.now():%Y%m%d-%H%M%S}.csv")
            shutil.move(csv_path, dst)
            print(f"moved existing {csv_path} -> {dst}")

    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
