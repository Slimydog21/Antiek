"""Persistent rollover ledger (master-spec §9.5).

Backs the in-memory ``rev_share/rollover.py`` ``RolloverLedger`` with
a DuckDB-backed singleton row per recipient. Without persistence the
ledger dies on process restart and the operator loses the §9.5
accrual state.

The persistent shape mirrors ``RolloverEntry`` (minus the in-memory
history list — history reconstructs from ``payout_decisions`` rows
plus the operator's typed event log, which carries finer-grained
audit).

Schema chunk in ``substrate/graph/schema.py`` V6.

Two-way bridge:
  - ``load_ledger(con)`` materializes a ``RolloverLedger`` from
    persistent state. Use at process startup.
  - ``persist_ledger(con, ledger)`` flushes the in-memory ledger
    back to the table. Use after settlement passes.
"""

from __future__ import annotations

from typing import Any, Optional

from .rollover import RolloverEntry, RolloverLedger, RolloverState


def ensure_table(con: Any) -> None:
    """Defensive table create. Canonical schema in V6 chunk."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rollover_ledger (
                recipient_ref               TEXT PRIMARY KEY,
                balance_cents               INTEGER NOT NULL DEFAULT 0
                    CHECK (balance_cents >= 0),
                accrual_started_month       INTEGER,
                state                       TEXT NOT NULL DEFAULT 'accruing'
                    CHECK (state IN (
                        'accruing', 'notice_sent', 'settled', 'forfeited'
                    )),
                last_event_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def load_ledger(con: Any) -> RolloverLedger:
    """Materialize an in-memory ``RolloverLedger`` from the persistent
    ``rollover_ledger`` table. Empty table → empty ledger."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT recipient_ref, balance_cents, accrual_started_month,
               state,
               strftime(last_event_at, '%Y-%m-%dT%H:%M:%S')
        FROM rollover_ledger
        ORDER BY recipient_ref
        """
    ).fetchall()
    ledger = RolloverLedger()
    for r in rows:
        recipient_ref, balance, started, state, last_event = r
        entry = RolloverEntry(
            recipient_ref=recipient_ref,
            balance_cents=int(balance),
            accrual_started_month=(
                int(started) if started is not None else None
            ),
            state=RolloverState(state),
            last_event_at=last_event or "",
        )
        ledger.entries[recipient_ref] = entry
    return ledger


def persist_ledger(con: Any, ledger: RolloverLedger) -> None:
    """Flush every entry in the in-memory ledger back to the
    persistent table. Idempotent — UPSERTs by recipient_ref."""
    ensure_table(con)
    for recipient_ref, entry in ledger.entries.items():
        persist_entry(con, entry)


def persist_entry(con: Any, entry: RolloverEntry) -> None:
    """UPSERT one ``RolloverEntry``. The unique key is
    ``recipient_ref`` (single ledger row per recipient — history is
    in the typed event log)."""
    ensure_table(con)
    existing = con.execute(
        "SELECT 1 FROM rollover_ledger WHERE recipient_ref = ?",
        [entry.recipient_ref],
    ).fetchone()
    if existing is None:
        con.execute(
            """
            INSERT INTO rollover_ledger (
                recipient_ref, balance_cents, accrual_started_month,
                state
            ) VALUES (?, ?, ?, ?)
            """,
            [
                entry.recipient_ref, entry.balance_cents,
                entry.accrual_started_month, entry.state.value,
            ],
        )
    else:
        con.execute(
            """
            UPDATE rollover_ledger SET
                balance_cents = ?,
                accrual_started_month = ?,
                state = ?,
                last_event_at = CURRENT_TIMESTAMP
            WHERE recipient_ref = ?
            """,
            [
                entry.balance_cents, entry.accrual_started_month,
                entry.state.value, entry.recipient_ref,
            ],
        )


def load_balance_cents(con: Any, recipient_ref: str) -> int:
    """Read-only convenience for the creator-payouts endpoint."""
    ensure_table(con)
    row = con.execute(
        "SELECT balance_cents FROM rollover_ledger WHERE recipient_ref = ?",
        [recipient_ref],
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


__all__ = [
    "ensure_table",
    "load_balance_cents",
    "load_ledger",
    "persist_entry",
    "persist_ledger",
]
