"""Typed proposal + operator-verdict primitives.

A ConfigProposal is the full reproducibility envelope:
- the baseline config that was the prior
- the proposed delta (what changed)
- the cohort window the sweep ran over
- the sweep axes that were explored
- the scoring function name + the score the proposed delta achieved

OperatorVerdict closes the loop: accept, reject, or modify-then-accept.
The verdict is persisted alongside the proposal so a year later the
operator can audit *why* a config came to be.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CohortWindow:
    """The window over which the sweep ran."""

    cohort_id: str
    started_at: str
    ended_at: str
    graded_outcomes_count: int


@dataclass(frozen=True)
class SweepAxes:
    """The axes the sweep explored. Documented so a future operator
    can replay the sweep deterministically."""

    context_pack_compositions: tuple[str, ...]
    dispatch_tier_routes: tuple[str, ...]
    scoring_function_name: str


@dataclass(frozen=True)
class ConfigProposal:
    """A single sweep-produced proposal."""

    proposal_id: str = field(default_factory=lambda: f"prop-{uuid.uuid4().hex[:12]}")
    baseline_config: dict = field(default_factory=dict)
    proposed_delta: dict = field(default_factory=dict)
    cohort: CohortWindow | None = None
    axes: SweepAxes | None = None
    score: float = 0.0
    baseline_score: float = 0.0
    held_out_score: float | None = None  # post-promotion eval, when available
    created_at: str = field(default_factory=_now_iso)

    @property
    def score_improvement(self) -> float:
        return self.score - self.baseline_score


class OperatorVerdictKind(str, enum.Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"
    DEFER = "defer"


@dataclass(frozen=True)
class OperatorVerdict:
    """The operator's decision on a proposal."""

    verdict_id: str = field(default_factory=lambda: f"verd-{uuid.uuid4().hex[:12]}")
    proposal_id: str = ""
    kind: OperatorVerdictKind = OperatorVerdictKind.DEFER
    operator_id: str = "__operator__"
    rationale: str = ""
    modified_delta: dict | None = None  # populated only when kind=MODIFY
    decided_at: str = field(default_factory=_now_iso)


@dataclass
class ProposalLedger:
    """In-memory ledger of proposals + verdicts. Persistence to
    substrate is the caller's responsibility (a substrate table
    schema for this lands in Sprint 30+ if the thread activates)."""

    proposals: dict[str, ConfigProposal] = field(default_factory=dict)
    verdicts: dict[str, OperatorVerdict] = field(default_factory=dict)

    def record_proposal(self, proposal: ConfigProposal) -> None:
        self.proposals[proposal.proposal_id] = proposal

    def record_verdict(self, verdict: OperatorVerdict) -> None:
        if verdict.proposal_id not in self.proposals:
            raise KeyError(f"unknown proposal {verdict.proposal_id!r}")
        self.verdicts[verdict.proposal_id] = verdict

    def verdict_for(self, proposal_id: str) -> OperatorVerdict | None:
        return self.verdicts.get(proposal_id)

    def accepted_proposals(self) -> list[ConfigProposal]:
        return [
            p for pid, p in self.proposals.items()
            if (v := self.verdicts.get(pid)) is not None
            and v.kind in {OperatorVerdictKind.ACCEPT, OperatorVerdictKind.MODIFY}
        ]
