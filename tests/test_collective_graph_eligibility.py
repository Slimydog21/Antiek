"""Tests for substrate.collective_graph eligibility."""

from __future__ import annotations

from substrate.collective_graph import (
    CollectiveGraphDocument,
    compute_eligibility,
    is_ad_eligible,
    is_attribution_eligible,
)
from substrate.quality_gate import (
    CheckResult,
    CheckResultKind,
    QualityGateResult,
    QualityGateVerdict,
)


def _passing_gate() -> QualityGateResult:
    return QualityGateResult(
        verdict=QualityGateVerdict.PASS_PUBLIC,
        checks=(
            CheckResult(check_name="verification", kind=CheckResultKind.PASS,
                        score=1.0, reasons=("ok",)),
            CheckResult(check_name="voice_style", kind=CheckResultKind.PASS,
                        score=0.9, reasons=("ok",)),
            CheckResult(check_name="source_tier", kind=CheckResultKind.PASS,
                        score=1.0, reasons=("ok",)),
        ),
    )


def _reroute_gate() -> QualityGateResult:
    return QualityGateResult(
        verdict=QualityGateVerdict.REROUTE_PRIVATE,
        checks=(
            CheckResult(check_name="verification", kind=CheckResultKind.PASS,
                        score=1.0, reasons=("ok",)),
            CheckResult(check_name="voice_style", kind=CheckResultKind.FAIL,
                        score=0.40, reasons=("bullet abuse",)),
        ),
    )


def _passing_doc(content_class: str = "user_public_contribution") -> CollectiveGraphDocument:
    return CollectiveGraphDocument(
        document_id="d-1", note_id="n-1", owner_user_id="u-1",
        content_class=content_class,
        quality_gate_result=_passing_gate(),
    )


def test_user_public_contribution_with_pass_gate_is_attribution_eligible():
    assert is_attribution_eligible(_passing_doc()) is True


def test_operator_uploaded_is_never_attribution_eligible():
    doc = CollectiveGraphDocument(
        document_id="d-2", note_id="n-2", owner_user_id="__operator__",
        content_class="operator_uploaded",
        quality_gate_result=_passing_gate(),
    )
    assert is_attribution_eligible(doc) is False


def test_restricted_pending_opt_in_is_never_attribution_eligible():
    doc = CollectiveGraphDocument(
        document_id="d-3", note_id="n-3", owner_user_id="u-1",
        content_class="restricted_pending_opt_in",
        quality_gate_result=_passing_gate(),
    )
    assert is_attribution_eligible(doc) is False


def test_publisher_unclaimed_is_not_attribution_eligible():
    doc = CollectiveGraphDocument(
        document_id="d-4", note_id="n-4", owner_user_id="ip-mit",
        content_class="opt_in_licensed",
        quality_gate_result=_passing_gate(),
        ip_holder_claimed=False,
    )
    assert is_attribution_eligible(doc) is False


def test_publisher_claimed_is_attribution_eligible():
    doc = CollectiveGraphDocument(
        document_id="d-4", note_id="n-4", owner_user_id="ip-mit",
        content_class="opt_in_licensed",
        quality_gate_result=_passing_gate(),
        ip_holder_claimed=True,
    )
    assert is_attribution_eligible(doc) is True


def test_reroute_private_gate_blocks_attribution():
    doc = CollectiveGraphDocument(
        document_id="d-5", note_id="n-5", owner_user_id="u-1",
        content_class="user_public_contribution",
        quality_gate_result=_reroute_gate(),
    )
    assert is_attribution_eligible(doc) is False


def test_no_gate_result_blocks_attribution():
    doc = CollectiveGraphDocument(
        document_id="d-6", note_id="n-6", owner_user_id="u-1",
        content_class="user_public_contribution",
        quality_gate_result=None,
    )
    assert is_attribution_eligible(doc) is False


def test_ad_eligibility_implies_attribution_eligibility():
    """ad-eligible ⊂ attribution-eligible."""
    doc = _passing_doc()
    if is_ad_eligible(doc):
        assert is_attribution_eligible(doc)


def test_public_domain_is_attribution_and_ad_eligible():
    doc = CollectiveGraphDocument(
        document_id="d-7", note_id="n-7", owner_user_id="public",
        content_class="public_domain",
        quality_gate_result=_passing_gate(),
    )
    assert is_attribution_eligible(doc) is True
    assert is_ad_eligible(doc) is True


def test_compute_eligibility_returns_both_flags():
    flags = compute_eligibility(_passing_doc())
    assert flags.attribution_eligible is True
    assert flags.ad_eligible is True
    assert "PASS_PUBLIC" in flags.reason


def test_compute_eligibility_reason_explains_failure():
    doc = CollectiveGraphDocument(
        document_id="d-8", note_id="n-8", owner_user_id="u-1",
        content_class="restricted_pending_opt_in",
        quality_gate_result=_passing_gate(),
    )
    flags = compute_eligibility(doc)
    assert flags.attribution_eligible is False
    assert "restricted_pending_opt_in" in flags.reason
