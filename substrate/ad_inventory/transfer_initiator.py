"""Stripe Connect transfer initiator (master-spec §13.5 + §9.10 + §13.7).

Consumes ``RevShareDecision`` records emitted by the PayoutRouter and
drives them through the Stripe Connect provider with persistent
status tracking. Per the binding master-spec invariants:

  - §9.10 publisher escrow: ``requires_escrow=True`` decisions DO NOT
    transfer — they accrue in substrate-side escrow until the
    publisher claims. The initiator records ``skipped_escrow`` for
    these.
  - §13.5 platform residual: PLATFORM-kind decisions don't transfer
    (Stripe holds the residual after creator/publisher transfers).
    Recorded as ``skipped_platform``.
  - Idempotency: the ``decision_id`` rides as the Stripe
    idempotency_key. Re-running the initiator with the same decision
    is safe; the second attempt returns the original transfer id.
  - Single-writer: writes go through a ``LockedConnection`` from
    ``runtime.db_lock.connect_write``.

Status state machine:
  pending → transferred | skipped_escrow | skipped_platform | failed

The initiator NEVER catches & swallows provider exceptions silently —
``failed`` rows carry the exception message for operator triage.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from tools.stripe_connect.providers import StripeProvider

from .payout import RevShareDecision, RevShareKind


class TransferInitiatorError(Exception):
    """Surfaces structural issues — schema missing, recipient unknown,
    etc. Provider-level errors land in the ``failed`` row instead."""


# Status literals — also enforced at the SQL CHECK level.
STATUS_PENDING: str = "pending"
STATUS_TRANSFERRED: str = "transferred"
STATUS_SKIPPED_ESCROW: str = "skipped_escrow"
STATUS_SKIPPED_PLATFORM: str = "skipped_platform"
STATUS_FAILED: str = "failed"


@dataclass(frozen=True)
class TransferOutcome:
    """One row from the initiator's persistent transfer log."""

    transfer_attempt_id: str
    decision_id: str
    stripe_transfer_id: str | None
    recipient_account_id: str | None
    amount_usd_cents: int
    status: str
    note: str
    initiated_at: str


def ensure_table(con: Any) -> None:
    """Defensive table-creation. The canonical schema definition lives
    in ``substrate/graph/schema.py``; this is a no-op on a fully-
    initialized DB. Read-only connections fail silently."""
    with suppress(Exception):
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS payout_transfers (
                transfer_attempt_id     TEXT PRIMARY KEY,
                decision_id             TEXT NOT NULL UNIQUE,
                stripe_transfer_id      TEXT,
                recipient_account_id    TEXT,
                amount_usd_cents        INTEGER NOT NULL,
                status                  TEXT NOT NULL CHECK (status IN (
                    'pending', 'transferred', 'skipped_escrow',
                    'skipped_platform', 'failed'
                )),
                note                    TEXT,
                initiated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    with suppress(Exception):
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_payout_transfers_decision_unique "
            "ON payout_transfers(decision_id)"
        )


def _record(
    con: Any,
    *,
    decision_id: str,
    stripe_transfer_id: str | None,
    recipient_account_id: str | None,
    amount_usd_cents: int,
    status: str,
    note: str,
    allow_existing_mismatch: bool = False,
) -> TransferOutcome:
    """Insert one transfer-log row. Idempotent on ``decision_id`` —
    if a row already exists for that decision, the existing outcome
    is returned and the insert is skipped. Re-runs are safe."""
    ensure_table(con)
    existing = con.execute(
        "SELECT transfer_attempt_id, stripe_transfer_id, recipient_account_id, "
        "amount_usd_cents, status, note, initiated_at "
        "FROM payout_transfers WHERE decision_id = ?",
        [decision_id],
    ).fetchone()
    if existing is not None:
        if not _existing_matches_attempt(
            existing,
            stripe_transfer_id=stripe_transfer_id,
            recipient_account_id=recipient_account_id,
            amount_usd_cents=amount_usd_cents,
            status=status,
            note=note,
        ):
            if _can_upgrade_failed_to_transferred(
                existing,
                recipient_account_id=recipient_account_id,
                amount_usd_cents=amount_usd_cents,
                status=status,
            ):
                return _upgrade_failed_to_transferred(
                    con,
                    decision_id=decision_id,
                    existing=existing,
                    stripe_transfer_id=stripe_transfer_id,
                    recipient_account_id=recipient_account_id,
                    amount_usd_cents=amount_usd_cents,
                    note=note,
                )
            if allow_existing_mismatch:
                return _existing_outcome(decision_id, existing)
            raise TransferInitiatorError(
                f"decision {decision_id!r} already has a different "
                "transfer outcome"
            )
        return _existing_outcome(decision_id, existing)

    attempt_id = f"xfer-{uuid.uuid4().hex[:12]}"
    try:
        con.execute(
            """
            INSERT INTO payout_transfers (
                transfer_attempt_id, decision_id, stripe_transfer_id,
                recipient_account_id, amount_usd_cents, status, note,
                initiated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                attempt_id, decision_id, stripe_transfer_id,
                recipient_account_id, amount_usd_cents, status, note,
            ],
        )
    except Exception as exc:
        raced = con.execute(
            "SELECT transfer_attempt_id, stripe_transfer_id, recipient_account_id, "
            "amount_usd_cents, status, note, initiated_at "
            "FROM payout_transfers WHERE decision_id = ?",
            [decision_id],
        ).fetchone()
        if raced is not None:
            if not _existing_matches_attempt(
                raced,
                stripe_transfer_id=stripe_transfer_id,
                recipient_account_id=recipient_account_id,
                amount_usd_cents=amount_usd_cents,
                status=status,
                note=note,
            ):
                if _can_upgrade_failed_to_transferred(
                    raced,
                    recipient_account_id=recipient_account_id,
                    amount_usd_cents=amount_usd_cents,
                    status=status,
                ):
                    return _upgrade_failed_to_transferred(
                        con,
                        decision_id=decision_id,
                        existing=raced,
                        stripe_transfer_id=stripe_transfer_id,
                        recipient_account_id=recipient_account_id,
                        amount_usd_cents=amount_usd_cents,
                        note=note,
                    )
                if allow_existing_mismatch:
                    return _existing_outcome(decision_id, raced)
                raise TransferInitiatorError(
                    f"decision {decision_id!r} was recorded concurrently "
                    "with a different transfer outcome"
                ) from exc
            return _existing_outcome(decision_id, raced)
        raise
    return TransferOutcome(
        transfer_attempt_id=attempt_id,
        decision_id=decision_id,
        stripe_transfer_id=stripe_transfer_id,
        recipient_account_id=recipient_account_id,
        amount_usd_cents=amount_usd_cents,
        status=status,
        note=note,
        initiated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def _existing_outcome(decision_id: str, row: tuple) -> TransferOutcome:
    return TransferOutcome(
        transfer_attempt_id=row[0],
        decision_id=decision_id,
        stripe_transfer_id=row[1],
        recipient_account_id=row[2],
        amount_usd_cents=int(row[3]),
        status=row[4],
        note=row[5] or "",
        initiated_at=(
            row[6].isoformat() if hasattr(row[6], "isoformat")
            else str(row[6])
        ),
    )


def _existing_matches_attempt(
    row: tuple,
    *,
    stripe_transfer_id: str | None,
    recipient_account_id: str | None,
    amount_usd_cents: int,
    status: str,
    note: str,
) -> bool:
    return (
        row[1] == stripe_transfer_id
        and row[2] == recipient_account_id
        and int(row[3]) == amount_usd_cents
        and row[4] == status
        and (row[5] or "") == note
    )


def _can_upgrade_failed_to_transferred(
    row: tuple,
    *,
    recipient_account_id: str | None,
    amount_usd_cents: int,
    status: str,
) -> bool:
    return (
        row[4] == STATUS_FAILED
        and status == STATUS_TRANSFERRED
        and row[2] == recipient_account_id
        and int(row[3]) == amount_usd_cents
    )


def _upgrade_failed_to_transferred(
    con: Any,
    *,
    decision_id: str,
    existing: tuple,
    stripe_transfer_id: str | None,
    recipient_account_id: str | None,
    amount_usd_cents: int,
    note: str,
) -> TransferOutcome:
    if stripe_transfer_id is None:
        raise TransferInitiatorError(
            f"decision {decision_id!r} retry cannot upgrade failed transfer "
            "without a Stripe transfer id"
        )
    con.execute(
        """
        UPDATE payout_transfers
        SET stripe_transfer_id = ?,
            recipient_account_id = ?,
            amount_usd_cents = ?,
            status = ?,
            note = ?,
            initiated_at = CURRENT_TIMESTAMP
        WHERE decision_id = ? AND status = ?
        """,
        [
            stripe_transfer_id,
            recipient_account_id,
            amount_usd_cents,
            STATUS_TRANSFERRED,
            note,
            decision_id,
            STATUS_FAILED,
        ],
    )
    row = con.execute(
        "SELECT transfer_attempt_id, stripe_transfer_id, recipient_account_id, "
        "amount_usd_cents, status, note, initiated_at "
        "FROM payout_transfers WHERE decision_id = ?",
        [decision_id],
    ).fetchone()
    if row is None or not _existing_matches_attempt(
        row,
        stripe_transfer_id=stripe_transfer_id,
        recipient_account_id=recipient_account_id,
        amount_usd_cents=amount_usd_cents,
        status=STATUS_TRANSFERRED,
        note=note,
    ):
        raise TransferInitiatorError(
            f"decision {decision_id!r} failed transfer retry did not persist"
        )
    return _existing_outcome(decision_id, row)


def initiate_transfer(
    *,
    con: Any,
    provider: StripeProvider,
    decision: RevShareDecision,
    account_id_for_recipient: str | None,
    metadata: dict | None = None,
) -> TransferOutcome:
    """Drive one ``RevShareDecision`` through Stripe Connect with full
    audit. Returns a ``TransferOutcome`` describing what happened.

    Args:
      con: ``LockedConnection`` on the substrate DuckDB.
      provider: a ``StripeProvider`` (real or mock); the protocol's
        ``transfer_to_connect`` is invoked.
      decision: the ``RevShareDecision`` from the PayoutRouter.
      account_id_for_recipient: the Stripe Connect account id for the
        recipient. The caller resolves this from the recipient_ref
        (user_id or ip_holder_id) → Connect account lookup. Required
        for CREATOR and non-escrow PUBLISHER decisions; ignored for
        PLATFORM (always None).
      metadata: optional extra metadata to ride on the Stripe call.
        The decision_id always lands in metadata regardless.

    Per master-spec §9.10 + §13.5:
      - PLATFORM → recorded as skipped_platform, no Stripe call.
      - escrow-required PUBLISHER → recorded as skipped_escrow.
      - non-escrow PUBLISHER + CREATOR → transfer_to_connect is called
        with decision_id as the idempotency_key. Success records
        ``transferred`` with the Stripe transfer id; failure records
        ``failed`` with the exception text.

    The function never raises on provider failure — failures surface
    in ``TransferOutcome.status == 'failed'`` for operator triage.
    """
    meta = dict(metadata or {})
    meta.setdefault("decision_id", decision.decision_id)
    meta.setdefault("kind", decision.kind.value)
    if decision.document_id:
        meta.setdefault("document_id", decision.document_id)

    if decision.kind == RevShareKind.PLATFORM:
        return _record(
            con,
            decision_id=decision.decision_id,
            stripe_transfer_id=None,
            recipient_account_id=None,
            amount_usd_cents=decision.amount_usd_cents,
            status=STATUS_SKIPPED_PLATFORM,
            note="platform residual; no transfer initiated per §13.5",
        )

    if decision.requires_escrow:
        return _record(
            con,
            decision_id=decision.decision_id,
            stripe_transfer_id=None,
            recipient_account_id=account_id_for_recipient,
            amount_usd_cents=decision.amount_usd_cents,
            status=STATUS_SKIPPED_ESCROW,
            note="publisher pre-onboarded; escrow holds until claim per §9.10",
        )

    if account_id_for_recipient is None:
        raise TransferInitiatorError(
            f"decision {decision.decision_id} kind={decision.kind.value} "
            f"requires a Connect account id for "
            f"recipient_ref={decision.recipient_ref!r}; caller must resolve "
            "the user/publisher → Connect account lookup before calling"
        )

    if decision.amount_usd_cents <= 0:
        # Zero-amount decision shouldn't reach the initiator (the
        # PayoutRouter skips these), but defensive: record + skip.
        return _record(
            con,
            decision_id=decision.decision_id,
            stripe_transfer_id=None,
            recipient_account_id=account_id_for_recipient,
            amount_usd_cents=0,
            status=STATUS_SKIPPED_PLATFORM,
            note="zero-amount decision; no transfer initiated",
        )

    try:
        stripe_id = provider.transfer_to_connect(
            account_id=account_id_for_recipient,
            amount_usd_cents=decision.amount_usd_cents,
            idempotency_key=decision.decision_id,
            metadata=meta,
        )
    except Exception as exc:
        return _record(
            con,
            decision_id=decision.decision_id,
            stripe_transfer_id=None,
            recipient_account_id=account_id_for_recipient,
            amount_usd_cents=decision.amount_usd_cents,
            status=STATUS_FAILED,
            note=f"provider error: {exc!r}",
            allow_existing_mismatch=True,
        )

    return _record(
        con,
        decision_id=decision.decision_id,
        stripe_transfer_id=stripe_id,
        recipient_account_id=account_id_for_recipient,
        amount_usd_cents=decision.amount_usd_cents,
        status=STATUS_TRANSFERRED,
        note="transferred via Stripe Connect",
    )


def load_transfers_for_recipient(
    con: Any, recipient_account_id: str,
) -> list[TransferOutcome]:
    """Audit query — load every transfer attempt routed to a single
    Connect account, oldest first."""
    ensure_table(con)
    rows = con.execute(
        "SELECT transfer_attempt_id, decision_id, stripe_transfer_id, "
        "recipient_account_id, amount_usd_cents, status, note, initiated_at "
        "FROM payout_transfers WHERE recipient_account_id = ? "
        "ORDER BY initiated_at",
        [recipient_account_id],
    ).fetchall()
    outcomes: list[TransferOutcome] = []
    for r in rows:
        outcomes.append(TransferOutcome(
            transfer_attempt_id=r[0],
            decision_id=r[1],
            stripe_transfer_id=r[2],
            recipient_account_id=r[3],
            amount_usd_cents=int(r[4]),
            status=r[5],
            note=r[6] or "",
            initiated_at=(
                r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7])
            ),
        ))
    return outcomes


__all__ = [
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_SKIPPED_ESCROW",
    "STATUS_SKIPPED_PLATFORM",
    "STATUS_TRANSFERRED",
    "TransferInitiatorError",
    "TransferOutcome",
    "ensure_table",
    "initiate_transfer",
    "load_transfers_for_recipient",
]
