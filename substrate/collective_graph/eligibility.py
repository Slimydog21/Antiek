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
    content_class: str  # "user_public_contribution" | "opt_in_licensed" | "public_domain"
    quality_gate_result: Optional[QualityGateResult]
    # The §9.10 publisher state — only relevant for content_class="opt_in_licensed"
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
# be retrieved on ad surfaces).
NON_ATTRIBUTABLE_CONTENT_CLASSES = frozenset({
    "operator_uploaded",
    "restricted_pending_opt_in",
})


def is_attribution_eligible(doc: CollectiveGraphDocument) -> bool:
    """Per §13.9: a document earns rev-share IFF
    (a) its gate result is PASS_PUBLIC, AND
    (b) its content_class permits attribution, AND
    (c) for publisher-licensed content, the publisher has claimed.
    """
    if doc.content_class in NON_ATTRIBUTABLE_CONTENT_CLASSES:
        return False
    if doc.content_class == "opt_in_licensed" and not doc.ip_holder_claimed:
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
    if doc.content_class not in {"user_public_contribution", "opt_in_licensed", "public_domain"}:
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
        else:
            reason = "attribution-ineligible"
    else:
        reason = "ad-ineligible"
    return EligibilityFlags(
        attribution_eligible=attribution,
        ad_eligible=ad,
        reason=reason,
    )
