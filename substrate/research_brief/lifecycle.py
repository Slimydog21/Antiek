"""Lifecycle transitions and the sole run-authorization constructor."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .model import BriefState, LifecycleEvent, ResearchBrief
from .provenance import brief_content_hash


def _transition(
    brief: ResearchBrief, target: BriefState, *, actor: str, occurred_at: str
) -> ResearchBrief:
    allowed = {
        BriefState.DRAFT: (BriefState.AMENDED, BriefState.APPROVED),
        BriefState.AMENDED: (BriefState.AMENDED, BriefState.APPROVED),
        BriefState.APPROVED: (),
    }
    if target not in allowed[brief.state]:
        raise ValueError(f"cannot transition {brief.state.value} to {target.value}")
    if not actor.strip() or not occurred_at.strip():
        raise ValueError("actor and occurred_at are required injected values")
    event = LifecycleEvent(target.value, actor, occurred_at)
    return replace(brief, state=target, events=(*brief.events, event))


def amend(brief: ResearchBrief, *, actor: str, occurred_at: str) -> ResearchBrief:
    return _transition(brief, BriefState.AMENDED, actor=actor, occurred_at=occurred_at)


def approve(brief: ResearchBrief, *, actor: str, occurred_at: str) -> ResearchBrief:
    return _transition(brief, BriefState.APPROVED, actor=actor, occurred_at=occurred_at)


@dataclass(frozen=True)
class RunToken:
    brief_id: str
    brief_hash: str


def run_token(brief: ResearchBrief) -> RunToken:
    """Mint authorization only after approval and unattended spend consent."""
    if brief.state is not BriefState.APPROVED:
        raise ValueError("brief must be approved before a run token can be minted")
    if brief.unattended and brief.price_ceiling is None:
        raise ValueError("unattended brief requires a price ceiling")
    return RunToken(brief.brief_id, brief_content_hash(brief))

