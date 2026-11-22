"""Shared configuration, cost model and Windows timer fixes.

Experiment parameters (server profiles, application classes, cost weights, workload and drift
scenario) are all defined here.
"""
from __future__ import annotations

import asyncio
import math
import sys
import time

HOST = "127.0.0.1"
N_SERVERS = 8
SERVER_IDS = [f"S{i + 1}" for i in range(N_SERVERS)]
DATA_PORTS = [9001 + i for i in range(N_SERVERS)]
CONTROL_PORTS = [9101 + i for i in range(N_SERVERS)]

# ---------------------------------------------------------------------------
# Server profiles ("tradeoff" set): no server is best for every application.
# ---------------------------------------------------------------------------
_PROFILE_ROWS = [
    # id    base  jitter fail    loss  capacity load_factor
    ("S1", 15.0, 1.0, 0.12, 0.00, 20, 20.0),
    ("S2", 60.0, 25.0, 0.001, 0.00, 240, 8.0),
    ("S3", 30.0, 2.0, 0.03, 0.00, 80, 10.0),
    ("S4", 35.0, 60.0, 0.02, 0.00, 90, 5.0),
    ("S5", 45.0, 1.0, 0.01, 0.00, 120, 6.0),
    ("S6", 25.0, 1.0, 0.00, 0.03, 80, 6.0),
    ("S7", 30.0, 1.0, 0.005, 0.00, 20, 20.0),
    ("S8", 90.0, 2.0, 0.001, 0.00, 240, 6.0),
]

# ---------------------------------------------------------------------------
# Application SLA profiles.
# ---------------------------------------------------------------------------
APPS = ["gaming", "banking", "streaming", "browsing"]
APP_MAX_LATENCY_MS = {"gaming": 60.0, "banking": 120.0, "streaming": 80.0, "browsing": 500.0}
APP_MIN_SUCCESS = {"gaming": 0.99, "banking": 0.9995, "streaming": 0.99, "browsing": 0.95}
APP_PAYLOAD_BYTES = {"gaming": 128, "banking": 512, "streaming": 4096, "browsing": 216}

# ===========================================================================
# Cost model, workload and drift parameters.
# ===========================================================================
# Cost weights of eq. 3: (w_fail, w_lat, lat_ref_ms)
# Gaming trades occasional failures for speed; banking is dominated by the failure term.
COST_WEIGHTS = {
    "gaming": (0.4, 0.6, 60.0),
    "banking": (5.0, 0.05, 120.0),
    "streaming": (0.8, 0.2, 80.0),
    "browsing": (0.3, 0.1, 500.0),
}
# Alternative weight sets for the sensitivity analysis (run_experiment.py --weights NAME).
# "base" is the set above. The others shift emphasis towards failures or towards latency.
WEIGHT_SETS = {
    "base": dict(COST_WEIGHTS),
    "reliability": {
        "gaming": (1.0, 0.5, 60.0),
        "banking": (10.0, 0.05, 120.0),
        "streaming": (1.5, 0.2, 80.0),
        "browsing": (0.5, 0.1, 500.0),
    },
    "latency": {
        "gaming": (0.2, 0.8, 60.0),
        "banking": (2.0, 0.2, 120.0),
        "streaming": (0.4, 0.4, 80.0),
        "browsing": (0.1, 0.3, 500.0),
    },
}


def use_weight_set(name: str) -> None:
    """Switch the cost weights in place (call before any policy is created)."""
    COST_WEIGHTS.clear()
    COST_WEIGHTS.update(WEIGHT_SETS[name])


# Application mix (probabilities, same order as APPS)
APP_MIX = {"gaming": 0.25, "banking": 0.25, "streaming": 0.25, "browsing": 0.25}
# How long a server holds a "lost" request before dropping it without reply (ms).
LOSS_HOLD_MS = 2000.0
# Drift scenario: S7 degrades permanently at request 200.
DRIFT_SERVER = 6  # index of S7
DRIFT_INDEX = 200
DRIFT_CONFIG = {"base_latency_ms": 150.0, "failure_prob": 0.30}
DRIFT_RATE = 100.0
# ===========================================================================

CLIENT_TIMEOUT_S = 1.5
COOLDOWN_S = 1.0


def default_server_config(index: int) -> dict:
    sid, base, jit, fail, loss, cap, lf = _PROFILE_ROWS[index]
    return {
        "server_id": sid,
        "base_latency_ms": base,
        "jitter": jit,
        "failure_prob": fail,
        "packet_loss_prob": loss,
        "capacity": cap,
        "load_factor": lf,
        "timeout_ms": LOSS_HOLD_MS,
    }


def server_seed(seed: int, index: int) -> int:
    """Per-server RNG seed derived from the run seed."""
    return seed * 1000 + index + 1


def request_cost(app: str, latency_ms: float, failed: bool) -> float:
    """Eq. 3: c = w_fail*f + w_lat*min(1, latency/lat_ref)."""
    w_fail, w_lat, lat_ref = COST_WEIGHTS[app]
    return w_fail * (1.0 if failed else 0.0) + w_lat * min(1.0, latency_ms / lat_ref)


def sla_violation(app: str, latency_ms: float, failed: bool) -> bool:
    return bool(failed or latency_ms > APP_MAX_LATENCY_MS[app])


# ---------------------------------------------------------------------------
# Windows high-resolution timing fix. Call at the start of every async main.
# ---------------------------------------------------------------------------
def _disable_power_throttling() -> None:
    """Windows 11 ignores timeBeginPeriod for processes without a visible window
    after a few seconds (power throttling), silently returning to 15.6 ms ticks.
    Opt out: PROCESS_POWER_THROTTLING_EXECUTION_SPEED | IGNORE_TIMER_RESOLUTION, state 0."""
    import ctypes

    class _State(ctypes.Structure):
        _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]

    st = _State(1, 0x1 | 0x4, 0)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    ok = k32.SetProcessInformation(ctypes.c_void_p(k32.GetCurrentProcess()), 4,  # ProcessPowerThrottling
                                   ctypes.byref(st), ctypes.sizeof(st))
    if not ok:
        print("warning: SetProcessInformation(ProcessPowerThrottling) failed", file=sys.stderr)


def enable_hires_timer() -> None:
    loop = asyncio.get_running_loop()
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.winmm.timeBeginPeriod(1)
        _disable_power_throttling()
    loop.time = time.perf_counter  # type: ignore[method-assign]
    loop._clock_resolution = 1e-6  # type: ignore[attr-defined]


async def measure_sleep_accuracy(targets_ms=(15, 30, 45), reps: int = 20) -> dict:
    """Measure actual asyncio.sleep durations (perf_counter) for each target."""
    out = {}
    for t in targets_ms:
        vals = []
        for _ in range(reps):
            s = time.perf_counter()
            await asyncio.sleep(t / 1000.0)
            vals.append((time.perf_counter() - s) * 1000.0)
        vals.sort()
        out[str(t)] = {
            "mean": sum(vals) / len(vals),
            "min": vals[0],
            "max": vals[-1],
            "median": vals[len(vals) // 2],
        }
    return out


def install_quiet_exception_handler() -> None:
    """Suppress noisy ConnectionResetError logs from proactor transports."""
    loop = asyncio.get_running_loop()
    default = loop.default_exception_handler

    def handler(lp, context):
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        default(context)

    loop.set_exception_handler(handler)


def expected_cost_zero_load(app: str, cfg: dict, grid: int = 20001) -> float:
    """Expected per-request cost of `app` on a server with config `cfg` at zero load.

    'Zero load' here means only the request itself is active (load = 1/capacity),
    which is what the server code computes for an isolated request.
    A lost packet is a client timeout: f = 1, latency term capped at 1.
    """
    w_fail, w_lat, lat_ref = COST_WEIGHTS[app]
    base = cfg["base_latency_ms"] + cfg["load_factor"] * (1.0 / cfg["capacity"])
    j = cfg["jitter"]
    if j > 0:
        # midpoint rule over uniform(-j, j)
        step = 2 * j / grid
        acc = 0.0
        for k in range(grid):
            lat = max(0.0, base - j + (k + 0.5) * step)
            acc += min(1.0, lat / lat_ref)
        e_lat_term = acc / grid
    else:
        e_lat_term = min(1.0, max(0.0, base) / lat_ref)
    q = cfg["packet_loss_prob"]
    fp = cfg["failure_prob"]
    replied = fp * w_fail + w_lat * e_lat_term
    lost = w_fail + w_lat * min(1.0, CLIENT_TIMEOUT_S * 1000.0 / lat_ref)
    return (1 - q) * replied + q * lost


def fmt(x, nd=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x:.{nd}f}"
