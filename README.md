# Application-aware server selection on a live TCP testbed

Code and raw data for the paper *Application-Aware Server Selection with Shared-Model Thompson
Sampling: An Evaluation on a Live TCP Testbed*.

A client sends a mixed stream of gaming, banking, streaming and browsing requests to eight
asynchronous TCP backend servers with different latency, jitter, reliability and capacity profiles.
Ten selection policies are compared on mean cost, SLA violations, tail latency, adaptation to an
injected degradation, and decision overhead. Python standard library plus NumPy only.

## Files
- `common.py`: server profiles, application SLA profiles and cost weights, cost function, SLA check,
  workload and drift parameters, cost-weight sets for the sensitivity analysis, Windows timer fix,
  and the analytic zero-load expected cost used by the static oracles.
- `backend.py`: one backend server process (data ports 9001-9008, control ports 9101-9108).
- `client.py`: request client (one TCP connection per request) and control-port helper.
- `policies.py`: the ten selection strategies. `python policies.py` prints the expected-cost table
  and the static oracles' choices.
- `run_experiment.py`: experiment runner.
- `analyze.py`: computes all metrics and writes `results/summary.md`.
- `results/`: raw per-request CSVs, run order, per-session timing checks and logs.

## Usage
```
python run_experiment.py --mode smoke     # seeds 501-502, 50 req/s, 200 requests, all strategies
python run_experiment.py --mode static    # seeds 501-512, 50 and 150 req/s, 600 requests, all strategies
python run_experiment.py --mode drift     # seeds 501-512, 100 req/s, 600 requests, 5 strategies
python run_experiment.py --mode repeat    # seed 501 five times, 50 req/s, 4 strategies
python run_experiment.py --mode static --weights reliability --rates 50 --seeds 501-506
python analyze.py
```
Options: `--seeds`, `--rates`, `--n`, `--strategies a,b`, `--reps`, `--weights base|reliability|latency`,
`--append`. Each mode writes `results/<mode>.csv` (one row per request; non-base weight sets write
`results/static_w-<name>.csv`), appends to `results/run_order.csv`, and saves a sleep-accuracy check
for every process before and after the session as `results/sleep_check_<mode>_<session>.json`.
An existing static/drift CSV is moved to `results/old/` unless `--append` is given.

## Testbed
**Servers.** Each server is its own process running an asyncio TCP server. On a request it computes
load = active connections / capacity and a delay of max(0, base + U(-jitter, jitter) +
load_factor * load). With the packet-loss probability it never replies (the client times out after
1.5 s); otherwise it replies after the delay, reporting failure with the failure probability. The
control port accepts `{"cmd": "set", "config": {...}}` to change parameters at run time and
`{"cmd": "reset", "seed": N}` to restore the profile and reseed the server.

| Server | Role | Base (ms) | Jitter (ms) | Failure prob. | Loss prob. | Capacity | Load factor |
|---|---|---|---|---|---|---|---|
| S1 | fast, failure-prone | 15 | 1 | 0.12 | 0 | 20 | 20 |
| S2 | reliable, slow | 60 | 25 | 0.001 | 0 | 240 | 8 |
| S3 | balanced | 30 | 2 | 0.03 | 0 | 80 | 10 |
| S4 | wide jitter | 35 | 60 | 0.02 | 0 | 90 | 5 |
| S5 | steady, mid | 45 | 1 | 0.01 | 0 | 120 | 6 |
| S6 | lossy | 25 | 1 | 0 | 0.03 | 80 | 6 |
| S7 | fast, small | 30 | 1 | 0.005 | 0 | 20 | 20 |
| S8 | slow, reliable | 90 | 2 | 0.001 | 0 | 240 | 6 |

**Applications and cost.** A request of class *a* with latency *L* and failure indicator *f* costs
`w_fail(a)*f + w_lat(a)*min(1, L/lat_ref(a))`; it violates the SLA if it fails or exceeds the
class's maximum latency. The four classes are equally likely.

| Class | Max latency (ms) | Min. success | Payload (B) | w_fail | w_lat | lat_ref (ms) |
|---|---|---|---|---|---|---|
| gaming | 60 | 0.99 | 128 | 0.4 | 0.6 | 60 |
| banking | 120 | 0.9995 | 512 | 5.0 | 0.05 | 120 |
| streaming | 80 | 0.99 | 4096 | 0.8 | 0.2 | 80 |
| browsing | 500 | 0.95 | 216 | 0.3 | 0.1 | 500 |

The sensitivity analysis adds a *reliability* set (w_fail 1.0 / 10 / 1.5 / 0.5, same w_lat) and a
*latency* set (w_fail 0.2 / 2.0 / 0.4 / 0.1, w_lat 0.8 / 0.2 / 0.4 / 0.3), defined in `WEIGHT_SETS`.

**Workload.** Open loop: requests are dispatched every 1/rate seconds regardless of outstanding
replies. A seed fixes the application sequence (`random.Random("apps-<seed>")`), the policy's RNG
(`random.Random(seed)`) and each server's RNG (`seed*1000 + index + 1`, set through the control port),
so all strategies see identical requests and server randomness. Runs are separated by a 1 s cooldown
and the strategy order is rotated per seed.

**Drift.** At request 200 of 600 (100 req/s), S7's base latency is set to 150 ms and its failure
probability to 0.30, permanently.

## Strategies
- `random`, `round_robin`.
- `lowest_latency`: lowest EWMA (beta 0.2) of measured latency of all requests; untried servers
  first; application-blind.
- `p2c_cost`: power of two choices on running-mean cost per server; application-blind.
- `arms_app_ts`: per-(class, server) Gaussian Thompson sampling on cost, Normal(mean, 0.3/sqrt(n+1)).
- `shared_cost_ts_fast` (shared-model TS): one model per server shared by all classes, discounted by
  0.995 on every update: Beta(1+a, 1+b) success probability and discounted mean/variance of
  successful latency (variance floor 1 ms^2). For each request it samples both for every server and
  picks the lowest cost under the requesting class's weights. Untried servers first; a server with
  no successful reply yet is given latency lat_ref. Each decision has a one-line explanation, e.g.
  `gaming -> S1: success=0.899, predicted latency=17.84 ms, cost=0.219; runner-up=S6 cost=0.271`.
- `softmax_cost` / `softmax_cost_global`: softmax over running-mean cost (tau 0.05, floor 0.02) per
  (class, server) or per server; each pair or server is tried once first.
- `oracle_per_app` / `oracle_blind`: static clairvoyant references. Expected cost per (class, server)
  is computed from the true profiles at zero load; `oracle_per_app` sends each class to its cheapest
  server (gaming S1, banking S2, streaming S7, browsing S7) and `oracle_blind` sends all traffic to
  the server with the lowest mix-weighted cost (S7). They do not react to load or drift.

## Timing on Windows
Millisecond measurements need three fixes in every process, all in `enable_hires_timer()`:
`timeBeginPeriod(1)`, replacing the event loop's clock with `time.perf_counter`, and opting the
process out of Windows 11 power throttling. Without the last one, windowless processes fall back to
15.6 ms timer ticks a few seconds after start (dispatch lag up to 15.8 ms; with it, about 2.5 ms at
most). The client uses a raw non-blocking socket with SO_LINGER(1, 0) and closes it directly:
asyncio streams on Windows left 1000 of 1000 test connections in TIME_WAIT, the raw socket none.

## Results
Full tables are in `results/summary.md` (12 seeds, 600 requests per run). Mean cost per request:

| Strategy | 50 req/s | 150 req/s |
|---|---|---|
| random | 0.171 | 0.174 |
| round_robin | 0.174 | 0.173 |
| lowest_latency | 0.246 | 0.247 |
| p2c_cost | 0.167 | 0.163 |
| arms_app_ts | 0.141 | 0.140 |
| softmax_cost_global | 0.159 | 0.158 |
| softmax_cost | 0.138 | 0.137 |
| **shared_cost_ts_fast** | **0.120** | **0.127** |
| oracle_blind (static reference) | 0.118 | 0.136 |
| oracle_per_app (static reference) | 0.088 | 0.093 |

- Shared-model TS is the cheapest learning policy at both rates, 27-30% below random, and the
  cheapest learning policy under all three cost-weight sets.
- After S7 degrades, shared-model TS moves traffic off it in about 21 requests, against 47-83 for
  the other learning policies.
- Decision overhead is under 0.1 ms per request for every policy.
- The app-aware softmax beats its app-blind twin by about 0.021 under the base weights and by 0.030
  under the latency set, but is worse under the reliability set.

## Data-collection notes
- The 50 req/s static data was collected over more than one session: the first session was stopped
  by the host after 74 of 240 runs (system low on memory) and the rest were appended with `--append`
  (see the `session` column of `results/run_order.csv`). The interrupted session's before-runs
  timing check is in `results/static_log.txt` (UTF-16).
- Learning policies are not bit-for-bit repeatable for a fixed seed, because reply order depends on
  OS scheduling. `--mode repeat` measures this: five repeats of seed 501 give a cost standard
  deviation of 0.0001 for random and 0.005-0.010 for the learning policies.
- Drift adaptation time is computed only for seeds in which S7 carried more than 5% of the 100
  requests before the change; ineligible and censored seeds are counted separately.
- Killing the runner hard (not Ctrl+C) can leave the server processes running.
