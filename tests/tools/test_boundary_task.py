"""
End-to-end tests for the boundary-task queue.

Uses a tmp ``ANTIEK_BOUNDARY_QUEUE_DB`` so each test gets a fresh
DuckDB file; goes through ``runtime.db_lock`` so the I-001 single-
writer property is exercised the same way it would be in
production.

Covers:

- ``queue`` validation (duration bounds, non-empty description)
- monotonic ``id`` assignment + ordering of ``status`` output
- ``pop`` returns oldest queued, leaves it in ``running`` state
- ``pop`` on empty queue returns None
- ``mark_done`` errors on non-running tasks
- ``cancel`` works for queued and running; idempotent on done/cancelled
- concurrent ``pop`` doesn't double-pop (two threads enter, only one
  gets the task)
- CLI subcommands round-trip via ``main()`` invocation
- markdown ``status`` output is well-formed

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e5-boundary-cli.html
"""

from __future__ import annotations

import io
import json
import os
import threading
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

from tools.boundary_task import store
from tools.boundary_task.__main__ import build_parser, main


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch) -> Path:
    """Isolated DuckDB queue per test."""
    p = tmp_path / "boundary.db"
    monkeypatch.setenv("ANTIEK_BOUNDARY_QUEUE_DB", str(p))
    return p


# ---------------------------------------------------------------------------
# queue() validation
# ---------------------------------------------------------------------------


def test_queue_rejects_blank_description(tmp_db: Path) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        store.queue("   ", 30)


def test_queue_rejects_under_minimum_duration(tmp_db: Path) -> None:
    with pytest.raises(ValueError, match="below"):
        store.queue("test", store.MIN_DURATION_MINUTES - 1)


def test_queue_rejects_over_maximum_duration(tmp_db: Path) -> None:
    with pytest.raises(ValueError, match="above"):
        store.queue("test", store.MAX_DURATION_MINUTES + 1)


def test_queue_returns_task_with_assigned_id(tmp_db: Path) -> None:
    t1 = store.queue("first", 30)
    t2 = store.queue("second", 45)
    assert t1.id == 1
    assert t2.id == 2
    assert t1.status == "queued"
    assert t1.description == "first"


def test_queue_trims_whitespace(tmp_db: Path) -> None:
    t = store.queue("  trimmed  ", 30)
    assert t.description == "trimmed"


# ---------------------------------------------------------------------------
# status() ordering and pop() FIFO
# ---------------------------------------------------------------------------


def test_status_returns_newest_first(tmp_db: Path) -> None:
    store.queue("a", 30)
    store.queue("b", 30)
    tasks = store.status()
    assert [t.description for t in tasks] == ["b", "a"]


def test_pop_returns_oldest_queued(tmp_db: Path) -> None:
    store.queue("a", 30)
    store.queue("b", 30)
    popped = store.pop()
    assert popped is not None
    assert popped.description == "a"  # FIFO — oldest first
    assert popped.status == "running"


def test_pop_returns_none_on_empty_queue(tmp_db: Path) -> None:
    assert store.pop() is None


def test_pop_skips_completed_tasks(tmp_db: Path) -> None:
    t1 = store.queue("a", 30)
    store.queue("b", 30)
    popped1 = store.pop()
    store.mark_done(popped1.id)
    popped2 = store.pop()
    assert popped2.description == "b"


# ---------------------------------------------------------------------------
# mark_done() and cancel()
# ---------------------------------------------------------------------------


def test_mark_done_errors_on_queued_task(tmp_db: Path) -> None:
    t = store.queue("a", 30)
    with pytest.raises(ValueError, match="expected 'running'"):
        store.mark_done(t.id)


def test_mark_done_errors_on_unknown_id(tmp_db: Path) -> None:
    with pytest.raises(KeyError):
        store.mark_done(9999)


def test_cancel_works_on_queued_task(tmp_db: Path) -> None:
    t = store.queue("a", 30)
    cancelled = store.cancel(t.id)
    assert cancelled.status == "cancelled"


def test_cancel_works_on_running_task(tmp_db: Path) -> None:
    store.queue("a", 30)
    popped = store.pop()
    cancelled = store.cancel(popped.id)
    assert cancelled.status == "cancelled"


def test_cancel_is_idempotent_on_done_task(tmp_db: Path) -> None:
    store.queue("a", 30)
    popped = store.pop()
    store.mark_done(popped.id)
    # No error, just a no-op.
    result = store.cancel(popped.id)
    assert result.status == "done"  # unchanged


def test_cancel_errors_on_unknown_id(tmp_db: Path) -> None:
    with pytest.raises(KeyError):
        store.cancel(9999)


# ---------------------------------------------------------------------------
# Concurrent pop — the load-bearing safety guarantee.
# ---------------------------------------------------------------------------


def test_concurrent_pop_does_not_double_pop(tmp_db: Path) -> None:
    """Two threads enter pop() at the same instant; only one wins.

    The flock from runtime.db_lock.connect_write serializes the
    transaction. We verify by counting how many threads got a real
    task back — exactly one must succeed; the other must get None
    (queue empty after the first pop committed).
    """
    store.queue("only-one", 30)
    barrier = threading.Barrier(2)
    results: list[store.BoundaryTask | None] = [None, None]

    def worker(slot: int) -> None:
        barrier.wait()
        results[slot] = store.pop()

    t1 = threading.Thread(target=worker, args=(0,))
    t2 = threading.Thread(target=worker, args=(1,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    got_task = [r for r in results if r is not None]
    assert len(got_task) == 1, (
        f"expected exactly one thread to pop the task; got {len(got_task)} "
        f"(double-pop indicates the flock is not serializing pop())"
    )


# ---------------------------------------------------------------------------
# CLI subcommands via main()
# ---------------------------------------------------------------------------


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def test_cli_queue_then_status(tmp_db: Path) -> None:
    code, out, _ = _run_cli(["queue", "find papers on", "X", "--duration=30"])
    assert code == 0
    assert "queued task id=1" in out
    code, out, _ = _run_cli(["status"])
    assert code == 0
    assert "find papers on X" in out


def test_cli_queue_then_pop_then_done(tmp_db: Path) -> None:
    _run_cli(["queue", "do thing", "--duration=30"])
    code, out, _ = _run_cli(["pop"])
    assert code == 0
    assert "popped task id=1" in out
    code, out, _ = _run_cli(["done", "1"])
    assert code == 0
    assert "marked task id=1 done" in out


def test_cli_status_handles_empty_queue(tmp_db: Path) -> None:
    code, out, _ = _run_cli(["status"])
    assert code == 0
    assert "no boundary tasks" in out


def test_cli_json_mode_emits_valid_json(tmp_db: Path) -> None:
    _run_cli(["queue", "x", "--duration=30"])
    code, out, _ = _run_cli(["--json", "status"])
    assert code == 0
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["description"] == "x"


def test_cli_queue_rejects_short_duration(tmp_db: Path) -> None:
    code, _, err = _run_cli(["queue", "x", f"--duration={store.MIN_DURATION_MINUTES - 1}"])
    assert code == 1
    assert "below" in err.lower()


def test_cli_done_on_unknown_task_returns_1(tmp_db: Path) -> None:
    code, _, err = _run_cli(["done", "9999"])
    assert code == 1
    assert "no boundary task" in err.lower()


def test_cli_cancel_on_queued_task(tmp_db: Path) -> None:
    _run_cli(["queue", "x", "--duration=30"])
    code, out, _ = _run_cli(["cancel", "1"])
    assert code == 0
    assert "cancelled" in out


# ---------------------------------------------------------------------------
# Parser sanity
# ---------------------------------------------------------------------------


def test_parser_requires_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_rejects_unknown_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])
