"""Composite anti-gaming detector — runs all three detector classes
and aggregates verdicts to a single PASS / REVIEW / BLOCK decision
that the PayoutRouter can respect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .attribution_fraud import (
    AttributionFraudScorer,
    score_attribution_payout,
)
from .click_fraud import (
    ClickFraudScorer,
    score_click_event,
)
from .verdict import FraudSignal, FraudVerdict, FraudVerdictKind, verdict_from_signals
from .view_fraud import (
    ViewFraudScorer,
    score_view_event,
)


@dataclass
class AntiGamingDetector:
    """Holds the per-session and per-creator scorers."""

    click_scorer: ClickFraudScorer = field(default_factory=ClickFraudScorer)
    view_scorers: dict[str, ViewFraudScorer] = field(default_factory=dict)
    attribution_scorer: AttributionFraudScorer = field(default_factory=AttributionFraudScorer)

    def view_scorer_for(self, session_id: str) -> ViewFraudScorer:
        if session_id not in self.view_scorers:
            self.view_scorers[session_id] = ViewFraudScorer()
        return self.view_scorers[session_id]


def _merge_verdicts(
    verdicts: list[FraudVerdict],
    subject_ref: str | None = None,
) -> FraudVerdict:
    all_signals: list[FraudSignal] = []
    for v in verdicts:
        all_signals.extend(v.signals)
    return verdict_from_signals(tuple(all_signals), subject_ref=subject_ref)


def run_full_check(
    detector: AntiGamingDetector,
    *,
    session_id: str,
    user_agent: str,
    ip: str,
    dwell_seconds: float,
    view_dwell_ms: float,
    ad_id: str,
    ts_seconds: float,
    creator_id: str | None = None,
    chain_depth: int = 0,
) -> FraudVerdict:
    """Run all three detector classes on a single impression-and-click.

    Returns the composite verdict; the caller (PayoutRouter or escrow
    queue) decides whether to route, escrow, or block the payout.
    """
    detector.click_scorer.record(user_agent=user_agent, ip=ip)
    window_ua_h, window_ip_h = detector.click_scorer.score()
    click_v = score_click_event(
        dwell_seconds=dwell_seconds,
        window_ua_entropy=window_ua_h,
        window_ip_entropy=window_ip_h,
        subject_ref=session_id,
    )

    view_scorer = detector.view_scorer_for(session_id)
    is_repeat, rate = view_scorer.record(ad_id=ad_id, ts_seconds=ts_seconds)
    view_v = score_view_event(
        dwell_ms=view_dwell_ms,
        session_rate_per_minute=rate,
        is_repeat_impression=is_repeat,
        subject_ref=session_id,
    )

    verdicts: list[FraudVerdict] = [click_v, view_v]

    if creator_id is not None:
        consumer_share = detector.attribution_scorer.consumer_share_for(creator_id)
        attr_v = score_attribution_payout(
            creator_id=creator_id,
            consumer_share=consumer_share,
            chain_depth=chain_depth,
            subject_ref=creator_id,
        )
        verdicts.append(attr_v)

    return _merge_verdicts(verdicts, subject_ref=session_id)


__all__ = [
    "AntiGamingDetector",
    "FraudVerdictKind",
    "run_full_check",
]
