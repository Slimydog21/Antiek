"""Auction feature pipeline — pure (context, candidate) → feature vector (SPR-10 M1).

The first layer of the Axon-style learned ad auction. AppLovin's Axon ranks
candidates by a *learned* prediction of the value of showing a given ad in a
given context, rather than a hand-tuned rule. This module produces the input
features that prediction is computed over: a deterministic, side-effect-free
projection of a ``(PageContext, AdInventoryItem + InventoryTargeting)`` pair
into a small fixed-length float vector.

DESIGN DISCIPLINE (read before adding a feature):

* **PURE.** :func:`extract_features` reads only its arguments. No DB, no clock,
  no network, no global state. Same input → byte-identical vector. This is what
  makes the model trainable offline and replayable.

* **NO TARGET LEAKAGE.** The training LABEL is the realized per-second
  frame-attention value / revenue an impression earned (see
  ``frame_attention.weigh_second`` + ``reader_impressions.revenue_usd_cents``).
  That outcome must NEVER appear as an input feature — a feature that encodes
  the realized value would let the model "predict" the label by copying it,
  inflating offline lift while learning nothing generalizable. Every feature
  here is computable BEFORE the ad is served (it is a property of the
  context/candidate pair, not of what happened after). The leakage guard is
  the unit test ``test_no_label_field_in_feature_provenance``.

* **TARGETING DENYLIST HONORED.** The features are derived ONLY from the
  multi-dimensional targeting signals (sector / sub_sector / audience_intents /
  flat_topics) and the candidate's own targeting + CPM — never from gated book
  body text or reader notes. We assert the context carries none of the
  forbidden keys (``targeting._FORBIDDEN_SIGNAL_KEYS``) defensively; the
  ``PageContext`` shape cannot carry them, but the guard makes the boundary
  unmissable if the shape ever grows.

FEATURE PROVENANCE (rigor #5 — every feature's meaning + substrate origin is
auditable). The order is FIXED; the model's coefficients are positional, so a
reorder is a breaking change and bumps ``FEATURE_SCHEMA_VERSION``.

  idx name                         provenance / meaning
  --- ---------------------------- ------------------------------------------
  0   bias                         constant 1.0 (the intercept term)
  1   sector_match                 1.0 iff context.sector ∈ targeting.target_sectors
  2   sub_sector_match             1.0 iff context.sub_sector ∈ targeting.target_sub_sectors
  3   audience_intent_overlap      |intents ∩ target_intents| / |context.audience_intents|
  4   flat_topic_overlap           |flat_topics ∩ candidate.target_topics| / |flat_topics|
  5   rule_score_norm              intent_targeting.score_inventory_match / MAX_RULE_SCORE
  6   log_cpm                      log1p(float(cpm_usd)) — advertiser's stated bid
  7   targeting_specificity        filled targeting dimensions / 3 (generic vs precise)
  8   context_richness             filled context dimensions / 4 (how much signal we have)

None of 0..8 reads the served outcome. CPM (idx 6) is the advertiser's
PRE-impression stated bid, not realized revenue — it is an input the auction
has at decision time, not a leak of the label.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .ad_bidding import AdInventoryItem
from .intent_targeting import (
    WEIGHT_AUDIENCE_INTENT_MATCH,
    WEIGHT_SECTOR_MATCH,
    WEIGHT_SUB_SECTOR_MATCH,
    InventoryTargeting,
    PageContext,
    score_inventory_match,
)
from .targeting import _FORBIDDEN_SIGNAL_KEYS

# Bump on ANY change to the feature vector shape (a new feature, a reorder, a
# changed normalization). The model artifact stamps the schema version it was
# trained under; loading a model whose schema does not match the current
# extractor is refused (the coefficients would be positionally wrong).
FEATURE_SCHEMA_VERSION = "auction-feat-v1"

# The fixed feature names, in vector order. Length == FEATURE_DIM.
FEATURE_NAMES: tuple[str, ...] = (
    "bias",
    "sector_match",
    "sub_sector_match",
    "audience_intent_overlap",
    "flat_topic_overlap",
    "rule_score_norm",
    "log_cpm",
    "targeting_specificity",
    "context_richness",
)
FEATURE_DIM = len(FEATURE_NAMES)

# Max attainable rule score (all three dimensions hit) — used to normalize
# feature 5 into [0,1] so it is on the same scale as the overlap features.
_MAX_RULE_SCORE = (
    WEIGHT_SECTOR_MATCH + WEIGHT_SUB_SECTOR_MATCH + WEIGHT_AUDIENCE_INTENT_MATCH
)


@dataclass(frozen=True)
class AuctionCandidate:
    """The candidate side of one (context, candidate) pair: an inventory item
    plus its multi-dimensional targeting. Mirrors ``TargetedInventoryItem`` but
    is named for the auction so the ranker's intent reads clearly; the ranker
    builds these straight from ``TargetedInventoryItem``."""

    item: AdInventoryItem
    targeting: InventoryTargeting


def _assert_no_forbidden_context(context: PageContext) -> None:
    """Defense in depth: refuse any context that smuggled a gated/private key.

    ``PageContext`` is a frozen dataclass with fixed fields, so it cannot carry
    a forbidden key today. This guard makes the denylist boundary explicit and
    will trip loudly if the shape ever grows a free-form field. Mirrors
    ``targeting.assert_no_forbidden_signals``."""
    present = {f for f in vars(context)} & _FORBIDDEN_SIGNAL_KEYS
    if present:
        raise ValueError(
            f"PageContext carries forbidden gated/private keys {sorted(present)}; "
            "auction features may use only targeting signals, never body text "
            "or reader notes"
        )


def extract_features(
    context: PageContext, candidate: AuctionCandidate
) -> tuple[float, ...]:
    """Project one (context, candidate) pair to its fixed-length feature vector.

    PURE + deterministic: reads only its arguments. The vector is positional —
    index i is ``FEATURE_NAMES[i]`` — and is exactly ``FEATURE_DIM`` long. No
    served-outcome value is ever read (no label leakage)."""
    _assert_no_forbidden_context(context)
    targeting = candidate.targeting
    item = candidate.item

    sector_match = (
        1.0
        if targeting.target_sectors
        and context.sector is not None
        and context.sector in targeting.target_sectors
        else 0.0
    )
    sub_sector_match = (
        1.0
        if targeting.target_sub_sectors
        and context.sub_sector is not None
        and context.sub_sector in targeting.target_sub_sectors
        else 0.0
    )

    if context.audience_intents and targeting.target_audience_intents:
        hit = sum(
            1 for i in context.audience_intents
            if i in targeting.target_audience_intents
        )
        audience_intent_overlap = hit / len(context.audience_intents)
    else:
        audience_intent_overlap = 0.0

    if context.flat_topics and item.target_topics:
        topic_set = {t.lower() for t in item.target_topics}
        hit_t = sum(1 for t in context.flat_topics if t.lower() in topic_set)
        flat_topic_overlap = hit_t / len(context.flat_topics)
    else:
        flat_topic_overlap = 0.0

    rule_score = score_inventory_match(context, targeting)
    rule_score_norm = rule_score / _MAX_RULE_SCORE if _MAX_RULE_SCORE > 0 else 0.0

    log_cpm = math.log1p(max(0.0, float(item.cpm_usd)))

    filled_targeting = (
        (1 if targeting.target_sectors else 0)
        + (1 if targeting.target_sub_sectors else 0)
        + (1 if targeting.target_audience_intents else 0)
    )
    targeting_specificity = filled_targeting / 3.0

    filled_context = (
        (1 if context.sector is not None else 0)
        + (1 if context.sub_sector is not None else 0)
        + (1 if context.audience_intents else 0)
        + (1 if context.flat_topics else 0)
    )
    context_richness = filled_context / 4.0

    return (
        1.0,
        sector_match,
        sub_sector_match,
        audience_intent_overlap,
        flat_topic_overlap,
        rule_score_norm,
        log_cpm,
        targeting_specificity,
        context_richness,
    )


def feature_provenance() -> dict[str, str]:
    """Read-only map ``feature_name -> substrate provenance`` (rigor #5). Used
    by the leakage guard test and by the runbook to document what each
    coefficient means. NONE of these provenance strings reference a served
    outcome / realized value — that is the no-leakage contract."""
    return {
        "bias": "constant 1.0 intercept",
        "sector_match": "PageContext.sector ∈ InventoryTargeting.target_sectors",
        "sub_sector_match": "PageContext.sub_sector ∈ InventoryTargeting.target_sub_sectors",
        "audience_intent_overlap": (
            "|PageContext.audience_intents ∩ target_audience_intents| / "
            "|PageContext.audience_intents|"
        ),
        "flat_topic_overlap": (
            "|PageContext.flat_topics ∩ AdInventoryItem.target_topics| / "
            "|PageContext.flat_topics|"
        ),
        "rule_score_norm": (
            "intent_targeting.score_inventory_match(context, targeting) / max_rule_score"
        ),
        "log_cpm": "log1p(AdInventoryItem.cpm_usd) — advertiser's pre-impression bid",
        "targeting_specificity": "filled InventoryTargeting dimensions / 3",
        "context_richness": "filled PageContext dimensions / 4",
    }


__all__ = [
    "FEATURE_DIM",
    "FEATURE_NAMES",
    "FEATURE_SCHEMA_VERSION",
    "AuctionCandidate",
    "extract_features",
    "feature_provenance",
]
