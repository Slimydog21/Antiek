"""Tests for tools.antiek_cli.check.

Covers StageResult flags, parser shape, the skip behaviors of runners
whose backing files/dirs are missing, _run's tool-not-found fallback,
and the all-subcommand orchestration semantics. Mocks the underlying
runners — does not exercise real subprocesses.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.antiek_cli import __main__ as antiek_cli_main
from tools.antiek_cli.check import (
    ALL_ORDER,
    DEFAULT_SCOPE,
    RUNNERS,
    StageResult,
    _build_parser,
    _run,
    _run_all,
    main,
    run_invariants,
    run_perf,
    run_props,
)
from tools.benchmarks.hot_paths.compare import compare_runs


def test_stage_pass_flags() -> None:
    r = StageResult(name="t", rc=0, elapsed_s=0.5)
    assert r.is_pass and not r.is_fail and not r.is_skip


def test_stage_fail_flags() -> None:
    r = StageResult(name="t", rc=1, elapsed_s=0.5)
    assert r.is_fail and not r.is_pass


def test_stage_skip_flags() -> None:
    r = StageResult(name="t", rc=-1, elapsed_s=0.0, skipped_reason="x")
    assert r.is_skip and not r.is_pass and not r.is_fail


def test_format_pass() -> None:
    s = StageResult("lint", 0, 0.42).format_report_line()
    assert "lint" in s and "PASS" in s and "0.42s" in s


def test_format_fail() -> None:
    s = StageResult("types", 2, 1.10).format_report_line()
    assert "FAIL" in s


def test_format_skip() -> None:
    s = StageResult("props", -1, 0.0, skipped_reason="no dir").format_report_line()
    assert "SKIP" in s and "no dir" in s


def test_parser_subcommands() -> None:
    parser = _build_parser()
    for name in (*RUNNERS.keys(), "all"):
        args = parser.parse_args([name])
        assert args.cmd == name


def test_parser_default_scope() -> None:
    args = _build_parser().parse_args(["lint"])
    assert args.scope == DEFAULT_SCOPE


def test_parser_scope_override() -> None:
    args = _build_parser().parse_args(["types", "--scope", "substrate/x.py"])
    assert args.scope == "substrate/x.py"


def test_parser_strict() -> None:
    args = _build_parser().parse_args(["types", "--strict"])
    assert args.strict is True


def test_parser_all_continue_on_error() -> None:
    args = _build_parser().parse_args(["all", "--continue-on-error"])
    assert args.continue_on_error is True


def test_parser_perf_compare_args() -> None:
    args = _build_parser().parse_args(
        [
            "perf",
            "--baseline",
            "base.json",
            "--current",
            "head.json",
            "--max-regression-pct",
            "10",
        ]
    )
    assert args.cmd == "perf"
    assert args.baseline == "base.json"
    assert args.current == "head.json"
    assert args.max_regression_pct == 10.0


def test_parser_perf_default_regression_threshold() -> None:
    args = _build_parser().parse_args(["perf"])
    assert args.max_regression_pct == 25.0


def test_parser_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args([])


def test_run_invariants_skip_when_module_missing(tmp_path: Path) -> None:
    with patch("tools.antiek_cli.check.PROJECT_ROOT", tmp_path):
        r = run_invariants(scope="substrate/")
    assert r.is_skip


def test_run_props_skip_when_dir_missing(tmp_path: Path) -> None:
    with patch("tools.antiek_cli.check.PROJECT_ROOT", tmp_path):
        r = run_props(scope="substrate/")
    assert r.is_skip


def test_run_tool_not_found_rc_127() -> None:
    r = _run("missing", ["/nonexistent/binary/that/cannot/be/found"])
    assert r.rc == 127
    assert r.skipped_reason is not None


def test_run_all_all_pass(capsys) -> None:  # type: ignore[no-untyped-def]
    fake_pass = StageResult("x", 0, 0.1)
    fake = {n: (lambda s, strict=False, fp=fake_pass: fp) for n in ALL_ORDER}
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, False)
    assert rc == 0
    assert "overall PASS" in capsys.readouterr().out


def test_run_all_stops_on_first_fail() -> None:
    seen: list[str] = []

    def runner_for(name: str, fail: bool):  # type: ignore[no-untyped-def]
        def r(scope: str, strict: bool = False) -> StageResult:
            seen.append(name)
            return StageResult(name, 1 if fail else 0, 0.0)
        return r

    fake = {n: runner_for(n, n == "lint") for n in ALL_ORDER}
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, False)
    assert rc == 1
    assert seen == ["lint"]


def test_run_all_continue_on_error_runs_every_stage() -> None:
    seen: list[str] = []

    def runner_for(name: str, fail: bool):  # type: ignore[no-untyped-def]
        def r(scope: str, strict: bool = False) -> StageResult:
            seen.append(name)
            return StageResult(name, 1 if fail else 0, 0.0)
        return r

    fake = {n: runner_for(n, n == "lint") for n in ALL_ORDER}
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, True)
    assert rc == 1
    assert seen == list(ALL_ORDER)


def test_run_all_skip_is_not_a_fail(capsys) -> None:  # type: ignore[no-untyped-def]
    fake = {
        "lint": lambda s, strict=False: StageResult("lint", 0, 0.0),
        "types": lambda s, strict=False: StageResult("types", 0, 0.0),
        "tests": lambda s, strict=False: StageResult("tests", 0, 0.0),
        "doctest": lambda s, strict=False: StageResult("doctest", 0, 0.0),
        "props": lambda s, strict=False: StageResult("props", -1, 0.0,
                                                     skipped_reason="x"),
        "invariants": lambda s, strict=False: StageResult("invariants", 0, 0.0),
    }
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, False)
    assert rc == 0
    assert "1 skip" in capsys.readouterr().out


def test_main_returns_runner_rc() -> None:
    fake = lambda s, strict=False: StageResult("lint", 0, 0.0)  # noqa: E731
    with patch.dict("tools.antiek_cli.check.RUNNERS", {"lint": fake}, clear=False):
        assert main(["lint"]) == 0


def test_main_returns_fail_rc() -> None:
    fake = lambda s, strict=False: StageResult("lint", 2, 0.0)  # noqa: E731
    with patch.dict("tools.antiek_cli.check.RUNNERS", {"lint": fake}, clear=False):
        assert main(["lint"]) == 2


def test_main_skip_returns_zero() -> None:
    fake = lambda s, strict=False: StageResult(  # noqa: E731
        "props", -1, 0.0, skipped_reason="x")
    with patch.dict("tools.antiek_cli.check.RUNNERS", {"props": fake}, clear=False):
        assert main(["props"]) == 0


def _bench_run(path: Path, bench_name: str, *, median: int, p95: int, p99: int) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "bench_name": bench_name,
                    "iterations": 100,
                    "median_ns": median,
                    "p95_ns": p95,
                    "p99_ns": p99,
                    "min_ns": median,
                    "max_ns": p99,
                    "total_wall_s": 0.1,
                    "timestamp_utc": "2026-07-01T00:00:00+00:00",
                    "python_version": "3.12",
                    "platform": "test",
                    "metadata": {},
                }
            ]
        ),
        encoding="utf-8",
    )


def test_perf_compare_passes_when_within_threshold(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _bench_run(baseline, "bench.a", median=100, p95=150, p99=200)
    _bench_run(current, "bench.a", median=110, p95=160, p99=210)

    rc = main(
        [
            "perf",
            "--baseline",
            str(baseline),
            "--current",
            str(current),
            "--max-regression-pct",
            "20",
        ]
    )

    assert rc == 0
    assert "Perf comparison PASS" in capsys.readouterr().out


def test_perf_compare_fails_on_regression(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _bench_run(baseline, "bench.a", median=100, p95=150, p99=200)
    _bench_run(current, "bench.a", median=140, p95=160, p99=210)

    rc = main(
        [
            "perf",
            "--baseline",
            str(baseline),
            "--current",
            str(current),
            "--max-regression-pct",
            "20",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 1
    assert "Perf regressions:" in out
    assert "bench.a median_ns" in out


def test_perf_compare_requires_paired_paths(tmp_path: Path) -> None:
    result = run_perf("substrate/", baseline=str(tmp_path / "baseline.json"))
    assert result.rc == 2
    assert result.skipped_reason == "--baseline and --current must be passed together"

    result = run_perf("substrate/", current=str(tmp_path / "current.json"))
    assert result.rc == 2
    assert result.skipped_reason == "--baseline and --current must be passed together"


def test_perf_compare_rejects_negative_threshold(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _bench_run(baseline, "bench.a", median=100, p95=150, p99=200)
    _bench_run(current, "bench.a", median=90, p95=140, p99=190)

    result = run_perf(
        "substrate/",
        baseline=str(baseline),
        current=str(current),
        max_regression_pct=-1,
    )
    assert result.rc == 2
    assert result.skipped_reason == "--max-regression-pct must be >= 0"


def test_compare_runs_reports_median_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _bench_run(baseline, "bench.a", median=100, p95=150, p99=200)
    _bench_run(current, "bench.a", median=130, p95=150, p99=200)

    findings = compare_runs(baseline, current, max_regression_pct=20)
    assert [f.metric for f in findings] == ["median_ns"]
    assert findings[0].regression_pct == 30.0


def test_compare_runs_reports_tail_metric_regressions(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _bench_run(baseline, "bench.a", median=100, p95=150, p99=200)
    _bench_run(current, "bench.a", median=100, p95=210, p99=260)

    findings = compare_runs(baseline, current, max_regression_pct=20)
    assert [f.metric for f in findings] == ["p95_ns", "p99_ns"]


def test_compare_runs_rejects_missing_baseline_bench(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _bench_run(baseline, "bench.a", median=100, p95=150, p99=200)
    _bench_run(current, "bench.b", median=100, p95=150, p99=200)

    with pytest.raises(ValueError, match="missing benchmark"):
        compare_runs(baseline, current, max_regression_pct=20)


def test_compare_runs_rejects_duplicate_bench_names(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    row = {
        "bench_name": "bench.a",
        "iterations": 100,
        "median_ns": 100,
        "p95_ns": 150,
        "p99_ns": 200,
        "min_ns": 90,
        "max_ns": 210,
        "total_wall_s": 0.1,
        "timestamp_utc": "2026-07-01T00:00:00+00:00",
        "python_version": "3.12",
        "platform": "test",
        "metadata": {},
    }
    baseline.write_text(json.dumps([row, row]), encoding="utf-8")
    current.write_text(json.dumps([row]), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate benchmark"):
        compare_runs(baseline, current, max_regression_pct=20)


def test_compare_runs_rejects_missing_metric(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _bench_run(baseline, "bench.a", median=100, p95=150, p99=200)
    current.write_text(
        json.dumps(
            [
                {
                    "bench_name": "bench.a",
                    "iterations": 100,
                    "median_ns": 100,
                    "p95_ns": 150,
                    "min_ns": 90,
                    "max_ns": 210,
                    "total_wall_s": 0.1,
                    "timestamp_utc": "2026-07-01T00:00:00+00:00",
                    "python_version": "3.12",
                    "platform": "test",
                    "metadata": {},
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing p99_ns"):
        compare_runs(baseline, current, max_regression_pct=20)


def test_perf_compare_bad_path_returns_usage_error(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "missing.json"
    current = tmp_path / "current.json"
    _bench_run(current, "bench.a", median=100, p95=150, p99=200)

    rc = main(
        [
            "perf",
            "--baseline",
            str(baseline),
            "--current",
            str(current),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 2
    assert "Perf comparison error:" in out


def test_package_entrypoint_accepts_documented_check_namespace() -> None:
    seen: list[list[str]] = []

    def fake_check_main(argv: list[str] | None = None) -> int:
        seen.append(list(argv or []))
        return 0

    with patch("tools.antiek_cli.__main__.check_main", fake_check_main):
        assert antiek_cli_main.main(["check", "props"]) == 0

    assert seen == [["props"]]


def test_package_entrypoint_keeps_direct_subcommand_alias() -> None:
    seen: list[list[str]] = []

    def fake_check_main(argv: list[str] | None = None) -> int:
        seen.append(list(argv or []))
        return 0

    with patch("tools.antiek_cli.__main__.check_main", fake_check_main):
        assert antiek_cli_main.main(["props"]) == 0

    assert seen == [["props"]]
