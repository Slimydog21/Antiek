"""Crash-conservative append-only journal for measured model calls."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

Status = Literal["reserved", "ok", "failed", "timeout", "skipped_budget"]
TerminalStatus = Literal["ok", "failed", "timeout", "skipped_budget"]


class JournalCorruptionError(RuntimeError):
    """The durable journal contains corruption before its final line."""


def deterministic_call_id(
    wedge_id: str,
    week_id: str,
    suite_version: str,
    requested_provider: str,
    requested_model: str,
    task_class: str,
    item_id: str,
    prompt_hash: str,
) -> str:
    """Return an identity scoped to a concrete benchmark wedge."""
    material = json.dumps(
        [
            wedge_id,
            week_id,
            suite_version,
            requested_provider,
            requested_model,
            task_class,
            item_id,
            prompt_hash,
        ],
        separators=(",", ":"),
    )
    return "lc_" + hashlib.sha256(f"live-call:v2:{material}".encode()).hexdigest()


@dataclass(frozen=True)
class LiveCallRecord:
    """One reservation or settlement event for a provider call."""

    wedge_id: str
    week_id: str
    suite_version: str
    requested_provider: str
    requested_model: str
    task_class: str
    item_id: str
    status: Status
    reserved_usd: Decimal
    actual_provider: str = ""
    actual_model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    latency_ms: int = 0
    prompt_hash: str = ""
    response_hash: str = ""
    route_receipt_id: str = ""
    failure_text: str = ""
    schema_version: int = 2

    @property
    def call_id(self) -> str:
        return deterministic_call_id(
            self.wedge_id,
            self.week_id,
            self.suite_version,
            self.requested_provider,
            self.requested_model,
            self.task_class,
            self.item_id,
            self.prompt_hash,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status != "reserved"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reserved_usd"] = str(self.reserved_usd)
        data["cost_usd"] = str(self.cost_usd)
        data["call_id"] = self.call_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveCallRecord:
        values = dict(data)
        stored_id = str(values.pop("call_id"))
        values["reserved_usd"] = Decimal(str(values["reserved_usd"]))
        values["cost_usd"] = Decimal(str(values.get("cost_usd", "0")))
        record = cls(**values)
        if stored_id != record.call_id:
            raise ValueError("stored call_id does not match deterministic identity")
        _validate_record(record)
        return record


def _validate_record(record: LiveCallRecord) -> None:
    for name in (
        "wedge_id",
        "week_id",
        "suite_version",
        "requested_provider",
        "requested_model",
        "task_class",
        "item_id",
    ):
        if not str(getattr(record, name)).strip():
            raise ValueError(f"{name} must not be blank")
    if record.schema_version != 2:
        raise ValueError("unsupported schema_version")
    if record.status not in {"reserved", "ok", "failed", "timeout", "skipped_budget"}:
        raise ValueError(f"invalid status: {record.status!r}")
    if min(record.reserved_usd, record.cost_usd) < 0:
        raise ValueError("costs must be non-negative")
    if min(record.prompt_tokens, record.completion_tokens, record.latency_ms) < 0:
        raise ValueError("usage and latency must be non-negative")
    if record.status == "reserved" and record.cost_usd:
        raise ValueError("a reservation cannot have realized cost")


class Journal:
    """JSONL event journal; reservation and settlement share a call id."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def _fold(events: list[LiveCallRecord]) -> dict[str, LiveCallRecord]:
        records: dict[str, LiveCallRecord] = {}
        phases: dict[str, set[str]] = {}
        for event in events:
            phase = "terminal" if event.is_terminal else "reserved"
            seen = phases.setdefault(event.call_id, set())
            if phase in seen or (phase == "terminal" and "reserved" not in seen):
                raise JournalCorruptionError(f"invalid event sequence for {event.call_id}")
            seen.add(phase)
            records[event.call_id] = event
        return records

    @staticmethod
    def _parse(raw: bytes) -> list[LiveCallRecord]:
        if not raw:
            return []
        lines = raw.splitlines(keepends=True)
        events: list[LiveCallRecord] = []
        for index, raw_line in enumerate(lines):
            if not raw_line.strip():
                continue
            complete = raw_line.endswith(b"\n")
            if index == len(lines) - 1 and not complete:
                break
            try:
                decoded = json.loads(raw_line)
                if not isinstance(decoded, dict):
                    raise ValueError("journal row must be an object")
                events.append(LiveCallRecord.from_dict(decoded))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise JournalCorruptionError(f"invalid journal row {index + 1}") from exc
        return events

    def replay(self) -> dict[str, LiveCallRecord]:
        if not self._path.exists():
            return {}
        return self._fold(self._parse(self._path.read_bytes()))

    def append(self, record: LiveCallRecord) -> None:
        """Validate and append while holding one lock across check and write."""
        _validate_record(record)
        fd = os.open(str(self._path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, os.fstat(fd).st_size)
            events = self._parse(raw)
            if raw and not raw.endswith(b"\n"):
                # The ignored torn suffix must be removed before appending or it
                # would be joined to the next JSON object permanently.
                valid_end = raw.rfind(b"\n") + 1
                os.ftruncate(fd, valid_end)
            current = self._fold(events).get(record.call_id)
            if current is None and record.status != "reserved":
                raise ValueError("terminal event requires a durable reservation")
            if current is not None and (current.is_terminal or record.status == "reserved"):
                raise ValueError(f"duplicate event for call_id: {record.call_id}")
            line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def reserve_within_cap(self, record: LiveCallRecord, cap_usd: Decimal) -> bool:
        """Atomically admit and persist a reservation under a hard cap."""
        _validate_record(record)
        if record.status != "reserved":
            raise ValueError("reserve_within_cap requires a reservation")
        fd = os.open(str(self._path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, os.fstat(fd).st_size)
            events = self._parse(raw)
            if raw and not raw.endswith(b"\n"):
                os.ftruncate(fd, raw.rfind(b"\n") + 1)
            current = self._fold(events)
            if record.call_id in current:
                return False
            charged = sum(
                (max(event.reserved_usd, event.cost_usd) for event in current.values()),
                Decimal("0"),
            )
            if charged + record.reserved_usd > cap_usd:
                return False
            line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def lookup(self, call_id: str) -> LiveCallRecord | None:
        return self.replay().get(call_id)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
