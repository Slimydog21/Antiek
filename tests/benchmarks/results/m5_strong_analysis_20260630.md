# ARE-12 M4 Comparison Report
Generated: deterministic-from-input
| Path | p50 | p95 | mean | stddev | samples | Bottleneck map |
|------|-----|-----|------|--------|---------|----------------|
| event_log_parquet_read | 0.024771 | 0.032187 | 0.027822 | 0.019907 | 100 | substrate/event_log/events.py::trajectory:535-574 |
| json_repair_error_path | 0.002666 | 0.002875 | 0.002682 | 0.000117 | 100 | substrate/dispatch/json_repair.py::repair_json_string:13-26 |
| loop_3_rl_prep | 0.002166 | 0.002375 | 0.00221 | 0.000259 | 100 | substrate/loop_3/verifiers_env.py::build_env_from_trajectory:101-116 |
| dispatch_fanout | 0.000333 | 0.00054 | 0.000409 | 0.000423 | 100 | substrate/dispatch/router.py::_compute_cost_usd:226-246 |
| verifier_throughput | 0.000166 | 0.000292 | 0.00021 | 0.000507 | 100 | tests/benchmarks/test_hot_paths.py::verify_pair:66-69 |

## Top-2 Bottlenecks
1. bottleneck: event_log_parquet_read (p95=0.032187ms) at substrate/event_log/events.py::trajectory:535-574
2. bottleneck: json_repair_error_path (p95=0.002875ms) at substrate/dispatch/json_repair.py::repair_json_string:13-26
