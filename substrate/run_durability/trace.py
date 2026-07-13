"""Strict, canonical durable-run trace records and prefix reconstruction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, cast, runtime_checkable

from .checkpoints import (
    MAX_REF_BYTES,
    MAX_REF_COUNT,
    CheckpointKind,
    FloorName,
    validate_ref,
    validate_sequence,
    validate_sha256,
)

SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64
_ENVELOPE_FIELDS = frozenset(
    {
        "approved_brief_hash",
        "data",
        "event_hash",
        "kind",
        "occurred_at",
        "previous_hash",
        "run_id",
        "schema_version",
        "sequence",
    }
)


class TraceError(ValueError):
    pass


class ConcurrentAppendError(TraceError):
    pass


class EventKind(StrEnum):
    RUN_STARTED = "run_started"
    STEP_RECORDED = "step_recorded"
    SOURCE_FETCHED = "source_fetched"
    FLOOR_TRIPPED = "floor_tripped"
    CHECKPOINT_RECORDED = "checkpoint_recorded"
    FAILURE_RECORDED = "failure_recorded"
    RUN_RESUMED = "run_resumed"
    RUN_COMPLETED = "run_completed"


_DATA_FIELDS = {
    EventKind.RUN_STARTED: frozenset(),
    EventKind.STEP_RECORDED: frozenset({"step_ref"}),
    EventKind.SOURCE_FETCHED: frozenset({"source_ref"}),
    EventKind.FLOOR_TRIPPED: frozenset({"floor", "observed", "required"}),
    EventKind.CHECKPOINT_RECORDED: frozenset({"checkpoint_kind", "refs"}),
    EventKind.FAILURE_RECORDED: frozenset(
        {"failure", "attempt", "attempt_limit", "decision", "decided_at", "retry_at"}
    ),
    EventKind.RUN_RESUMED: frozenset({"from_sequence"}),
    EventKind.RUN_COMPLETED: frozenset({"report_ref"}),
}
_TRANSIENT_FAILURES = frozenset(
    {"timeout", "rate_limited", "temporary_unavailable", "connection_failure", "process_killed"}
)


def canonical_timestamp(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise TraceError("timestamp must be an aware UTC datetime")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TraceError(f"{field_name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise TraceError(f"{field_name} must be a canonical UTC timestamp") from exc
    if canonical_timestamp(parsed) != value:
        raise TraceError(f"{field_name} must be a canonical UTC timestamp")
    return value


def _snapshot(value: object, *, field_name: str) -> dict[object, object]:
    if not isinstance(value, Mapping):
        raise TraceError(f"{field_name} must be a mapping")
    try:
        first = tuple(value.items())
        second = tuple(value.items())
        claimed_length = len(value)
    except Exception as exc:
        raise TraceError(f"{field_name} mapping could not be read safely") from exc
    try:
        if first != second or claimed_length != len(first):
            raise TraceError(f"{field_name} mapping changed while being read")
        result: dict[object, object] = {}
        for key, item in first:
            if key in result:
                raise TraceError(f"{field_name} contains a duplicate key")
            result[key] = item
    except TraceError:
        raise
    except Exception as exc:
        raise TraceError(f"{field_name} mapping contains unsafe keys or values") from exc
    return result


def _finite_number(value: object, *, field_name: str) -> float:
    import math

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceError(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise TraceError(f"{field_name} must be finite and non-negative")
    return result


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TraceError("record must contain canonical JSON primitives") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TraceError("JSON objects must not contain duplicate keys")
        result[key] = value
    return result


def _validate_data(kind: EventKind, raw: object) -> Mapping[str, object]:
    data = _snapshot(raw, field_name="data")
    if any(not isinstance(key, str) for key in data) or frozenset(data) != _DATA_FIELDS[kind]:
        raise TraceError("event data has missing, extra, or non-string keys")
    clean: dict[str, object] = {}
    if kind is EventKind.CHECKPOINT_RECORDED:
        checkpoint = data["checkpoint_kind"]
        if not isinstance(checkpoint, str):
            raise TraceError("checkpoint_kind must be a string")
        try:
            CheckpointKind(checkpoint)
        except ValueError as exc:
            raise TraceError("unknown checkpoint kind") from exc
        refs = _snapshot(data["refs"], field_name="refs")
        if not refs:
            raise TraceError("refs must not be empty")
        if len(refs) > MAX_REF_COUNT:
            raise TraceError("checkpoint contains too many references")
        clean_refs: dict[str, str] = {}
        for key, value in refs.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TraceError("refs must contain only string keys and values")
            if not key.endswith("_ref"):
                raise TraceError("checkpoint reference keys must end in _ref")
            clean_refs[validate_ref(key, field="ref key")] = validate_ref(value)
        if (
            sum(len(key.encode()) + len(value.encode()) for key, value in clean_refs.items())
            > MAX_REF_BYTES
        ):
            raise TraceError("checkpoint reference payload is too large")
        clean = {
            "checkpoint_kind": checkpoint,
            "refs": MappingProxyType(dict(sorted(clean_refs.items()))),
        }
    elif kind in {EventKind.STEP_RECORDED, EventKind.SOURCE_FETCHED, EventKind.RUN_COMPLETED}:
        name = next(iter(_DATA_FIELDS[kind]))
        clean[name] = validate_ref(data[name], field=name)
    elif kind is EventKind.FLOOR_TRIPPED:
        floor = data["floor"]
        if not isinstance(floor, str):
            raise TraceError("floor must be a string")
        try:
            FloorName(floor)
        except ValueError as exc:
            raise TraceError("unknown floor") from exc
        observed = _finite_number(data["observed"], field_name="observed")
        required = _finite_number(data["required"], field_name="required")
        if observed >= required:
            raise TraceError("a floor trip must describe a failed observation")
        clean = {"floor": floor, "observed": observed, "required": required}
    elif kind is EventKind.RUN_RESUMED:
        clean = {"from_sequence": validate_sequence(data["from_sequence"], field="from_sequence")}
    elif kind is EventKind.FAILURE_RECORDED:
        failure, decision = data["failure"], data["decision"]
        if not isinstance(failure, str) or not isinstance(decision, str):
            raise TraceError("failure and decision must be strings")
        attempt = validate_sequence(data["attempt"], field="attempt")
        attempt_limit = validate_sequence(data["attempt_limit"], field="attempt_limit")
        if not 1 <= attempt_limit <= 3:
            raise TraceError("attempt_limit must be between 1 and 3")
        expected_decision = (
            "retry" if failure in _TRANSIENT_FAILURES and attempt < attempt_limit else "terminal"
        )
        if decision != expected_decision:
            raise TraceError(
                "failure decision does not match fail-closed taxonomy and attempt limit"
            )
        retry_at = data["retry_at"]
        if retry_at is not None and not isinstance(retry_at, str):
            raise TraceError("retry_at must be null or a canonical timestamp")
        if (decision == "retry") != (retry_at is not None):
            raise TraceError("retry_at must exist exactly for retry decisions")
        decided_at = _parse_timestamp(data["decided_at"], field_name="decided_at")
        canonical_retry = (
            None if retry_at is None else _parse_timestamp(retry_at, field_name="retry_at")
        )
        if canonical_retry is not None and canonical_retry < decided_at:
            raise TraceError("retry_at cannot precede decided_at")
        clean = {
            "failure": validate_ref(failure, field="failure"),
            "attempt": attempt,
            "attempt_limit": attempt_limit,
            "decision": decision,
            "decided_at": decided_at,
            "retry_at": canonical_retry,
        }
    return MappingProxyType(clean)


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class TraceEvent:
    run_id: str
    approved_brief_hash: str
    sequence: int
    kind: EventKind
    occurred_at: str
    data: Mapping[str, object]
    previous_hash: str
    event_hash: str = field(default="")
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_ref(self.run_id, field="run_id")
        validate_sha256(self.approved_brief_hash, field="approved_brief_hash")
        validate_sequence(self.sequence)
        if not isinstance(self.kind, EventKind):
            raise TraceError("kind must be a known EventKind")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise TraceError("unsupported schema version")
        _parse_timestamp(self.occurred_at, field_name="occurred_at")
        validate_sha256(self.previous_hash, field="previous_hash")
        clean = _validate_data(self.kind, self.data)
        object.__setattr__(self, "data", clean)
        expected = self.compute_hash()
        if self.event_hash and (
            not isinstance(self.event_hash, str) or self.event_hash != expected
        ):
            raise TraceError("event hash does not match record")
        object.__setattr__(self, "event_hash", expected)

    def body(self) -> dict[str, object]:
        return {
            "approved_brief_hash": self.approved_brief_hash,
            "data": _thaw(self.data),
            "kind": self.kind.value,
            "occurred_at": self.occurred_at,
            "previous_hash": self.previous_hash,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
        }

    def to_mapping(self) -> dict[str, object]:
        return {**self.body(), "event_hash": self.event_hash}

    def to_json(self) -> bytes:
        return _canonical_json(self.to_mapping())

    def compute_hash(self) -> str:
        return hashlib.sha256(_canonical_json(self.body())).hexdigest()

    @classmethod
    def from_mapping(cls, raw: object) -> TraceEvent:
        record = _snapshot(raw, field_name="event")
        if any(not isinstance(key, str) for key in record) or frozenset(record) != _ENVELOPE_FIELDS:
            raise TraceError("event has missing, extra, or non-string fields")
        for name in (
            "run_id",
            "approved_brief_hash",
            "kind",
            "occurred_at",
            "previous_hash",
            "event_hash",
        ):
            if not isinstance(record[name], str):
                raise TraceError(f"{name} must be a string")
        if isinstance(record["schema_version"], bool) or not isinstance(
            record["schema_version"], int
        ):
            raise TraceError("schema_version must be an integer")
        try:
            kind = EventKind(cast(str, record["kind"]))
        except ValueError as exc:
            raise TraceError("unknown event kind") from exc
        return cls(
            run_id=cast(str, record["run_id"]),
            approved_brief_hash=cast(str, record["approved_brief_hash"]),
            sequence=validate_sequence(record["sequence"]),
            kind=kind,
            occurred_at=cast(str, record["occurred_at"]),
            data=cast(Mapping[str, object], record["data"]),
            previous_hash=cast(str, record["previous_hash"]),
            event_hash=cast(str, record["event_hash"]),
            schema_version=record["schema_version"],
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> TraceEvent:
        if (
            not isinstance(raw, (bytes, str))
            or isinstance(raw, str)
            and raw.encode() != raw.encode("utf-8")
        ):
            raise TraceError("event JSON must be UTF-8 bytes or text")
        try:
            parsed = json.loads(
                raw,
                object_pairs_hook=_unique_object,
                parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
            )
        except TraceError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise TraceError("invalid event JSON") from exc
        event = cls.from_mapping(parsed)
        if event.to_json() != (raw.encode("utf-8") if isinstance(raw, str) else raw):
            raise TraceError("event JSON is not canonical")
        return event

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        approved_brief_hash: str,
        sequence: int,
        kind: EventKind,
        occurred_at: datetime,
        data: Mapping[str, object],
        previous_hash: str,
    ) -> TraceEvent:
        return cls(
            run_id,
            approved_brief_hash,
            sequence,
            kind,
            canonical_timestamp(occurred_at),
            data,
            previous_hash,
        )


@runtime_checkable
class EventLogPort(Protocol):
    def read(self, run_id: str) -> Sequence[TraceEvent]: ...
    def append(self, event: TraceEvent, *, expected_sequence: int) -> None: ...


@dataclass(frozen=True, slots=True)
class RunView:
    run_id: str
    approved_brief_hash: str
    next_sequence: int
    last_hash: str
    checkpoint_refs: Mapping[str, Mapping[str, str]]
    steps: tuple[str, ...]
    sources: tuple[str, ...]
    floor_trips: int
    failures: int
    resumes: int
    unresolved_resumable_sequence: int | None
    terminal_failure: bool
    report_ref: str | None
    completed: bool


def reconstruct(events: Sequence[TraceEvent]) -> RunView | None:
    if not events:
        return None
    run_id, brief = events[0].run_id, events[0].approved_brief_hash
    previous, checkpoints = GENESIS_HASH, {}
    steps: list[str] = []
    sources: list[str] = []
    trips = failures = resumes = 0
    unresolved: int | None = None
    terminal = completed = False
    report_ref: str | None = None
    last_checkpoint = -1
    last_timestamp: str | None = None
    failure_attempts: dict[str, int] = {}
    order = {kind: index for index, kind in enumerate(CheckpointKind)}
    for expected, original in enumerate(events):
        event = TraceEvent.from_json(original.to_json())
        if last_timestamp is not None and event.occurred_at < last_timestamp:
            raise TraceError("event timestamps must be monotonic")
        last_timestamp = event.occurred_at
        if (
            event.sequence != expected
            or event.run_id != run_id
            or event.approved_brief_hash != brief
        ):
            raise TraceError("out-of-order, cross-run, or cross-brief event")
        if event.previous_hash != previous or event.compute_hash() != event.event_hash:
            raise TraceError("forked or tampered hash chain")
        if expected == 0 and event.kind is not EventKind.RUN_STARTED:
            raise TraceError("trace must begin with run_started")
        if expected > 0 and event.kind is EventKind.RUN_STARTED:
            raise TraceError("run_started may occur only once")
        if completed or terminal:
            raise TraceError("events cannot follow a terminal trace event")
        if event.kind is EventKind.CHECKPOINT_RECORDED:
            kind = CheckpointKind(cast(str, event.data["checkpoint_kind"]))
            position = order[kind]
            if position <= last_checkpoint:
                raise TraceError("checkpoint boundaries must move forward without duplicates")
            last_checkpoint = position
            refs = event.data["refs"]
            assert isinstance(refs, Mapping)
            checkpoints[kind.value] = MappingProxyType(dict(refs))
        elif event.kind is EventKind.STEP_RECORDED:
            steps.append(cast(str, event.data["step_ref"]))
        elif event.kind is EventKind.SOURCE_FETCHED:
            sources.append(cast(str, event.data["source_ref"]))
        elif event.kind is EventKind.FLOOR_TRIPPED:
            if unresolved is not None:
                raise TraceError("a resumable cause is already unresolved")
            trips += 1
            unresolved = expected
        elif event.kind is EventKind.FAILURE_RECORDED:
            if unresolved is not None:
                raise TraceError("a resumable cause is already unresolved")
            failures += 1
            failure = cast(str, event.data["failure"])
            expected_attempt = failure_attempts.get(failure, 0)
            if event.data["attempt"] != expected_attempt:
                raise TraceError("failure attempts must advance monotonically from durable history")
            failure_attempts[failure] = expected_attempt + 1
            if event.data["decision"] == "retry":
                unresolved = expected
            else:
                terminal = True
        elif event.kind is EventKind.RUN_RESUMED:
            if unresolved is None or event.data["from_sequence"] != unresolved:
                raise TraceError("resume must match one unresolved resumable cause")
            resumes += 1
            unresolved = None
        elif event.kind is EventKind.RUN_COMPLETED:
            if unresolved is not None:
                raise TraceError("cannot complete with an unresolved resumable cause")
            report_ref = cast(str, event.data["report_ref"])
            completed = True
        previous = event.event_hash
    frozen = MappingProxyType(dict(checkpoints))
    return RunView(
        run_id,
        brief,
        len(events),
        previous,
        frozen,
        tuple(steps),
        tuple(sources),
        trips,
        failures,
        resumes,
        unresolved,
        terminal,
        report_ref,
        completed,
    )


def append_cas(port: EventLogPort, event: TraceEvent) -> RunView:
    before = tuple(port.read(event.run_id))
    view = reconstruct(before)
    expected = 0 if view is None else view.next_sequence
    if event.sequence != expected:
        raise ConcurrentAppendError("stale expected sequence")
    # Validate the proposed transition before granting the adapter a write.
    reconstruct((*before, event))
    port.append(event, expected_sequence=expected)
    after = tuple(port.read(event.run_id))
    if (
        len(after) != len(before) + 1
        or after[:-1] != before
        or after[-1].to_json() != event.to_json()
    ):
        raise ConcurrentAppendError("port did not append the exact event atomically")
    result = reconstruct(after)
    if result is None:
        raise ConcurrentAppendError("port lost the appended event")
    return result
