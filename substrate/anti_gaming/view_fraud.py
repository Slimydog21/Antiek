"""View-fraud detection — session burst + short dwell + repeat impression.

Per master-spec §9.2 view-fraud surface: a real session has roughly
human pacing (≤ ~30 impressions/minute even on a fast scroller); short
dwell (impression rendered but page closed within 200ms) indicates a
headless render; the same (session_id, ad_id) repeated within a minute
indicates impression-spamming.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .verdict import FraudSignal, FraudVerdict, verdict_from_signals


BURST_WINDOW_SECONDS = 60
BURST_THRESHOLD_PER_MINUTE = 30
SHORT_DWELL_MS = 200
REPEAT_WINDOW_SECONDS = 60


@dataclass
class SessionBurstWindow:
    """Rolling window over impression timestamps for a single session."""

    window_seconds: float = BURST_WINDOW_SECONDS
    threshold_per_minute: int = BURST_THRESHOLD_PER_MINUTE
    timestamps: deque[float] = field(default_factory=deque)

    def record(self, ts_seconds: float) -> None:
        self.timestamps.append(ts_seconds)
        cutoff = ts_seconds - self.window_seconds
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def rate_per_minute(self) -> float:
        if not self.timestamps:
            return 0.0
        return len(self.timestamps) * (60.0 / self.window_seconds)


@dataclass
class ViewFraudScorer:
    """One scorer per session — tracks burst rate + recent (session, ad) pairs."""

    burst: SessionBurstWindow = field(default_factory=SessionBurstWindow)
    recent_pairs: dict[str, float] = field(default_factory=dict)

    def record(self, *, ad_id: str, ts_seconds: float) -> tuple[bool, float]:
        """Record an impression. Returns (is_repeat, current_rate)."""
        self.burst.record(ts_seconds)
        last_seen = self.recent_pairs.get(ad_id, -1e9)
        is_repeat = (ts_seconds - last_seen) < REPEAT_WINDOW_SECONDS
        self.recent_pairs[ad_id] = ts_seconds
        return (is_repeat, self.burst.rate_per_minute())


def score_view_event(
    *,
    dwell_ms: float,
    session_rate_per_minute: float,
    is_repeat_impression: bool,
    subject_ref: Optional[str] = None,
) -> FraudVerdict:
    """Score a single view event."""
    signals: list[FraudSignal] = []
    if dwell_ms < SHORT_DWELL_MS:
        score = 1.0 - (dwell_ms / SHORT_DWELL_MS)
        signals.append(FraudSignal(
            name="short_dwell",
            score=max(0.0, min(1.0, score)),
            detail=f"dwell_ms={dwell_ms:.0f} below {SHORT_DWELL_MS}",
        ))
    if session_rate_per_minute > BURST_THRESHOLD_PER_MINUTE:
        excess = session_rate_per_minute - BURST_THRESHOLD_PER_MINUTE
        score = min(1.0, excess / BURST_THRESHOLD_PER_MINUTE)
        signals.append(FraudSignal(
            name="session_burst",
            score=score,
            detail=f"rate={session_rate_per_minute:.1f}/min above {BURST_THRESHOLD_PER_MINUTE}",
        ))
    if is_repeat_impression:
        signals.append(FraudSignal(
            name="repeat_impression",
            score=0.85,
            detail=f"same ad seen within {REPEAT_WINDOW_SECONDS}s",
        ))
    return verdict_from_signals(tuple(signals), subject_ref=subject_ref)
