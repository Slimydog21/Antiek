"""Tests for middleware/source_tier/.

What this file proves:

1. ``classify(document_type)`` is the deterministic spec §C.1 catalogue.
2. ``assign_tier_at_ingestion`` follows three paths in priority order:
   document_type_lookup → keyword_fallback → default-4.
3. ``adjust_tier_after_extraction`` enforces the asymmetric LLM-downward
   invariant (adjusted_tier >= original_tier).
4. ``effective_tier`` implements the §C.4 k-of-N rule, including the
   single-Tier-1-source-vs-cohort failure mode.
5. The three emit helpers produce typed events that round-trip through
   Event.model_validate with the right payload type.
6. ``emit_tier_overridden`` raises if asked to violate asymmetry.
"""

from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.source_tier import (  # noqa: E402
    DOCUMENT_TYPE_TIER,
    HEDGING_PATTERNS,
    adjust_tier_after_extraction,
    assign_tier_at_ingestion,
    classify,
    effective_tier,
    emit_tier_assigned,
    emit_tier_overridden,
    emit_tier_rewrite_bulk,
)
from substrate.constants import SYSTEM_INVESTIGATION_ID  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    Event,
    TierAssignedPayload,
    TierOverriddenPayload,
    TierRewriteBulkPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ---------------------------------------------------------------------------
# 1. classify()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dtype,expected", [
    ("sec_filing_10k", 1),
    ("expert_interview", 1),
    ("peer_reviewed_paper", 2),
    ("patent_uspto", 2),
    ("white_paper", 3),
    ("trade_press", 3),
    ("blog_post", 4),
    ("youtube_transcript", 4),
    ("anonymous", 5),
    ("forum_post", 5),
])
def test_classify_known_types_match_catalogue(dtype, expected):
    assert classify(dtype) == expected


def test_classify_unknown_falls_through_to_5():
    assert classify("totally_unknown_type") == 5
    assert classify("") == 5
    assert classify(None) == 5


def test_classify_normalizes_case_and_whitespace():
    assert classify("  SEC_Filing_10K  ") == 1


# ---------------------------------------------------------------------------
# 2. assign_tier_at_ingestion()
# ---------------------------------------------------------------------------


def test_assign_uses_document_type_lookup_when_available():
    tier, method, matches = assign_tier_at_ingestion({
        "document_type": "peer_reviewed_paper",
        "title": "Quantum Foo",
    })
    assert tier == 2
    assert method == "document_type_lookup"
    assert matches == []


def test_assign_falls_back_to_keyword_when_type_unknown():
    tier, method, matches = assign_tier_at_ingestion({
        "document_type": "weird_unknown",
        "title": "10-K Annual Report",
        "raw_text": "audited financial statements ...",
    })
    # Both 10-k and audited financial point to tier 1.
    assert tier == 1
    assert method == "keyword_fallback"
    assert "10-k" in matches or "audited financial" in matches


def test_assign_defaults_to_tier_4_when_no_signal():
    tier, method, _ = assign_tier_at_ingestion({})
    assert tier == 4
    assert method == "default"


def test_assign_keyword_tie_resolves_to_higher_tier_number():
    """Ties resolve toward less-trusted (higher number) — conservative."""
    # Construct text that hits one keyword in tier 4 and one in tier 5.
    tier, method, _ = assign_tier_at_ingestion({
        "document_type": "unknown_type_no_match",
        "raw_text": "tech press mentions a forum post about X.",
    })
    # tier 4: "tech press"; tier 5: "forum post". Tie → 5.
    assert tier == 5
    assert method == "keyword_fallback"


# ---------------------------------------------------------------------------
# 3. adjust_tier_after_extraction() — asymmetric downward path
# ---------------------------------------------------------------------------


def test_adjust_no_hedging_keeps_tier():
    result = adjust_tier_after_extraction(
        "Q4 revenue was $12.3B, audited.", current_tier=1,
    )
    assert result["tier_changed"] is False
    assert result["adjusted_tier"] == 1
    assert result["adjustment_method"] == "none"


def test_adjust_strong_hedging_moves_tier_downward():
    """Multiple strong hedging signals should push tier number UP (less trust)."""
    text = (
        "According to unnamed sources, results may not generalize. "
        "Unverified, anecdotal evidence from rumored deals."
    )
    result = adjust_tier_after_extraction(text, current_tier=2)
    assert result["adjusted_tier"] > 2
    assert result["tier_changed"] is True
    assert result["adjustment_method"] == "regex"
    assert "anonymous_source" in result["hedging_signals"]


def test_adjust_never_moves_tier_upward():
    """The asymmetric invariant: adjusted_tier >= current_tier always."""
    text = "Limited sample size, preliminary results suggest..."
    for starting in (1, 2, 3, 4, 5):
        result = adjust_tier_after_extraction(text, current_tier=starting)
        assert result["adjusted_tier"] >= starting, (
            f"asymmetry violated at starting tier {starting}: "
            f"got {result['adjusted_tier']}"
        )


def test_adjust_tier_5_caps_at_5():
    """Already at the bottom — no further downward room."""
    result = adjust_tier_after_extraction(
        "rumored, allegedly, unverified, anecdotal", current_tier=5,
    )
    assert result["adjusted_tier"] == 5


def test_adjust_llm_fallback_raises_not_implemented():
    """LLM path is gated until middleware ↔ dispatch integration lands."""
    with pytest.raises(NotImplementedError, match="dispatch"):
        adjust_tier_after_extraction(
            "preliminary results suggest", current_tier=2, llm_fallback=True,
        )


def test_adjust_validates_current_tier_in_range():
    for bad in (0, 6, -1, "1", 1.0):
        with pytest.raises((ValueError, TypeError)):
            adjust_tier_after_extraction("text", current_tier=bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4. effective_tier() — multi-source aggregation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tiers,k,expected", [
    ([1], 2, None),                  # only one source, k=2 unreachable
    ([1, 1], 2, 1),
    ([1, 3, 3, 3], 2, 3),            # one Tier-1 doesn't outweigh three Tier-3
    ([2, 2], 2, 2),
    ([5, 5, 5], 2, 5),
    ([1, 2, 3], 2, 2),               # cumulative reaches 2 at tier 2
    ([1, 1, 1, 1, 1], 3, 1),
    ([4, 5, 5, 5], 2, 5),
])
def test_effective_tier_kofn_rule(tiers, k, expected):
    assert effective_tier(tiers, k=k) == expected


def test_effective_tier_default_k_from_constants():
    """Default k is TIER_AGGREGATE_K (2) — empty list returns None
    because 0 < 2."""
    assert effective_tier([]) is None


def test_effective_tier_single_tier_1_source_does_not_override_cohort():
    """The §C.4 failure mode it was designed to catch: a single Tier-1
    source must not silently override a contradicting Tier-3 cohort."""
    assert effective_tier([1, 3, 3, 3], k=2) == 3


# ---------------------------------------------------------------------------
# 5. Emit helpers — typed events round-trip
# ---------------------------------------------------------------------------


def test_emit_tier_assigned_event():
    eid = emit_tier_assigned(
        investigation_id="inv-1",
        document_id="doc-A",
        document_type="peer_reviewed_paper",
        assigned_tier=2,
        classification_method="document_type_lookup",
    )
    rows = trajectory("inv-1")
    assert len(rows) == 1
    event = Event.model_validate(rows[0])
    assert event.event_id == eid
    assert isinstance(event.payload, TierAssignedPayload)
    assert event.payload.document_id == "doc-A"
    assert event.payload.assigned_tier == 2
    assert event.payload.classification_method == "document_type_lookup"
    assert event.payload.keyword_matches == []
    # Envelope document_id is set by the helper.
    assert event.document_id == "doc-A"


def test_emit_tier_assigned_keyword_fallback_records_matches():
    emit_tier_assigned(
        investigation_id="inv-kw", document_id="doc-B",
        document_type=None, assigned_tier=1,
        classification_method="keyword_fallback",
        keyword_matches=["10-k", "audited financial"],
    )
    event = Event.model_validate(trajectory("inv-kw")[0])
    assert event.payload.keyword_matches == ["10-k", "audited financial"]


def test_emit_tier_overridden_event():
    eid = emit_tier_overridden(
        investigation_id="inv-o", chunk_id="chk-1",
        original_tier=2, adjusted_tier=3,
        adjustment_method="regex",
        hedging_signals=["anecdotal", "unconfirmed"],
        reason="Regex detected 2 hedging signals",
    )
    event = Event.model_validate(trajectory("inv-o")[0])
    assert event.event_id == eid
    assert isinstance(event.payload, TierOverriddenPayload)
    assert event.payload.original_tier == 2
    assert event.payload.adjusted_tier == 3
    assert event.payload.adjustment_method == "regex"
    assert event.payload.hedging_signals == ["anecdotal", "unconfirmed"]


def test_emit_tier_overridden_rejects_asymmetry_violation():
    """Defense in depth: even if a caller bug tried to argue UP,
    the emit helper refuses."""
    with pytest.raises(ValueError, match="asymmetry"):
        emit_tier_overridden(
            investigation_id="inv-bad", chunk_id="chk-x",
            original_tier=3, adjusted_tier=2,  # 2 < 3 — argues UP, illegal
            adjustment_method="regex",
            hedging_signals=[], reason="should never land",
        )


def test_emit_tier_rewrite_bulk_event():
    eid = emit_tier_rewrite_bulk(
        investigation_id=SYSTEM_INVESTIGATION_ID,
        total=120, updated=14, unchanged=106,
        by_tier={1: 22, 2: 35, 3: 28, 4: 25, 5: 10},
    )
    event = Event.model_validate(trajectory(SYSTEM_INVESTIGATION_ID)[0])
    assert event.event_id == eid
    assert isinstance(event.payload, TierRewriteBulkPayload)
    assert event.payload.total == 120
    assert event.payload.updated == 14
    assert event.payload.unchanged == 106
    assert event.payload.by_tier[1] == 22
    assert event.investigation_id == SYSTEM_INVESTIGATION_ID


# ---------------------------------------------------------------------------
# 6. Catalogue + payload sanity
# ---------------------------------------------------------------------------


def test_document_type_catalogue_only_uses_tiers_1_through_5():
    for dtype, tier in DOCUMENT_TYPE_TIER.items():
        assert tier in (1, 2, 3, 4, 5), (
            f"document type {dtype!r} mapped to invalid tier {tier}"
        )


def test_hedging_patterns_are_well_formed():
    """Each entry must be (pattern, signal_type, adjustment ∈ {0,1,2})."""
    import re as _re
    for entry in HEDGING_PATTERNS:
        assert len(entry) == 3
        pattern, signal_type, adjustment = entry
        assert isinstance(pattern, str)
        assert isinstance(signal_type, str) and signal_type
        assert adjustment in (0, 1, 2)
        # Pattern must compile.
        _re.compile(pattern)


def test_tier_assigned_payload_rejects_out_of_range_tier():
    """Defense at the schema level — Pydantic Field(ge=1, le=5)."""
    with pytest.raises(ValidationError):
        TierAssignedPayload(
            document_id="d", document_type=None, assigned_tier=6,
            classification_method="default",
        )
    with pytest.raises(ValidationError):
        TierAssignedPayload(
            document_id="d", document_type=None, assigned_tier=0,
            classification_method="default",
        )
