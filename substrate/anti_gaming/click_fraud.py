"""Click-fraud detection — UA + IP entropy + dwell time.

Per master-spec §9.2: bot traffic looks like (a) low-entropy
User-Agent strings (many sessions sharing the same string), (b)
low-entropy IP subnet (many clicks from a /24 in a small window),
and (c) sub-threshold dwell time between page-load and click.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .verdict import FraudSignal, FraudVerdict, verdict_from_signals


DWELL_FAST_SECONDS = 1.5  # clicks faster than this are bot-suspicious
UA_LOW_ENTROPY = 0.6
IP_LOW_ENTROPY = 0.5


MIN_WINDOW_SAMPLES = 8  # below this, entropy is undefined; treat as "no signal"


def _shannon(values: Iterable[str]) -> float:
    counts: dict[str, int] = {}
    n = 0
    for v in values:
        counts[v] = counts.get(v, 0) + 1
        n += 1
    if n < MIN_WINDOW_SAMPLES:
        # Too few samples to derive an entropy signal; return 1.0 so the
        # downstream scorer sees "diverse" rather than "low-entropy".
        # Otherwise the first N legitimate sessions all false-positive.
        return 1.0
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log2(p) if p > 0 else 0.0
    # Normalise: max entropy for n items is log2(n).
    max_h = math.log2(n)
    return h / max_h if max_h > 0 else 0.0


def ua_entropy(user_agents: Iterable[str]) -> float:
    """Normalised Shannon entropy of UA strings. Low = bot-like."""
    return _shannon(user_agents)


def ip_subnet_entropy(ips: Iterable[str]) -> float:
    """Entropy of /24 subnets (first three IPv4 octets)."""
    subnets = []
    for ip in ips:
        parts = ip.split(".")
        if len(parts) >= 3:
            subnets.append(".".join(parts[:3]))
        else:
            subnets.append(ip)
    return _shannon(subnets)


@dataclass
class ClickFraudScorer:
    """Aggregates click events to compute per-window entropy scores."""

    window_user_agents: list[str] = field(default_factory=list)
    window_ips: list[str] = field(default_factory=list)

    def record(self, *, user_agent: str, ip: str) -> None:
        self.window_user_agents.append(user_agent)
        self.window_ips.append(ip)

    def score(self) -> tuple[float, float]:
        return (
            ua_entropy(self.window_user_agents),
            ip_subnet_entropy(self.window_ips),
        )


def score_click_event(
    *,
    dwell_seconds: float,
    window_ua_entropy: float,
    window_ip_entropy: float,
    subject_ref: Optional[str] = None,
) -> FraudVerdict:
    """Score a single click against the window's entropy."""
    signals: list[FraudSignal] = []
    if dwell_seconds < DWELL_FAST_SECONDS:
        # Map [0, DWELL_FAST_SECONDS] → score [1, 0].
        score = 1.0 - (dwell_seconds / DWELL_FAST_SECONDS)
        signals.append(FraudSignal(
            name="fast_dwell",
            score=max(0.0, min(1.0, score)),
            detail=f"dwell={dwell_seconds:.2f}s below threshold {DWELL_FAST_SECONDS}s",
        ))
    if window_ua_entropy < UA_LOW_ENTROPY:
        score = 1.0 - (window_ua_entropy / UA_LOW_ENTROPY)
        signals.append(FraudSignal(
            name="low_ua_entropy",
            score=max(0.0, min(1.0, score)),
            detail=f"window UA entropy={window_ua_entropy:.2f} below {UA_LOW_ENTROPY}",
        ))
    if window_ip_entropy < IP_LOW_ENTROPY:
        score = 1.0 - (window_ip_entropy / IP_LOW_ENTROPY)
        signals.append(FraudSignal(
            name="low_ip_entropy",
            score=max(0.0, min(1.0, score)),
            detail=f"window IP entropy={window_ip_entropy:.2f} below {IP_LOW_ENTROPY}",
        ))
    return verdict_from_signals(tuple(signals), subject_ref=subject_ref)
