# Independent reimplementation: application-aware service selection testbed

From-scratch rebuild of the experiment in "Application-Aware Dynamic Service Selection
using Contextual Bandits with Drift Detection and Explainable Decisions" (sections 7-9).
The original code and data are not available. Standard library + numpy only.

## Files
- `common.py`: server profiles (Table 7.2), app SLA profiles (Table 7.3), cost (eq. 3), SLA check,
  **all ASSUMED values**, Windows timer fix, analytic zero-load expected cost (used by the oracles).
- `backend.py`: one backend server process (data port 9001-9008, control port 9101-9108).
  `_process_request` follows Figure 7.3.
- `client.py`: `send_request` (Figure 7.3 logic, raw socket, see below), control helper, payload padding.
- `policies.py`: the 10 strategies. `python policies.py` prints the oracle expected-cost table.
- `run_experiment.py`: runner (`--mode smoke|static|drift`).
- `analyze.py`: writes `results/summary.md`.

## Usage
```
python run_experiment.py --mode smoke          # seeds 501-502, 50 req/s, n=200, all strategies
python run_experiment.py --mode static         # seeds 501-512, 50 and 150 req/s, n=600, all strategies
python run_experiment.py --mode drift          # seeds 501-512, 100 req/s, n=600, 5 strategies
python analyze.py
```
Options: `--seeds 501-512`, `--rates 50,150`, `--n 600`, `--strategies a,b`, `--append`.
Outputs: `results/{smoke,static,drift}.csv` (one row per request), `results/run_order.csv`
(execution order, one row per run), `results/sleep_check_<mode>.json` (timer accuracy before and
after the runs, in every process). smoke.csv is overwritten; an existing static/drift CSV is moved
to `results/old/` unless `--append` is given.

## Taken from the paper
8 servers (Table 7.2, not the contradicting Figure 7.4 launch log), each its own process; JSON-line
protocol; server behaviour of `_process_request` (load = active/capacity, latency = base +
U(-jitter, jitter) + load_factor*load, loss -> hold then no reply, else ok = random() >= failure_prob);
app profiles (Table 7.3); cost eq. 3; SLA violation = failure or latency > max latency; client
timeout 1.5 s; 600 requests/run; 50 and 150 req/s; seeds 501-512; 1.0 s cooldown; softmax
tau = 0.05, eps = 0.02 (eq. 8); 95% percentile bootstrap.

## ASSUMED (not given in the paper) — all in `common.py`
| item | value |
|---|---|
| cost weights (w_fail, w_lat, lat_ref ms) | gaming 0.4/0.6/60; banking 5.0/0.05/120; streaming 0.8/0.2/80; browsing 0.3/0.1/500 (see note below) |
| application mix | 25% each |
| server hold time for a lost request | 2000 ms (> client timeout, so a loss is a client timeout) |
| drift scenario | at request idx 200, S7 set to base_latency_ms 150, failure_prob 0.30; no restore; 100 req/s |
| per-server RNG seed | `seed*1000 + index + 1`, set via control `reset` before every run |
| app sequence RNG | `random.Random("apps-<seed>")`, independent of the policy RNG (`random.Random(seed)`) |
| execution order | for each rate, for each seed, strategies in a fixed list rotated by the seed's position |

**Provenance of the cost weights.** The gaming and streaming weights are inferred from the paper's
own demo log (Figure 9.9): e.g. "gaming -> S1: success=0.885, predicted latency=18.01 ms,
cost=0.235" and "streaming -> S6: success=0.980, predicted latency=27.63 ms, cost=0.083" are roughly
consistent with gaming (0.4, 0.6, 60) and streaming (0.8, 0.2, 80), and the demo sends 62% of gaming
to S1 (fast but failure-prone). This inference is noisy: those logged values are Thompson-sampled
draws, not posterior means. The banking and browsing weights remain guesses. None of the weights
were fitted to the paper's Table 9.1, and they must not be tuned to match it. (A first version
used gaming 2.0/0.5/60 and streaming 1.0/0.2/80; under those, S7 was best for nearly every app.)

## Strategy reconstructions (the paper does not define most of them)
- `random`, `round_robin`.
- `lowest_latency`: lowest EWMA (beta 0.2) of client-measured latency of *all* requests (timeouts
  contribute ~1500 ms); untried servers first; app-blind.
- `p2c_cost`: two distinct random servers, lower running-mean cost wins (untried = 0); app-blind.
- `arms_app_ts`: per-(app, server) Gaussian TS on cost, Normal(mean, 0.3/sqrt(n+1)), prior mean 0.
- `shared_cost_ts_fast`: per-server shared model, discount 0.995 on every update; Beta(1+a, 1+b)
  success; discounted mean/var of successful latency (var floor 1 ms^2), lat ~ Normal(mean,
  sqrt(var/max(n_eff, 1))); app-specific cost at decision time. A tried server with no successful
  latency yet uses predicted latency = lat_ref(app). Explanation string built outside the timed section.
- `softmax_cost` / `softmax_cost_global`: running-mean cost per (app, server) / per server; cold start
  over untried pairs/servers (marked at select time); a tried pair with no completed response yet has
  estimate 0. Fixed tau (the paper mentions a schedule but also a fixed tau = 0.05; fixed used).
- `oracle_per_app` / `oracle_blind`: **static clairvoyant references, not true per-request hindsight
  oracles** — counterfactual per-request costs are unobservable on a live testbed. Expected cost per
  (app, server) is computed numerically from the true config at zero load (load = 1/capacity, i.e.
  only the request itself; latency uniform in base +- jitter clipped at 0; failure prob; packet loss
  = timeout with f = 1 and capped latency term). per_app sends each app to its best server;
  blind sends everything to the server with the lowest mix-weighted expected cost. With the assumed
  weights: per_app = gaming S1, banking S2, streaming S7, browsing S7; blind = S7.

## Windows timing / socket fixes (each verified empirically)
1. In every process: `timeBeginPeriod(1)`, `loop.time = time.perf_counter`, `loop._clock_resolution = 1e-6`.
   **Additionally required on Windows 11:** opting the process out of power throttling
   (`SetProcessInformation(ProcessPowerThrottling, EXECUTION_SPEED | IGNORE_TIMER_RESOLUTION, 0)`).
   Without it, windowless processes silently fall back to 15.6 ms timer ticks a few seconds after
   start (measured: dispatch lag sawtooth up to 15.8 ms; with the opt-out max ~2.5 ms).
2. The client uses a raw non-blocking socket (`loop.sock_connect/sock_sendall/sock_recv`) with
   SO_LINGER(1, 0) and closes it directly. The asyncio stream transport on Windows calls
   `shutdown(SHUT_RDWR)` before closing, which defeats SO_LINGER: 1000 of 1000 test connections went
   to TIME_WAIT with streams, 0 of 1000 with the raw socket. Request/response logic and error mapping
   are otherwise identical to Figure 7.3's `send_request`. The server tolerates ConnectionResetError.

## Data-collection note
The first full static session was stopped by the host (system low on memory) after 74 of 240 runs
(50 req/s: seeds 501-507 complete, seed 508 only softmax_cost_global, oracle_per_app, oracle_blind,
random). The remaining runs were appended in further sessions with `--append`, so the 50 req/s
static data was collected across more than one session (see `results/run_order.csv`, `session`
column, and `results/static*_log.txt`). Each session's sleep check is saved as
`results/sleep_check_<mode>_<session>.json` (the interrupted first session has only its
before-runs check, in `results/static_log.txt`, which is UTF-16 encoded).

## Known limitations
- Learning policies are not bit-for-bit reproducible per seed: response arrival order and measured
  latencies vary slightly between runs, which changes later decisions. Non-learning strategies are
  nearly identical across repeats (e.g. random seed 501 mean cost 0.1524 / 0.1529 / 0.1529).
- Drift adaptation time is computed only for "eligible" seeds (S7 share in [drift-100, drift) > 0.05);
  ineligible and censored seeds are counted separately. Mean cost over [d-100, d), [d, d+100) and
  [d+100, end) is reported as a threshold-free view of recovery.
- `--mode repeat` reruns seed 501 at 50 req/s five times (random, p2c_cost, shared_cost_ts_fast,
  softmax_cost) to measure run-to-run timing noise; the CSV has a `rep` column.
- Killing the runner hard (not Ctrl+C / exception) can orphan the server processes.

## Findings so far
Full tables are in `results/summary.md` (12 seeds, 600 requests per run, 50 and 150 req/s).
- Reproduced in direction: learned strategies beat random and power-of-two-choices;
  `shared_cost_ts_fast` is the best learned strategy at both rates; the app-aware softmax beats its
  app-blind twin by about 0.021 cost per request (the paper reports 0.020-0.022); selection overhead
  is under 0.1 ms; after an injected degradation `shared_cost_ts_fast` recovers fastest.
- Not reproduced: the paper's gap between the per-app oracle and the app-blind oracle (0.084-0.089;
  here 0.030-0.043), and the absolute cost of the random, `p2c_cost` and `arms_app_ts` baselines
  (0.02-0.04 lower here).
- Agreement in absolute values is not a verification, because the cost weights and several
  strategies are reconstructions (see the ASSUMED and reconstruction sections above).

## Next steps
In rough order of value:
1. **Get the missing definitions from the paper's authors.** The original `selector/app_profiles.py`
   (cost weights `w_fail`, `w_lat`, `lat_ref` and the application mix), the implementation of
   `shared_cost_ts_fast` and `p2c_cost`, and the definitions of `oracle_blind_split` and
   `oracle_per_app_cost_v6`. Replace the ASSUMED block in `common.py` and the reconstructions in
   `policies.py`, then rerun everything. This is the only route to an actual verification.
2. **Settle the server profile.** The paper's Table 7.2 and its Figure 7.4 launch log disagree; this
   code uses Table 7.2. Confirm which one the reported runs used.
3. **Define the drift scenario.** The paper's `D1_premium_degrades` is unspecified; the scenario here
   (S7 to 150 ms base latency and 0.30 failure probability at request 200, no restore) is invented.
   Add the paper's other scenarios (load surge, intermittent flakiness, recovery) once defined.
4. **Sensitivity analysis on the assumed weights.** Rerun the static experiment over a grid of
   weights and mixes and report which conclusions (ranking, app-aware vs app-blind gap) survive.
   Do not pick the grid point that best matches the paper and present it as a reproduction.
5. **Implement the missing baselines and components** named in the paper but not built here:
   `lowest_load`, `static_weighted_score`, the linear contextual bandit (`global_bandit` and
   per-app), the random-forest ranker, the drift detector, and event-loop lag measurement.
6. **Report regret.** The paper defines cumulative regret but never reports it; add it to
   `analyze.py` against `oracle_per_app`.
7. **Reduce timing noise.** Repeating one seed gives a cost standard deviation of 0.005-0.010 for
   learning strategies, about half the seed-to-seed spread. Use more seeds (30 or more), repeat each
   seed, and run on an otherwise idle machine; consider a second machine for the servers.
8. **Collect the 50 req/s static data in one session.** The current data spans several sessions
   because the first was interrupted (see the data-collection note).
9. **Add figures.** `analyze.py` writes tables only; add the equivalents of the paper's F1-F7 once
   matplotlib is available.
10. **Add unit tests** for the cost function, the policies' cold-start behaviour and the backend's
    control channel, and a `requirements.txt` pinning the Python and numpy versions used
    (Python 3.12.10, numpy 1.26.4).
