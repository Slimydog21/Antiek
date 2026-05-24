"""Tests for tools.benchmarks.hot_paths._harness.

The harness is performance-measurement infrastructure, not a correctness
check. The tests here verify the harness produces the documented shape
(every field present, types correct, JSON-serializable) and that the
``run()`` entry point of every registered bench module returns a list
of BenchResult instances. We do NOT assert specific latency numbers —
those are platform-dependent.
"""

from __future__ import annotations

import json

from tools.benchmarks.hot_paths._harness import BenchResult, _percentile, measure


def test_measure_returns_bench_result() -> None:
    r = measure("test.noop", lambda: None, iterations=10, warmup=2)
    assert isinstance(r, BenchResult)
    assert r.bench_name == "test.noop"
    assert r.iterations == 10
    assert r.median_ns >= 0
    assert r.p95_ns >= r.median_ns
    assert r.p99_ns >= r.p95_ns
    assert r.min_ns <= r.median_ns
    assert r.max_ns >= r.p99_ns
    assert r.total_wall_s >= 0.0
    assert r.timestamp_utc.endswith("+00:00") or r.timestamp_utc.endswith("Z")
    assert r.python_version
    assert r.platform


def test_bench_result_to_dict_json_serializable() -> None:
    r = measure("test.json", lambda: None, iterations=5, warmup=1,
                metadata={"key": "value"})
    d = r.to_dict()
    # Must be JSON-serializable (default=str fallback covers timestamps etc)
    json.dumps(d, default=str)
    assert d["bench_name"] == "test.json"
    assert d["metadata"] == {"key": "value"}


def test_bench_result_format_summary_line_includes_name_and_stats() -> None:
    r = measure("test.fmt", lambda: None, iterations=5, warmup=1)
    s = r.format_summary_line()
    assert "test.fmt" in s
    assert "med=" in s
    assert "p95=" in s
    assert "p99=" in s
    assert "n=5" in s


def test_percentile_empty_returns_zero() -> None:
    assert _percentile([], 95.0) == 0


def test_percentile_p50_is_median_for_odd_n() -> None:
    samples = sorted([10, 20, 30, 40, 50])
    assert _percentile(samples, 50.0) == 30


def test_percentile_p100_is_max() -> None:
    samples = sorted([10, 20, 30, 40, 50])
    assert _percentile(samples, 100.0) == 50


def test_every_registered_bench_module_runs() -> None:
    """Smoke test: import every BENCH_MODULES entry and call its run()."""
    import importlib

    from tools.benchmarks.hot_paths.__main__ import BENCH_MODULES

    for mod_path in BENCH_MODULES:
        mod = importlib.import_module(mod_path)
        assert hasattr(mod, "run"), f"{mod_path} missing run()"
        results = mod.run()
        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            assert isinstance(r, BenchResult)


def test_measure_metadata_round_trips() -> None:
    meta = {"variants": 5, "seed": "0xCAFEBEEF", "note": "test"}
    r = measure("test.meta", lambda: None, iterations=5, metadata=meta)
    assert r.metadata == meta
