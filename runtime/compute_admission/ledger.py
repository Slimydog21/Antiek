"""A private, single-writer compute_ledger.v1 JSONL journal."""

from __future__ import annotations

import fcntl
import os
import stat
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from .models import (
    TERMINAL_STATES,
    Identifier,
    JobState,
    OutcomeCode,
    OwnerUserId,
    ReasonCode,
    Reference,
    StrictModel,
    WorkloadClass,
)


class LedgerUnavailable(RuntimeError):
    pass


class LedgerEvent(StrictModel):
    schema_version: Literal["compute_ledger.v1"] = "compute_ledger.v1"
    event_id: str
    timestamp: datetime
    policy_version: str
    owner_user_id: OwnerUserId
    tenant_id: Identifier
    project_id: Identifier
    job_id: str
    idempotency_key: Identifier
    lane_key: Identifier
    workload_class: WorkloadClass = Field(strict=False)
    inputs_digest: str
    who_pays: Literal["antiek_hosted", "byot"]
    bead_id: Identifier | None
    state: JobState = Field(strict=False)
    prev_state: JobState | None = Field(strict=False)
    admission_code: OutcomeCode = Field(strict=False)
    reason: ReasonCode = Field(strict=False)
    attempt: Literal[0, 1]
    backend: str | None
    region: str | None
    pool: str | None
    acu_units: int = Field(ge=0)
    estimated_cost_usd: None = None
    actual_cost_usd: None = None
    cost_source: Literal["unknown"] = "unknown"
    trace_ref: Reference | None
    artifact_refs: tuple[Reference, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def aware_timestamp(self) -> Self:
        if self.timestamp.utcoffset() is None:
            raise ValueError("ledger timestamps must include UTC offset")
        return self


class LedgerRow(LedgerEvent):
    ledger_seq: int = Field(gt=0)


_NEXT = {
    JobState.REQUESTED: {JobState.QUEUED, JobState.ADMITTED, JobState.REFUSED},
    JobState.QUEUED: {JobState.QUEUED, JobState.ADMITTED, JobState.REFUSED, JobState.CANCELLED},
    JobState.ADMITTED: {JobState.QUEUED, JobState.RUNNING, JobState.REFUSED, JobState.CANCELLED},
    JobState.RUNNING: {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CREDENTIAL_BLOCKED,
        JobState.BILLING_BLOCKED,
    },
}
_IDENTITY = (
    "owner_user_id",
    "tenant_id",
    "project_id",
    "job_id",
    "idempotency_key",
    "lane_key",
    "workload_class",
    "inputs_digest",
    "who_pays",
    "bead_id",
    "policy_version",
    "backend",
    "region",
    "pool",
    "acu_units",
)


class JsonlLedger:
    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError("compute ledger path must be explicitly absolute")
        self.path = path
        self._fd: int | None = None
        self._lock = threading.RLock()
        self._closed = False
        self._failed = False
        self._sequence = 0
        self._last: dict[str, LedgerRow] = {}
        self._prior_keys: set[tuple[str, str, str, str]] = set()

    @staticmethod
    def _key(row: LedgerRow) -> tuple[str, str, str, str]:
        return row.owner_user_id, row.tenant_id, row.project_id, row.idempotency_key

    def append(self, event: LedgerEvent) -> LedgerRow:
        with self._lock:
            if self._closed or self._failed:
                raise LedgerUnavailable("compute ledger is closed or failed")
            try:
                self._open()
                row = LedgerRow(**event.model_dump(), ledger_seq=self._sequence + 1)
                self._validate_next(row)
                payload = (row.model_dump_json() + "\n").encode()
                if len(payload) > 65536:
                    raise ValueError("ledger row exceeds the bounded record size")
                assert self._fd is not None
                # A partial record stays visible for operator recovery; never truncate history.
                if os.write(self._fd, payload) != len(payload):
                    raise OSError("partial compute ledger write")
                os.fsync(self._fd)
                self._sequence = row.ledger_seq
                self._last[row.job_id] = row
                return row
            except (OSError, ValueError) as exc:
                self._failed = True
                raise LedgerUnavailable("compute ledger append failed; execution is held") from exc

    def _validate_next(self, row: LedgerRow) -> None:
        old = self._last.get(row.job_id)
        if row.ledger_seq != self._sequence + 1:
            raise ValueError("compute ledger sequence is discontinuous")
        if old is None:
            if row.prev_state is not None or row.state != JobState.REQUESTED or row.attempt != 0:
                raise ValueError("first job event must be requested without an attempt")
            if self._key(row) in self._prior_keys:
                raise ValueError("historical idempotency keys require explicit reconciliation")
            return
        if (
            old.state in TERMINAL_STATES
            or row.prev_state != old.state
            or row.state not in _NEXT.get(old.state, set())
            or any(getattr(row, field) != getattr(old, field) for field in _IDENTITY)
            or row.attempt != (1 if row.state == JobState.RUNNING else old.attempt)
        ):
            raise ValueError("invalid compute ledger transition or identity")

    def _open(self) -> None:
        if self._fd is not None:
            return
        fd = os.open(
            self.path,
            os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            0o600,
        )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_mode & 0o077
                or info.st_uid != os.getuid()
            ):
                raise ValueError("compute ledger must be a private regular file")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with os.fdopen(os.dup(fd), "rb") as reader:
                while line := reader.readline(65537):
                    if len(line) > 65536 or not line.endswith(b"\n"):
                        raise ValueError("compute ledger has an incomplete or oversized row")
                    row = LedgerRow.model_validate_json(line)
                    self._validate_next(row)
                    self._sequence = row.ledger_seq
                    self._last[row.job_id] = row
            if any(row.state not in TERMINAL_STATES for row in self._last.values()):
                raise ValueError("unfinished historical jobs require explicit reconciliation")
            self._prior_keys = {self._key(row) for row in self._last.values()}
            self._fd = fd
        except BaseException:
            os.close(fd)
            raise

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
