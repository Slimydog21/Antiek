"""Single-process admission and one-shot execution of trusted local callables."""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .backends import BillingFailure, CredentialFailure, adapter_registry
from .capacity import CapacitySnapshot, capacity_refusal, host_capacity
from .ledger import JsonlLedger, LedgerEvent, LedgerUnavailable
from .models import (
    TERMINAL_STATES,
    BackendKind,
    DataLocality,
    Decision,
    ExecutionReport,
    JobContext,
    JobEnvelope,
    JobOutput,
    JobRequest,
    JobState,
    OutcomeCode,
    ReasonCode,
)
from .policy import ComputePolicy, WorkloadPolicy

ENABLE_ENV = "ANTIEK_COMPUTE_LAYER_ENABLED"


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
    output: JobOutput | None = None


class AdmissionScheduler:
    def __init__(
        self,
        policy: ComputePolicy,
        *,
        enabled: bool | None = None,
        ledger_path: Path | None = None,
        capacity_probe: Callable[[Path], CapacitySnapshot | None] = host_capacity,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy.model_copy(deep=True)
        self._enabled = (
            enabled
            if enabled is not None
            else os.environ.get(ENABLE_ENV, "0").lower() in {"1", "true", "yes"}
        )
        self._ledger = JsonlLedger(ledger_path) if ledger_path is not None else None
        self._broken = False
        self._closed = False
        self._capacity_probe = capacity_probe
        self._clock = clock
        self._lock = threading.RLock()
        self._instance_id = str(uuid4())
        self._node = socket.gethostname()
        self._pid = os.getpid()
        self._backends = adapter_registry()
        self._jobs: dict[str, _Job] = {}
        self._idempotency: dict[tuple[str, str, str, str], str] = {}
        self._leases: dict[tuple[str, str, str], _Lease] = {}
        self._route_blocks: dict[tuple[str, str], ReasonCode] = {}
        self._used_slots: dict[str, int] = {}
        self._reserved_acu: dict[str, int] = {}
        self._spent_acu: dict[str, int] = {}

    def submit(self, request: JobRequest) -> Decision:
        self._check_process()
        with self._lock:
            self._check_ledger()
            key = (
                request.owner_user_id,
                request.tenant_id,
                request.project_id,
                request.idempotency_key,
            )
            previous_id = self._idempotency.get(key)
            conflict = previous_id is not None
            if previous_id is not None:
                previous = self._jobs[previous_id].decision
                if previous.job.model_dump(exclude={"job_id"}) == request.model_dump():
                    return previous
            envelope = JobEnvelope(**request.model_dump(), job_id=str(uuid4()))
            workload = self._policy.classes.get(request.workload_class)
            decision = Decision(
                envelope,
                OutcomeCode.QUEUED,
                JobState.REQUESTED,
                ReasonCode.REQUESTED,
                self._policy.policy_version,
                workload.backend if workload else None,
                0,
            )
            self._jobs[envelope.job_id] = _Job(decision, workload)
            if not conflict:
                self._idempotency[key] = envelope.job_id
            if not self._enabled:
                return self._set(
                    envelope.job_id,
                    OutcomeCode.REFUSED_POLICY,
                    JobState.REFUSED,
                    ReasonCode.DISABLED,
                )
            if self._ledger is None:
                return self._set(
                    envelope.job_id,
                    OutcomeCode.REFUSED_POLICY,
                    JobState.REFUSED,
                    ReasonCode.LEDGER_UNBOUND,
                )
            self._emit(decision, None)
            reason = (
                ReasonCode.IDEMPOTENCY_CONFLICT
                if conflict
                else self._policy_refusal(request, workload)
            )
            if reason is not None:
                return self._set(
                    envelope.job_id, OutcomeCode.REFUSED_POLICY, JobState.REFUSED, reason
                )
            lane = self._lane(envelope)
            if lane in self._leases:
                return self._set(
                    envelope.job_id, OutcomeCode.LEASE_HELD, JobState.REFUSED, ReasonCode.LANE_OWNED
                )
            now = datetime.now(UTC)
            self._leases[lane] = _Lease(envelope.job_id, now, now, self._clock())
            return self._consider(envelope.job_id)

    def advance(self, job_id: str) -> Decision:
        """Reconsider an existing queued job without creating an execution attempt."""
        self._check_process()
        with self._lock:
            self._check_ledger()
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
            self._check_ledger()
            decision = self._jobs[job_id].decision
            if decision.state not in {JobState.QUEUED, JobState.ADMITTED}:
                return False
            self._set(job_id, decision.code, JobState.CANCELLED, ReasonCode.CANCELLED)
            return True

    def run(self, job_id: str, task: Callable[[JobContext], object]) -> ExecutionReport:
        self._check_process()
        with self._lock:
            self._check_ledger()
            job = self._jobs[job_id]
            decision = job.decision
            if decision.state != JobState.ADMITTED:
                return ExecutionReport(decision, job.output.value if job.output else None)
            assert job.workload is not None
            route = job.workload.backend
            blocked = self._route_refusal(job)
            if blocked is not None:
                return ExecutionReport(
                    self._set(job_id, OutcomeCode.ROUTE_BLOCKED, JobState.REFUSED, blocked)
                )
            headroom = self._headroom()
            if headroom is not None:
                return ExecutionReport(
                    self._set(job_id, OutcomeCode.QUEUED, JobState.QUEUED, headroom)
                )
            self._set(
                job_id, OutcomeCode.ADMITTED, JobState.RUNNING, ReasonCode.STARTED, attempts=1
            )
            lease = self._leases[self._lane(decision.job)]
            lease.thread = threading.current_thread()
            self.heartbeat(job_id)
        context = JobContext(decision.job, lambda: self.heartbeat(job_id))
        backend = self._backends[self._policy.backends[route].kind]
        try:
            value = backend.execute(task, context)
            output = value if isinstance(value, JobOutput) else JobOutput(value=value)
        except BaseException as exc:
            with self._lock:
                state, reason, code = JobState.FAILED, ReasonCode.FAILED, OutcomeCode.ADMITTED
                if isinstance(exc, CredentialFailure):
                    state, reason = JobState.CREDENTIAL_BLOCKED, ReasonCode.CREDENTIAL_BLOCKED
                elif isinstance(exc, BillingFailure):
                    state, reason = JobState.BILLING_BLOCKED, ReasonCode.BILLING_BLOCKED
                if state != JobState.FAILED:
                    self._route_blocks[(decision.job.tenant_id, route)] = reason
                    code = OutcomeCode.ROUTE_BLOCKED
                result = self._set(job_id, code, state, reason)
            if not isinstance(exc, Exception):
                raise
            return ExecutionReport(result)
        with self._lock:
            job.output = output
            return ExecutionReport(
                self._set(job_id, OutcomeCode.ADMITTED, JobState.SUCCEEDED, ReasonCode.COMPLETED),
                output.value,
            )

    def close(self) -> None:
        self._check_process(allow_closed=True)
        with self._lock:
            if self._closed:
                return
            if any(job.decision.state == JobState.RUNNING for job in self._jobs.values()):
                raise RuntimeError("cannot close a scheduler with a running task")
            try:
                for job_id, job in self._jobs.items():
                    if job.decision.state in {JobState.ADMITTED, JobState.QUEUED}:
                        if self._broken:
                            self._release(job_id)
                        else:
                            self._set(
                                job_id, job.decision.code, JobState.CANCELLED, ReasonCode.CANCELLED
                            )
            finally:
                self._closed = True
                if self._ledger is not None:
                    self._ledger.close()

    def _policy_refusal(
        self, request: JobRequest, workload: WorkloadPolicy | None
    ) -> ReasonCode | None:
        if workload is None or not workload.enabled:
            return ReasonCode.WORKLOAD_DISABLED
        tenant = self._policy.tenants.get(request.tenant_id)
        if tenant is None or request.project_id not in tenant.projects:
            return ReasonCode.UNALLOCATED
        if request.owner_user_id not in tenant.owner_user_ids:
            return ReasonCode.OWNER_UNALLOCATED
        backend = self._policy.backends[workload.backend]
        if tenant.data_locality == DataLocality.ANTIEK_USER and backend.region != "eu":
            return ReasonCode.RESIDENCY
        if tenant.data_locality == DataLocality.MINI_ONLY and backend.kind not in {
            BackendKind.IN_PROCESS,
            BackendKind.MINI_NODE,
        }:
            return ReasonCode.MINI_REQUIRED
        if tenant.data_locality == DataLocality.CLOUD_OK_NO_RETENTION:
            return ReasonCode.RETENTION_UNPROVEN
        gates = self._policy.gates
        if (
            gates.disk_path is None
            or gates.min_free_memory_percent is None
            or gates.min_free_disk_bytes is None
        ):
            return ReasonCode.GATES_UNBOUND
        return None

    def _check_process(self, *, allow_closed: bool = False) -> None:
        # Forked copies must not become additional lease controllers.
        if os.getpid() != self._pid:
            raise RuntimeError("compute scheduler cannot be used from a different process")
        if self._closed and not allow_closed:
            raise RuntimeError("compute scheduler is closed")

    def _check_ledger(self) -> None:
        if self._broken:
            raise LedgerUnavailable("compute ledger failed; scheduler execution is held")

    @staticmethod
    def _lane(job: JobEnvelope) -> tuple[str, str, str]:
        return job.tenant_id, job.project_id, job.lane_key

    def _route_refusal(self, job: _Job) -> ReasonCode | None:
        assert job.workload is not None
        blocked = self._route_blocks.get((job.decision.job.tenant_id, job.workload.backend))
        if blocked is not None:
            return blocked
        backend = self._policy.backends[job.workload.backend]
        return None if self._backends[backend.kind].available else ReasonCode.STUB

    def _headroom(self) -> ReasonCode | None:
        gates = self._policy.gates
        assert (
            gates.disk_path is not None
            and gates.min_free_memory_percent is not None
            and gates.min_free_disk_bytes is not None
        )
        return capacity_refusal(
            self._capacity_probe(Path(gates.disk_path)),
            gates.min_free_memory_percent,
            gates.min_free_disk_bytes,
            gates.max_memory_pressure,
        )

    def _consider(self, job_id: str) -> Decision:
        job = self._jobs[job_id]
        decision, workload = job.decision, job.workload
        assert workload is not None
        blocked = self._route_refusal(job)
        if blocked is not None:
            return self._set(job_id, OutcomeCode.ROUTE_BLOCKED, JobState.REFUSED, blocked)
        tenant = decision.job.tenant_id
        committed = self._reserved_acu.get(tenant, 0) + self._spent_acu.get(tenant, 0)
        if committed + workload.acu_units > self._policy.tenants[tenant].session_budget_acu:
            return self._set(
                job_id, OutcomeCode.BUDGET_BLOCKED, JobState.REFUSED, ReasonCode.BUDGET_EXHAUSTED
            )
        headroom = self._headroom()
        if headroom is not None:
            return self._set(job_id, OutcomeCode.QUEUED, JobState.QUEUED, headroom)
        used = self._used_slots.get(workload.pool, 0)
        if used + workload.slot_cost > self._policy.pools[workload.pool].slots:
            return self._set(job_id, OutcomeCode.QUEUED, JobState.QUEUED, ReasonCode.POOL_FULL)
        result = self._set(
            job_id, OutcomeCode.ADMITTED, JobState.ADMITTED, ReasonCode.CAPACITY_AVAILABLE
        )
        self.heartbeat(job_id)
        return result

    def _unreserve(self, job: _Job) -> None:
        assert job.workload is not None
        self._used_slots[job.workload.pool] -= job.workload.slot_cost
        if job.decision.state == JobState.ADMITTED:
            self._reserved_acu[job.decision.job.tenant_id] -= job.workload.acu_units

    def _release(self, job_id: str) -> None:
        job = self._jobs[job_id]
        lane = self._lane(job.decision.job)
        lease = self._leases.get(lane)
        if lease is not None and lease.job_id == job_id:
            del self._leases[lane]
        if job.decision.state in {JobState.ADMITTED, JobState.RUNNING}:
            self._unreserve(job)

    def _set(
        self,
        job_id: str,
        code: OutcomeCode,
        state: JobState,
        reason: ReasonCode,
        *,
        attempts: Literal[0, 1] | None = None,
    ) -> Decision:
        job = self._jobs[job_id]
        old = job.decision
        new = Decision(
            old.job,
            code,
            state,
            reason,
            old.policy_version,
            old.route_alias,
            old.attempts if attempts is None else attempts,
        )
        if new == old:
            return old
        try:
            self._emit(new, old.state)
        except LedgerUnavailable:
            self._release(job_id)
            job.decision = (
                new
                if state in TERMINAL_STATES
                else Decision(
                    old.job,
                    OutcomeCode.REFUSED_POLICY,
                    JobState.REFUSED,
                    ReasonCode.LEDGER_FAILED,
                    old.policy_version,
                    old.route_alias,
                    old.attempts,
                )
            )
            raise
        if state in TERMINAL_STATES:
            self._release(job_id)
        elif old.state == JobState.ADMITTED and state == JobState.QUEUED:
            self._unreserve(job)
        elif state == JobState.ADMITTED:
            assert job.workload is not None
            self._used_slots[job.workload.pool] = (
                self._used_slots.get(job.workload.pool, 0) + job.workload.slot_cost
            )
            tenant = old.job.tenant_id
            self._reserved_acu[tenant] = self._reserved_acu.get(tenant, 0) + job.workload.acu_units
        elif state == JobState.RUNNING:
            assert job.workload is not None
            tenant = old.job.tenant_id
            self._reserved_acu[tenant] -= job.workload.acu_units
            self._spent_acu[tenant] = self._spent_acu.get(tenant, 0) + job.workload.acu_units
        job.decision = new
        return new

    def _emit(self, decision: Decision, previous: JobState | None) -> None:
        if not self._enabled or self._ledger is None:
            return
        job = self._jobs[decision.job.job_id]
        workload = job.workload
        backend = self._policy.backends[workload.backend] if workload else None
        output = job.output
        try:
            self._ledger.append(
                LedgerEvent(
                    **decision.job.model_dump(),
                    event_id=str(uuid4()),
                    timestamp=datetime.now(UTC),
                    policy_version=decision.policy_version,
                    state=decision.state,
                    prev_state=previous,
                    admission_code=decision.code,
                    reason=decision.reason,
                    attempt=decision.attempts,
                    backend=workload.backend if workload else None,
                    region=backend.region if backend else None,
                    pool=workload.pool if workload else None,
                    acu_units=workload.acu_units if workload else 0,
                    trace_ref=output.trace_ref if output else None,
                    artifact_refs=output.artifact_refs if output else (),
                )
            )
        except LedgerUnavailable:
            self._broken = True
            raise
