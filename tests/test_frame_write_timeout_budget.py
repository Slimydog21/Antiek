"""Frame-telemetry write budget must cover a cold-connect queue ahead.

Incident class (2026-10-02): the arXiv bulk sync held the DuckDB write lock
at ~97% duty; PR #3653 made the sync honour the writer handoff. What remained:
once a queued API writer finally gets the in-process write gate, the writer
AHEAD of it may be paying a cold ``duckdb.connect`` inside its session
(~6.8s on the ~900MB prod store — ``runtime.db_lock.PROD_COLD_CONNECT_S``).
The second writer's budget is spent entirely on the gate wait, and it is
refused with ``WriteLockTimeout`` ("Could not acquire in-process write gate")
-> 503 ``ad_frame_writer_busy`` — with NO cross-process contention at all.

A SOLO cold writer is never refused (the connect itself is not
deadline-enforced); only a QUEUED writer loses. These tests pin both the
budget contract and that queue behaviour.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from interfaces.research.api import ad_routes
from runtime import db_lock


def test_frame_write_budget_covers_two_cold_connects() -> None:
    """Contract: a queued writer's budget must cover the full cold session
    ahead of it in the gate queue (connect + write + close) and still leave
    room for its own connect. 2 x the prod cold-connect figure is the floor.
    """
    assert ad_routes._FRAME_WRITE_TIMEOUT_S >= 2 * db_lock.PROD_COLD_CONNECT_S, (
        f"_FRAME_WRITE_TIMEOUT_S={ad_routes._FRAME_WRITE_TIMEOUT_S}s cannot "
        f"cover a writer queued behind one cold session "
        f"(2 x PROD_COLD_CONNECT_S={2 * db_lock.PROD_COLD_CONNECT_S:.1f}s); "
        "the queued writer 503s with no cross-process contention."
    )


def test_queued_writer_survives_a_prod_length_cold_session_ahead(
    tmp_path: Path,
) -> None:
    """Behavioural: writer A holds a real ``connect_write`` for one
    prod-length cold session (the test store's real connect is ~ms, so the
    hold simulates the documented prod cold connect); writer B, arriving
    behind A with the route's real budget, must be ACQUIRED — not refused.

    Red pre-fix: budget 5.0s < A's ~7.8s session -> B times out on the
    in-process write gate with zero cross-process contention.
    """
    db = str(tmp_path / "frame_budget.duckdb")
    # A's session length = prod cold connect + a small write/close margin.
    a_session_s = db_lock.PROD_COLD_CONNECT_S + 1.0
    outcome: dict[str, str] = {}

    def writer_a() -> None:
        with db_lock.connect_write(db, purpose="test/writer-A", timeout_s=30.0) as con:
            con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
            time.sleep(a_session_s)

    def writer_b() -> None:
        time.sleep(0.2)  # arrive while A holds the gate mid-session
        started = time.monotonic()
        try:
            with db_lock.connect_write(
                db,
                purpose="test/writer-B",
                timeout_s=ad_routes._FRAME_WRITE_TIMEOUT_S,
            ) as con:
                con.execute("INSERT INTO t VALUES (1)")
            outcome["B"] = f"acquired after {time.monotonic() - started:.2f}s"
        except db_lock.WriteLockTimeout as exc:
            outcome["B"] = f"refused after {time.monotonic() - started:.2f}s: {exc}"

    ta = threading.Thread(target=writer_a)
    tb = threading.Thread(target=writer_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()

    assert outcome["B"].startswith("acquired"), (
        "writer B was refused behind one prod-length cold session with no "
        f"cross-process contention: {outcome['B']}"
    )
