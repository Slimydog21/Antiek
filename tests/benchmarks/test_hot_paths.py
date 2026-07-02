"""ARE-12 deterministic benchmark harness for the five enumerated hot paths.

Run with:
  python -m pytest tests/benchmarks/test_hot_paths.py -q

Results are appended to ``tests/benchmarks/results/baseline_m3_<date>.jsonl``.
Each test executes three measured samples so the M4 analysis gate can require
at least three samples for every path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.dispatch.json_repair import repair_json_string
from substrate.dispatch.router import NormalizedUsage, TierPricing, _compute_cost_usd
from substrate.errors import BudgetExceeded
from substrate.event_log import log_event, trajectory
from substrate.hot_path_timing import hot_path_timing, set_hot_path_timing_sink
from substrate.loop_3 import build_env_from_trajectory
from substrate.results import Err, Ok, is_err, is_ok

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_PATH = RESULTS_DIR / f"baseline_m3_{datetime.now(UTC):%Y%m%d}.jsonl"
REQUIRED_PATHS = {
    "verifier_throughput",
    "dispatch_fanout",
    "event_log_parquet_read",
    "json_repair_error_path",
    "loop_3_rl_prep",
}


def _append_record(row: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


@pytest.fixture(scope="session", autouse=True)
def _reset_baseline_artifact():
    if RESULTS_PATH.exists():
        RESULTS_PATH.unlink()
    yield


@pytest.fixture(autouse=True)
def _timing_sink():
    set_hot_path_timing_sink(_append_record)
    yield
    set_hot_path_timing_sink(None)


def _sample(fn):
    out = None
    set_hot_path_timing_sink(None)
    fn()
    set_hot_path_timing_sink(_append_record)
    for _ in range(3):
        out = fn()
    return out


# Hot path 1: verifiers throughput (result verification)
def test_hot_path_1_verifier() -> None:
    sample_ok = Ok(value={"foo": 1})
    sample_err = Err(error=BudgetExceeded(cap=10, attempted=11))

    @hot_path_timing("verifier_throughput")
    def verify_pair() -> tuple[bool, bool, str]:
        return is_ok(sample_ok), is_err(sample_err), sample_err.error.kind

    assert _sample(verify_pair) == (True, True, "budget_exceeded")


# Hot path 2: dispatch fan-out (router cost computation)
def test_hot_path_2_dispatch() -> None:
    @hot_path_timing("dispatch_fanout")
    def compute_dispatch_cost() -> float:
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
        return _compute_cost_usd(usage, pricing)

    assert _sample(compute_dispatch_cost) > 0


# Hot path 3: event_log read path
def test_hot_path_3_event_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path))
    investigation_id = "are12-bench"
    log_event(investigation_id, "bench.started", payload={"n": 1})

    @hot_path_timing("event_log_parquet_read")
    def read_events() -> list[dict]:
        return trajectory(investigation_id, events_dir=str(tmp_path))

    rows = _sample(read_events)
    assert len(rows) == 1
    assert rows[0]["action_type"] == "bench.started"


# Hot path 4: json_repair error path
def test_hot_path_4_json_repair() -> None:
    @hot_path_timing("json_repair_error_path")
    def repair_error_path() -> dict:
        repaired = repair_json_string('prefix text {"key": "value", "nested": [1, 2]}')
        assert isinstance(repaired, dict)
        return repaired

    assert _sample(repair_error_path)["nested"] == [1, 2]


def test_hot_path_5_rl_prep() -> None:
    trajectory_events = [
        {"event_id": "e1", "action_type": "decomposer.delivered", "payload": {"q": "X"}},
        {"event_id": "e2", "action_type": "synthesizer.delivered", "payload": {"t": "Y"}},
    ]

    @hot_path_timing("loop_3_rl_prep")
    def prep_env() -> str:
        env = build_env_from_trajectory(trajectory_events)
        return env.reset().observation

    assert "X" in _sample(prep_env)


def test_baseline_artifact_has_all_required_paths() -> None:
    if not RESULTS_PATH.exists():
        pytest.fail(f"missing baseline artifact: {RESULTS_PATH}")
    rows = [
        json.loads(line)
        for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_path = {path: 0 for path in REQUIRED_PATHS}
    for row in rows:
        if row.get("schema_version") == 1 and row.get("path") in by_path:
            by_path[row["path"]] += 1
            assert row["duration_ms"] >= 0
            assert row["git_sha"]
            assert row["python_version"]
            assert row["os"]
    missing = {path: count for path, count in by_path.items() if count < 3}
    assert missing == {}


if __name__ == "__main__":
    # Allow direct run for smoke test
    raise SystemExit(pytest.main([__file__, "-q"]))
