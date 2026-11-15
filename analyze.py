"""Analyse results/{smoke,static,drift}.csv -> results/summary.md (and stdout).

numpy + csv only. Works on partial data: missing files, strategies, seeds are skipped.
All metrics are computed per seed first, then averaged across seeds; CIs are 95%
percentile bootstrap intervals over seeds (10,000 resamples, fixed RNG seed).
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

import numpy as np

import common

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
N_BOOT = 10_000
BOOT_SEED = 12345

STRAT_ORDER = [
    "random", "round_robin", "lowest_latency", "p2c_cost", "arms_app_ts", "shared_cost_ts_fast",
    "softmax_cost", "softmax_cost_global", "oracle_blind", "oracle_per_app",
]
PAPER_T91 = {
    "random": (0.2043, 0.2111),
    "p2c_cost": (0.1898, 0.1896),
    "arms_app_ts": (0.1807, 0.1625),
    "shared_cost_ts_fast": (0.1277, 0.1356),
    "softmax_cost": (0.1453, 0.1495),
    "softmax_cost_global": (0.1676, 0.1699),
    "oracle_blind": (0.1845, 0.1870),
    "oracle_per_app": (0.0959, 0.1032),
}
PAIRS = [
    ("softmax_cost_global", "softmax_cost"),
    ("oracle_blind", "oracle_per_app"),
    ("p2c_cost", "shared_cost_ts_fast"),
    ("random", "shared_cost_ts_fast"),
    ("arms_app_ts", "shared_cost_ts_fast"),
]


def load(path):
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["rate"] = float(r["rate"])
            r["seed"] = int(r["seed"])
            r["idx"] = int(r["idx"])
            r["latency_ms"] = float(r["latency_ms"])
            r["ok"] = int(r["ok"])
            r["cost"] = float(r["cost"])
            r["sla_violation"] = int(r["sla_violation"])
            r["overhead_ms"] = float(r["overhead_ms"])
            rows.append(r)
    return rows


def boot_ci(vals, n_boot=N_BOOT, seed=BOOT_SEED):
    v = np.asarray(vals, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return (float("nan"), float("nan"), float("nan"))
    if len(v) == 1:
        return (float(v[0]), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    means = v[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return (float(v.mean()), float(lo), float(hi))


def f4(x):
    return "n/a" if x is None or np.isnan(x) else f"{x:.4f}"


def f2(x):
    return "n/a" if x is None or np.isnan(x) else f"{x:.2f}"


def ci_str(m, lo, hi, fmt=f4):
    if np.isnan(lo):
        return f"{fmt(m)}"
    return f"{fmt(m)} [{fmt(lo)}, {fmt(hi)}]"


def order_strats(strats):
    known = [s for s in STRAT_ORDER if s in strats]
    return known + sorted(s for s in strats if s not in STRAT_ORDER)


def group(rows, *keys):
    g = defaultdict(list)
    for r in rows:
        g[tuple(r[k] for k in keys)].append(r)
    return g


def seed_metrics(rs):
    cost = np.array([r["cost"] for r in rs])
    ok = np.array([r["ok"] for r in rs], dtype=bool)
    lat_ok = np.array([r["latency_ms"] for r in rs if r["ok"]])
    return {
        "cost": cost.mean(),
        "sla": np.mean([r["sla_violation"] for r in rs]),
        "fail": 1.0 - ok.mean(),
        "lat_mean": lat_ok.mean() if len(lat_ok) else np.nan,
        "lat_p95": np.percentile(lat_ok, 95) if len(lat_ok) else np.nan,
        "jitter": lat_ok.std(ddof=1) if len(lat_ok) > 1 else np.nan,
        "overhead": np.mean([r["overhead_ms"] for r in rs]),
    }


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def static_section(rows, title):
    md = [f"## {title}", ""]
    rates = sorted({r["rate"] for r in rows})
    strats = order_strats({r["strategy"] for r in rows})
    by = group(rows, "rate", "strategy", "seed")
    seeds_all = sorted({r["seed"] for r in rows})
    md.append(f"Rows: {len(rows)}; seeds: {seeds_all}; rates: {rates}")
    for rate in rates:
        lag = [float(r["dispatch_lag_ms"]) for r in rows if r["rate"] == rate and r.get("dispatch_lag_ms")]
        if lag:
            p = np.percentile(lag, [50, 99, 100])
            md.append(f"\nDispatch lag vs. schedule at {rate:g} req/s (timing health): p50 {p[0]:.2f} ms, "
                      f"p99 {p[1]:.2f} ms, max {p[2]:.2f} ms")
    md.append("")

    per_seed = {}  # (rate, strat) -> {seed: metrics}
    for (rate, st, seed), rs in by.items():
        per_seed.setdefault((rate, st), {})[seed] = seed_metrics(rs)

    for rate in rates:
        md.append(f"### Overall metrics at {rate:g} req/s (mean across seeds)")
        md.append("")
        body = []
        for st in strats:
            d = per_seed.get((rate, st))
            if not d:
                continue
            seeds = sorted(d)
            m = lambda k: float(np.nanmean([d[s][k] for s in seeds]))  # noqa: E731
            mc, lo, hi = boot_ci([d[s]["cost"] for s in seeds])
            body.append([
                st, len(seeds), ci_str(mc, lo, hi), f4(m("sla")), f4(m("fail")), f2(m("lat_mean")),
                f2(m("lat_p95")), f2(m("jitter")), f"{m('overhead'):.4f}",
            ])
        md.append(table(["strategy", "seeds", "mean cost [95% CI]", "SLA viol", "fail rate",
                         "mean lat ok (ms)", "p95 lat ok (ms)", "jitter (ms)", "overhead (ms)"], body))
        md.append("")

    # per-app cost
    for rate in rates:
        md.append(f"### Per-application mean cost at {rate:g} req/s (per-seed mean, averaged over seeds)")
        md.append("")
        body = []
        for st in strats:
            sub = [r for r in rows if r["rate"] == rate and r["strategy"] == st]
            if not sub:
                continue
            row = [st]
            for app in common.APPS:
                bs = group([r for r in sub if r["app"] == app], "seed")
                vals = [np.mean([r["cost"] for r in v]) for v in bs.values()]
                row.append(f4(float(np.mean(vals))) if vals else "n/a")
            body.append(row)
        md.append(table(["strategy"] + common.APPS, body))
        md.append("")

    # server share
    for rate in rates:
        md.append(f"### Server share at {rate:g} req/s (fraction of requests)")
        md.append("")
        body = []
        for st in strats:
            sub = [r for r in rows if r["rate"] == rate and r["strategy"] == st]
            if not sub:
                continue
            cnt = defaultdict(int)
            for r in sub:
                cnt[r["server"]] += 1
            body.append([st] + [f"{cnt[s] / len(sub):.3f}" for s in common.SERVER_IDS])
        md.append(table(["strategy"] + common.SERVER_IDS, body))
        md.append("")

    # paired differences
    for rate in rates:
        md.append(f"### Paired per-seed cost differences at {rate:g} req/s (A - B; >0 means B is cheaper)")
        md.append("")
        body = []
        for a, b in PAIRS:
            da, db = per_seed.get((rate, a)), per_seed.get((rate, b))
            if not da or not db:
                body.append([f"{a} - {b}", 0, "n/a"])
                continue
            common_seeds = sorted(set(da) & set(db))
            diffs = [da[s]["cost"] - db[s]["cost"] for s in common_seeds]
            m, lo, hi = boot_ci(diffs)
            body.append([f"{a} - {b}", len(common_seeds), ci_str(m, lo, hi)])
        md.append(table(["difference", "paired seeds", "mean diff [95% CI]"], body))
        md.append("")

    # paper comparison
    md.append("### Mean cost vs. paper Table 9.1")
    md.append("")
    body = []
    for st in strats:
        row = [st]
        for i, rate in enumerate([50.0, 150.0]):
            d = per_seed.get((rate, st))
            ours = f4(float(np.mean([v["cost"] for v in d.values()]))) if d else "n/a"
            paper = f"{PAPER_T91[st][i]:.4f}" if st in PAPER_T91 else "-"
            row += [ours, paper]
        body.append(row)
    md.append(table(["strategy", "ours 50", "paper 50", "ours 150", "paper 150"], body))
    md.append("")

    # error counts
    md.append("### Error counts per strategy and rate (all seeds)")
    md.append("")
    errs = sorted({r["error"] for r in rows if r["error"]})
    body = []
    for rate in rates:
        for st in strats:
            sub = [r for r in rows if r["strategy"] == st and r["rate"] == rate]
            if sub:
                body.append([f"{rate:g}", st, len(sub)] + [sum(1 for r in sub if r["error"] == e) for e in errs])
    md.append(table(["rate", "strategy", "requests"] + errs, body))
    md.append("")

    # per-server latency under random (sanity check of the testbed)
    for rate in rates:
      sub = [r for r in rows if r["strategy"] == "random" and r["rate"] == rate]
      if sub:
        md.append(f"### Testbed check at {rate:g} req/s: measured latency per server under `random` (successful requests)")
        md.append("")
        body = []
        for i, sid in enumerate(common.SERVER_IDS):
            cfg = common.default_server_config(i)
            lats = np.array([r["latency_ms"] for r in sub if r["server"] == sid and r["ok"]])
            nall = sum(1 for r in sub if r["server"] == sid)
            fails = sum(1 for r in sub if r["server"] == sid and not r["ok"])
            body.append([
                sid, f"{cfg['base_latency_ms']:g}", f"{cfg['jitter']:g}", nall,
                f2(lats.mean()) if len(lats) else "n/a",
                f2(lats.mean() - cfg["base_latency_ms"]) if len(lats) else "n/a",
                f2(np.median(lats)) if len(lats) else "n/a",
                f"{fails / nall:.3f}" if nall else "n/a",
                f"{cfg['failure_prob'] + cfg['packet_loss_prob']:.3f}",
            ])
        md.append(table(["server", "base ms", "jitter ms", "n", "mean lat ok", "mean - base",
                         "median", "fail rate", "configured fail+loss"], body))
        md.append("")
    return "\n".join(md)


def drift_section(rows):
    md = ["## Drift", ""]
    drift_idx = int(rows[0]["drift_idx"]) if rows[0]["drift_idx"] else common.ASSUMED_DRIFT_INDEX
    target = common.SERVER_IDS[common.ASSUMED_DRIFT_SERVER]
    win, thr, pre_win, post_win = 50, 0.05, 100, 100
    md.append(
        f"Drift at idx {drift_idx} on {target} (config {common.ASSUMED_DRIFT_CONFIG}, no restore). "
        f"A seed is eligible if {target}'s share in [drift-{pre_win}, drift) > {thr}. For eligible seeds, "
        f"adaptation time = smallest j>=0 with {target} share in [drift+j, drift+j+{win}) <= {thr}; "
        f"censored if never reached. Mean and 95% bootstrap CI over uncensored eligible seeds."
    )
    md.append("")
    strats = order_strats({r["strategy"] for r in rows})
    body, body_cost = [], []
    for st in strats:
        by_seed = group([r for r in rows if r["strategy"] == st], "seed")
        pre_share, post_share, adapt = [], [], []
        c_pre, c_post1, c_post2 = [], [], []
        eligible = censored = ineligible = 0
        for (seed,), rs in by_seed.items():
            rs = sorted(rs, key=lambda r: r["idx"])
            pre = [r for r in rs if drift_idx - pre_win <= r["idx"] < drift_idx]
            post = [r for r in rs if r["idx"] >= drift_idx]
            p1 = [r for r in rs if drift_idx <= r["idx"] < drift_idx + post_win]
            p2 = [r for r in rs if r["idx"] >= drift_idx + post_win]
            ps = float(np.mean([r["server"] == target for r in pre])) if pre else np.nan
            pre_share.append(ps)
            post_share.append(np.mean([r["server"] == target for r in post]) if post else np.nan)
            c_pre.append(np.mean([r["cost"] for r in pre]) if pre else np.nan)
            c_post1.append(np.mean([r["cost"] for r in p1]) if p1 else np.nan)
            c_post2.append(np.mean([r["cost"] for r in p2]) if p2 else np.nan)
            if not (ps > thr):
                ineligible += 1
                continue
            eligible += 1
            on = np.array([r["server"] == target for r in post], dtype=float)
            found = None
            for j in range(0, len(on) - win + 1):
                if on[j:j + win].mean() <= thr:
                    found = j
                    break
            if found is None:
                censored += 1
            else:
                adapt.append(found)
        m, lo, hi = boot_ci(adapt)
        body.append([st, len(by_seed), f4(float(np.nanmean(pre_share))), f4(float(np.nanmean(post_share))),
                     eligible, ci_str(m, lo, hi, f2) if adapt else "n/a", len(adapt), censored, ineligible])
        cis = [boot_ci(v) for v in (c_pre, c_post1, c_post2)]
        body_cost.append([st] + [ci_str(*c) for c in cis])
    md.append(table(["strategy", "seeds", f"{target} share [d-{pre_win}, d)", f"{target} share [d, end)",
                     "eligible seeds", "adaptation (requests) [95% CI]", "uncensored", "censored",
                     "ineligible"], body))
    md.append("")
    md.append(f"### Drift: mean cost by window (mean across seeds [95% CI])")
    md.append("")
    md.append(table(["strategy", f"[d-{pre_win}, d)", f"[d, d+{post_win})", f"[d+{post_win}, end)"], body_cost))
    md.append("")
    return "\n".join(md)


def repeat_section(rows):
    md = ["## Repeatability (same seed, repeated runs)", ""]
    seeds = sorted({r["seed"] for r in rows})
    rates = sorted({r["rate"] for r in rows})
    md.append(f"Seed(s) {seeds}, rate(s) {rates}. Mean cost of each repetition, and the std (ddof=1) across repetitions.")
    md.append("")
    reps = sorted({int(r.get("rep") or 0) for r in rows})
    body = []
    for st in order_strats({r["strategy"] for r in rows}):
        g = group([r for r in rows if r["strategy"] == st], "rep")
        vals = []
        row = [st]
        for rp in reps:
            rs = g.get((str(rp),)) or g.get((rp,))
            if rs:
                v = float(np.mean([r["cost"] for r in rs]))
                vals.append(v)
                row.append(f4(v))
            else:
                row.append("n/a")
        row += [f4(float(np.mean(vals))) if vals else "n/a",
                f4(float(np.std(vals, ddof=1))) if len(vals) > 1 else "n/a"]
        body.append(row)
    md.append(table(["strategy"] + [f"rep {r}" for r in reps] + ["mean", "std"], body))
    md.append("")
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=RESULTS)
    args = ap.parse_args()
    parts = ["# Reimplementation results summary", ""]
    any_data = False
    for name, title in [("smoke", "Smoke test"), ("static", "Static experiment")]:
        rows = load(os.path.join(args.results, f"{name}.csv"))
        if rows:
            any_data = True
            parts.append(static_section(rows, title))
    rows = load(os.path.join(args.results, "drift.csv"))
    if rows:
        any_data = True
        parts.append(drift_section(rows))
    rows = load(os.path.join(args.results, "repeat.csv"))
    if rows:
        any_data = True
        parts.append(repeat_section(rows))
    if not any_data:
        parts.append("No result CSVs found.")
    md = "\n".join(parts)
    with open(os.path.join(args.results, "summary.md"), "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
