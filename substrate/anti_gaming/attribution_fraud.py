"""Attribution-fraud detection — outsized single-user rev-share + collusion.

Per master-spec §9.2 + the Sprint 30+ long-tail thread:
attribution-gaming looks like (a) a single consuming user accounting
for an outsized fraction of one creator's monthly rev-share (likely
self-attribution), (b) suspicious attribution-chain depth on a single
session (long synthetic citation chains pulling in a creator's content
artificially), and (c) creator-cluster collusion — a small group of
creators that disproportionately attribute to each other (mutual
boosting).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .verdict import FraudSignal, FraudVerdict, verdict_from_signals


SINGLE_USER_DOMINANCE_THRESHOLD = 0.55  # > 55% from one consumer is suspicious
DEEP_CHAIN_THRESHOLD = 8
CLUSTER_COLLUSION_THRESHOLD = 0.6


@dataclass
class AttributionFraudScorer:
    """Tracks per-creator per-consumer accrual to spot dominance."""

    creator_consumer_cents: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))

    def record(self, *, creator_id: str, consumer_user_id: str, cents: int) -> None:
        self.creator_consumer_cents[creator_id][consumer_user_id] += cents

    def consumer_share_for(self, creator_id: str) -> dict[str, float]:
        per = self.creator_consumer_cents.get(creator_id, {})
        total = sum(per.values())
        if total == 0:
            return {}
        return {c: v / total for c, v in per.items()}


def score_attribution_payout(
    *,
    creator_id: str,
    consumer_share: dict[str, float],
    chain_depth: int,
    subject_ref: Optional[str] = None,
) -> FraudVerdict:
    """Score a payout decision against the creator's accrual history."""
    signals: list[FraudSignal] = []
    if consumer_share:
        top = max(consumer_share.values())
        if top > SINGLE_USER_DOMINANCE_THRESHOLD:
            # Map [SINGLE_USER_DOMINANCE_THRESHOLD, 1.0] → [0, 1].
            denom = max(1e-9, 1.0 - SINGLE_USER_DOMINANCE_THRESHOLD)
            score = (top - SINGLE_USER_DOMINANCE_THRESHOLD) / denom
            signals.append(FraudSignal(
                name="single_consumer_dominance",
                score=max(0.0, min(1.0, score)),
                detail=f"top consumer={top:.2%} of creator {creator_id}'s accrual",
            ))
    if chain_depth > DEEP_CHAIN_THRESHOLD:
        excess = chain_depth - DEEP_CHAIN_THRESHOLD
        score = min(1.0, excess / DEEP_CHAIN_THRESHOLD)
        signals.append(FraudSignal(
            name="deep_attribution_chain",
            score=score,
            detail=f"chain_depth={chain_depth} above {DEEP_CHAIN_THRESHOLD}",
        ))
    return verdict_from_signals(tuple(signals), subject_ref=subject_ref or creator_id)


def detect_creator_cluster_collusion(
    *,
    creator_pairwise_attribution: dict[tuple[str, str], int],
    creators: list[str],
) -> list[FraudVerdict]:
    """Detect mutually-boosting creator clusters.

    `creator_pairwise_attribution[(a, b)]` = cents that creator-a's
    notes attributed to creator-b's documents over the audit window.
    `creators` is the candidate ring (the set under suspicion).

    A cluster fires for creator c when:
      - c is in the candidate ring,
      - c's attribution to OTHER ring members ÷ c's total outbound
        attribution exceeds CLUSTER_COLLUSION_THRESHOLD, AND
      - the ring has ≥ 3 members.

    Attributions from c to non-ring recipients are correctly counted
    in the denominator (outbound) but NOT the numerator (ring-share).
    A creator with healthy outbound diversity to non-ring recipients
    will not be flagged even if some attribution lands within the ring.
    """
    verdicts: list[FraudVerdict] = []
    if len(creators) < 3:
        return verdicts
    ring = set(creators)
    outbound_totals: dict[str, int] = defaultdict(int)
    for (a, _b), cents in creator_pairwise_attribution.items():
        outbound_totals[a] += cents
    for c in creators:
        outbound = outbound_totals.get(c, 0)
        if outbound == 0:
            continue
        # Ring-internal attribution only.
        ring_receivers = [
            (other, cents) for (a, other), cents in creator_pairwise_attribution.items()
            if a == c and cents > 0 and other != c and other in ring
        ]
        if len(ring_receivers) < 2:
            continue
        ring_total = sum(v for _, v in ring_receivers)
        ratio = ring_total / outbound if outbound > 0 else 0.0
        if ratio >= CLUSTER_COLLUSION_THRESHOLD:
            verdicts.append(verdict_from_signals(
                (FraudSignal(
                    name="cluster_collusion",
                    score=min(1.0, ratio),
                    detail=(
                        f"creator {c} routes {ratio:.2%} of outbound to "
                        f"{len(ring_receivers)} ring peers"
                    ),
                ),),
                subject_ref=c,
            ))
    return verdicts
