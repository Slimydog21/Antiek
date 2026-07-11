"""Refs-only, restartable execution seam for durable research work.

This module intentionally does not adapt ``BrowseLoop``.  A caller must provide
an idempotent effect executor whose receipts remain queryable after a process
dies.  That is the minimum contract which can reconcile the dangerous window
between an external effect and its durability checkpoint.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Protocol

from substrate.run_durability import (
    Checkpoint,
    CheckpointKind,
    ConcurrentAppendError,
    EventKind,
    EventLogPort,
    FailureKind,
    FailurePolicy,
    FakeDurableRunner,
)
from substrate.run_durability.checkpoints import validate_ref, validate_sha256


@dataclass(frozen=True, slots=True)
class AuthorizedRun:
    run_id: str
    approved_brief_hash: str
    brief_ref: str
    plan_ref: str
    work_plan_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", validate_ref(self.run_id, field="run_id"))
        object.__setattr__(
            self,
            "approved_brief_hash",
            validate_sha256(self.approved_brief_hash, field="approved_brief_hash"),
        )
        object.__setattr__(self, "brief_ref", validate_ref(self.brief_ref, field="brief_ref"))
        object.__setattr__(self, "plan_ref", validate_ref(self.plan_ref, field="plan_ref"))
        object.__setattr__(
            self, "work_plan_hash", validate_sha256(self.work_plan_hash, field="work_plan_hash")
        )


@dataclass(frozen=True, slots=True)
class WorkUnit:
    boundary: CheckpointKind
    input_refs: Mapping[str, str]

    def __post_init__(self) -> None:
        checkpoint = Checkpoint(self.boundary, self.input_refs)
        object.__setattr__(self, "input_refs", checkpoint.refs)


@dataclass(frozen=True, slots=True)
class EffectReceipt:
    idempotency_key: str
    outcome_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "idempotency_key", validate_sha256(self.idempotency_key, field="idempotency_key")
        )
        object.__setattr__(self, "outcome_ref", validate_ref(self.outcome_ref, field="outcome_ref"))


class IdempotentEffectExecutor(Protocol):
    def lookup(self, idempotency_key: str) -> EffectReceipt | None: ...
    def execute(self, unit: WorkUnit, *, idempotency_key: str) -> EffectReceipt: ...


Clock = Callable[[], datetime]


def effect_key(authorization: AuthorizedRun, unit: WorkUnit) -> str:
    material = {
        "approved_brief_hash": authorization.approved_brief_hash,
        "brief_ref": authorization.brief_ref,
        "boundary": unit.boundary.value,
        "input_refs": dict(unit.input_refs),
        "run_id": authorization.run_id,
        "plan_ref": authorization.plan_ref,
        "work_plan_hash": authorization.work_plan_hash,
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class DurableWorkSupervisor:
    """Drive ordered work through queryable effect receipts and CAS checkpoints."""

    def __init__(
        self,
        port: EventLogPort,
        executor: IdempotentEffectExecutor,
        authorization: AuthorizedRun,
        *,
        clock: Clock,
        max_transient_attempts: int = 3,
    ) -> None:
        self._executor = executor
        self._authorization = authorization
        self._runner = FakeDurableRunner(
            port,
            run_id=authorization.run_id,
            approved_brief_hash=authorization.approved_brief_hash,
            clock=clock,
            failure_policy=FailurePolicy(
                clock=clock, max_transient_attempts=max_transient_attempts
            ),
        )

    @property
    def runner(self) -> FakeDurableRunner:
        return self._runner

    def _retry_cas(self, operation: Callable[[], object]) -> None:
        with suppress(ConcurrentAppendError):
            operation()

    def _append_step(self, step_ref: str) -> None:
        self._runner.step(step_ref)

    def _append_checkpoint(self, boundary: CheckpointKind, ref_name: str, outcome_ref: str) -> None:
        self._runner.checkpoint(Checkpoint(boundary, {ref_name: outcome_ref}))

    def recover_interrupted(self) -> None:
        """Persist an explicit process-loss edge before continuing a known crash."""
        view = self._runner.view
        if view is None or view.completed or view.terminal_failure:
            return
        if view.unresolved_resumable_sequence is None:
            attempt = sum(
                event.kind is EventKind.FAILURE_RECORDED
                and event.data["failure"] == FailureKind.PROCESS_KILLED.value
                for event in self._runner.port.read(self._authorization.run_id)
            )
            self._retry_cas(lambda: self._runner.fail(FailureKind.PROCESS_KILLED, attempt=attempt))
        view = self._runner.view
        if view is not None and view.unresolved_resumable_sequence is not None:
            events = tuple(self._runner.port.read(self._authorization.run_id))
            cause = events[view.unresolved_resumable_sequence]
            if not (
                cause.kind is EventKind.FAILURE_RECORDED
                and cause.data["failure"] == FailureKind.PROCESS_KILLED.value
            ):
                raise RuntimeError("crash recovery may resume only its own process_killed edge")
            self._retry_cas(self._runner.resume)

    @staticmethod
    def work_plan_hash(units: Sequence[WorkUnit]) -> str:
        material = [
            {"boundary": unit.boundary.value, "input_refs": dict(unit.input_refs)} for unit in units
        ]
        return hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def execute(self, units: Sequence[WorkUnit]) -> str:
        boundaries = [unit.boundary for unit in units]
        if len(set(boundaries)) != len(boundaries):
            raise ValueError("work boundaries must be unique")
        if boundaries != sorted(boundaries, key=list(CheckpointKind).index):
            raise ValueError("work boundaries must follow canonical checkpoint order")
        if not units or units[-1].boundary is not CheckpointKind.REPORT_READY:
            raise ValueError("completion requires an explicit REPORT_READY effect unit")
        if any(
            boundary in {CheckpointKind.BRIEF_APPROVED, CheckpointKind.PLAN_READY}
            for boundary in boundaries
        ):
            raise ValueError("brief and plan boundaries are reserved for authorization fencing")
        if self.work_plan_hash(units) != self._authorization.work_plan_hash:
            raise ValueError("work units do not match the authorized work plan hash")
        view = self._runner.view
        if view is None:
            self._retry_cas(self._runner.start)
        view = self._runner.view
        if view is None or view.terminal_failure:
            raise RuntimeError("durable run could not start or is terminal")
        if view.unresolved_resumable_sequence is not None:
            raise RuntimeError("recover_interrupted must resolve the durable failure first")
        brief_refs = {"brief_ref": self._authorization.brief_ref}
        durable_brief = view.checkpoint_refs.get(CheckpointKind.BRIEF_APPROVED.value)
        if durable_brief is None:
            self._retry_cas(
                lambda: self._runner.checkpoint(
                    Checkpoint(CheckpointKind.BRIEF_APPROVED, brief_refs)
                )
            )
            view = self._runner.view
            assert view is not None
            durable_brief = view.checkpoint_refs.get(CheckpointKind.BRIEF_APPROVED.value)
        if durable_brief != brief_refs:
            raise ConcurrentAppendError("run is fenced to a different approved brief reference")
        plan_refs = {
            "plan_ref": self._authorization.plan_ref,
            "work_plan_ref": f"sha256:{self._authorization.work_plan_hash}",
        }
        durable_plan = view.checkpoint_refs.get(CheckpointKind.PLAN_READY.value)
        if durable_plan is None:
            self._retry_cas(
                lambda: self._runner.checkpoint(Checkpoint(CheckpointKind.PLAN_READY, plan_refs))
            )
            view = self._runner.view
            assert view is not None
            durable_plan = view.checkpoint_refs.get(CheckpointKind.PLAN_READY.value)
        if durable_plan != plan_refs:
            raise ConcurrentAppendError("run is fenced to a different durable work plan")
        was_completed = view.completed

        if was_completed:
            verified_outcomes: list[str] = []
            for unit in units:
                key = effect_key(self._authorization, unit)
                step_ref = f"effect:sha256:{key}"
                if step_ref not in view.steps:
                    raise RuntimeError("completed run is missing an expected effect step")
                ref_name = (
                    "report_ref" if unit.boundary is CheckpointKind.REPORT_READY else "outcome_ref"
                )
                persisted = view.checkpoint_refs.get(unit.boundary.value)
                if persisted is None or set(persisted) != {ref_name}:
                    raise RuntimeError("completed run is missing an exact work checkpoint")
                receipt = self._executor.lookup(key)
                if receipt is None or receipt.idempotency_key != key:
                    raise RuntimeError("completed run is missing its durable effect receipt")
                if persisted[ref_name] != receipt.outcome_ref:
                    raise RuntimeError("completed checkpoint and effect receipt disagree")
                verified_outcomes.append(receipt.outcome_ref)
            expected = verified_outcomes[-1]
            if view.report_ref != expected:
                raise RuntimeError("completed report disagrees with the durable report receipt")
            return expected

        outcomes: list[str] = []
        for unit in units:
            key = effect_key(self._authorization, unit)
            existing = self._runner.view
            assert existing is not None
            persisted = existing.checkpoint_refs.get(unit.boundary.value)
            if persisted is not None:
                ref_name = (
                    "report_ref" if unit.boundary is CheckpointKind.REPORT_READY else "outcome_ref"
                )
                outcome = persisted.get(ref_name)
                if outcome is None:
                    raise RuntimeError("durable checkpoint lacks its outcome reference")
                receipt = self._executor.lookup(key)
                expected_step = f"effect:sha256:{key}"
                if expected_step not in existing.steps:
                    raise RuntimeError("durable checkpoint lacks its exact effect step")
                if (
                    receipt is None
                    or receipt.idempotency_key != key
                    or receipt.outcome_ref != outcome
                ):
                    raise RuntimeError("durable checkpoint and effect receipt disagree")
                outcomes.append(outcome)
                continue

            receipt = self._executor.lookup(key)
            if receipt is None:
                proposed = self._executor.execute(unit, idempotency_key=key)
                receipt = self._executor.lookup(key)
                if receipt is None or receipt != proposed:
                    raise RuntimeError("executor did not durably publish its exact receipt")
            if receipt.idempotency_key != key:
                raise RuntimeError("executor returned a receipt for a different effect")
            step_ref = f"effect:sha256:{key}"
            latest = self._runner.view
            assert latest is not None
            if step_ref not in latest.steps:
                self._retry_cas(partial(self._append_step, step_ref))
            latest = self._runner.view
            if latest is None or step_ref not in latest.steps:
                raise ConcurrentAppendError("effect step fence did not commit exactly")
            latest = self._runner.view
            assert latest is not None
            if unit.boundary.value not in latest.checkpoint_refs:
                ref_name = (
                    "report_ref" if unit.boundary is CheckpointKind.REPORT_READY else "outcome_ref"
                )
                self._retry_cas(
                    partial(
                        self._append_checkpoint,
                        unit.boundary,
                        ref_name,
                        receipt.outcome_ref,
                    )
                )
            committed = self._runner.view
            assert committed is not None
            refs = committed.checkpoint_refs.get(unit.boundary.value)
            ref_name = (
                "report_ref" if unit.boundary is CheckpointKind.REPORT_READY else "outcome_ref"
            )
            if refs is None or refs.get(ref_name) != receipt.outcome_ref:
                raise ConcurrentAppendError("competing checkpoint committed a different receipt")
            outcomes.append(receipt.outcome_ref)

        expected = outcomes[-1]
        self._retry_cas(
            lambda: self._runner.append_prepared(
                self._runner.prepare(EventKind.RUN_COMPLETED, {"report_ref": expected})
            )
        )
        final = self._runner.view
        if final is None or not final.completed or final.report_ref != expected:
            raise ConcurrentAppendError("completion did not commit the stable report reference")
        return expected


__all__ = [
    "AuthorizedRun",
    "DurableWorkSupervisor",
    "EffectReceipt",
    "IdempotentEffectExecutor",
    "WorkUnit",
    "effect_key",
]
