"""Provider-neutral job, placement and outcome contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class WorkloadClass(StrEnum):
    DEV_AGENT_LANE = "dev.agent_lane"
    DEV_AGENT_SUB = "dev.agent_sub"
    DEV_TEST_SUITE = "dev.test_suite"
    DEV_BUILD = "dev.build"
    DEV_DEVSERVER = "dev.devserver"
    INGEST = "research.ingest"
    FETCH = "research.fetch"
    OCR = "research.ocr"
    EMBED_INDEX = "research.embed_index"
    AGENT_RUN = "research.agent_run"
    AGENT_TURN = "research.agent_turn"
    RENDER_PDF = "research.render_pdf"
    BATCH_CPU = "research.batch_cpu"
    BATCH_GPU = "research.batch_gpu"


class BackendKind(StrEnum):
    IN_PROCESS = "in_process"
    MODAL = "modal"
    PRIME_SANDBOXES = "prime_sandboxes"
    MINI_NODE = "mini_node"


class DataLocality(StrEnum):
    ANTIEK_USER = "antiek_user"
    CLOUD_OK = "cloud-ok"
    CLOUD_OK_NO_RETENTION = "cloud-ok-no-retention"
    MINI_ONLY = "mini-only"


class OutcomeCode(StrEnum):
    ADMITTED = "admitted"
    QUEUED = "queued"
    REFUSED_POLICY = "refused_policy"
    LEASE_HELD = "lease_held"
    ROUTE_BLOCKED = "route_blocked"
    BUDGET_BLOCKED = "budget_blocked"


class JobState(StrEnum):
    REQUESTED = "requested"
    QUEUED = "queued"
    ADMITTED = "admitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUSED = "refused"
    CREDENTIAL_BLOCKED = "credential_blocked"
    BILLING_BLOCKED = "billing_blocked"


TERMINAL_STATES = frozenset(
    {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.REFUSED,
        JobState.CREDENTIAL_BLOCKED,
        JobState.BILLING_BLOCKED,
    }
)


class ReasonCode(StrEnum):
    REQUESTED = "submission_requested"
    POOL_FULL = "pool_full"
    DISABLED = "compute_layer_disabled"
    WORKLOAD_DISABLED = "workload_disabled_or_unknown"
    UNALLOCATED = "tenant_or_project_unallocated"
    OWNER_UNALLOCATED = "owner_unallocated"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    LANE_OWNED = "lane_owned"
    CREDENTIAL_BLOCKED = "credential_blocked"
    BILLING_BLOCKED = "billing_blocked"
    BUDGET_EXHAUSTED = "session_acu_exhausted"
    CAPACITY_AVAILABLE = "local_capacity_available"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled_before_start"
    RESIDENCY = "eu_residency_required"
    MINI_REQUIRED = "mini_locality_required"
    RETENTION_UNPROVEN = "no_retention_unproven"
    STUB = "adapter_not_implemented"
    LEDGER_UNBOUND = "ledger_unbound"
    LEDGER_FAILED = "ledger_failed"
    GATES_UNBOUND = "capacity_policy_unconfigured"
    CAPACITY_UNKNOWN = "capacity_unavailable"
    MEMORY_LOW = "memory_headroom"
    DISK_LOW = "disk_headroom"


class JobRequest(StrictModel):
    owner_user_id: Identifier
    tenant_id: Identifier
    project_id: Identifier
    idempotency_key: Identifier
    lane_key: Identifier
    workload_class: WorkloadClass = Field(strict=False)
    inputs_digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    who_pays: Literal["antiek_hosted", "byot"]
    bead_id: Identifier | None = None

    @model_validator(mode="after")
    def bead_lane(self) -> Self:
        if self.bead_id is not None and self.bead_id != self.lane_key:
            raise ValueError("bead-driven jobs must use the exact bead id as lane_key")
        return self


class JobEnvelope(JobRequest):
    job_id: str


Reference = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class JobOutput(StrictModel):
    value: object = None
    trace_ref: Reference | None = None
    artifact_refs: tuple[Reference, ...] = Field(default=(), max_length=64)


@dataclass(frozen=True)
class Decision:
    job: JobEnvelope
    code: OutcomeCode
    state: JobState
    reason: ReasonCode
    policy_version: str
    route_alias: str | None
    attempts: Literal[0, 1]
    retryable: bool = field(default=False, init=False)


@dataclass(frozen=True)
class ExecutionReport:
    decision: Decision
    value: object = None


@dataclass(frozen=True)
class JobContext:
    job: JobEnvelope
    heartbeat: Callable[[], bool]
