# Evaluation summary (config 8dfd7dcb)

Sources: real:534760ec, real:8d37ae96, real:b6179b48, real:48844f9b, synth:100, synth:101, synth:102

| Check | Result | Target |
| --- | --- | --- |
| Injected rings ≥ 8 accounts: recall | 1.00 | ≥ 0.8 |
| Injected rings ≥ 8 accounts: precision | 1.0 | ≥ 0.8 |
| Control places flagged | 0 of 7 | ≤ 1 of 10 |
| Null graphs with p < α (196 shuffles) | 0.005 | 0.005–0.02 |
| Credits for 0.8 recall: priority / BFS / random | 40 / 60 / None | priority ≤ 50% of BFS |

Stress grid (8 × 8, camouflage 0.3), recall by coverage × place popularity:

- cov0.4_dp100-400: 0.29
- cov0.4_dp5-60: 0.57
- cov0.4_dp500-2000: 0.00
- cov0.6_dp100-400: 0.71
- cov0.6_dp5-60: 1.00
- cov0.6_dp500-2000: 0.57
- cov0.85_dp100-400: 1.00
- cov0.85_dp5-60: 1.00
- cov0.85_dp500-2000: 1.00

Calibration suggested by the controls: {'mass_scale': 1.0, 'tau': 0.6038928854026926} (frozen values: config.yaml)

Wall time 1164s
