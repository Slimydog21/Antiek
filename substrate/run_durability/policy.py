"""Fail-closed, clock-injected failure classification and retry policy.

Exhaustive taxonomy and rationale:

* timeout, rate_limited, temporary_unavailable, and connection_failure are
  transient transport/service conditions; retrying from a checkpoint can
  succeed without changing the approved brief.
* process_killed is transient because reopening is the durability use case.
* invalid_input, authorization, policy_violation, integrity_failure, and
  floor_failure require changed input, authority, or evidence; repeating them
  would be dishonest, so they are terminal.
* every unknown future value is terminal. New failures never inherit retry.

The sprint contract specifies bounded attempts but no backoff or deadline.
Therefore a retry is eligible immediately at the injected UTC decision time;
this module invents neither wall sleeps nor an unsupported deadline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .checkpoints import validate_sequence
from .trace import canonical_timestamp


class FailureKind(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    TEMPORARY_UNAVAILABLE = "temporary_unavailable"
    CONNECTION_FAILURE = "connection_failure"
    PROCESS_KILLED = "process_killed"
    INVALID_INPUT = "invalid_input"
    AUTHORIZATION = "authorization"
    POLICY_VIOLATION = "policy_violation"
    INTEGRITY_FAILURE = "integrity_failure"
    FLOOR_FAILURE = "floor_failure"


class FailureDecision(StrEnum):
    RETRY = "retry"
    TERMINAL = "terminal"


_TRANSIENT = frozenset(
    {
        FailureKind.TIMEOUT,
        FailureKind.RATE_LIMITED,
        FailureKind.TEMPORARY_UNAVAILABLE,
        FailureKind.CONNECTION_FAILURE,
        FailureKind.PROCESS_KILLED,
    }
)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: FailureDecision
    attempt: int
    decided_at: str
    retry_at: str | None


@dataclass(frozen=True, slots=True)
class FailurePolicy:
    clock: Callable[[], datetime]
    max_transient_attempts: int = 3

    def __post_init__(self) -> None:
        if not callable(self.clock):
            raise TypeError("clock must be callable")
        validate_sequence(self.max_transient_attempts, field="max_transient_attempts")
        if not 1 <= self.max_transient_attempts <= 3:
            raise ValueError("max_transient_attempts must be between 1 and 3")

    def decide(self, failure: FailureKind | str, *, attempt: int) -> PolicyDecision:
        validate_sequence(attempt, field="attempt")
        now = canonical_timestamp(self.clock())
        try:
            known = failure if isinstance(failure, FailureKind) else FailureKind(failure)
        except TypeError, ValueError:
            known = None
        decision = (
            FailureDecision.RETRY
            if known in _TRANSIENT and attempt < self.max_transient_attempts
            else FailureDecision.TERMINAL
        )
        return PolicyDecision(
            decision, attempt, now, now if decision is FailureDecision.RETRY else None
        )
