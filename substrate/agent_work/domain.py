"""Pure state transitions for durable agent work.

This module owns lifecycle legality. Persistence and transport code consume
``Transition`` values rather than updating work state ad hoc.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    WORKING = "working"
    REPLIED = "replied"
    DECLINED = "declined"
    APPROVAL_REQUESTED = "approval_requested"
    FAILED = "failed"


class ResultKind(StrEnum):
    REPLY = "reply"
    DECLINE = "decline"
    APPROVAL_REQUEST = "approval_request"
    FAILURE = "failure"


class InvalidTransition(ValueError):
    """Raised when a command is not legal from the current state."""


@dataclass(frozen=True, slots=True)
class LeaseWork:
    """Request authority to deliver one queued work item."""


@dataclass(frozen=True, slots=True)
class MarkSubmitted:
    """Record that the adapter handed the work to its transport."""


@dataclass(frozen=True, slots=True)
class MarkAcknowledged:
    """Record a machine-verifiable transport acknowledgement."""


@dataclass(frozen=True, slots=True)
class MarkWorking:
    """Record that the correlated agent turn is in progress."""


@dataclass(frozen=True, slots=True)
class FinishWork:
    """Record a structured terminal result or a bounded retryable failure."""

    kind: ResultKind
    retryable: bool = False
    attempt_no: int = 1
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if self.attempt_no < 1:
            raise ValueError("attempt_no must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.attempt_no > self.max_attempts:
            raise ValueError("attempt_no cannot exceed max_attempts")
        if self.retryable and self.kind is not ResultKind.FAILURE:
            raise ValueError("only failures can be retryable")


@dataclass(frozen=True, slots=True)
class Transition:
    before: WorkState
    after: WorkState
    reason: str


WorkCommand = LeaseWork | MarkSubmitted | MarkAcknowledged | MarkWorking | FinishWork


def decide_transition(state: WorkState, command: WorkCommand) -> Transition:
    """Return the canonical transition for a valid work command."""
    if state is WorkState.QUEUED and isinstance(command, LeaseWork):
        return Transition(before=state, after=WorkState.LEASED, reason="leased")
    if state is WorkState.LEASED and isinstance(command, MarkSubmitted):
        return Transition(before=state, after=WorkState.SUBMITTED, reason="submitted")
    if state is WorkState.SUBMITTED and isinstance(command, MarkAcknowledged):
        return Transition(before=state, after=WorkState.ACKNOWLEDGED, reason="acknowledged")
    if state in {WorkState.SUBMITTED, WorkState.ACKNOWLEDGED} and isinstance(command, MarkWorking):
        return Transition(before=state, after=WorkState.WORKING, reason="working")
    if state in {
        WorkState.LEASED,
        WorkState.SUBMITTED,
        WorkState.ACKNOWLEDGED,
        WorkState.WORKING,
    } and isinstance(command, FinishWork):
        if command.kind is ResultKind.REPLY:
            return Transition(before=state, after=WorkState.REPLIED, reason="replied")
        if command.kind is ResultKind.DECLINE:
            return Transition(before=state, after=WorkState.DECLINED, reason="declined")
        if command.kind is ResultKind.APPROVAL_REQUEST:
            return Transition(
                before=state,
                after=WorkState.APPROVAL_REQUESTED,
                reason="approval_requested",
            )
        if command.retryable and command.attempt_no < command.max_attempts:
            return Transition(
                before=state,
                after=WorkState.QUEUED,
                reason="retryable_failure",
            )
        reason = "attempts_exhausted" if command.retryable else "failed"
        return Transition(before=state, after=WorkState.FAILED, reason=reason)
    raise InvalidTransition(
        f"invalid agent-work transition: {state.value} + {type(command).__name__}"
    )
