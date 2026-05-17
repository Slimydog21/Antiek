"""Verification result dataclasses.

Two result shapes — one for **role re-dispatch** verification
(``VerifyResult`` from upstream ``verify.py``) and one for **claim**
verification (``VerificationResult`` from upstream ``rlm_verify.py``).
Kept separate because the two paths surface different evidence:

- ``VerifyResult`` carries full re-dispatched trace records so the
  caller can archive the disagreement reason for backtesting.
- ``VerificationResult`` carries the (possibly numeric) agreed
  answer plus plausibility issues so the DAG-layer verifier can
  decide whether to propagate the value to children.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class VerifyResult:
    """Result of ``verify_with_redispatch``. ``votes`` lists each
    independent dispatch's agreement status; ``dispatched_responses``
    is the full trace-record list so the caller can archive the
    disagreement evidence for backtesting."""

    agreed: bool
    agreement_count: int
    dispatched_count: int
    votes: List[Dict[str, Any]] = field(default_factory=list)
    dispatched_responses: List[Dict[str, Any]] = field(default_factory=list)
    tiebreaker_used: bool = False
    ts: str = field(default_factory=_utc_iso_now)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    """Result of ``verify_claim`` / ``verified_answer`` (RLM-style).
    ``agreed_answer`` is the normalized winning value when ``accepted``
    is True; ``disagreement_reason`` is set when False.
    ``plausibility_issues`` is non-empty when the agreed answer
    failed a sign / range / units check — the claim is accepted but
    flagged for human review (``hedged=True``)."""

    claim_id: str
    accepted: bool
    agreement_count: int
    dispatch_count: int
    responses: List[str] = field(default_factory=list)
    agreed_answer: Optional[str] = None
    disagreement_reason: Optional[str] = None
    hedged: bool = False
    plausibility_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "accepted": self.accepted,
            "agreement_count": self.agreement_count,
            "dispatch_count": self.dispatch_count,
            "agreed_answer": self.agreed_answer,
            "disagreement_reason": self.disagreement_reason,
            "hedged": self.hedged,
            "plausibility_issues": self.plausibility_issues,
        }
