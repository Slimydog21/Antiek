"""Eligibility predicates over collective-graph documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from substrate.quality_gate import QualityGateResult, QualityGateVerdict


@dataclass(frozen=True)
class CollectiveGraphDocument:
    """One row's worth of post-ingest state. Carries the gate trail
    so eligibility is derivable, not stored."""

    document_id: str
    note_id: str
    owner_user_id: str
    content_class: str  # "user_public_contribution" | "opt_in_licensed" | "source_declared_open" | "public_domain"
    quality_gate_result: Optional[QualityGateResult]
    # The claim state of the rights holder. Relevant for classes that HAVE a
    # rights holder with attribution rights but require a claim before payout:
    # "opt_in_licensed" (§9.10 publisher claim) and "source_declared_open"
    # (CC-BY / CC-BY-SA: attribution is owed but the holder must still claim to
    # be paid). public_domain has no holder to claim, so this is ignored there.
    ip_holder_claimed: bool = False


@dataclass(frozen=True)
class EligibilityFlags:
    """Derived flags. Always computed from the doc's gate trail +
    content_class + publisher state."""

    attribution_eligible: bool
    ad_eligible: bool
    reason: str


# Content classes that NEVER get attribution rev-share (operator
# uploads aren't user-as-IP-holder; restricted content can't even
# be retrieved on ad surfaces; personal_reading is the owner's private
# third-party reading — it has no rights basis to earn and no holder to
# ever pay, so it accrues zero ad attribution and zero IP escrow BY
# CONSTRUCTION, which is the §9.0 proof the Personal-Reading Lane SPR-01
# leans on: a personal_reading doc reaching is_attribution_eligible()
# returns False at the first branch below).
NON_ATTRIBUTABLE_CONTENT_CLASSES = frozenset({
    "operator_uploaded",
    "restricted_pending_opt_in",
    "personal_reading",
})


# Content classes that DO have a rights holder with attribution rights but
# must NOT pay out until that holder claims. opt_in_licensed is a §9.10
# publisher; source_declared_open (CC-BY / CC-BY-SA) carries an attribution
# obligation to an as-yet-unclaimed holder. Until the holder claims, the
# accrual sits in escrow rather than being released (mirrors the §9.10
# escrow-not-payout gap). public_domain is NOT here: it has no holder to claim.
CLAIM_GATED_CONTENT_CLASSES = frozenset({
    "opt_in_licensed",
    "source_declared_open",
})


def is_attribution_eligible(doc: CollectiveGraphDocument) -> bool:
    """Per §13.9: a document earns rev-share IFF
    (a) its gate result is PASS_PUBLIC, AND
    (b) its content_class permits attribution, AND
    (c) for content with an unclaimed rights holder (publisher opt-in OR a
        source-declared CC-BY/CC-BY-SA work), the holder has claimed.
    """
    if doc.content_class in NON_ATTRIBUTABLE_CONTENT_CLASSES:
        return False
    if doc.content_class in CLAIM_GATED_CONTENT_CLASSES and not doc.ip_holder_claimed:
        return False
    if doc.quality_gate_result is None:
        return False
    return doc.quality_gate_result.verdict == QualityGateVerdict.PASS_PUBLIC


def is_ad_eligible(doc: CollectiveGraphDocument) -> bool:
    """Per Sprint 23-24 §2 Phase 1 + Sprint 25+ Phase 1: a page is
    ad-eligible IFF
    (a) attribution-eligible (precondition), AND
    (b) content_class is in the ad-supported public surface, AND
    (c) the underlying note passed the §5.5 voice rubric AT INGEST
        TIME — the runtime suppression hook (substrate.voice_style)
        handles inline-render-time decisions separately.
    """
    if not is_attribution_eligible(doc):
        return False
    if doc.content_class not in {
        "user_public_contribution",
        "opt_in_licensed",
        "source_declared_open",
        "public_domain",
    }:
        return False
    if doc.quality_gate_result is None:
        return False
    # PASS_PUBLIC implies the voice-style check passed too (see
    # quality_gate._verdict_from_checks). Double-check by reading
    # the named voice_style check result if present.
    for check in doc.quality_gate_result.checks:
        if check.check_name == "voice_style" and check.kind.value == "fail":
            return False
    return True


def compute_eligibility(doc: CollectiveGraphDocument) -> EligibilityFlags:
    """Derive both flags + a human-readable reason."""
    attribution = is_attribution_eligible(doc)
    ad = is_ad_eligible(doc)
    if attribution and ad:
        reason = "PASS_PUBLIC + voice-passed + ad-supported content_class"
    elif attribution and not ad:
        reason = "attribution-eligible but content_class not ad-supported"
    elif not attribution:
        if doc.quality_gate_result is None:
            reason = "no quality-gate result attached"
        elif doc.quality_gate_result.verdict != QualityGateVerdict.PASS_PUBLIC:
            reason = f"gate verdict={doc.quality_gate_result.verdict.value}"
        elif doc.content_class in NON_ATTRIBUTABLE_CONTENT_CLASSES:
            reason = f"content_class={doc.content_class} is non-attributable"
        elif doc.content_class == "opt_in_licensed" and not doc.ip_holder_claimed:
            reason = "publisher has not claimed under §9.10"
        elif doc.content_class == "source_declared_open" and not doc.ip_holder_claimed:
            reason = (
                "source-declared open (CC-BY/CC-BY-SA) rights holder has not "
                "claimed; accrues to escrow, not payout"
            )
        else:
            reason = "attribution-ineligible"
    else:
        reason = "ad-ineligible"
    return EligibilityFlags(
        attribution_eligible=attribution,
        ad_eligible=ad,
        reason=reason,
    )
