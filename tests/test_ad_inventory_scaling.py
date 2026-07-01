"""Sprint 25+ ad-inventory scaling policy tests."""

from __future__ import annotations

import pytest

from substrate.ad_inventory import (
    AdPlacementContext,
    AdSlotPattern,
    evaluate_ad_placement,
    should_suppress_ad_slot,
)


GOOD_PROSE = (
    "The dispatch tier decision was not a taste call. It was an accounting "
    "claim about acceptable synthesis cost under verifier pressure. The "
    "operator can keep Opus on the synthesis tier only if the resulting "
    "artifact quality pays for the additional spend."
)

MEDIUM_PROSE = (
    "The synthesis tier changed after the measurement window. Moreover, the "
    "operator kept the quality bar fixed while cost pressure increased. "
    "Perhaps, arguably, it could be argued that this makes the conclusion "
    "less direct than the underlying evidence."
)

BAD_PROSE = (
    "Key takeaways:\n"
    "- one\n- two\n- three\n- four\n- five\n- six\n- seven\n"
    "In conclusion, these are the key takeaways."
)


def test_inline_sponsor_renders_for_clean_prose():
    decision = evaluate_ad_placement(
        AdPlacementContext(
            page_id="page-1",
            surrounding_text=GOOD_PROSE,
            pattern=AdSlotPattern.INLINE_SPONSOR,
        )
    )
    assert decision.should_suppress is False
    assert decision.pattern == AdSlotPattern.INLINE_SPONSOR
    assert decision.voice_score >= 0.85


def test_inline_sponsor_uses_stricter_threshold_than_page_border():
    inline = evaluate_ad_placement(
        AdPlacementContext(
            page_id="page-inline",
            surrounding_text=MEDIUM_PROSE,
            pattern="inline-sponsor",
        )
    )
    border = evaluate_ad_placement(
        AdPlacementContext(
            page_id="page-border",
            surrounding_text=MEDIUM_PROSE,
            pattern="page-border",
        )
    )
    assert inline.voice_score == pytest.approx(border.voice_score)
    assert inline.should_suppress is True
    assert border.should_suppress is False


def test_heavy_voice_violation_suppresses_any_pattern():
    for pattern in ("inline-sponsor", "page-border"):
        decision = evaluate_ad_placement(
            AdPlacementContext(
                page_id=f"page-{pattern}",
                surrounding_text=BAD_PROSE,
                pattern=pattern,
            )
        )
        assert decision.should_suppress is True
        assert "heavy violation" in decision.reason


def test_boolean_helper_matches_decision_contract():
    decision = evaluate_ad_placement(
        AdPlacementContext(
            page_id="page-1",
            surrounding_text=GOOD_PROSE,
            pattern="page-border",
        )
    )
    assert should_suppress_ad_slot(
        page_id="page-1",
        surrounding_text=GOOD_PROSE,
        pattern="page-border",
    ) == decision.should_suppress


def test_unknown_slot_pattern_is_rejected_loudly():
    with pytest.raises(ValueError, match="unknown ad slot pattern"):
        evaluate_ad_placement(
            AdPlacementContext(
                page_id="page-1",
                surrounding_text=GOOD_PROSE,
                pattern="mid-prose-takeover",
            )
        )
