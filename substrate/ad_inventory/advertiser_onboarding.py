"""Lead-gen advertiser onboarding (Sprint 23-24 phase 5).

Per master-spec §9.4 Option C + the Sprint 23-24 breakdown phase 5:
"Manual sales motion for the first wave of advertisers. Vertical SaaS,
consulting firms, recruiting platforms targeted by topic. Operator-
driven; tooling stays light."

The advertiser registry is intentionally minimal — no programmatic
self-serve onboarding. The operator approves each advertiser by hand;
this module is the substrate-side state machine that backs that
approval flow.

Admission state machine::

    PENDING_REVIEW -> APPROVED -> ACTIVE
                  \\-> REJECTED
    ACTIVE -> SUSPENDED (operator pause)
    ACTIVE -> CHURNED (advertiser stops paying)

Inventory items in ``ad_bidding.py`` carry an ``advertiser_id`` that
joins back to this registry. ``select_lead_gen_ad`` filters out any
inventory whose advertiser is not currently ACTIVE — this is the
gate that keeps churned/suspended advertisers' creatives from being
served by accident.

Substrate-only; no Stripe customer creation, no email outbound,
no contract management. The Sprint 18 legal-gate (§9.0) applies:
no advertiser may be ACTIVE on a graph that has not passed the
legal-gate review.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AdvertiserStatus(str, enum.Enum):
    """Lifecycle states for a lead-gen advertiser admission record."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    ACTIVE = "active"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CHURNED = "churned"


# Status values that may run ads.
SERVING_STATUSES: frozenset[AdvertiserStatus] = frozenset(
    {AdvertiserStatus.ACTIVE}
)


class AdvertiserOnboardingError(Exception):
    """Raised when a transition would violate the admission state
    machine — e.g. attempting to approve a record that has already
    been rejected."""


@dataclass(frozen=True)
class AdvertiserRecord:
    """One row in the advertiser registry. ``frozen=True`` so the
    state machine returns new records rather than mutating in place
    — keeps the audit trail honest."""

    advertiser_id: str
    display_name: str
    contact_email: str
    verticals: tuple[str, ...]
    # Audience-intent dimensions the advertiser bids on. Matched
    # against page-level intent vectors in ad_bidding.
    audience_intents: tuple[str, ...]
    status: AdvertiserStatus
    submitted_at: str
    last_status_change_at: str
    operator_notes: str = ""
    rejection_reason: Optional[str] = None
    monthly_budget_usd_cents: Optional[int] = None


@dataclass
class AdvertiserRegistry:
    """In-memory advertiser registry. Persistence lives in
    ``substrate/graph/schema.py`` (table: ``advertisers``); this
    in-memory shape mirrors the row contract for tests and offline
    analysis. Use ``ensure_table`` + ``load_registry`` / ``save_record``
    to round-trip against DuckDB.

    The registry is intentionally a list of frozen records rather
    than a mutating dict-of-record — every state change appends a
    new record so the audit trail is preserved."""

    records: list[AdvertiserRecord] = field(default_factory=list)

    def latest(self, advertiser_id: str) -> Optional[AdvertiserRecord]:
        """Return the most recent record for an advertiser, or None."""
        for r in reversed(self.records):
            if r.advertiser_id == advertiser_id:
                return r
        return None

    def all_serving(self) -> list[AdvertiserRecord]:
        """Return latest records for every advertiser whose current
        status is in SERVING_STATUSES. The result is deterministic
        (ordered by advertiser_id) so audit + tests are stable."""
        latest_by_id: dict[str, AdvertiserRecord] = {}
        for r in self.records:
            latest_by_id[r.advertiser_id] = r
        serving = [
            r for r in latest_by_id.values()
            if r.status in SERVING_STATUSES
        ]
        serving.sort(key=lambda r: r.advertiser_id)
        return serving


def submit_application(
    registry: AdvertiserRegistry,
    *,
    display_name: str,
    contact_email: str,
    verticals: tuple[str, ...],
    audience_intents: tuple[str, ...] = (),
    monthly_budget_usd_cents: Optional[int] = None,
    advertiser_id: Optional[str] = None,
) -> AdvertiserRecord:
    """Submit a new advertiser application. Lands in PENDING_REVIEW.

    The operator approves or rejects via ``approve_advertiser`` /
    ``reject_advertiser``. Returns the resulting frozen record."""
    aid = advertiser_id or f"adv-{uuid.uuid4().hex[:12]}"
    if registry.latest(aid) is not None:
        raise AdvertiserOnboardingError(
            f"advertiser_id {aid!r} already exists; submit_application "
            "is for new applications only"
        )
    now = _now_iso()
    record = AdvertiserRecord(
        advertiser_id=aid,
        display_name=display_name,
        contact_email=contact_email,
        verticals=tuple(verticals),
        audience_intents=tuple(audience_intents),
        status=AdvertiserStatus.PENDING_REVIEW,
        submitted_at=now,
        last_status_change_at=now,
        monthly_budget_usd_cents=monthly_budget_usd_cents,
    )
    registry.records.append(record)
    return record


def approve_advertiser(
    registry: AdvertiserRegistry,
    *,
    advertiser_id: str,
    operator_notes: str = "",
) -> AdvertiserRecord:
    """Operator approves a PENDING_REVIEW application. Lands in
    APPROVED. ``activate_advertiser`` is the separate step that
    flips APPROVED → ACTIVE (so the operator can defer activation
    until the creative + Stripe account are in place)."""
    current = registry.latest(advertiser_id)
    if current is None:
        raise AdvertiserOnboardingError(
            f"unknown advertiser_id {advertiser_id!r}"
        )
    if current.status != AdvertiserStatus.PENDING_REVIEW:
        raise AdvertiserOnboardingError(
            f"cannot approve advertiser_id {advertiser_id!r} in status "
            f"{current.status.value!r}; only PENDING_REVIEW is approvable"
        )
    new_record = AdvertiserRecord(
        advertiser_id=current.advertiser_id,
        display_name=current.display_name,
        contact_email=current.contact_email,
        verticals=current.verticals,
        audience_intents=current.audience_intents,
        status=AdvertiserStatus.APPROVED,
        submitted_at=current.submitted_at,
        last_status_change_at=_now_iso(),
        operator_notes=operator_notes or current.operator_notes,
        monthly_budget_usd_cents=current.monthly_budget_usd_cents,
    )
    registry.records.append(new_record)
    return new_record


def reject_advertiser(
    registry: AdvertiserRegistry,
    *,
    advertiser_id: str,
    rejection_reason: str,
) -> AdvertiserRecord:
    """Operator rejects an application. REJECTED is terminal; a
    rejected advertiser must submit a new application (with a new
    advertiser_id) to re-enter the queue."""
    current = registry.latest(advertiser_id)
    if current is None:
        raise AdvertiserOnboardingError(
            f"unknown advertiser_id {advertiser_id!r}"
        )
    if current.status not in {
        AdvertiserStatus.PENDING_REVIEW, AdvertiserStatus.APPROVED,
    }:
        raise AdvertiserOnboardingError(
            f"cannot reject advertiser_id {advertiser_id!r} in status "
            f"{current.status.value!r}; only PENDING_REVIEW or APPROVED"
        )
    new_record = AdvertiserRecord(
        advertiser_id=current.advertiser_id,
        display_name=current.display_name,
        contact_email=current.contact_email,
        verticals=current.verticals,
        audience_intents=current.audience_intents,
        status=AdvertiserStatus.REJECTED,
        submitted_at=current.submitted_at,
        last_status_change_at=_now_iso(),
        operator_notes=current.operator_notes,
        rejection_reason=rejection_reason,
        monthly_budget_usd_cents=current.monthly_budget_usd_cents,
    )
    registry.records.append(new_record)
    return new_record


def activate_advertiser(
    registry: AdvertiserRegistry,
    *,
    advertiser_id: str,
    legal_gate_passed: bool,
) -> AdvertiserRecord:
    """Flip APPROVED → ACTIVE. Refuses if the legal gate (§9.0) has
    not been recorded as passed for the graph — the binding invariant
    from the cover §3 disciplines.

    The legal-gate state is determined by the caller (typically by
    consulting ``substrate/legal_gate/``); this function records the
    operator's affirmation that it has been checked.
    """
    if not legal_gate_passed:
        raise AdvertiserOnboardingError(
            f"cannot activate advertiser_id {advertiser_id!r}: legal "
            "gate (§9.0) has not passed; ACTIVE status would route real "
            "ad inventory against an ungated graph"
        )
    current = registry.latest(advertiser_id)
    if current is None:
        raise AdvertiserOnboardingError(
            f"unknown advertiser_id {advertiser_id!r}"
        )
    if current.status != AdvertiserStatus.APPROVED:
        raise AdvertiserOnboardingError(
            f"cannot activate advertiser_id {advertiser_id!r} in status "
            f"{current.status.value!r}; only APPROVED is activatable"
        )
    new_record = AdvertiserRecord(
        advertiser_id=current.advertiser_id,
        display_name=current.display_name,
        contact_email=current.contact_email,
        verticals=current.verticals,
        audience_intents=current.audience_intents,
        status=AdvertiserStatus.ACTIVE,
        submitted_at=current.submitted_at,
        last_status_change_at=_now_iso(),
        operator_notes=current.operator_notes,
        monthly_budget_usd_cents=current.monthly_budget_usd_cents,
    )
    registry.records.append(new_record)
    return new_record


def suspend_advertiser(
    registry: AdvertiserRegistry,
    *,
    advertiser_id: str,
    reason: str,
) -> AdvertiserRecord:
    """Operator pauses an ACTIVE advertiser. SUSPENDED can return to
    ACTIVE via ``activate_advertiser`` (which re-checks legal gate)."""
    current = registry.latest(advertiser_id)
    if current is None:
        raise AdvertiserOnboardingError(
            f"unknown advertiser_id {advertiser_id!r}"
        )
    if current.status != AdvertiserStatus.ACTIVE:
        raise AdvertiserOnboardingError(
            f"cannot suspend advertiser_id {advertiser_id!r} in status "
            f"{current.status.value!r}; only ACTIVE is suspendable"
        )
    new_record = AdvertiserRecord(
        advertiser_id=current.advertiser_id,
        display_name=current.display_name,
        contact_email=current.contact_email,
        verticals=current.verticals,
        audience_intents=current.audience_intents,
        status=AdvertiserStatus.SUSPENDED,
        submitted_at=current.submitted_at,
        last_status_change_at=_now_iso(),
        operator_notes=f"{current.operator_notes}\n[suspended] {reason}".strip(),
        monthly_budget_usd_cents=current.monthly_budget_usd_cents,
    )
    registry.records.append(new_record)
    return new_record


def churn_advertiser(
    registry: AdvertiserRegistry,
    *,
    advertiser_id: str,
) -> AdvertiserRecord:
    """Advertiser stops paying / leaves the platform. Terminal."""
    current = registry.latest(advertiser_id)
    if current is None:
        raise AdvertiserOnboardingError(
            f"unknown advertiser_id {advertiser_id!r}"
        )
    if current.status not in {
        AdvertiserStatus.ACTIVE, AdvertiserStatus.SUSPENDED,
    }:
        raise AdvertiserOnboardingError(
            f"cannot churn advertiser_id {advertiser_id!r} in status "
            f"{current.status.value!r}; only ACTIVE or SUSPENDED"
        )
    new_record = AdvertiserRecord(
        advertiser_id=current.advertiser_id,
        display_name=current.display_name,
        contact_email=current.contact_email,
        verticals=current.verticals,
        audience_intents=current.audience_intents,
        status=AdvertiserStatus.CHURNED,
        submitted_at=current.submitted_at,
        last_status_change_at=_now_iso(),
        operator_notes=current.operator_notes,
        monthly_budget_usd_cents=current.monthly_budget_usd_cents,
    )
    registry.records.append(new_record)
    return new_record


def is_serving(record: AdvertiserRecord) -> bool:
    """True iff this record is in a serving (ad-eligible) status."""
    return record.status in SERVING_STATUSES


# ── Persistence (Sprint 23-24 phase 5) ─────────────────────────────


def ensure_table(con: Any) -> None:
    """Defensive table-creation. Canonical schema lives in
    ``substrate/graph/schema.py`` and runs at boot via ``init_database``;
    this is a no-op on a fully-initialized DB. Read-only connections
    fail silently."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS advertisers (
                attempt_id              TEXT PRIMARY KEY,
                advertiser_id           TEXT NOT NULL,
                display_name            TEXT NOT NULL,
                contact_email           TEXT NOT NULL,
                verticals               TEXT NOT NULL DEFAULT '',
                audience_intents        TEXT NOT NULL DEFAULT '',
                status                  TEXT NOT NULL CHECK (status IN (
                    'pending_review', 'approved', 'active',
                    'rejected', 'suspended', 'churned'
                )),
                submitted_at            TIMESTAMP NOT NULL,
                last_status_change_at   TIMESTAMP NOT NULL,
                operator_notes          TEXT NOT NULL DEFAULT '',
                rejection_reason        TEXT,
                monthly_budget_usd_cents INTEGER,
                row_inserted_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def _serialize_csv(tup: tuple[str, ...]) -> str:
    """Encode a tuple of bare identifiers as a comma-separated string.
    The values are restricted to ASCII identifiers by upstream
    validation so no escaping is required — matches the
    federation_config_store.py partner-serialization posture."""
    return ",".join(v for v in tup if v)


def _deserialize_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(v for v in raw.split(",") if v)


def save_record(con: Any, record: AdvertiserRecord) -> str:
    """Append one ``AdvertiserRecord`` to the advertisers table.
    Returns the attempt_id assigned to the row. Idempotent on
    (advertiser_id, status, last_status_change_at)."""
    ensure_table(con)
    existing = con.execute(
        "SELECT attempt_id FROM advertisers "
        "WHERE advertiser_id = ? AND status = ? AND last_status_change_at = ? "
        "ORDER BY row_inserted_at LIMIT 1",
        [
            record.advertiser_id, record.status.value,
            record.last_status_change_at,
        ],
    ).fetchone()
    if existing is not None:
        return existing[0]

    attempt_id = f"advrec-{uuid.uuid4().hex[:12]}"
    con.execute(
        """
        INSERT INTO advertisers (
            attempt_id, advertiser_id, display_name, contact_email,
            verticals, audience_intents, status,
            submitted_at, last_status_change_at,
            operator_notes, rejection_reason, monthly_budget_usd_cents
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            attempt_id,
            record.advertiser_id,
            record.display_name,
            record.contact_email,
            _serialize_csv(record.verticals),
            _serialize_csv(record.audience_intents),
            record.status.value,
            record.submitted_at,
            record.last_status_change_at,
            record.operator_notes,
            record.rejection_reason,
            record.monthly_budget_usd_cents,
        ],
    )
    return attempt_id


def load_registry(con: Any) -> AdvertiserRegistry:
    """Reconstruct an in-memory ``AdvertiserRegistry`` from persisted
    state. Returns rows in row_inserted_at order so ``latest()`` returns
    the same record the in-memory state machine would have."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT advertiser_id, display_name, contact_email,
               verticals, audience_intents, status,
               submitted_at, last_status_change_at,
               operator_notes, rejection_reason, monthly_budget_usd_cents
        FROM advertisers
        ORDER BY row_inserted_at, attempt_id
        """
    ).fetchall()
    registry = AdvertiserRegistry()
    for r in rows:
        submitted_at = (
            r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])
        )
        last_status_change_at = (
            r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7])
        )
        registry.records.append(AdvertiserRecord(
            advertiser_id=r[0],
            display_name=r[1],
            contact_email=r[2],
            verticals=_deserialize_csv(r[3]),
            audience_intents=_deserialize_csv(r[4]),
            status=AdvertiserStatus(r[5]),
            submitted_at=submitted_at,
            last_status_change_at=last_status_change_at,
            operator_notes=r[8] or "",
            rejection_reason=r[9],
            monthly_budget_usd_cents=
                int(r[10]) if r[10] is not None else None,
        ))
    return registry


__all__ = [
    "SERVING_STATUSES",
    "AdvertiserOnboardingError",
    "AdvertiserRecord",
    "AdvertiserRegistry",
    "AdvertiserStatus",
    "activate_advertiser",
    "approve_advertiser",
    "churn_advertiser",
    "ensure_table",
    "is_serving",
    "load_registry",
    "reject_advertiser",
    "save_record",
    "submit_application",
    "suspend_advertiser",
]
