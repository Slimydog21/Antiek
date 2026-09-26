"""Publisher opt-in escrow accrual — the §9.10 servable-by-grant revenue source.

When a publisher submits their OWN catalog with a valid serving grant, the
opt-in intake lane (``acquisition.opt_in.intake``) ingests the work servable
(``opt_in_licensed``) and seeds escrow to the publisher's pre-onboarded
``ip_holder`` at intake — the acknowledgement that a servable opt-in work begins
accruing to its holder. This module is the SUBSTRATE-LAYER seam the intake lane
calls so the escrow write stays under ``substrate/`` with the other sanctioned
revenue sources (Speak's contributor split, Read's book/publisher escrow, the
per-second frame-attention border, the gated-mass-ingest accrual) — NOT a
cross-layer ``accrue_escrow`` call reaching out of ``acquisition/``.

It is a NEW sanctioned revenue SOURCE for the escrow ledger and routes through
the ONE low-level writer (``ip_holders.accrue_escrow``), never a second
escrow-balance writer (collision #3 / seam #3 invariant; see
``tests/test_seam_single_escrow_writer.py``). This module is added to
``_SANCTIONED_ESCROW_CALLERS`` there — the seam's intended path for a new
sanctioned source.

Escrow ACCRUES only — it never disburses. ``payout.py`` / ``stripe_connect``
are not imported here; whether the publisher receives the money is the separate
``claim`` -> Stripe Connect path, operator-gated on G2/G3. The caller passes a
connection from ``runtime.db_lock.connect_write`` (the single-writer lock) so
this participates in the writer transaction and never opens a second connection.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import accrue_escrow

# One row per (holder, work) ever seeded. The seed is once per work, but intake
# re-runs are routine (resubmission, grant flips, the corpus CLI has no
# already-ingested check) and the escrow column is a bare running sum, so the
# key has to live somewhere a re-run cannot reset. A staging ingest writes its
# rows into the staging DB; tools/merge_staging carries them into live together
# with the escrow balance of each holder it inserts.
SEED_LEDGER_TABLE = "opt_in_intake_seeds"
_SEED_LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {SEED_LEDGER_TABLE} (
    ip_holder_id  TEXT NOT NULL,
    document_id   TEXT NOT NULL,
    amount_usd    DECIMAL(18, 6) NOT NULL,
    seeded_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ip_holder_id, document_id)
)
"""


def ensure_seed_ledger(con: Any) -> None:
    """Create the seed ledger if this DB does not have it yet."""
    con.execute(_SEED_LEDGER_DDL)


def accrue_opt_in_escrow(
    con: Any, ip_holder_id: str, amount_usd: Decimal, *, document_id: str
) -> bool:
    """Accrue the opt-in intake seed to a granted publisher's holder, at most
    once per (``ip_holder_id``, ``document_id``). Returns True only when this
    call accrued.

    The thin seam ``acquisition.opt_in.intake.ingest_entry`` calls for a
    SERVABLE opt-in work. ``document_id`` is the content-hash id the ingest
    dedups on, so it is stable across re-runs and grant flips. The seed row and
    the escrow increment commit together (``con`` is a ``connect_write``
    connection): a failed increment leaves no row claiming the seed happened.
    Delegates to the ONE low-level writer (``ip_holders.accrue_escrow``), which
    rejects a non-positive amount and an unknown holder. Accrual only;
    disbursement stays operator-gated (G2/G3)."""
    ensure_seed_ledger(con)
    with con.transaction():
        inserted = con.execute(
            """
            INSERT INTO opt_in_intake_seeds (ip_holder_id, document_id, amount_usd)
            VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
            RETURNING ip_holder_id
            """,
            [ip_holder_id, document_id, str(amount_usd)],
        ).fetchall()
        if not inserted:
            return False
        accrue_escrow(con, ip_holder_id, amount_usd)
    return True


__all__ = ["SEED_LEDGER_TABLE", "accrue_opt_in_escrow", "ensure_seed_ledger"]
