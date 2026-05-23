"""Tests for substrate.ad_targeting — topic → campaign matcher."""

from __future__ import annotations

import pytest

from substrate.ad_targeting import (
    AdCampaign,
    AdSlotPlacement,
    MatchScore,
    PageTopicVector,
    match_candidates,
    score_campaign,
)


def _campaign(
    *,
    campaign_id: str = "cam-1",
    sector: str = "developer-tools",
    sub_sector: str | None = None,
    intent: str = "trial-signup",
    topics: tuple[str, ...] = (),
    status: str = "active",
) -> AdCampaign:
    return AdCampaign(
        campaign_id=campaign_id,
        advertiser_name="X",
        sector=sector,
        sub_sector=sub_sector,
        intent=intent,
        target_topics=topics,
        creative_headline="headline",
        creative_url="https://example.com",
        status=status,
    )


def _page(
    *,
    sector: str = "developer-tools",
    sub_sector: str | None = None,
    intent: str = "trial-signup",
    topics: tuple[str, ...] = (),
) -> PageTopicVector:
    return PageTopicVector(
        page_id="page-1",
        primary_sector=sector,
        sub_sector=sub_sector,
        intent_signal=intent,
        topic_tags=topics,
    )


# ── score_campaign ──────────────────────────────────────────────


def test_perfect_match_scores_high():
    score = score_campaign(
        page=_page(topics=("python", "tooling"), sub_sector="ide"),
        campaign=_campaign(sub_sector="ide", topics=("python", "tooling")),
    )
    assert score.score >= 0.95
    assert score.sector_component == 1.0
    assert score.intent_component == 1.0
    assert score.topic_component > 0.5


def test_sector_only_match_scores_medium():
    score = score_campaign(
        page=_page(topics=("a",), sub_sector="frontend"),
        campaign=_campaign(sub_sector="backend", topics=()),
    )
    assert score.sector_component == 0.7  # sector matches, sub differs
    assert score.intent_component == 1.0  # both intents match default
    assert 0.3 < score.score < 0.9


def test_sector_mismatch_zeros_sector():
    score = score_campaign(
        page=_page(sector="finance"),
        campaign=_campaign(sector="developer-tools"),
    )
    assert score.sector_component == 0.0


def test_intent_mismatch_zeros_intent():
    score = score_campaign(
        page=_page(intent="trial-signup"),
        campaign=_campaign(intent="newsletter"),
    )
    assert score.intent_component == 0.0


def test_empty_intent_signal_returns_neutral():
    score = score_campaign(
        page=_page(intent=""),
        campaign=_campaign(intent="trial-signup"),
    )
    assert score.intent_component == 0.5


def test_topic_overlap_uses_jaccard():
    score = score_campaign(
        page=_page(topics=("a", "b", "c")),
        campaign=_campaign(topics=("a", "b", "x", "y")),
    )
    # Intersection {a, b} / Union {a, b, c, x, y} = 2/5 = 0.4
    assert abs(score.topic_component - 0.4) < 1e-9


def test_topic_disjoint_scores_zero():
    score = score_campaign(
        page=_page(topics=("a",)),
        campaign=_campaign(topics=("z",)),
    )
    assert score.topic_component == 0.0


def test_weights_override_scoring():
    page = _page(topics=("a",))
    campaign = _campaign(topics=("a",))
    default = score_campaign(page=page, campaign=campaign)
    only_topic = score_campaign(
        page=page, campaign=campaign,
        weights={"sector": 0.0, "intent": 0.0, "topic": 1.0},
    )
    # Forcing all weight onto topic axis changes the score.
    assert only_topic.score != default.score


# ── match_candidates ───────────────────────────────────────────


def test_match_candidates_filters_below_min_score():
    page = _page(sector="finance", intent="newsletter")
    # Mismatched sector + mismatched intent → score = 0 across all axes
    inventory = [_campaign(sector="developer-tools", intent="trial-signup")]
    placements = match_candidates(page=page, inventory=inventory)
    assert placements == []


def test_match_candidates_filters_inactive():
    page = _page()
    inventory = [
        _campaign(campaign_id="cam-active", status="active"),
        _campaign(campaign_id="cam-paused", status="paused"),
        _campaign(campaign_id="cam-draft", status="draft"),
    ]
    placements = match_candidates(page=page, inventory=inventory)
    ids = {p.campaign.campaign_id for p in placements}
    assert "cam-active" in ids
    assert "cam-paused" not in ids
    assert "cam-draft" not in ids


def test_match_candidates_orders_by_score_descending():
    page = _page(sub_sector="ide", topics=("python",))
    inventory = [
        _campaign(campaign_id="cam-perfect", sub_sector="ide", topics=("python",)),
        _campaign(campaign_id="cam-sector-only", sub_sector="backend"),
        _campaign(campaign_id="cam-no-topics", sub_sector="ide"),
    ]
    placements = match_candidates(page=page, inventory=inventory)
    assert placements[0].campaign.campaign_id == "cam-perfect"
    assert placements[0].score >= placements[-1].score


def test_match_candidates_eligible_statuses_override():
    """Caller can broaden eligibility (e.g., include paused for preview)."""
    page = _page()
    inventory = [_campaign(status="paused")]
    placements = match_candidates(
        page=page, inventory=inventory,
        statuses_eligible=("active", "paused"),
    )
    assert len(placements) == 1


def test_match_candidates_empty_inventory_returns_empty():
    page = _page()
    placements = match_candidates(page=page, inventory=[])
    assert placements == []


def test_match_candidates_ties_break_deterministically():
    """Equal-score campaigns sort by campaign_id ascending."""
    page = _page()
    inventory = [
        _campaign(campaign_id="cam-z"),
        _campaign(campaign_id="cam-a"),
    ]
    placements = match_candidates(page=page, inventory=inventory)
    assert placements[0].campaign.campaign_id == "cam-a"
    assert placements[1].campaign.campaign_id == "cam-z"


def test_min_score_threshold_configurable():
    page = _page(sector="finance")
    inventory = [_campaign(sector="developer-tools")]
    # Default min_score filters this; lower min_score includes it.
    placements = match_candidates(page=page, inventory=inventory, min_score=0.0)
    assert len(placements) == 1
