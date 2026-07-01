#!/usr/bin/env python3
"""Run ARE-12 hot-path samples outside pytest.

The pytest harness proves integration. This runner produces enough samples for
M5 closeout decisions without coupling benchmark evidence to test collection.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from substrate.dispatch.json_repair import repair_json_string  # noqa: E402
from substrate.dispatch.router import (  # noqa: E402
    NormalizedUsage,
    TierPricing,
    _compute_cost_usd,
)
from substrate.errors import BudgetExceeded  # noqa: E402
from substrate.event_log import log_event, trajectory  # noqa: E402
from substrate.hot_path_timing import (  # noqa: E402
    hot_path_timing,
    set_hot_path_timing_sink,
)
from substrate.loop_3 import build_env_from_trajectory  # noqa: E402
from substrate.results import Err, Ok, is_err, is_ok  # noqa: E402


def _verifier_path() -> Callable[[], object]:
    sample_ok = Ok(value={"foo": 1})
    sample_err = Err(error=BudgetExceeded(cap=10, attempted=11))

    @hot_path_timing("verifier_throughput")
    def run() -> tuple[bool, bool, str]:
        return is_ok(sample_ok), is_err(sample_err), sample_err.error.kind

    return run


def _dispatch_path() -> Callable[[], object]:
    usage = NormalizedUsage(
        input_tokens=1_500,
        output_tokens=250,
        cached_input_tokens=250,
        cache_creation_input_tokens=100,
    )
    pricing = TierPricing(
        input_per_mtok=5.0,
        output_per_mtok=15.0,
        cached_input_per_mtok=0.5,
    )

    @hot_path_timing("dispatch_fanout")
    def run() -> float:
        return _compute_cost_usd(usage, pricing)

    return run


def _event_log_path(tmpdir: str) -> Callable[[], object]:
    investigation_id = "are12-strong-bench"
    log_event(
        investigation_id,
        "bench.started",
        payload={"n": 1},
        events_dir=tmpdir,
    )

    @hot_path_timing("event_log_parquet_read")
    def run() -> list[dict[str, Any]]:
        return trajectory(investigation_id, events_dir=tmpdir)

    return run


def _json_repair_path() -> Callable[[], object]:
    raw = 'prefix text {"key": "value", "nested": [1, 2]}'

    @hot_path_timing("json_repair_error_path")
    def run() -> dict[str, Any]:
        repaired = repair_json_string(raw)
        if not isinstance(repaired, dict):
            raise TypeError("repair_json_string did not return a JSON object")
        return repaired

    return run


def _loop3_path() -> Callable[[], object]:
    trajectory_events = [
        {"event_id": "e1", "action_type": "decomposer.delivered", "payload": {"q": "X"}},
        {"event_id": "e2", "action_type": "synthesizer.delivered", "payload": {"t": "Y"}},
    ]

    @hot_path_timing("loop_3_rl_prep")
    def run() -> str:
        env = build_env_from_trajectory(trajectory_events)
        return env.reset().observation

    return run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=f"tests/benchmarks/results/optimized_m5_strong_{datetime.now(UTC):%Y%m%d}.jsonl",
    )
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=25)
    args = parser.parse_args()

    if args.samples < 20:
        raise SystemExit("--samples must be at least 20 for a p95 closeout run")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    all_records: list[dict[str, Any]] = []

    def collect(row: dict[str, Any]) -> None:
        all_records.append(row)

    with tempfile.TemporaryDirectory(prefix="antiek-are12-") as tmpdir:
        path_fns = [
            _verifier_path(),
            _dispatch_path(),
            _event_log_path(tmpdir),
            _json_repair_path(),
            _loop3_path(),
        ]
        for path_fn in path_fns:
            set_hot_path_timing_sink(None)
            for _ in range(args.warmup):
                path_fn()
            set_hot_path_timing_sink(collect)
            try:
                for _ in range(args.samples):
                    path_fn()
            finally:
                set_hot_path_timing_sink(None)

    with out.open("w", encoding="utf-8") as fh:
        for row in all_records:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"Wrote {len(all_records)} rows to {out}")


if __name__ == "__main__":
    main()
