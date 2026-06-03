"""Tests for the antiek check perf subcommand (run_perf).

Separate test file so it can ship in the same commit as the perf
runner without touching tests/test_antiek_cli.py (already committed
in 63f857c; parallel-stream tooling occasionally rewrites it).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tools.antiek_cli.check import run_perf


def test_run_perf_skip_when_harness_main_missing(tmp_path: Path) -> None:
    """When tools/benchmarks/hot_paths/__main__.py is absent on this
    branch (e.g., parallel-stream branch without the harness), the
    perf stage skips cleanly rather than failing."""
    with patch("tools.antiek_cli.check.PROJECT_ROOT", tmp_path):
        result = run_perf(scope="substrate/")
    assert result.is_skip
    assert "hot_paths" in (result.skipped_reason or "")


def test_run_perf_is_in_runners_registry() -> None:
    """The perf subcommand must be registered in RUNNERS so the parser
    auto-picks it up."""
    from tools.antiek_cli.check import RUNNERS
    assert "perf" in RUNNERS


def test_run_perf_is_not_in_all_order() -> None:
    """perf intentionally runs on a different cadence than correctness
    checks; `antiek check all` should NOT trigger it. Invoke explicitly."""
    from tools.antiek_cli.check import ALL_ORDER
    assert "perf" not in ALL_ORDER


def test_perf_appears_in_parser_subcommands() -> None:
    from tools.antiek_cli.check import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["perf"])
    assert args.cmd == "perf"


def test_perf_accepts_scope_and_strict_flags_like_other_subcommands() -> None:
    from tools.antiek_cli.check import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["perf", "--scope", "substrate/", "--strict"])
    assert args.scope == "substrate/"
    assert args.strict is True
