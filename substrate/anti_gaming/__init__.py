"""Anti-gaming detectors for ad inventory + rev-share (Sprint 23-24).

Per master-spec §9.2 + §9.7 + the Sprint 23-24 Phase 4 ads gate:
sprints 23-24 ship ONLY after the anti-gaming layer passes a documented
adversarial review. This module is the substrate side of that review.

Three detector classes, all running BEFORE the payout router:

1. click_fraud — bot-traffic scoring against UA + IP entropy + dwell time
2. view_fraud — session-burst detection + short-dwell + repeat-impression
3. attribution_fraud — single-user-outsized creator rev-share +
   suspicious attribution-chain depth + cross-user collusion (long-tail)

Detectors emit a FraudVerdict (PASS / REVIEW / BLOCK). The PayoutRouter
respects the verdict: PASS → route, REVIEW → escrow + operator queue,
BLOCK → drop + audit.

Substrate-only. Activation gated on Sprint 22 multi-user pivot stability +
external red-team report at docs/sprint23_red_team.md (see the Sprint
23-24 §1 callout in docs/sprint-breakdown.html).
"""

from .attribution_fraud import (
    AttributionFraudScorer,
    detect_creator_cluster_collusion,
    score_attribution_payout,
)
from .click_fraud import (
    ClickFraudScorer,
    ip_subnet_entropy,
    score_click_event,
    ua_entropy,
)
from .detector import AntiGamingDetector, run_full_check
from .verdict import FraudSignal, FraudVerdict, FraudVerdictKind
from .view_fraud import (
    SessionBurstWindow,
    ViewFraudScorer,
    score_view_event,
)

__all__ = [
    "AntiGamingDetector",
    "AttributionFraudScorer",
    "ClickFraudScorer",
    "FraudSignal",
    "FraudVerdict",
    "FraudVerdictKind",
    "SessionBurstWindow",
    "ViewFraudScorer",
    "detect_creator_cluster_collusion",
    "ip_subnet_entropy",
    "run_full_check",
    "score_attribution_payout",
    "score_click_event",
    "score_view_event",
    "ua_entropy",
]
