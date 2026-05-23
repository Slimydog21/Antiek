"""Topic-classification → ad-inventory selection (Sprint 23-24).

Per master-spec §9.4 + the Sprint 23-24 Phase 1 deliverable:
*"The substrate's existing topic classification (from `decomposer`)
chooses the slot's ad inventory: sector + sub-sector +
audience-intent dimensions."*

This module is the substrate-side matcher. Given a synthesis page's
topic tags (output of `decomposer.classify_topics`) and an inventory
pool (registered ad campaigns), the matcher returns ranked candidate
ads — the highest match wins the slot impression.

Discipline:
- Pure-functional `match_candidates(page_topics, inventory) -> ranked list`
- Scoring weights operator-tunable; defaults align with §9.4
  preference for sector-tagged lead-gen inventory
- No actual bidding (Sprints 23-24 is manual-curated; programmatic
  is Sprint 30+ conditional)
- Inventory items are typed; scorer reads only the published
  targeting fields (no creative-content inspection)
"""

from .matcher import (
    AdCampaign,
    AdSlotPlacement,
    MatchScore,
    PageTopicVector,
    match_candidates,
    score_campaign,
)

__all__ = [
    "AdCampaign",
    "AdSlotPlacement",
    "MatchScore",
    "PageTopicVector",
    "match_candidates",
    "score_campaign",
]
