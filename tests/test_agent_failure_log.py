"""
Unit tests for ``orchestration.agent_failure_log``.

Covers:

- ``AgentFailure`` JSON-line serialization (round-trips).
- ``record()`` appends atomically; concurrent writes from threads
  don't tear (the POSIX O_APPEND contract is the load-bearing
  guarantee; we exercise it).
- Daily rotation: a file whose first record is from yesterday
  is moved aside on the first write of today.
- ``iter_records()`` is tolerant of malformed lines.
- ``recent_failures(since_days=N)`` filters correctly.
- ``log_path()`` honors ``ANTIEK_AGENT_FAILURE_LOG`` env override.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from orchestration.agent_failure_log import (
    DEFAULT_LOG_PATH,
    AgentFailure,
    _archive_dir_for,
    iter_records,
    log_path,
    recent_failures,
    record,
)

# ---------------------------------------------------------------------------
# AgentFailure serialization
# ---------------------------------------------------------------------------


def test_to_json_line_is_single_newline_terminated() -> None:
    fx = AgentFailure(failure_id="x", failure_type="foo")
    line = fx.to_json_line()
    assert line.endswith("\n")
    assert line.count("\n") == 1


def test_to_json_line_round_trips_through_json_loads() -> None:
    fx = AgentFailure(
        failure_id="round-trip",
        agent="claude",
        phase="synthesis",
        failure_type="timeout",
        context_summary="hello",
        regression_fixture_path="tests/regression/agent_failures/round-trip.yaml",
    )
    line = fx.to_json_line()
    row = json.loads(line)
    assert row["failure_id"] == "round-trip"
    assert row["agent"] == "claude"
    assert row["regression_fixture_path"] == "tests/regression/agent_failures/round-trip.yaml"
    assert row["prompt_hash"] is None  # default → null in JSON


def test_default_observed_at_is_iso_z_format() -> None:
    fx = AgentFailure(failure_id="x")
    assert fx.observed_at.endswith("Z")
    # Year-month-day boundaries at canonical positions.
    assert fx.observed_at[4] == "-" and fx.observed_at[7] == "-"


# ---------------------------------------------------------------------------
# log_path() and ANTIEK_AGENT_FAILURE_LOG env override
# ---------------------------------------------------------------------------


def test_log_path_defaults_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("ANTIEK_AGENT_FAILURE_LOG", raising=False)
    assert log_path() == DEFAULT_LOG_PATH


def test_log_path_honors_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTIEK_AGENT_FAILURE_LOG", str(tmp_path / "custom.jsonl"))
    assert log_path() == tmp_path / "custom.jsonl"


def test_log_path_expands_tilde(monkeypatch) -> None:
    monkeypatch.setenv("ANTIEK_AGENT_FAILURE_LOG", "~/custom.jsonl")
    p = log_path()
    assert str(p).startswith(str(Path.home()))


# ---------------------------------------------------------------------------
# record() — single + concurrent
# ---------------------------------------------------------------------------


def test_record_writes_one_line(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    fx = AgentFailure(failure_id="solo")
    out = record(fx, path=p)
    assert out == p
    text = p.read_text(encoding="utf-8")
    assert text.count("\n") == 1
    row = json.loads(text.strip())
    assert row["failure_id"] == "solo"


def test_record_appends_not_overwrites(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    record(AgentFailure(failure_id="first"), path=p)
    record(AgentFailure(failure_id="second"), path=p)
    lines = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()]
    assert [r["failure_id"] for r in lines] == ["first", "second"]


def test_record_concurrent_writes_dont_tear(tmp_path: Path) -> None:
    """Spin N threads, each appends M records. End state: N*M lines,
    each parses as JSON, no torn writes mid-line.

    The POSIX guarantee: writes ≤ PIPE_BUF (≥512 bytes) issued with
    O_APPEND are atomic. Our records well under that. Threads share
    one process so the kernel level contention is the test.
    """
    p = tmp_path / "log.jsonl"
    N_THREADS = 8
    N_PER = 50
    barrier = threading.Barrier(N_THREADS)

    def worker(i: int) -> None:
        barrier.wait()
        for j in range(N_PER):
            record(
                AgentFailure(
                    failure_id=f"thread-{i}-record-{j}",
                    context_summary="x" * 50,  # keep the line under PIPE_BUF
                ),
                path=p,
            )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    text = p.read_text(encoding="utf-8")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    assert len(lines) == N_THREADS * N_PER
    # Every line must round-trip as JSON. A torn line would fail here.
    for ln in lines:
        row = json.loads(ln)
        assert "failure_id" in row


# ---------------------------------------------------------------------------
# iter_records() tolerance
# ---------------------------------------------------------------------------


def test_iter_records_returns_empty_when_file_absent(tmp_path: Path) -> None:
    assert list(iter_records(tmp_path / "nothing.jsonl")) == []


def test_iter_records_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    p.write_text(
        '{"failure_id": "ok-1"}\n'
        'this-is-not-json\n'
        '{"failure_id": "ok-2"}\n'
        '\n'  # blank line — also skipped
        '{"failure_id": "ok-3"}\n',
        encoding="utf-8",
    )
    ids = [r.failure_id for r in iter_records(p)]
    assert ids == ["ok-1", "ok-2", "ok-3"]


def test_iter_records_yields_typed_AgentFailure(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    record(AgentFailure(failure_id="typed", agent="claude"), path=p)
    rows = list(iter_records(p))
    assert len(rows) == 1
    assert isinstance(rows[0], AgentFailure)
    assert rows[0].agent == "claude"


# ---------------------------------------------------------------------------
# recent_failures() window filtering
# ---------------------------------------------------------------------------


def test_recent_failures_filters_by_window(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    now = datetime.now(UTC)
    old = (now - timedelta(days=30)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    recent = (now - timedelta(hours=2)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    p.write_text(
        json.dumps({"failure_id": "old", "observed_at": old}) + "\n"
        + json.dumps({"failure_id": "recent", "observed_at": recent}) + "\n",
        encoding="utf-8",
    )
    last_week = recent_failures(since_days=7, path=p)
    ids = [r.failure_id for r in last_week]
    assert ids == ["recent"]


def test_recent_failures_rejects_negative_window(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    with pytest.raises(ValueError):
        recent_failures(since_days=-1, path=p)


# ---------------------------------------------------------------------------
# Daily rotation
# ---------------------------------------------------------------------------


def test_rotation_archives_yesterday_file_on_first_write_today(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    yesterday = (datetime.now(UTC) - timedelta(days=2)).date()
    yesterday_iso = (
        datetime.combine(yesterday, datetime.min.time())
        .replace(tzinfo=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    # Write an "old" line directly.
    p.write_text(
        json.dumps({"failure_id": "yesterday", "observed_at": yesterday_iso}) + "\n",
        encoding="utf-8",
    )
    # Now record today's first.
    record(AgentFailure(failure_id="today"), path=p)
    # The current active file should contain only today's.
    active_text = p.read_text(encoding="utf-8")
    assert "yesterday" not in active_text
    assert "today" in active_text
    # And the archive should hold yesterday.
    archive = _archive_dir_for(p) / f"{yesterday}.jsonl"
    assert archive.exists()
    assert "yesterday" in archive.read_text(encoding="utf-8")


def test_rotation_no_op_when_file_is_empty(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    p.touch()
    record(AgentFailure(failure_id="single"), path=p)
    # No archive directory should have been created.
    assert not _archive_dir_for(p).exists()
    assert "single" in p.read_text(encoding="utf-8")


def test_rotation_appends_to_existing_archive_if_present(tmp_path: Path) -> None:
    """If the rotation target already exists (clock skew, manual
    restore), the rotator appends rather than overwrites."""
    p = tmp_path / "log.jsonl"
    yesterday = (datetime.now(UTC) - timedelta(days=2)).date()
    yesterday_iso = (
        datetime.combine(yesterday, datetime.min.time())
        .replace(tzinfo=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    # Pre-existing archive for the same date.
    archive_dir = _archive_dir_for(p)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_file = archive_dir / f"{yesterday}.jsonl"
    archive_file.write_text(
        json.dumps({"failure_id": "preexisting"}) + "\n", encoding="utf-8"
    )
    # Active file with a record from yesterday → triggers rotation.
    p.write_text(
        json.dumps({"failure_id": "yesterday-new", "observed_at": yesterday_iso}) + "\n",
        encoding="utf-8",
    )
    record(AgentFailure(failure_id="today-fresh"), path=p)
    # Archive now contains both.
    text = archive_file.read_text(encoding="utf-8")
    assert "preexisting" in text and "yesterday-new" in text
    # Active contains today.
    assert "today-fresh" in p.read_text(encoding="utf-8")
