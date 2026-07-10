"""Immutable model for the cheap, operator-editable pre-run artifact."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class BriefState(StrEnum):
    DRAFT = "draft"
    AMENDED = "amended"
    APPROVED = "approved"


@dataclass(frozen=True)
class BudgetTuple:
    """Local W1 placeholder until SPR-01's TierBudget is available."""

    tier: str
    duration_minutes: int
    fanout_depth: int

    def __post_init__(self) -> None:
        if not self.tier.strip() or self.duration_minutes <= 0 or self.fanout_depth <= 0:
            raise ValueError("budget fields must be non-empty and positive")


@dataclass(frozen=True)
class LifecycleEvent:
    action: str
    actor: str
    occurred_at: str
    content_hash: str | None = None


@dataclass(frozen=True)
class ResearchBrief:
    brief_id: str
    question: str
    scope: str
    exclusions: tuple[str, ...] = ()
    source_preferences: tuple[str, ...] = ()
    budget: BudgetTuple | tuple[str, int, int] = ("deep", 60, 3)
    price_ceiling: Decimal | None = None
    unattended: bool = False
    state: BriefState = BriefState.DRAFT
    events: tuple[LifecycleEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.brief_id.strip():
            raise ValueError("brief_id is required")
        if not self.question.strip():
            raise ValueError("question is required")
        if not self.scope.strip():
            raise ValueError("scope is required")
        if isinstance(self.budget, tuple):
            object.__setattr__(self, "budget", BudgetTuple(*self.budget))
        if self.price_ceiling is not None and self.price_ceiling <= 0:
            raise ValueError("price_ceiling must be positive")
        if self.state is BriefState.DRAFT:
            if self.events:
                raise ValueError("draft brief cannot have lifecycle events")
            return
        if not self.events or self.events[-1].action != self.state.value:
            raise ValueError("non-draft brief requires a consistent lifecycle event trail")
        if any(not event.actor.strip() or not event.occurred_at.strip() for event in self.events):
            raise ValueError("lifecycle events require actor and occurred_at")
