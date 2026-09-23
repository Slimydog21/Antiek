"""Unit tests for the capacity-probe harness helpers (SPR-09).

The unit tests are pure: no network, no server, no DuckDB — they pin the
pure helpers (percentile, ps parser, wait-log parser, CLI spec parser,
exit-code rule) that the harness leans on for honest numbers.

One integration test runs the real harness against a real local server;
it is skipped unless ``ANTIEK_RUN_CAPACITY_PROBE=1`` because it spends
~30s of real time (server boot + 2s window) and is not meant for the
normal suite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.capacity_probe import (
    exit_code_for_runs,
    parse_concurrency_spec,
    parse_ps_line,
    parse_wait_log_text,
    percentile,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_INTEGRATION = os.environ.get("ANTIEK_RUN_CAPACITY_PROBE") == "1"


def test_percentile_known_inputs() -> None:
    vals = [float(i) for i in range(1, 101)]
    assert percentile(vals, 50) == 50.0
    assert percentile(vals, 95) == 95.0
    assert percentile(vals, 99) == 99.0


def test_percentile_edges() -> None:
    assert percentile([], 50) is None
    assert percentile([7.0], 95) == 7.0
    # Unsorted input is tolerated (helper sorts internally).
    assert percentile(list(reversed(range(1, 101))), 50) == 50.0


def test_parse_ps_line() -> None:
    # ps -o %cpu=,rss= -p <pid>: cpu percent, rss in KiB -> MB.
    assert parse_ps_line("  12.5  123456") == (12.5, 123456 / 1024)
    assert parse_ps_line("0.0 512\n") == (0.0, 0.5)
    # Process gone / header noise / garbage -> None, never a crash.
    assert parse_ps_line("") is None
    assert parse_ps_line("garbage line") is None


def test_parse_wait_log_text() -> None:
    text = (
        '{"purpose": "speak/api:list_projects", "wait_s": 0.012, "ok": true}\n'
        "\n"
        "not json at all\n"
        '{"purpose": "compute-capacity:gate", "wait_s": 300.1, "ok": false}\n'
    )
    rows = parse_wait_log_text(text)
    assert rows == [
        {"purpose": "speak/api:list_projects", "wait_s": 0.012, "ok": True},
        {"purpose": "compute-capacity:gate", "wait_s": 300.1, "ok": False},
    ]
    # Records without a numeric wait_s are dropped, not coerced.
    assert parse_wait_log_text('{"purpose": "x"}\n') == []
    assert parse_wait_log_text("") == []


def test_parse_concurrency_spec() -> None:
    assert parse_concurrency_spec("1,5,25") == [1, 5, 25]
    assert parse_concurrency_spec(" 3 ") == [3]
    assert parse_concurrency_spec("1,,2") == [1, 2]


def test_parse_concurrency_spec_rejects() -> None:
    with pytest.raises(ValueError, match="invalid concurrency level"):
        parse_concurrency_spec("a,b")
    with pytest.raises(ValueError, match=">= 1"):
        parse_concurrency_spec("0")
    with pytest.raises(ValueError, match="at least one"):
        parse_concurrency_spec("")


def test_exit_code_zero_when_reads_completed() -> None:
    assert exit_code_for_runs([]) == 0
    assert exit_code_for_runs([{"requests_completed": 10}]) == 0
    assert (
        exit_code_for_runs([{"requests_completed": 10}, {"requests_completed": 3}]) == 0
    )


def test_exit_code_one_on_zero_completed_reads() -> None:
    runs = [{"requests_completed": 10}, {"requests_completed": 0}]
    assert exit_code_for_runs(runs) == 1
    # Missing key counts as zero: a run dict without evidence is not a
    # measurement either.
    assert exit_code_for_runs([{}]) == 1


@pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="set ANTIEK_RUN_CAPACITY_PROBE=1 to run the local-server integration test",
)
def test_capacity_probe_harness_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "cap.json"
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and k != "PYTEST_CURRENT_TEST"
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "benchmarks" / "capacity_probe.py"),
            "--concurrency",
            "1",
            "--duration-s",
            "2",
            "--out",
            str(out),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["runs"]) == 1
    assert data["runs"][0]["requests_completed"] > 0
