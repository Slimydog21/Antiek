from __future__ import annotations

import pytest

from substrate.agent_work.domain import (
    FinishWork,
    InvalidTransition,
    LeaseWork,
    MarkAcknowledged,
    MarkSubmitted,
    MarkWorking,
    ResultKind,
    WorkState,
    decide_transition,
)


def test_queued_work_can_be_leased() -> None:
    transition = decide_transition(WorkState.QUEUED, LeaseWork())

    assert transition.before is WorkState.QUEUED
    assert transition.after is WorkState.LEASED
    assert transition.reason == "leased"


def test_live_lease_can_be_marked_submitted() -> None:
    transition = decide_transition(WorkState.LEASED, MarkSubmitted())

    assert transition.after is WorkState.SUBMITTED
    assert transition.reason == "submitted"


def test_queued_work_cannot_skip_directly_to_submitted() -> None:
    with pytest.raises(InvalidTransition, match="queued.*MarkSubmitted"):
        decide_transition(WorkState.QUEUED, MarkSubmitted())


@pytest.mark.parametrize(
    ("before", "command", "after"),
    [
        (WorkState.SUBMITTED, MarkAcknowledged(), WorkState.ACKNOWLEDGED),
        (WorkState.SUBMITTED, MarkWorking(), WorkState.WORKING),
        (WorkState.ACKNOWLEDGED, MarkWorking(), WorkState.WORKING),
        (WorkState.LEASED, FinishWork(ResultKind.REPLY), WorkState.REPLIED),
        (WorkState.SUBMITTED, FinishWork(ResultKind.REPLY), WorkState.REPLIED),
        (WorkState.WORKING, FinishWork(ResultKind.DECLINE), WorkState.DECLINED),
        (
            WorkState.WORKING,
            FinishWork(ResultKind.APPROVAL_REQUEST),
            WorkState.APPROVAL_REQUESTED,
        ),
    ],
)
def test_delivery_and_result_transitions_are_explicit(before, command, after) -> None:
    assert decide_transition(before, command).after is after


def test_acknowledgement_cannot_be_claimed_before_submission() -> None:
    with pytest.raises(InvalidTransition):
        decide_transition(WorkState.LEASED, MarkAcknowledged())


def test_retryable_failure_requeues_until_attempt_budget_is_exhausted() -> None:
    retry = decide_transition(
        WorkState.WORKING,
        FinishWork(ResultKind.FAILURE, retryable=True, attempt_no=2, max_attempts=3),
    )
    exhausted = decide_transition(
        WorkState.WORKING,
        FinishWork(ResultKind.FAILURE, retryable=True, attempt_no=3, max_attempts=3),
    )

    assert retry.after is WorkState.QUEUED
    assert retry.reason == "retryable_failure"
    assert exhausted.after is WorkState.FAILED
    assert exhausted.reason == "attempts_exhausted"
