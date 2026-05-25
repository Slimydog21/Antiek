"""Speak SPR-06 — informant-as-contributor economics.

"If you say important facts, you get paid; if you say slop, you don't."
When a Speak project is published with ads, the 70% ad-revenue slice
(``CREATOR_REV_SHARE``) is split among contributors by what they
actually contributed.

The missing link (flagged in grounding): there was no informant→payee
mapping. An interviewee became a document with an ``ip_holder_id``, but
nothing paid the interviewee. This module is that link, built on the
existing machinery:

  • ``ip_holders`` pre-onboarded escrow (the payee + the escrow);
  • ``ad_inventory/attribution.py`` Option B (claim_confidence ×
    (6 − source_tier)) — reused at the CLAIM granularity, with the
    interviewee as the attributed "document";
  • ``CREATOR_REV_SHARE = 0.70`` — the slice contributors split;
  • the slop gate — a low-quality contribution earns $0.

Two invariants are load-bearing and honest:

  • Accrue now, disburse later. Shares accrue to escrow; disbursement
    (Stripe Connect) is hard-gated on G2/G3. There is NO pre-gate payout
    path — ``attempt_disbursement`` refuses. With zero ad buyers there
    is $0 anyway: we track the share, never show a fictional balance.
  • Contribution is heuristic and gameable. Someone could spam plausible
    "facts". The slop gate + cross-interviewee corroboration (SPR-05)
    blunt it; we don't pretend the measurement is perfect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from substrate.ad_inventory.attribution import (
    AttributionAlgorithm,
    compute_attribution_option_b,
)
from substrate.ad_inventory.payout import CREATOR_REV_SHARE
from substrate import ip_holders

from . import gate_status
from .events import (
    SPEAK_CONTRIBUTION_ACCRUED,
    SPEAK_CONTRIBUTOR_MAPPED,
    SPEAK_DISBURSEMENT_BLOCKED,
    record_speak_event,
)
from .ids import new_accrual_id
from .schema import ensure_speak_schema
from .third_party import list_claims

# Default voice-note source tier (interviews are first-person primary
# sources). Mirrors acquisition.voice's DEFAULT_VOICE_SOURCE_TIER intent.
DEFAULT_INTERVIEWEE_TIER = 2
# Below this composite quality score, a contribution is slop → earns $0.
DEFAULT_SLOP_THRESHOLD = 0.4


class DisbursementBlocked(Exception):
    """Raised on any attempt to disburse money before G2/G3."""


# ---------------------------------------------------------------------------
# M1 — informant → payee mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContributorMapping:
    interview_id: str
    project_id: str
    ip_holder_id: Optional[str]
    holding_bucket: bool


def map_contributor(
    con: Any,
    *,
    interview_id: str,
    project_id: str,
    ip_holder_id: Optional[str] = None,
    display_name: Optional[str] = None,
    legal_contact_email: Optional[str] = None,
) -> ContributorMapping:
    """Map an interviewee to a pre-onboarded escrow payee.

    - ``ip_holder_id`` given → link to that existing payee.
    - else ``display_name`` given → create a pre-onboarded ip_holder
      (escrow accrues; no notification until operator + lawyer review).
    - else → flagged HOLDING bucket (``ip_holder_id`` NULL). An unmapped
      interviewee accrues to the bucket, never to a wrong payee.
    """
    ensure_speak_schema(con)
    holding = False
    if ip_holder_id is None and display_name is not None:
        ip_holder_id = ip_holders.create_pre_onboarded(
            con, display_name=display_name, legal_contact_email=legal_contact_email,
            metadata={"speak_interview_id": interview_id, "speak_project_id": project_id},
        )
    if ip_holder_id is None:
        holding = True
    con.execute(
        "INSERT INTO speak_contributors (interview_id, project_id, ip_holder_id, holding_bucket) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (interview_id) DO UPDATE SET "
        "ip_holder_id = excluded.ip_holder_id, holding_bucket = excluded.holding_bucket",
        [interview_id, project_id, ip_holder_id, holding],
    )
    record_speak_event(
        SPEAK_CONTRIBUTOR_MAPPED,
        {"interview_id": interview_id, "ip_holder_id": ip_holder_id, "holding_bucket": holding},
        project_id=project_id,
    )
    return ContributorMapping(interview_id, project_id, ip_holder_id, holding)


def get_payee(con: Any, interview_id: str) -> Optional[ContributorMapping]:
    row = con.execute(
        "SELECT interview_id, project_id, ip_holder_id, holding_bucket "
        "FROM speak_contributors WHERE interview_id = ?",
        [interview_id],
    ).fetchone()
    if row is None:
        return None
    return ContributorMapping(row[0], row[1], row[2], bool(row[3]))


# ---------------------------------------------------------------------------
# M2 — contribution measurement (reuse attribution Option B)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContributionResult:
    algorithm: str
    shares: dict[str, float]          # interview_id → share in [0, 1]
    slop_gated: tuple[str, ...] = ()  # interviewees whose contribution was gated


def measure_contribution(
    con: Any,
    *,
    project_id: str,
    quality_scores: Optional[dict[str, float]] = None,
    slop_threshold: float = DEFAULT_SLOP_THRESHOLD,
    tier_for: Optional[Callable[[str], int]] = None,
    publishable_only: bool = True,
) -> ContributionResult:
    """Per-interviewee contribution shares for a project's published
    content, via attribution Option B at the claim granularity (the
    interviewee is the attributed 'document').

    M3 slop gate: an interviewee whose ``quality_scores`` entry is below
    ``slop_threshold`` is EXCLUDED from the split (earns $0). A missing
    score defaults to substantive (1.0) — production wires the
    voice_style / synthesis scorers here.
    """
    quality_scores = quality_scores or {}
    claims = list_claims(con, project_id)
    if publishable_only:
        claims = [c for c in claims
                  if (not c.is_third_party)
                  or c.verification in ("multiply_attested", "operator_attested")]

    chunk_to_document: dict[str, str] = {}
    chunk_to_conf: dict[str, float] = {}
    document_to_tier: dict[str, int] = {}
    gated: set[str] = set()
    for c in claims:
        iv = c.interview_id
        if iv is None:
            continue
        if quality_scores.get(iv, 1.0) < slop_threshold:
            gated.add(iv)  # slop: doesn't earn
            continue
        chunk_to_document[c.claim_id] = iv
        chunk_to_conf[c.claim_id] = c.confidence
        document_to_tier[iv] = tier_for(iv) if tier_for else DEFAULT_INTERVIEWEE_TIER

    result = compute_attribution_option_b(
        page_id=project_id,
        chunk_to_document=chunk_to_document,
        chunk_to_claim_confidence=chunk_to_conf,
        document_to_source_tier=document_to_tier,
    )
    return ContributionResult(
        algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER.value,
        shares=result.shares,
        slop_gated=tuple(sorted(gated)),
    )


# ---------------------------------------------------------------------------
# M4 — accrual to escrow (accrue, never disburse)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccrualLine:
    interview_id: str
    ip_holder_id: Optional[str]
    share_fraction: float
    amount_usd: Decimal
    slop_gated: bool


def accrue_contributions(
    con: Any,
    *,
    project_id: str,
    ad_revenue_usd: Decimal,
    publication_id: Optional[str] = None,
    page_id: Optional[str] = None,
    impression_ref: Optional[str] = None,
    quality_scores: Optional[dict[str, float]] = None,
    slop_threshold: float = DEFAULT_SLOP_THRESHOLD,
) -> list[AccrualLine]:
    """Accrue each interviewee's share of the 70% contributor slice to
    escrow. Zero-buyer safe: ``ad_revenue_usd == 0`` accrues $0 but still
    records the share fraction (no fictional balances). Slop-gated
    interviewees get a $0, ``slop_gated=True`` line.

    Accrual ≠ disbursement — money only LEAVES escrow via
    ``attempt_disbursement``, which is gated on G2/G3.
    """
    ensure_speak_schema(con)
    contribution = measure_contribution(
        con, project_id=project_id, quality_scores=quality_scores,
        slop_threshold=slop_threshold,
    )
    contributor_pool = (Decimal(ad_revenue_usd) * CREATOR_REV_SHARE)

    lines: list[AccrualLine] = []

    # Earning lines.
    for interview_id, share in contribution.shares.items():
        mapping = get_payee(con, interview_id)
        ip_holder_id = mapping.ip_holder_id if mapping else None
        amount = (contributor_pool * Decimal(str(share))).quantize(Decimal("0.000001"))
        con.execute(
            "INSERT INTO speak_accruals "
            "(accrual_id, project_id, publication_id, interview_id, ip_holder_id, "
            " page_id, share_fraction, amount_usd, impression_ref, slop_gated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE)",
            [new_accrual_id(), project_id, publication_id, interview_id, ip_holder_id,
             page_id, float(share), amount, impression_ref],
        )
        if ip_holder_id is not None and amount > 0:
            ip_holders.accrue_escrow(con, ip_holder_id, amount)
        lines.append(AccrualLine(interview_id, ip_holder_id, float(share), amount, False))

    # Slop lines — recorded as $0 so the audit shows they were considered
    # and earned nothing ("slop doesn't earn").
    for interview_id in contribution.slop_gated:
        mapping = get_payee(con, interview_id)
        con.execute(
            "INSERT INTO speak_accruals "
            "(accrual_id, project_id, publication_id, interview_id, ip_holder_id, "
            " page_id, share_fraction, amount_usd, impression_ref, slop_gated) "
            "VALUES (?, ?, ?, ?, ?, ?, 0.0, 0, ?, TRUE)",
            [new_accrual_id(), project_id, publication_id, interview_id,
             mapping.ip_holder_id if mapping else None, page_id, impression_ref],
        )
        lines.append(AccrualLine(interview_id, mapping.ip_holder_id if mapping else None,
                                 0.0, Decimal("0"), True))

    record_speak_event(
        SPEAK_CONTRIBUTION_ACCRUED,
        {"publication_id": publication_id, "ad_revenue_usd": str(ad_revenue_usd),
         "contributor_pool_usd": str(contributor_pool),
         "n_earning": len(contribution.shares), "n_slop": len(contribution.slop_gated)},
        project_id=project_id,
    )
    return lines


def accrued_total(con: Any, project_id: str) -> Decimal:
    row = con.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) FROM speak_accruals WHERE project_id = ?",
        [project_id],
    ).fetchone()
    return Decimal(str(row[0]))


# ---------------------------------------------------------------------------
# M5 — the disbursement gate (no pre-gate payout path exists)
# ---------------------------------------------------------------------------


def attempt_disbursement(con: Any, *, project_id: str, interview_id: str) -> None:
    """Attempt to disburse a contributor's accrued escrow. ALWAYS refused
    before G2/G3 (``ANTIEK_STRIPE_PROVIDER`` is ``mock`` by default).
    There is intentionally no payout implementation here — the only
    behaviour pre-gate is refusal."""
    status = gate_status.disbursement_allowed()
    if not status.allowed:
        record_speak_event(
            SPEAK_DISBURSEMENT_BLOCKED,
            {"interview_id": interview_id, "reason": status.reason},
            project_id=project_id,
        )
        raise DisbursementBlocked(status.reason)
    # Post-G2/G3, disbursement routes through the existing Stripe Connect
    # path (tools/stripe_connect/payouts.py), which itself gates on
    # ip_holder status='claimed'. Speak does not implement a parallel
    # payout path; this is the seam.
    raise NotImplementedError(
        "post-G2/G3 disbursement routes through tools/stripe_connect/payouts.py "
        "(gated on ip_holder status='claimed'); Speak adds no parallel payout path."
    )
