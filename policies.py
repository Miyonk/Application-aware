"""Selection strategies.

Interface: select(app) -> (server_index, info); update(app, server_index, latency_ms, ok, cost).
select() is called at dispatch time, update() when the response arrives, so several
requests may be in flight. Cold-start logic marks a server as tried at select time.

See README.md for each strategy's definition.
"""
from __future__ import annotations

import math
import random

import common

K = common.N_SERVERS


class Policy:
    name = "base"

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def select(self, app: str):
        raise NotImplementedError

    def update(self, app: str, s: int, latency_ms: float, ok: bool, cost: float) -> None:
        pass

    def explain(self, app: str, s: int, info) -> str:
        return ""


class RandomPolicy(Policy):
    name = "random"

    def select(self, app):
        return self.rng.randrange(K), None


class RoundRobin(Policy):
    name = "round_robin"

    def __init__(self, seed):
        super().__init__(seed)
        self.i = 0

    def select(self, app):
        s = self.i % K
        self.i += 1
        return s, None


class LowestLatency(Policy):
    """Lowest EWMA latency (beta 0.2), untried first, app-blind.
    EWMA is fed with the client-measured latency of every request, including
    failures and timeouts (a timeout contributes ~1500 ms)."""

    name = "lowest_latency"
    beta = 0.2

    def __init__(self, seed):
        super().__init__(seed)
        self.tried = [False] * K
        self.ewma = [None] * K

    def select(self, app):
        untried = [s for s in range(K) if not self.tried[s]]
        if untried:
            s = self.rng.choice(untried)
            self.tried[s] = True
            return s, None
        known = [(self.ewma[s], s) for s in range(K) if self.ewma[s] is not None]
        if not known:  # all tried but none returned yet
            return self.rng.randrange(K), None
        best = min(v for v, _ in known)
        cands = [s for v, s in known if v == best]
        return self.rng.choice(cands), None

    def update(self, app, s, latency_ms, ok, cost):
        e = self.ewma[s]
        self.ewma[s] = latency_ms if e is None else self.beta * latency_ms + (1 - self.beta) * e


class P2CCost(Policy):
    """Power of two choices on running-mean cost per server (app-blind, untried = 0)."""

    name = "p2c_cost"

    def __init__(self, seed):
        super().__init__(seed)
        self.n = [0] * K
        self.mean = [0.0] * K

    def select(self, app):
        a, b = self.rng.sample(range(K), 2)
        return (a if self.mean[a] <= self.mean[b] else b), None

    def update(self, app, s, latency_ms, ok, cost):
        self.n[s] += 1
        self.mean[s] += (cost - self.mean[s]) / self.n[s]


class ArmsAppTS(Policy):
    """Per-(app, server) Gaussian Thompson sampling on cost, prior mean 0,
    sample ~ Normal(mean, 0.3/sqrt(n+1)), pick the minimum."""

    name = "arms_app_ts"
    v = 0.3

    def __init__(self, seed):
        super().__init__(seed)
        self.n = {a: [0] * K for a in common.APPS}
        self.mean = {a: [0.0] * K for a in common.APPS}

    def select(self, app):
        n, m, g = self.n[app], self.mean[app], self.rng.gauss
        best, bs = math.inf, 0
        for s in range(K):
            x = g(m[s], self.v / math.sqrt(n[s] + 1))
            if x < best:
                best, bs = x, s
        return bs, None

    def update(self, app, s, latency_ms, ok, cost):
        self.n[app][s] += 1
        self.mean[app][s] += (cost - self.mean[app][s]) / self.n[app][s]


class SharedCostTSFast(Policy):
    """One shared model per server (success prob + latency), app-specific cost at decision time.

    Per server: discounted success/failure counts -> Beta(1+a, 1+b);
    discounted weight / sum / sum of squares of successful-request latency.
    Discount 0.995 applied to all servers on every update.
    Selection: untried servers first; else p ~ Beta, lat ~ Normal(mean, sqrt(var/n_eff)),
    cost = w_fail*(1-p) + w_lat*min(1, lat/lat_ref); pick min.
    A server with no successful latency yet (e.g. its replies are still in flight)
    is given predicted latency = lat_ref(app), i.e. the full latency penalty.
    """

    name = "shared_cost_ts_fast"
    gamma = 0.995
    var_floor = 1.0  # ms^2, avoids zero variance from a single observation

    def __init__(self, seed):
        super().__init__(seed)
        self.tried = [False] * K
        self.a = [0.0] * K
        self.b = [0.0] * K
        self.w = [0.0] * K
        self.sx = [0.0] * K
        self.sxx = [0.0] * K

    def select(self, app):
        untried = [s for s in range(K) if not self.tried[s]]
        if untried:
            s = self.rng.choice(untried)
            self.tried[s] = True
            return s, ("explore",)
        w_fail, w_lat, lat_ref = common.COST_WEIGHTS[app]
        rng = self.rng
        best = (math.inf, -1, 0.0, 0.0)
        second = (math.inf, -1, 0.0, 0.0)
        for s in range(K):
            p = rng.betavariate(1.0 + self.a[s], 1.0 + self.b[s])
            w = self.w[s]
            if w > 1e-9:
                mu = self.sx[s] / w
                var = max(self.var_floor, self.sxx[s] / w - mu * mu)
                lat = rng.gauss(mu, math.sqrt(var / max(w, 1.0)))
            else:
                lat = lat_ref
            c = w_fail * (1.0 - p) + w_lat * min(1.0, max(0.0, lat) / lat_ref)
            cand = (c, s, p, lat)
            if c < best[0]:
                second, best = best, cand
            elif c < second[0]:
                second = cand
        return best[1], ("exploit", best, second)

    def update(self, app, s, latency_ms, ok, cost):
        g = self.gamma
        for i in range(K):
            self.a[i] *= g
            self.b[i] *= g
            self.w[i] *= g
            self.sx[i] *= g
            self.sxx[i] *= g
        if ok:
            self.a[s] += 1.0
            self.w[s] += 1.0
            self.sx[s] += latency_ms
            self.sxx[s] += latency_ms * latency_ms
        else:
            self.b[s] += 1.0

    def explain(self, app, s, info):
        if info is None or info[0] == "explore":
            return f"{app} -> {common.SERVER_IDS[s]}: exploring (no data yet)"
        _, best, second = info
        txt = (
            f"{app} -> {common.SERVER_IDS[best[1]]}: success={best[2]:.3f}, "
            f"predicted latency={best[3]:.2f} ms, cost={best[0]:.3f}"
        )
        if second[1] >= 0:
            txt += f"; runner-up={common.SERVER_IDS[second[1]]} cost={second[0]:.3f}"
        return txt


class SoftmaxCost(Policy):
    """Eq. 8 softmax over running-mean cost, tau = 0.05, eps = 0.02.
    App-aware: one estimate per (app, server); cold start tries every untried pair first.
    A pair that has been tried but has no completed response yet gets estimate 0 (optimistic)."""

    name = "softmax_cost"
    tau = 0.05
    eps = 0.02
    global_model = False

    def __init__(self, seed):
        super().__init__(seed)
        keys = ["*"] if self.global_model else common.APPS
        self.tried = {k: [False] * K for k in keys}
        self.n = {k: [0] * K for k in keys}
        self.mean = {k: [0.0] * K for k in keys}

    def _key(self, app):
        return "*" if self.global_model else app

    def select(self, app):
        k = self._key(app)
        tried = self.tried[k]
        untried = [s for s in range(K) if not tried[s]]
        if untried:
            s = self.rng.choice(untried)
            tried[s] = True
            return s, None
        m = self.mean[k]
        lo = min(m)
        ex = [math.exp(-(c - lo) / self.tau) for c in m]
        z = sum(ex)
        probs = [(1 - K * self.eps) * e / z + self.eps for e in ex]
        r = self.rng.random()
        acc = 0.0
        for s, p in enumerate(probs):
            acc += p
            if r < acc:
                return s, None
        return K - 1, None

    def update(self, app, s, latency_ms, ok, cost):
        k = self._key(app)
        self.n[k][s] += 1
        self.mean[k][s] += (cost - self.mean[k][s]) / self.n[k][s]


class SoftmaxCostGlobal(SoftmaxCost):
    name = "softmax_cost_global"
    global_model = True


def _oracle_table():
    return {
        app: [common.expected_cost_zero_load(app, common.default_server_config(s)) for s in range(K)]
        for app in common.APPS
    }


_ORACLE_CACHE = None


def oracle_table():
    global _ORACLE_CACHE
    if _ORACLE_CACHE is None:
        _ORACLE_CACHE = _oracle_table()
    return _ORACLE_CACHE


class OraclePerApp(Policy):
    """Static clairvoyant reference: each app always goes to its best server by
    expected zero-load cost computed from the true configs."""

    name = "oracle_per_app"

    def __init__(self, seed):
        super().__init__(seed)
        t = oracle_table()
        self.choice = {a: min(range(K), key=lambda s: t[a][s]) for a in common.APPS}

    def select(self, app):
        return self.choice[app], None


class OracleBlind(Policy):
    """Static clairvoyant reference: one server for all traffic, lowest mix-weighted expected cost."""

    name = "oracle_blind"

    def __init__(self, seed):
        super().__init__(seed)
        t = oracle_table()
        mix = common.APP_MIX
        self.server = min(range(K), key=lambda s: sum(mix[a] * t[a][s] for a in common.APPS))

    def select(self, app):
        return self.server, None


STRATEGIES = {
    c.name: c
    for c in [
        RandomPolicy,
        RoundRobin,
        LowestLatency,
        P2CCost,
        ArmsAppTS,
        SharedCostTSFast,
        SoftmaxCost,
        SoftmaxCostGlobal,
        OraclePerApp,
        OracleBlind,
    ]
}


if __name__ == "__main__":
    t = oracle_table()
    print("expected zero-load cost per (app, server)")
    print("app        " + " ".join(f"{s:>7}" for s in common.SERVER_IDS))
    for a in common.APPS:
        print(f"{a:10} " + " ".join(f"{v:7.4f}" for v in t[a]))
    mix = common.APP_MIX
    print("mix-wtd    " + " ".join(f"{sum(mix[a] * t[a][s] for a in common.APPS):7.4f}" for s in range(K)))
    print("oracle_per_app:", {a: common.SERVER_IDS[OraclePerApp(0).choice[a]] for a in common.APPS})
    print("oracle_blind:", common.SERVER_IDS[OracleBlind(0).server])
