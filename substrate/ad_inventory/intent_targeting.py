"""Multi-dimensional ad targeting (Sprint 25+ phase 1).

Per the Sprint 25+ breakdown phase 1: "The vertical-ad mechanic from
Sprints 23–24 expands to every public-graph page. Inventory scales
with traffic. Topic classification gets more nuanced (sector +
sub-sector + audience-intent dimensions)."

The existing ``ad_bidding.LeadGenAdInventory`` matches on a flat
topic-string list. This module adds the second-generation matcher:

  - ``PageContext`` — what we know about the page being rendered:
    sector, sub_sector, audience_intent signals.
  - ``InventoryTargeting`` — what an inventory item targets across
    the same three dimensions. Each dimension is optional; an empty
    tuple means "match any".
  - ``score_inventory_match`` — produces a non-negative score per
    (page, inventory) pair using weighted dimension overlap.
  - ``select_targeted_ad`` — picks the highest-scoring item; falls
    back to flat-topic matching for inventory items that haven't
    been re-tagged yet.

The match-scoring is deliberately a transparent weighted sum rather
than a learned ranker — per the master-spec §5 + §16 voice / dispatch
discipline, the substrate prefers explainable selection in the early
revenue regime. A learned ranker may replace this once the
``ad_impression`` outcomes table has enough labelled data, but that
is Sprint 30+ work and is REJECTed here as premature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .ad_bidding import AdInventoryItem


# Weights are intentionally exposed as module constants so the operator
# can tune them without touching the matcher. The default weighting
# favors sector > sub_sector > audience_intent because sector is the
# coarsest, most reliable signal — sub-sector and intent only add
# nuance, they don't substitute for the primary sector match.
WEIGHT_SECTOR_MATCH: float = 3.0
WEIGHT_SUB_SECTOR_MATCH: float = 2.0
WEIGHT_AUDIENCE_INTENT_MATCH: float = 1.0

# Minimum score required for a match to be considered. A page that
# scores zero on every dimension means there is no signal at all —
# we refuse to serve a contextually-arbitrary ad in that case.
MIN_MATCH_SCORE: float = 1.0


@dataclass(frozen=True)
class PageContext:
    """Render-time signal about the page being shown.

    Produced by the ``decomposer`` role's topic classification +
    Sprint 25+ enrichment. ``sector`` and ``sub_sector`` are single-
    valued (the page is primarily about one thing); ``audience_intents``
    is a small set (the same page can serve curious-onlooker AND
    decision-maker readers).
    """

    sector: Optional[str]
    sub_sector: Optional[str]
    audience_intents: tuple[str, ...]
    # Carried for fallback to flat-topic matching when inventory
    # hasn't been re-tagged yet. The flat topic list is the union
    # of (sector, sub_sector, audience_intents) plus any legacy
    # topic strings the decomposer produced.
    flat_topics: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class InventoryTargeting:
    """Multi-dimensional targeting metadata for one inventory item.

    Each dimension is optional. An empty tuple means "match any value
    on this dimension" — useful for a generic brand advertiser that
    accepts any context within a sector.
    """

    target_sectors: tuple[str, ...] = ()
    target_sub_sectors: tuple[str, ...] = ()
    target_audience_intents: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True iff this targeting has zero dimensions filled. Such
        items must fall through to flat-topic matching."""
        return (
            not self.target_sectors
            and not self.target_sub_sectors
            and not self.target_audience_intents
        )


@dataclass(frozen=True)
class TargetedInventoryItem:
    """Pairs an ad-bidding inventory item with its targeting metadata.

    Kept as a separate container (rather than extending AdInventoryItem)
    so the Sprint 23-24 mechanic stays intact for advertisers that
    haven't filled in the second-generation targeting fields. The
    matcher's fallback logic relies on the original ``target_topics``
    on the underlying ``AdInventoryItem``.
    """

    item: AdInventoryItem
    targeting: InventoryTargeting


def score_inventory_match(
    context: PageContext,
    targeting: InventoryTargeting,
) -> float:
    """Weighted-overlap score for one (page, inventory) pair.

    A dimension contributes its weight when:
      - the item targets that dimension (non-empty tuple), AND
      - the page's value (or any of its intents) is in the target set.

    A dimension with an empty target tuple contributes 0 — it does
    not penalize, but it also does not lift the score. The intent
    is that a fully-empty ``InventoryTargeting`` falls back to the
    flat-topic matcher instead of winning by default.

    Returns a non-negative float. Higher = better match.
    """
    score = 0.0
    if targeting.target_sectors and context.sector is not None:
        if context.sector in targeting.target_sectors:
            score += WEIGHT_SECTOR_MATCH
    if targeting.target_sub_sectors and context.sub_sector is not None:
        if context.sub_sector in targeting.target_sub_sectors:
            score += WEIGHT_SUB_SECTOR_MATCH
    if targeting.target_audience_intents and context.audience_intents:
        if any(
            i in targeting.target_audience_intents
            for i in context.audience_intents
        ):
            score += WEIGHT_AUDIENCE_INTENT_MATCH
    return score


def select_targeted_ad(
    *,
    context: PageContext,
    targeted_inventory: list[TargetedInventoryItem],
    flat_inventory_fallback: Optional[list[AdInventoryItem]] = None,
) -> Optional[AdInventoryItem]:
    """Pick the inventory item with the highest (match-score × CPM).

    Ties are broken by CPM (higher wins), then by ``inventory_id``
    (lexicographic, for determinism). Returns None if no item clears
    ``MIN_MATCH_SCORE``.

    If ``flat_inventory_fallback`` is supplied and no targeted item
    clears the threshold, the matcher falls back to the Sprint 23-24
    flat-topic ``select_lead_gen_ad`` behavior over the fallback list.
    This keeps un-retagged advertisers serving while the gradual
    rollout completes.

    LEARNED PATH (SPR-10): when ``ANTIEK_LEARNED_AD_RANKER`` is set, this
    delegates to ``auction_ranker.select_ad``, which re-orders candidates by a
    learned value model and picks among the SAME rule-eligible set — then
    degrades to this rule-based logic on any model failure. The signature and
    return type are unchanged, so callers (``ad_impressions.py``) need no edit;
    the flag flips learned↔rule with no code change. The import is lazy to keep
    the rule-based path free of the model machinery and to avoid an import
    cycle.
    """
    # SPR-10 seam: route to the learned ranker iff the flag is on. The lazy
    # import keeps the default (rule-based) path independent of the model
    # modules and breaks the auction_ranker → intent_targeting cycle. The
    # ranker degrades to ``select_targeted_ad_rule_based`` (NOT this function),
    # so a learned-path failure cannot re-enter the flag check and recurse.
    from .auction_ranker import learned_ranker_enabled

    if learned_ranker_enabled():
        from .auction_ranker import select_ad as _learned_select_ad

        return _learned_select_ad(
            context=context,
            targeted_inventory=targeted_inventory,
            flat_inventory_fallback=flat_inventory_fallback,
        )

    return select_targeted_ad_rule_based(
        context=context,
        targeted_inventory=targeted_inventory,
        flat_inventory_fallback=flat_inventory_fallback,
    )


def select_targeted_ad_rule_based(
    *,
    context: PageContext,
    targeted_inventory: list[TargetedInventoryItem],
    flat_inventory_fallback: Optional[list[AdInventoryItem]] = None,
) -> Optional[AdInventoryItem]:
    """The flag-independent rule-based selection core (the Sprint 25+ matcher).

    This is the guaranteed fallback the SPR-10 learned ranker degrades to, and
    the body ``select_targeted_ad`` runs when the flag is off. Kept as a
    separate function (not re-entering ``select_targeted_ad``) so the learned
    path's fallback cannot loop back through the flag check.
    """
    scored: list[tuple[float, Decimal, str, AdInventoryItem]] = []
    for ti in targeted_inventory:
        if ti.targeting.is_empty:
            continue
        s = score_inventory_match(context, ti.targeting)
        if s < MIN_MATCH_SCORE:
            continue
        scored.append((s, ti.item.cpm_usd, ti.item.inventory_id, ti.item))

    if scored:
        scored.sort(key=lambda t: (t[0] * float(t[1]), t[1], t[2]), reverse=True)
        return scored[0][3]

    if flat_inventory_fallback:
        # Fallback: flat-topic match against context.flat_topics, picking
        # the highest CPM among matches. Mirrors select_lead_gen_ad but
        # without coupling this module to that function's signature.
        target_set = {t.lower() for t in context.flat_topics}
        candidates = [
            item for item in flat_inventory_fallback
            if any(t.lower() in target_set for t in item.target_topics)
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda i: (i.cpm_usd, i.inventory_id), reverse=True,
        )
        return candidates[0]

    return None


def context_from_decomposer_topics(
    topics: list[str],
    *,
    sector: Optional[str] = None,
    sub_sector: Optional[str] = None,
    audience_intents: tuple[str, ...] = (),
) -> PageContext:
    """Build a ``PageContext`` from the legacy decomposer topic list
    plus optional second-generation enrichment. The flat-topic list
    is preserved so the fallback path still works for inventory items
    that have not been re-tagged.
    """
    return PageContext(
        sector=sector,
        sub_sector=sub_sector,
        audience_intents=audience_intents,
        flat_topics=tuple(topics),
    )


__all__ = [
    "MIN_MATCH_SCORE",
    "PageContext",
    "InventoryTargeting",
    "TargetedInventoryItem",
    "WEIGHT_AUDIENCE_INTENT_MATCH",
    "WEIGHT_SECTOR_MATCH",
    "WEIGHT_SUB_SECTOR_MATCH",
    "context_from_decomposer_topics",
    "score_inventory_match",
    "select_targeted_ad",
    "select_targeted_ad_rule_based",
]
