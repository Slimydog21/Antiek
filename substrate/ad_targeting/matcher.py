"""Topic + sector + intent → ad-campaign ranking."""

from __future__ import annotations

from dataclasses import dataclass

# Default weights (operator-tunable).
WEIGHT_SECTOR_MATCH = 0.50
WEIGHT_INTENT_MATCH = 0.30
WEIGHT_TOPIC_OVERLAP = 0.20
MIN_SCORE_FOR_INCLUSION = 0.30  # candidates below this are dropped


@dataclass(frozen=True)
class AdCampaign:
    """A campaign in the inventory pool. Matches AdvertiserConsole row."""

    campaign_id: str
    advertiser_name: str
    sector: str
    sub_sector: str | None
    intent: str  # one of "trial-signup" | "lead-gen" | "demo" | "newsletter" | etc.
    target_topics: tuple[str, ...]
    creative_headline: str
    creative_url: str
    daily_budget_cents: int = 0
    status: str = "active"  # "active" | "paused" | "draft" | "rejected"


@dataclass(frozen=True)
class PageTopicVector:
    """The decomposer's classification of one synthesis page."""

    page_id: str
    primary_sector: str
    sub_sector: str | None = None
    intent_signal: str = ""  # may be empty if decomposer didn't infer
    topic_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchScore:
    """The composite match score for one (page, campaign) pair."""

    campaign_id: str
    score: float  # in [0, 1]
    sector_component: float
    intent_component: float
    topic_component: float
    detail: str


@dataclass(frozen=True)
class AdSlotPlacement:
    """The selected placement for one impression."""

    page_id: str
    campaign: AdCampaign
    score: float


def _sector_score(page_sector: str, campaign_sector: str, page_sub: str | None, campaign_sub: str | None) -> float:
    """1.0 if sector+sub_sector match; 0.7 if sector only; 0.0 otherwise."""
    if not page_sector or not campaign_sector:
        return 0.0
    if page_sector.lower() != campaign_sector.lower():
        return 0.0
    if page_sub and campaign_sub and page_sub.lower() == campaign_sub.lower():
        return 1.0
    return 0.7


def _intent_score(page_intent: str, campaign_intent: str) -> float:
    if not page_intent or not campaign_intent:
        # No signal from page → neutral score (0.5), not zero.
        return 0.5
    return 1.0 if page_intent.lower() == campaign_intent.lower() else 0.0


def _topic_overlap_score(page_topics: tuple[str, ...], campaign_topics: tuple[str, ...]) -> float:
    if not page_topics or not campaign_topics:
        return 0.0
    page_set = {t.lower() for t in page_topics}
    campaign_set = {t.lower() for t in campaign_topics}
    intersection = page_set & campaign_set
    if not intersection:
        return 0.0
    # Jaccard-style normalisation.
    return len(intersection) / len(page_set | campaign_set)


def score_campaign(
    *,
    page: PageTopicVector,
    campaign: AdCampaign,
    weights: dict[str, float] | None = None,
) -> MatchScore:
    """Compute the composite score for one (page, campaign) pair."""
    w = weights or {
        "sector": WEIGHT_SECTOR_MATCH,
        "intent": WEIGHT_INTENT_MATCH,
        "topic": WEIGHT_TOPIC_OVERLAP,
    }
    sector = _sector_score(
        page.primary_sector, campaign.sector,
        page.sub_sector, campaign.sub_sector,
    )
    intent = _intent_score(page.intent_signal, campaign.intent)
    topic = _topic_overlap_score(page.topic_tags, campaign.target_topics)
    score = (
        w.get("sector", WEIGHT_SECTOR_MATCH) * sector +
        w.get("intent", WEIGHT_INTENT_MATCH) * intent +
        w.get("topic", WEIGHT_TOPIC_OVERLAP) * topic
    )
    return MatchScore(
        campaign_id=campaign.campaign_id,
        score=score,
        sector_component=sector,
        intent_component=intent,
        topic_component=topic,
        detail=(
            f"sector={sector:.2f}, intent={intent:.2f}, topic={topic:.2f}"
        ),
    )


def match_candidates(
    *,
    page: PageTopicVector,
    inventory: list[AdCampaign],
    weights: dict[str, float] | None = None,
    min_score: float = MIN_SCORE_FOR_INCLUSION,
    statuses_eligible: tuple[str, ...] = ("active",),
) -> list[AdSlotPlacement]:
    """Score and rank inventory by match-score for one page.

    Returns active campaigns sorted descending by score. Campaigns
    below `min_score` are filtered out — a low-score campaign on an
    unrelated page is worse than no ad (the AdSlot voice-discipline
    suppression then has more room to maneuver).
    """
    placements: list[AdSlotPlacement] = []
    for campaign in inventory:
        if campaign.status not in statuses_eligible:
            continue
        match = score_campaign(page=page, campaign=campaign, weights=weights)
        if match.score < min_score:
            continue
        placements.append(AdSlotPlacement(
            page_id=page.page_id,
            campaign=campaign,
            score=match.score,
        ))
    placements.sort(key=lambda p: (-p.score, p.campaign.campaign_id))
    return placements
