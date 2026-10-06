"""Single-process admission and one-shot execution of trusted local callables."""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import StringConstraints

from .policy import ComputePolicy, Identifier, StrictModel, WorkloadPolicy

ENABLE_ENV = "ANTIEK_COMPUTE_LAYER_ENABLED"


class OutcomeCode(StrEnum):
    ADMITTED = "admitted"
    QUEUED = "queued"
    REFUSED_POLICY = "refused_policy"
    LEASE_HELD = "lease_held"
    ROUTE_BLOCKED = "route_blocked"
    BUDGET_BLOCKED = "budget_blocked"


class JobState(StrEnum):
    QUEUED = "queued"
    ADMITTED = "admitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUSED = "refused"
    CREDENTIAL_BLOCKED = "credential_blocked"
    BILLING_BLOCKED = "billing_blocked"


class CredentialFailure(RuntimeError):
    """The selected route cannot authenticate. Do not retry or fall back."""


class BillingFailure(RuntimeError):
    """The selected route cannot bill. Do not retry or fall back."""


class JobRequest(StrictModel):
    tenant_id: Identifier
    project_id: Identifier
    idempotency_key: Identifier
    lane_key: Identifier
    workload_class: Identifier
    inputs_digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class JobEnvelope(JobRequest):
    job_id: str


@dataclass(frozen=True)
class Decision:
    job: JobEnvelope
    code: OutcomeCode
    state: JobState
    reason: str
    policy_version: str
    route_alias: str | None
    attempts: int
    retryable: bool = field(default=False, init=False)


@dataclass(frozen=True)
class LeaseSnapshot:
    job_id: str
    tenant_id: str
    project_id: str
    lane_key: str
    holder_node: str
    holder_pid: int
    scheduler_instance_id: str
    holder_thread_id: int | None
    acquired_at: datetime
    heartbeat_at: datetime
    stale: bool
    holder_alive: bool


@dataclass(frozen=True)
class ExecutionReport:
    decision: Decision
    value: object = None


@dataclass(frozen=True)
class JobContext:
    job: JobEnvelope
    heartbeat: Callable[[], bool]


class InProcessBackend:
    def execute(self, task: Callable[[JobContext], object], context: JobContext) -> object:
        return task(context)


@dataclass
class _Lease:
    job_id: str
    acquired_at: datetime
    heartbeat_at: datetime
    heartbeat_tick: float
    thread: threading.Thread | None = None


@dataclass
class _Job:
    decision: Decision
    workload: WorkloadPolicy | None
    value: object = None


class AdmissionScheduler:
    def __init__(
        self,
        policy: ComputePolicy,
        *,
        enabled: bool | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy.model_copy(deep=True)
        self._enabled = (
            enabled
            if enabled is not None
            else os.environ.get(ENABLE_ENV, "0").lower() in {"1", "true", "yes"}
        )
        self._clock = clock
        self._lock = threading.RLock()
        self._instance_id = str(uuid4())
        self._node = socket.gethostname()
        self._pid = os.getpid()
        self._backend = InProcessBackend()
        self._jobs: dict[str, _Job] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._leases: dict[tuple[str, str, str], _Lease] = {}
        self._route_blocks: dict[tuple[str, str], JobState] = {}
        self._used_slots: dict[str, int] = {}
        self._reserved_acu: dict[str, int] = {}
        self._spent_acu: dict[str, int] = {}

    def submit(self, request: JobRequest) -> Decision:
        self._check_process()
        with self._lock:
            key = (request.tenant_id, request.project_id, request.idempotency_key)
            previous_id = self._idempotency.get(key)
            if previous_id is not None:
                previous = self._jobs[previous_id].decision
                if previous.job.model_dump(exclude={"job_id"}) == request.model_dump():
                    return previous
                return Decision(
                    previous.job,
                    OutcomeCode.REFUSED_POLICY,
                    JobState.REFUSED,
                    "idempotency_conflict",
                    previous.policy_version,
                    previous.route_alias,
                    previous.attempts,
                )
            envelope = JobEnvelope(**request.model_dump(), job_id=str(uuid4()))
            workload = self._policy.classes.get(request.workload_class)
            decision = Decision(
                envelope,
                OutcomeCode.QUEUED,
                JobState.QUEUED,
                "pool_full",
                self._policy.policy_version,
                workload.backend if workload else None,
                0,
            )
            self._jobs[envelope.job_id] = _Job(decision, workload)
            self._idempotency[key] = envelope.job_id
            reason = self._policy_refusal(request, workload)
            if reason:
                return self._set(
                    envelope.job_id, OutcomeCode.REFUSED_POLICY, JobState.REFUSED, reason
                )
            lane = self._lane(envelope)
            if lane in self._leases:
                return self._set(
                    envelope.job_id, OutcomeCode.LEASE_HELD, JobState.REFUSED, "lane_owned"
                )
            now = datetime.now(UTC)
            self._leases[lane] = _Lease(envelope.job_id, now, now, self._clock())
            return self._consider(envelope.job_id)

    def advance(self, job_id: str) -> Decision:
        """Controller admission of an existing queued job, never a new attempt."""
        self._check_process()
        with self._lock:
            if self._jobs[job_id].decision.state != JobState.QUEUED:
                return self._jobs[job_id].decision
            return self._consider(job_id)

    def status(self, job_id: str) -> Decision:
        self._check_process()
        with self._lock:
            return self._jobs[job_id].decision

    def heartbeat(self, job_id: str) -> bool:
        self._check_process()
        with self._lock:
            lease = self._leases.get(self._lane(self._jobs[job_id].decision.job))
            if lease is None or lease.job_id != job_id:
                return False
            lease.heartbeat_at = datetime.now(UTC)
            lease.heartbeat_tick = self._clock()
            return True

    def inspect_lease(self, tenant_id: str, project_id: str, lane_key: str) -> LeaseSnapshot | None:
        self._check_process()
        with self._lock:
            lease = self._leases.get((tenant_id, project_id, lane_key))
            if lease is None:
                return None
            return LeaseSnapshot(
                lease.job_id,
                tenant_id,
                project_id,
                lane_key,
                self._node,
                self._pid,
                self._instance_id,
                lease.thread.ident if lease.thread else None,
                lease.acquired_at,
                lease.heartbeat_at,
                self._clock() - lease.heartbeat_tick >= self._policy.leases.stale_after_s,
                lease.thread.is_alive() if lease.thread else True,
            )

    def cancel(self, job_id: str) -> bool:
        self._check_process()
        with self._lock:
            decision = self._jobs[job_id].decision
            if decision.state not in {JobState.QUEUED, JobState.ADMITTED}:
                return False
            self._release(job_id)
            self._set(job_id, decision.code, JobState.CANCELLED, "cancelled_before_start")
            return True

    def run(self, job_id: str, task: Callable[[JobContext], object]) -> ExecutionReport:
        self._check_process()
        with self._lock:
            job = self._jobs[job_id]
            decision = job.decision
            if decision.state != JobState.ADMITTED:
                return ExecutionReport(decision, job.value)
            assert job.workload is not None
            route = job.workload.backend
            # A route may fail after another job was admitted but before it starts.
            blocked = self._route_blocks.get((decision.job.tenant_id, route))
            if blocked is not None:
                self._release(job_id)
                return ExecutionReport(
                    self._set(job_id, OutcomeCode.ROUTE_BLOCKED, JobState.REFUSED, blocked.value)
                )
            tenant = decision.job.tenant_id
            self._reserved_acu[tenant] -= job.workload.acu_units
            self._spent_acu[tenant] = self._spent_acu.get(tenant, 0) + job.workload.acu_units
            self._set(job_id, OutcomeCode.ADMITTED, JobState.RUNNING, "started", attempts=1)
            lease = self._leases[self._lane(decision.job)]
            lease.thread = threading.current_thread()
            self.heartbeat(job_id)
        context = JobContext(decision.job, lambda: self.heartbeat(job_id))
        try:
            value = self._backend.execute(task, context)
        except BaseException as exc:
            with self._lock:
                state = JobState.FAILED
                if isinstance(exc, CredentialFailure):
                    state = JobState.CREDENTIAL_BLOCKED
                elif isinstance(exc, BillingFailure):
                    state = JobState.BILLING_BLOCKED
                if state in {JobState.CREDENTIAL_BLOCKED, JobState.BILLING_BLOCKED}:
                    self._route_blocks[(tenant, route)] = state
                self._release(job_id)
                code = (
                    OutcomeCode.ADMITTED if state == JobState.FAILED else OutcomeCode.ROUTE_BLOCKED
                )
                result = self._set(job_id, code, state, state.value)
            if not isinstance(exc, Exception):
                raise
            return ExecutionReport(result)
        with self._lock:
            job.value = value
            self._release(job_id)
            return ExecutionReport(
                self._set(job_id, OutcomeCode.ADMITTED, JobState.SUCCEEDED, "completed"), value
            )

    def _policy_refusal(self, request: JobRequest, workload: WorkloadPolicy | None) -> str | None:
        if not self._enabled:
            return "compute_layer_disabled"
        if workload is None or not workload.enabled:
            return "workload_disabled_or_unknown"
        tenant = self._policy.tenants.get(request.tenant_id)
        if tenant is None or request.project_id not in tenant.projects:
            return "tenant_or_project_unallocated"
        return None

    def _check_process(self) -> None:
        # A fork copies locks and lease state; it cannot become a second controller.
        if os.getpid() != self._pid:
            raise RuntimeError("compute scheduler cannot be used from a different process")

    @staticmethod
    def _lane(job: JobEnvelope) -> tuple[str, str, str]:
        return job.tenant_id, job.project_id, job.lane_key

    def _consider(self, job_id: str) -> Decision:
        job = self._jobs[job_id]
        decision, workload = job.decision, job.workload
        assert workload is not None
        tenant = decision.job.tenant_id
        blocked = self._route_blocks.get((tenant, workload.backend))
        if blocked is not None:
            self._release(job_id)
            return self._set(job_id, OutcomeCode.ROUTE_BLOCKED, JobState.REFUSED, blocked.value)
        budget = self._policy.tenants[tenant].session_budget_acu
        committed = self._reserved_acu.get(tenant, 0) + self._spent_acu.get(tenant, 0)
        if committed + workload.acu_units > budget:
            self._release(job_id)
            return self._set(
                job_id, OutcomeCode.BUDGET_BLOCKED, JobState.REFUSED, "session_acu_exhausted"
            )
        used = self._used_slots.get(workload.pool, 0)
        if used + workload.slot_cost > self._policy.pools[workload.pool].slots:
            return decision
        self._used_slots[workload.pool] = used + workload.slot_cost
        self._reserved_acu[tenant] = self._reserved_acu.get(tenant, 0) + workload.acu_units
        self.heartbeat(job_id)
        return self._set(
            job_id, OutcomeCode.ADMITTED, JobState.ADMITTED, "local_capacity_available"
        )

    def _release(self, job_id: str) -> None:
        job = self._jobs[job_id]
        decision, workload = job.decision, job.workload
        lane = self._lane(decision.job)
        lease = self._leases.get(lane)
        if lease is not None and lease.job_id == job_id:
            del self._leases[lane]
        if workload is not None and decision.state in {JobState.ADMITTED, JobState.RUNNING}:
            self._used_slots[workload.pool] -= workload.slot_cost
            if decision.state == JobState.ADMITTED:
                self._reserved_acu[decision.job.tenant_id] -= workload.acu_units

    def _set(
        self,
        job_id: str,
        code: OutcomeCode,
        state: JobState,
        reason: str,
        *,
        attempts: int | None = None,
    ) -> Decision:
        old = self._jobs[job_id].decision
        new = Decision(
            old.job,
            code,
            state,
            reason,
            old.policy_version,
            old.route_alias,
            old.attempts if attempts is None else attempts,
        )
        self._jobs[job_id].decision = new
        return new
