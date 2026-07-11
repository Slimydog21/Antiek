"""Deterministic kill/reopen harness over an injected event-log port."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from .checkpoints import (
    Checkpoint,
    FloorObservation,
    validate_ref,
    validate_sequence,
    validate_sha256,
)
from .policy import FailureKind, FailurePolicy
from .trace import (
    GENESIS_HASH,
    ConcurrentAppendError,
    EventKind,
    EventLogPort,
    RunView,
    TraceEvent,
    append_cas,
    reconstruct,
)

Clock = Callable[[], datetime]


class InMemoryEventLogPort:
    """Reference adapter only; production persistence remains event_log-owned."""

    def __init__(self) -> None:
        self._events: dict[str, list[TraceEvent]] = {}

    def read(self, run_id: str) -> Sequence[TraceEvent]:
        return tuple(self._events.get(run_id, ()))

    def append(self, event: TraceEvent, *, expected_sequence: int) -> None:
        try:
            validate_sequence(expected_sequence, field="expected_sequence")
        except (TypeError, ValueError) as exc:
            raise ConcurrentAppendError("invalid expected sequence") from exc
        rows = self._events.setdefault(event.run_id, [])
        if len(rows) != expected_sequence or event.sequence != expected_sequence:
            raise ConcurrentAppendError("compare-and-swap rejected concurrent writer")
        rows.append(event)


class FakeDurableRunner:
    def __init__(
        self,
        port: EventLogPort,
        *,
        run_id: str,
        approved_brief_hash: str,
        clock: Clock,
        failure_policy: FailurePolicy | None = None,
    ) -> None:
        self.port = port
        self.run_id = validate_ref(run_id, field="run_id")
        self.approved_brief_hash = validate_sha256(approved_brief_hash, field="approved_brief_hash")
        self.clock = clock
        self.failure_policy = failure_policy or FailurePolicy(clock=clock)
        # This read/replay is intentional: a new instance owns no continuation state.
        view = reconstruct(tuple(port.read(run_id)))
        if view is not None and view.approved_brief_hash != approved_brief_hash:
            raise ValueError("existing run belongs to a different approved brief")

    @property
    def view(self) -> RunView | None:
        return reconstruct(tuple(self.port.read(self.run_id)))

    def prepare(self, kind: EventKind, data: Mapping[str, object]) -> TraceEvent:
        view = self.view
        return TraceEvent.create(
            run_id=self.run_id,
            approved_brief_hash=self.approved_brief_hash,
            sequence=0 if view is None else view.next_sequence,
            kind=kind,
            occurred_at=self.clock(),
            data=data,
            previous_hash=GENESIS_HASH if view is None else view.last_hash,
        )

    def append_prepared(self, event: TraceEvent) -> RunView:
        return append_cas(self.port, event)

    def _emit(self, kind: EventKind, data: Mapping[str, object]) -> RunView:
        return self.append_prepared(self.prepare(kind, data))

    def start(self) -> RunView:
        return self._emit(EventKind.RUN_STARTED, {})

    def step(self, step_ref: str) -> RunView:
        return self._emit(EventKind.STEP_RECORDED, {"step_ref": validate_ref(step_ref)})

    def source_fetched(self, source_ref: str) -> RunView:
        return self._emit(EventKind.SOURCE_FETCHED, {"source_ref": validate_ref(source_ref)})

    def checkpoint(self, checkpoint: Checkpoint) -> RunView:
        return self._emit(EventKind.CHECKPOINT_RECORDED, checkpoint.canonical())

    def trip_floor(self, observation: FloorObservation) -> RunView:
        if observation.passed:
            raise ValueError("only failed floor observations may trip a floor")
        data = observation.canonical()
        del data["passed"]
        return self._emit(EventKind.FLOOR_TRIPPED, data)

    def fail(self, failure: FailureKind | str, *, attempt: int) -> RunView:
        outcome = self.failure_policy.decide(failure, attempt=attempt)
        failure_value = failure.value if isinstance(failure, FailureKind) else failure
        if not isinstance(failure_value, str):
            failure_value = "unknown_failure"
        return self._emit(
            EventKind.FAILURE_RECORDED,
            {
                "failure": validate_ref(failure_value, field="failure"),
                "attempt": outcome.attempt,
                "attempt_limit": self.failure_policy.max_transient_attempts,
                "decision": outcome.decision.value,
                "decided_at": outcome.decided_at,
                "retry_at": outcome.retry_at,
            },
        )

    def resume(self) -> RunView:
        view = self.view
        if view is None or view.unresolved_resumable_sequence is None:
            raise ValueError("resume requires an unresolved retryable failure or floor trip")
        return self._emit(
            EventKind.RUN_RESUMED, {"from_sequence": view.unresolved_resumable_sequence}
        )

    def complete(self) -> RunView:
        """Complete with an identity derived only from reconstructed durable state."""
        view = self.view
        if view is None:
            raise ValueError("run has not started")
        material = {
            "approved_brief_hash": view.approved_brief_hash,
            "checkpoints": {kind: dict(refs) for kind, refs in view.checkpoint_refs.items()},
            "sources": view.sources,
            "steps": view.steps,
        }
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return self._emit(EventKind.RUN_COMPLETED, {"report_ref": f"report:sha256:{digest}"})
