"""Regression coverage for DuckDB write-lock retry coordination."""

from __future__ import annotations

import pytest

from runtime import db_lock


def test_connect_write_retrying_succeeds_after_transient_timeouts(monkeypatch):
    sentinel = object()
    calls: list[dict[str, object]] = []
    sleeps: list[float] = []

    def fake_connect_write(db_path: str, **kwargs):
        calls.append({"db_path": db_path, **kwargs})
        if len(calls) < 3:
            raise db_lock.WriteLockTimeout(f"busy-{len(calls)}")
        return sentinel

    monkeypatch.setattr(db_lock, "connect_write", fake_connect_write)
    monkeypatch.setattr(db_lock.time, "sleep", sleeps.append)

    result = db_lock.connect_write_retrying(
        "graph.duckdb",
        timeout_s=1.5,
        poll_interval_s=0.05,
        max_retries=3,
        retry_delay_s=2.0,
        purpose="daily_ingest",
    )

    assert result is sentinel
    assert sleeps == [2.0, 2.0]
    assert calls == [
        {
            "db_path": "graph.duckdb",
            "timeout_s": 1.5,
            "poll_interval_s": 0.05,
            "purpose": "daily_ingest",
        },
        {
            "db_path": "graph.duckdb",
            "timeout_s": 1.5,
            "poll_interval_s": 0.05,
            "purpose": "daily_ingest",
        },
        {
            "db_path": "graph.duckdb",
            "timeout_s": 1.5,
            "poll_interval_s": 0.05,
            "purpose": "daily_ingest",
        },
    ]


def test_connect_write_retrying_raises_chained_timeout_after_exhaustion(monkeypatch):
    attempts = 0
    sleeps: list[float] = []

    def fake_connect_write(db_path: str, **kwargs):
        nonlocal attempts
        attempts += 1
        raise db_lock.WriteLockTimeout(f"still busy for {db_path}")

    monkeypatch.setattr(db_lock, "connect_write", fake_connect_write)
    monkeypatch.setattr(db_lock.time, "sleep", sleeps.append)

    with pytest.raises(db_lock.WriteLockTimeout) as exc_info:
        db_lock.connect_write_retrying(
            "cron.duckdb",
            timeout_s=7.0,
            poll_interval_s=0.25,
            max_retries=2,
            retry_delay_s=3.0,
            purpose="weekly_monitor",
        )

    assert attempts == 3
    assert sleeps == [3.0, 3.0]
    assert "after 3 attempts" in str(exc_info.value)
    assert "(27s total wait budget)" in str(exc_info.value)
    assert "Last error: still busy for cron.duckdb" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, db_lock.WriteLockTimeout)


def test_connect_write_retrying_zero_retries_fails_without_sleep(monkeypatch):
    sleeps: list[float] = []

    def fake_connect_write(db_path: str, **kwargs):
        raise db_lock.WriteLockTimeout("busy once")

    monkeypatch.setattr(db_lock, "connect_write", fake_connect_write)
    monkeypatch.setattr(db_lock.time, "sleep", sleeps.append)

    with pytest.raises(db_lock.WriteLockTimeout) as exc_info:
        db_lock.connect_write_retrying(
            "manual.duckdb",
            max_retries=0,
            retry_delay_s=9.0,
        )

    assert sleeps == []
    assert "after 1 attempt" in str(exc_info.value)


def test_connect_write_retrying_rejects_negative_retries():
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        db_lock.connect_write_retrying("manual.duckdb", max_retries=-1)


def test_connect_write_retrying_does_not_retry_non_lock_errors(monkeypatch):
    attempts = 0
    sleeps: list[float] = []

    def fake_connect_write(db_path: str, **kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError("disk unavailable")

    monkeypatch.setattr(db_lock, "connect_write", fake_connect_write)
    monkeypatch.setattr(db_lock.time, "sleep", sleeps.append)

    with pytest.raises(OSError, match="disk unavailable"):
        db_lock.connect_write_retrying(
            "manual.duckdb",
            max_retries=3,
            retry_delay_s=9.0,
        )

    assert attempts == 1
    assert sleeps == []
