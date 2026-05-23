"""Fraud verdict primitives shared by all anti-gaming detectors."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class FraudVerdictKind(str, enum.Enum):
    PASS = "pass"
    REVIEW = "review"
    BLOCK = "block"


@dataclass(frozen=True)
class FraudSignal:
    """One signal contributing to a verdict. Multiple signals stack."""

    name: str
    score: float  # in [0, 1] — higher is more fraud-like
    detail: str


@dataclass(frozen=True)
class FraudVerdict:
    """The composite output of one or more detectors."""

    verdict_id: str = field(default_factory=lambda: f"av-{uuid.uuid4().hex[:12]}")
    kind: FraudVerdictKind = FraudVerdictKind.PASS
    signals: tuple[FraudSignal, ...] = ()
    subject_ref: Optional[str] = None
    decided_at: str = field(default_factory=_now_iso)

    @property
    def total_score(self) -> float:
        if not self.signals:
            return 0.0
        return sum(s.score for s in self.signals) / len(self.signals)


REVIEW_THRESHOLD = 0.45
BLOCK_THRESHOLD = 0.75


def verdict_from_signals(
    signals: tuple[FraudSignal, ...],
    *,
    subject_ref: Optional[str] = None,
) -> FraudVerdict:
    """Compose a verdict from signals using the documented thresholds.

    Thresholds (REVIEW=0.45 / BLOCK=0.75) are tuned for the §9.2
    adversarial review — too low and legitimate sessions get held up,
    too high and the red-team report's attack classes get through.
    """
    if not signals:
        return FraudVerdict(subject_ref=subject_ref)
    avg = sum(s.score for s in signals) / len(signals)
    if avg >= BLOCK_THRESHOLD:
        kind = FraudVerdictKind.BLOCK
    elif avg >= REVIEW_THRESHOLD:
        kind = FraudVerdictKind.REVIEW
    else:
        kind = FraudVerdictKind.PASS
    return FraudVerdict(kind=kind, signals=signals, subject_ref=subject_ref)
