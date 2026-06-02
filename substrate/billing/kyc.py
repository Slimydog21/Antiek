"""KYC state machine substrate (master-spec §9.5).

Per the Sprint 23-24 phase 4 exit criterion: *"a creator who crosses
the threshold completes KYC and receives payout cleanly."* This module
is the substrate side of that flow — it tracks each recipient's KYC
status as an append-only state machine and refuses to admit a payout
above the §9.5 threshold for a recipient who has not reached
COMPLETED.

State machine::

    NOT_STARTED  → INVITED      (operator/system sends Stripe Connect onboarding link)
                 → IN_PROGRESS  (recipient began the Stripe flow)
                 → COMPLETED    (Stripe Connect reports onboarding success)
    COMPLETED    → EXPIRED      (per §9.5 — Stripe links time out after 7 days
                                  of inactivity; reset to INVITED to re-send)
    any state    → REJECTED     (Stripe declined the recipient — terminal)

The substrate does NOT call Stripe directly. The integration layer
(``tools/stripe_connect/``) calls Stripe and feeds the status updates
into this state machine. Substrate stays Stripe-agnostic so tests
exercise the state machine without a live Stripe account.

Append-only persistence — every state transition appends a new row
to the ``kyc_status`` DuckDB table (canonical schema in
``substrate/graph/schema.py``; this module ships defensive
``ensure_table``). The audit trail is the row history.

Settlement gate: ``can_settle(con, recipient_ref, amount_usd_cents)``
returns True iff the recipient's LATEST row is COMPLETED. The
RolloverLedger / PayoutRouter integrations call this before initiating
a transfer above the $10 threshold. Below-threshold accruals are
permitted regardless of KYC — they roll over without ever leaving
escrow.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Per master-spec §9.5: $10 minimum payout threshold. Settlement of
# any decision strictly above this floor requires the recipient's
# KYC status == COMPLETED.
KYC_PAYOUT_FLOOR_USD_CENTS: int = 1000


# Per master-spec §9.5: Stripe links time out after 7 days of
# inactivity. The state machine flips COMPLETED → EXPIRED on this
# threshold; operator must re-invite.
KYC_EXPIRY_DAYS: int = 7


class KycState(str, enum.Enum):
    """Five-state machine. ``REJECTED`` is terminal."""

    NOT_STARTED = "not_started"
    INVITED = "invited"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"
    REJECTED = "rejected"


class KycError(Exception):
    """Raised when a transition violates the state machine."""


@dataclass(frozen=True)
class KycRecord:
    """One row in the kyc_status table. ``frozen=True`` so callers
    cannot mutate audit-recorded state."""

    recipient_ref: str  # user_id or ip_holder_id
    state: KycState
    last_state_change_at: str
    operator_notes: str = ""
    rejection_reason: str | None = None
    # Stripe Connect onboarding link / account id reference. Substrate
    # stores the opaque handle; the integration layer interprets it.
    stripe_account_ref: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ── In-memory registry (mirrors AdvertiserRegistry pattern) ────────


@dataclass
class KycRegistry:
    """Append-only in-memory store. Persistence round-trips via the
    DuckDB table; this is the in-process mirror for tests + offline
    analysis."""

    records: list[KycRecord] = field(default_factory=list)

    def latest(self, recipient_ref: str) -> KycRecord | None:
        """Most recent record for the given recipient, or None."""
        for r in reversed(self.records):
            if r.recipient_ref == recipient_ref:
                return r
        return None


# ── State-machine transition functions ────────────────────────────


def invite(
    registry: KycRegistry,
    *,
    recipient_ref: str,
    stripe_account_ref: str | None = None,
    operator_notes: str = "",
) -> KycRecord:
    """Move NOT_STARTED → INVITED. Idempotent: re-inviting an INVITED
    or IN_PROGRESS recipient refreshes the link and re-stamps the
    timestamp. Refused for COMPLETED + REJECTED (terminal-ish — use
    ``expire`` to flip COMPLETED back to INVITED)."""
    current = registry.latest(recipient_ref)
    allowed_from = {
        None: True,  # NOT_STARTED / first sight
        KycState.NOT_STARTED: True,
        KycState.INVITED: True,
        KycState.IN_PROGRESS: True,
        KycState.EXPIRED: True,
        KycState.COMPLETED: False,
        KycState.REJECTED: False,
    }
    state = None if current is None else current.state
    if not allowed_from.get(state, False):
        raise KycError(
            f"cannot invite recipient_ref {recipient_ref!r} in state "
            f"{state.value if state else 'unknown'!r}; only NOT_STARTED, "
            "INVITED, IN_PROGRESS, EXPIRED may be re-invited"
        )
    record = KycRecord(
        recipient_ref=recipient_ref,
        state=KycState.INVITED,
        last_state_change_at=_now_iso(),
        operator_notes=operator_notes,
        stripe_account_ref=stripe_account_ref,
    )
    registry.records.append(record)
    return record


def begin(
    registry: KycRegistry, *, recipient_ref: str,
) -> KycRecord:
    """Move INVITED → IN_PROGRESS. The integration layer flips this
    when Stripe reports the recipient opened the onboarding link."""
    current = registry.latest(recipient_ref)
    if current is None or current.state is not KycState.INVITED:
        cur_state = current.state.value if current else "not_started"
        raise KycError(
            f"cannot begin recipient_ref {recipient_ref!r} in state "
            f"{cur_state!r}; only INVITED is beginnable"
        )
    record = KycRecord(
        recipient_ref=recipient_ref,
        state=KycState.IN_PROGRESS,
        last_state_change_at=_now_iso(),
        operator_notes=current.operator_notes,
        stripe_account_ref=current.stripe_account_ref,
    )
    registry.records.append(record)
    return record


def complete(
    registry: KycRegistry,
    *,
    recipient_ref: str,
    stripe_account_ref: str | None = None,
) -> KycRecord:
    """Move IN_PROGRESS → COMPLETED. Final allowed account ref rides
    here (Stripe issues a stable account_id at completion)."""
    current = registry.latest(recipient_ref)
    if current is None or current.state is not KycState.IN_PROGRESS:
        cur_state = current.state.value if current else "not_started"
        raise KycError(
            f"cannot complete recipient_ref {recipient_ref!r} in state "
            f"{cur_state!r}; only IN_PROGRESS may complete"
        )
    record = KycRecord(
        recipient_ref=recipient_ref,
        state=KycState.COMPLETED,
        last_state_change_at=_now_iso(),
        operator_notes=current.operator_notes,
        stripe_account_ref=stripe_account_ref or current.stripe_account_ref,
    )
    registry.records.append(record)
    return record


def expire(
    registry: KycRegistry, *, recipient_ref: str,
) -> KycRecord:
    """Move COMPLETED → EXPIRED. Per §9.5 — Stripe links/sessions
    invalidate after inactivity; substrate refuses settlement on
    EXPIRED and operator must re-invite."""
    current = registry.latest(recipient_ref)
    if current is None or current.state is not KycState.COMPLETED:
        cur_state = current.state.value if current else "not_started"
        raise KycError(
            f"cannot expire recipient_ref {recipient_ref!r} in state "
            f"{cur_state!r}; only COMPLETED may expire"
        )
    record = KycRecord(
        recipient_ref=recipient_ref,
        state=KycState.EXPIRED,
        last_state_change_at=_now_iso(),
        operator_notes=current.operator_notes,
        stripe_account_ref=current.stripe_account_ref,
    )
    registry.records.append(record)
    return record


def reject(
    registry: KycRegistry,
    *,
    recipient_ref: str,
    rejection_reason: str,
) -> KycRecord:
    """Move ANY state → REJECTED (terminal). Stripe declined the
    recipient (sanctions list, identity mismatch, etc.). The
    recipient cannot be re-invited; the substrate refuses settlement
    permanently. A new recipient_ref is required to re-enter the
    flow."""
    current = registry.latest(recipient_ref)
    if current is not None and current.state is KycState.REJECTED:
        raise KycError(
            f"recipient_ref {recipient_ref!r} is already REJECTED; "
            f"original reason: {current.rejection_reason!r}"
        )
    record = KycRecord(
        recipient_ref=recipient_ref,
        state=KycState.REJECTED,
        last_state_change_at=_now_iso(),
        operator_notes=current.operator_notes if current else "",
        stripe_account_ref=current.stripe_account_ref if current else None,
        rejection_reason=rejection_reason,
    )
    registry.records.append(record)
    return record


# ── Settlement gate ───────────────────────────────────────────────


def can_settle(
    registry: KycRegistry,
    *,
    recipient_ref: str,
    amount_usd_cents: int,
) -> bool:
    """True iff a payout of ``amount_usd_cents`` may be settled to
    ``recipient_ref`` right now.

    Below the §9.5 floor: True regardless of KYC state (the amount
    rolls over without leaving escrow, so no KYC needed).

    At/above the §9.5 floor: True iff the recipient's latest record
    is COMPLETED. Every other state (including REJECTED and EXPIRED)
    refuses.
    """
    if amount_usd_cents <= KYC_PAYOUT_FLOOR_USD_CENTS:
        return True
    current = registry.latest(recipient_ref)
    if current is None:
        return False
    return current.state is KycState.COMPLETED


# ── Persistence ──────────────────────────────────────────────────


def ensure_table(con: Any) -> None:
    """Defensive table-creation. Canonical schema in
    ``substrate/graph/schema.py`` (V5 chunk shipped alongside this
    module). Read-only connections fail silently."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS kyc_status (
                attempt_id              TEXT PRIMARY KEY,
                recipient_ref           TEXT NOT NULL,
                state                   TEXT NOT NULL CHECK (state IN (
                    'not_started', 'invited', 'in_progress',
                    'completed', 'expired', 'rejected'
                )),
                last_state_change_at    TIMESTAMP NOT NULL,
                operator_notes          TEXT NOT NULL DEFAULT '',
                rejection_reason        TEXT,
                stripe_account_ref      TEXT,
                row_inserted_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def save_record(con: Any, record: KycRecord) -> str:
    """Append one ``KycRecord`` to the kyc_status table. Idempotent
    on (recipient_ref, state, last_state_change_at)."""
    ensure_table(con)
    existing = con.execute(
        "SELECT attempt_id FROM kyc_status "
        "WHERE recipient_ref = ? AND state = ? AND last_state_change_at = ? "
        "ORDER BY row_inserted_at LIMIT 1",
        [record.recipient_ref, record.state.value, record.last_state_change_at],
    ).fetchone()
    if existing is not None:
        return existing[0]

    attempt_id = f"kycrec-{uuid.uuid4().hex[:12]}"
    con.execute(
        """
        INSERT INTO kyc_status (
            attempt_id, recipient_ref, state, last_state_change_at,
            operator_notes, rejection_reason, stripe_account_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            attempt_id, record.recipient_ref, record.state.value,
            record.last_state_change_at, record.operator_notes,
            record.rejection_reason, record.stripe_account_ref,
        ],
    )
    return attempt_id


def load_registry(con: Any) -> KycRegistry:
    """Reconstruct an in-memory ``KycRegistry`` from persisted state.
    Rows in row_inserted_at order; ``latest()`` returns the same
    record the in-memory state machine would have."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT recipient_ref, state, last_state_change_at,
               operator_notes, rejection_reason, stripe_account_ref
        FROM kyc_status
        ORDER BY row_inserted_at, attempt_id
        """
    ).fetchall()
    registry = KycRegistry()
    for r in rows:
        last_state_change_at = (
            r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])
        )
        registry.records.append(KycRecord(
            recipient_ref=r[0],
            state=KycState(r[1]),
            last_state_change_at=last_state_change_at,
            operator_notes=r[3] or "",
            rejection_reason=r[4],
            stripe_account_ref=r[5],
        ))
    return registry


__all__ = [
    "KYC_EXPIRY_DAYS",
    "KYC_PAYOUT_FLOOR_USD_CENTS",
    "KycError",
    "KycRecord",
    "KycRegistry",
    "KycState",
    "begin",
    "can_settle",
    "complete",
    "ensure_table",
    "expire",
    "invite",
    "load_registry",
    "reject",
    "save_record",
]
