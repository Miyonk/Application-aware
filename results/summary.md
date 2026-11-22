# Reimplementation results summary

## Static experiment

Rows: 144000; seeds: [501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512]; rates: [50.0, 150.0]

Dispatch lag vs. schedule at 50 req/s (timing health): p50 0.76 ms, p99 2.06 ms, max 5.36 ms

Dispatch lag vs. schedule at 150 req/s (timing health): p50 0.71 ms, p99 2.07 ms, max 5.81 ms

### Overall metrics at 50 req/s (mean across seeds)

| strategy | seeds | mean cost [95% CI] | SLA viol | fail rate | mean lat ok (ms) | p95 lat ok (ms) | jitter (ms) | overhead (ms) |
|---|---|---|---|---|---|---|---|---|
| random | 12 | 0.1711 [0.1641, 0.1787] | 0.1286 | 0.0276 | 44.31 | 92.49 | 25.46 | 0.0069 |
| round_robin | 12 | 0.1741 [0.1640, 0.1841] | 0.1236 | 0.0267 | 44.46 | 92.51 | 25.35 | 0.0033 |
| lowest_latency | 12 | 0.2459 [0.2268, 0.2636] | 0.1199 | 0.1181 | 18.42 | 19.54 | 5.33 | 0.0187 |
| p2c_cost | 12 | 0.1667 [0.1566, 0.1778] | 0.0983 | 0.0249 | 40.93 | 90.93 | 22.82 | 0.0246 |
| arms_app_ts | 12 | 0.1410 [0.1339, 0.1493] | 0.0725 | 0.0356 | 40.11 | 91.81 | 23.62 | 0.0276 |
| shared_cost_ts_fast | 12 | 0.1203 [0.1123, 0.1296] | 0.0519 | 0.0446 | 30.21 | 57.83 | 14.21 | 0.0820 |
| softmax_cost | 12 | 0.1380 [0.1300, 0.1463] | 0.0729 | 0.0383 | 38.93 | 91.58 | 23.20 | 0.0268 |
| softmax_cost_global | 12 | 0.1589 [0.1549, 0.1636] | 0.0844 | 0.0281 | 38.68 | 90.18 | 21.13 | 0.0271 |
| oracle_blind | 12 | 0.1181 [0.1137, 0.1228] | 0.0047 | 0.0047 | 33.92 | 35.29 | 0.80 | 0.0022 |
| oracle_per_app | 12 | 0.0880 [0.0859, 0.0903] | 0.0324 | 0.0324 | 37.12 | 76.47 | 17.31 | 0.0026 |

### Overall metrics at 150 req/s (mean across seeds)

| strategy | seeds | mean cost [95% CI] | SLA viol | fail rate | mean lat ok (ms) | p95 lat ok (ms) | jitter (ms) | overhead (ms) |
|---|---|---|---|---|---|---|---|---|
| random | 12 | 0.1738 [0.1648, 0.1838] | 0.1274 | 0.0263 | 44.78 | 92.81 | 25.34 | 0.0075 |
| round_robin | 12 | 0.1729 [0.1628, 0.1832] | 0.1222 | 0.0260 | 44.73 | 92.74 | 25.30 | 0.0034 |
| lowest_latency | 12 | 0.2465 [0.2261, 0.2656] | 0.1181 | 0.1153 | 21.63 | 22.55 | 5.93 | 0.0227 |
| p2c_cost | 12 | 0.1625 [0.1500, 0.1752] | 0.0971 | 0.0244 | 41.62 | 91.95 | 22.86 | 0.0259 |
| arms_app_ts | 12 | 0.1398 [0.1316, 0.1499] | 0.0706 | 0.0328 | 40.15 | 92.09 | 23.25 | 0.0301 |
| shared_cost_ts_fast | 12 | 0.1268 [0.1163, 0.1381] | 0.0528 | 0.0461 | 29.68 | 54.27 | 13.38 | 0.0932 |
| softmax_cost | 12 | 0.1367 [0.1300, 0.1434] | 0.0675 | 0.0354 | 39.08 | 91.86 | 22.77 | 0.0292 |
| softmax_cost_global | 12 | 0.1579 [0.1475, 0.1690] | 0.0883 | 0.0242 | 40.27 | 91.19 | 21.88 | 0.0298 |
| oracle_blind | 12 | 0.1359 [0.1320, 0.1397] | 0.0047 | 0.0047 | 38.07 | 39.77 | 1.00 | 0.0022 |
| oracle_per_app | 12 | 0.0926 [0.0899, 0.0957] | 0.0338 | 0.0337 | 38.66 | 77.16 | 17.24 | 0.0028 |

### Per-application mean cost at 50 req/s (per-seed mean, averaged over seeds)

| strategy | gaming | banking | streaming | browsing |
|---|---|---|---|---|
| random | 0.3969 | 0.1425 | 0.1274 | 0.0166 |
| round_robin | 0.3976 | 0.1501 | 0.1299 | 0.0171 |
| lowest_latency | 0.2297 | 0.5764 | 0.1345 | 0.0424 |
| p2c_cost | 0.3789 | 0.1536 | 0.1188 | 0.0156 |
| arms_app_ts | 0.2969 | 0.1362 | 0.1140 | 0.0174 |
| shared_cost_ts_fast | 0.2478 | 0.1241 | 0.0956 | 0.0142 |
| softmax_cost | 0.2954 | 0.1242 | 0.1170 | 0.0157 |
| softmax_cost_global | 0.3598 | 0.1380 | 0.1204 | 0.0169 |
| oracle_blind | 0.3411 | 0.0340 | 0.0899 | 0.0078 |
| oracle_per_app | 0.2268 | 0.0309 | 0.0859 | 0.0087 |

### Per-application mean cost at 150 req/s (per-seed mean, averaged over seeds)

| strategy | gaming | banking | streaming | browsing |
|---|---|---|---|---|
| random | 0.4000 | 0.1516 | 0.1270 | 0.0160 |
| round_robin | 0.3959 | 0.1477 | 0.1291 | 0.0175 |
| lowest_latency | 0.2631 | 0.5347 | 0.1464 | 0.0403 |
| p2c_cost | 0.3781 | 0.1341 | 0.1199 | 0.0174 |
| arms_app_ts | 0.2981 | 0.1253 | 0.1210 | 0.0153 |
| shared_cost_ts_fast | 0.2517 | 0.1380 | 0.1034 | 0.0147 |
| softmax_cost | 0.2951 | 0.1217 | 0.1138 | 0.0165 |
| softmax_cost_global | 0.3721 | 0.1279 | 0.1164 | 0.0148 |
| oracle_blind | 0.3821 | 0.0547 | 0.0975 | 0.0089 |
| oracle_per_app | 0.2348 | 0.0315 | 0.0952 | 0.0088 |

### Server share at 50 req/s (fraction of requests)

| strategy | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |
|---|---|---|---|---|---|---|---|---|
| random | 0.126 | 0.120 | 0.126 | 0.122 | 0.124 | 0.132 | 0.122 | 0.129 |
| round_robin | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 |
| lowest_latency | 0.984 | 0.002 | 0.002 | 0.006 | 0.002 | 0.002 | 0.002 | 0.002 |
| p2c_cost | 0.078 | 0.084 | 0.126 | 0.143 | 0.113 | 0.207 | 0.164 | 0.085 |
| arms_app_ts | 0.183 | 0.100 | 0.118 | 0.110 | 0.101 | 0.158 | 0.142 | 0.089 |
| shared_cost_ts_fast | 0.244 | 0.023 | 0.052 | 0.079 | 0.044 | 0.319 | 0.229 | 0.010 |
| softmax_cost | 0.195 | 0.087 | 0.116 | 0.120 | 0.098 | 0.165 | 0.142 | 0.077 |
| softmax_cost_global | 0.099 | 0.069 | 0.130 | 0.116 | 0.095 | 0.220 | 0.201 | 0.070 |
| oracle_blind | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| oracle_per_app | 0.251 | 0.251 | 0.000 | 0.000 | 0.000 | 0.000 | 0.498 | 0.000 |

### Server share at 150 req/s (fraction of requests)

| strategy | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |
|---|---|---|---|---|---|---|---|---|
| random | 0.126 | 0.120 | 0.126 | 0.122 | 0.124 | 0.132 | 0.122 | 0.129 |
| round_robin | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 |
| lowest_latency | 0.974 | 0.002 | 0.002 | 0.016 | 0.002 | 0.002 | 0.002 | 0.002 |
| p2c_cost | 0.070 | 0.088 | 0.140 | 0.144 | 0.112 | 0.203 | 0.156 | 0.087 |
| arms_app_ts | 0.163 | 0.095 | 0.116 | 0.116 | 0.102 | 0.182 | 0.141 | 0.085 |
| shared_cost_ts_fast | 0.247 | 0.016 | 0.050 | 0.066 | 0.030 | 0.440 | 0.140 | 0.012 |
| softmax_cost | 0.191 | 0.084 | 0.113 | 0.112 | 0.105 | 0.180 | 0.137 | 0.077 |
| softmax_cost_global | 0.088 | 0.078 | 0.133 | 0.114 | 0.111 | 0.232 | 0.165 | 0.079 |
| oracle_blind | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| oracle_per_app | 0.251 | 0.251 | 0.000 | 0.000 | 0.000 | 0.000 | 0.498 | 0.000 |

### Paired per-seed cost differences at 50 req/s (A - B; >0 means B is cheaper)

| difference | paired seeds | mean diff [95% CI] |
|---|---|---|
| softmax_cost_global - softmax_cost | 12 | 0.0209 [0.0116, 0.0299] |
| oracle_blind - oracle_per_app | 12 | 0.0301 [0.0258, 0.0349] |
| p2c_cost - shared_cost_ts_fast | 12 | 0.0464 [0.0337, 0.0594] |
| random - shared_cost_ts_fast | 12 | 0.0509 [0.0401, 0.0616] |
| arms_app_ts - shared_cost_ts_fast | 12 | 0.0207 [0.0082, 0.0313] |

### Paired per-seed cost differences at 150 req/s (A - B; >0 means B is cheaper)

| difference | paired seeds | mean diff [95% CI] |
|---|---|---|
| softmax_cost_global - softmax_cost | 12 | 0.0213 [0.0112, 0.0322] |
| oracle_blind - oracle_per_app | 12 | 0.0434 [0.0378, 0.0484] |
| p2c_cost - shared_cost_ts_fast | 12 | 0.0357 [0.0218, 0.0507] |
| random - shared_cost_ts_fast | 12 | 0.0470 [0.0352, 0.0587] |
| arms_app_ts - shared_cost_ts_fast | 12 | 0.0130 [0.0035, 0.0222] |

### Error counts per strategy and rate (all seeds)

| rate | strategy | requests | simulated_failure | timeout |
|---|---|---|---|---|
| 50 | random | 7200 | 169 | 30 |
| 50 | round_robin | 7200 | 164 | 28 |
| 50 | lowest_latency | 7200 | 850 | 0 |
| 50 | p2c_cost | 7200 | 139 | 40 |
| 50 | arms_app_ts | 7200 | 222 | 34 |
| 50 | shared_cost_ts_fast | 7200 | 259 | 62 |
| 50 | softmax_cost | 7200 | 235 | 41 |
| 50 | softmax_cost_global | 7200 | 154 | 48 |
| 50 | oracle_blind | 7200 | 34 | 0 |
| 50 | oracle_per_app | 7200 | 233 | 0 |
| 150 | random | 7200 | 161 | 28 |
| 150 | round_robin | 7200 | 159 | 28 |
| 150 | lowest_latency | 7200 | 830 | 0 |
| 150 | p2c_cost | 7200 | 131 | 45 |
| 150 | arms_app_ts | 7200 | 202 | 34 |
| 150 | shared_cost_ts_fast | 7200 | 242 | 90 |
| 150 | softmax_cost | 7200 | 224 | 31 |
| 150 | softmax_cost_global | 7200 | 130 | 44 |
| 150 | oracle_blind | 7200 | 34 | 0 |
| 150 | oracle_per_app | 7200 | 243 | 0 |

### Testbed check at 50 req/s: measured latency per server under `random` (successful requests)

| server | base ms | jitter ms | n | mean lat ok | mean - base | median | fail rate | configured fail+loss |
|---|---|---|---|---|---|---|---|---|
| S1 | 15 | 1 | 907 | 17.89 | 2.89 | 17.88 | 0.105 | 0.120 |
| S2 | 60 | 25 | 865 | 62.44 | 2.44 | 63.56 | 0.002 | 0.001 |
| S3 | 30 | 2 | 905 | 32.03 | 2.03 | 32.03 | 0.035 | 0.030 |
| S4 | 35 | 60 | 877 | 39.49 | 4.49 | 36.28 | 0.027 | 0.020 |
| S5 | 45 | 1 | 894 | 46.91 | 1.91 | 46.88 | 0.013 | 0.010 |
| S6 | 25 | 1 | 949 | 27.05 | 2.05 | 27.02 | 0.032 | 0.030 |
| S7 | 30 | 1 | 877 | 33.03 | 3.03 | 32.98 | 0.005 | 0.005 |
| S8 | 90 | 2 | 926 | 91.89 | 1.89 | 91.81 | 0.000 | 0.001 |

### Testbed check at 150 req/s: measured latency per server under `random` (successful requests)

| server | base ms | jitter ms | n | mean lat ok | mean - base | median | fail rate | configured fail+loss |
|---|---|---|---|---|---|---|---|---|
| S1 | 15 | 1 | 907 | 18.39 | 3.39 | 18.32 | 0.109 | 0.120 |
| S2 | 60 | 25 | 865 | 62.90 | 2.90 | 63.25 | 0.000 | 0.001 |
| S3 | 30 | 2 | 905 | 32.39 | 2.39 | 32.31 | 0.033 | 0.030 |
| S4 | 35 | 60 | 877 | 40.10 | 5.10 | 38.00 | 0.030 | 0.020 |
| S5 | 45 | 1 | 894 | 47.28 | 2.28 | 47.30 | 0.006 | 0.010 |
| S6 | 25 | 1 | 949 | 27.42 | 2.42 | 27.46 | 0.030 | 0.030 |
| S7 | 30 | 1 | 877 | 33.82 | 3.82 | 33.81 | 0.001 | 0.005 |
| S8 | 90 | 2 | 926 | 92.16 | 2.16 | 92.07 | 0.000 | 0.001 |

## Drift

Drift at idx 200 on S7 (config {'base_latency_ms': 150.0, 'failure_prob': 0.3}, no restore). A seed is eligible if S7's share in [drift-100, drift) > 0.05. For eligible seeds, adaptation time = smallest j>=0 with S7 share in [drift+j, drift+j+50) <= 0.05; censored if never reached. Mean and 95% bootstrap CI over uncensored eligible seeds.

| strategy | seeds | S7 share [d-100, d) | S7 share [d, end) | eligible seeds | adaptation (requests) [95% CI] | uncensored | censored | ineligible |
|---|---|---|---|---|---|---|---|---|
| random | 12 | 0.1317 | 0.1202 | 12 | 101.90 [52.00, 167.60] | 10 | 2 | 0 |
| p2c_cost | 12 | 0.1183 | 0.0469 | 10 | 46.50 [25.10, 71.10] | 10 | 0 | 2 |
| arms_app_ts | 12 | 0.1333 | 0.0525 | 12 | 75.33 [56.17, 93.83] | 12 | 0 | 0 |
| shared_cost_ts_fast | 12 | 0.1175 | 0.0171 | 9 | 20.56 [10.67, 32.33] | 9 | 0 | 3 |
| softmax_cost | 12 | 0.1142 | 0.0669 | 12 | 83.42 [55.67, 109.42] | 12 | 0 | 0 |

### Drift: mean cost by window (mean across seeds [95% CI])

| strategy | [d-100, d) | [d, d+100) | [d+100, end) |
|---|---|---|---|
| random | 0.1823 [0.1636, 0.2047] | 0.2555 [0.2270, 0.2839] | 0.2475 [0.2320, 0.2633] |
| p2c_cost | 0.1755 [0.1509, 0.2023] | 0.2281 [0.2034, 0.2608] | 0.1890 [0.1724, 0.2098] |
| arms_app_ts | 0.1429 [0.1208, 0.1705] | 0.2117 [0.1736, 0.2523] | 0.1412 [0.1267, 0.1588] |
| shared_cost_ts_fast | 0.1348 [0.1072, 0.1695] | 0.1474 [0.1140, 0.1847] | 0.1396 [0.1218, 0.1584] |
| softmax_cost | 0.1608 [0.1372, 0.1842] | 0.1920 [0.1707, 0.2122] | 0.1568 [0.1398, 0.1743] |

## Repeatability (same seed, repeated runs)

Seed(s) [501], rate(s) [50.0]. Mean cost of each repetition, and the std (ddof=1) across repetitions.

| strategy | rep 0 | rep 1 | rep 2 | rep 3 | rep 4 | mean | std |
|---|---|---|---|---|---|---|---|
| random | 0.1605 | 0.1603 | 0.1605 | 0.1607 | 0.1606 | 0.1605 | 0.0001 |
| p2c_cost | 0.1460 | 0.1472 | 0.1462 | 0.1460 | 0.1574 | 0.1486 | 0.0049 |
| shared_cost_ts_fast | 0.1180 | 0.1213 | 0.1163 | 0.1024 | 0.1290 | 0.1174 | 0.0097 |
| softmax_cost | 0.1613 | 0.1365 | 0.1502 | 0.1453 | 0.1500 | 0.1487 | 0.0090 |

