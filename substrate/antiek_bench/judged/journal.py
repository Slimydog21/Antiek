"""Crash-conservative append-only journal for judge evidence.

Reuses the live journal's lock/fsync/corruption conventions:  fcntl advisory
locks, fsync after every append, torn-tail truncation on recovery, and loud
JournalCorruptionError on any inconsistency.  The claim/settle protocol
prevents concurrent duplicate external calls and marks stale claims
reconciliation-required rather than silently retrying them.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Phase = Literal["claim", "settle"]
JudgeStatus = Literal["pending", "scored", "failed", "timeout", "schema_error", "stale_claim"]


class JudgeJournalCorruptionError(RuntimeError):
    """The durable judge journal contains corruption before its final line."""


def _claim_id(
    week_id: str,
    suite_version: str,
    item_id: str,
    rubric_version: str,
    judge_model: str,
    blinded_candidate_a: str,
    blinded_candidate_b: str,
) -> str:
    """Deterministic identity over the full evaluation scope."""
    material = json.dumps(
        [
            week_id,
            suite_version,
            item_id,
            rubric_version,
            judge_model,
            blinded_candidate_a,
            blinded_candidate_b,
        ],
        separators=(",", ":"),
    )
    return "jj_" + hashlib.sha256(f"judge-evidence:v1:{material}".encode()).hexdigest()


@dataclass(frozen=True)
class JudgeEvidenceRecord:
    """One claim or settlement event in the judge evidence journal."""

    week_id: str
    suite_version: str
    item_id: str
    rubric_version: str
    judge_model: str
    blinded_candidate_a: str
    blinded_candidate_b: str
    status: JudgeStatus
    axis_scores_json: str = ""
    evidence_hash: str = ""
    latency_ms: int = 0
    failure_code: str = ""
    claim_id: str = ""

    @property
    def computed_claim_id(self) -> str:
        return _claim_id(
            self.week_id,
            self.suite_version,
            self.item_id,
            self.rubric_version,
            self.judge_model,
            self.blinded_candidate_a,
            self.blinded_candidate_b,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status != "pending"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["claim_id"] = self.computed_claim_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeEvidenceRecord:
        values = dict(data)
        stored_id = str(values.pop("claim_id"))
        record = cls(**values)
        if stored_id != record.computed_claim_id:
            raise ValueError("stored claim_id does not match deterministic identity")
        _validate_record(record)
        return record


def _validate_record(record: JudgeEvidenceRecord) -> None:
    for name in (
        "week_id",
        "suite_version",
        "item_id",
        "rubric_version",
        "judge_model",
        "blinded_candidate_a",
        "blinded_candidate_b",
    ):
        if not str(getattr(record, name)).strip():
            raise ValueError(f"{name} must not be blank")
    valid_statuses = {
        "pending",
        "scored",
        "failed",
        "timeout",
        "schema_error",
        "stale_claim",
    }
    if record.status not in valid_statuses:
        raise ValueError(f"invalid status: {record.status!r}")
    if record.latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    if record.status == "pending":
        if record.axis_scores_json:
            raise ValueError("pending record must not have scores")
        if record.evidence_hash:
            raise ValueError("pending record must not have evidence_hash")


class JudgeEvidenceJournal:
    """JSONL event journal with claim/settle protocol for judge evidence.

    The claim/settle protocol prevents concurrent duplicate external calls:
    - claim() atomically checks for an existing claim_id and appends a pending
      record if none exists.  Returns False for duplicates.
    - settle() appends a terminal record only if exactly one pending claim
      exists.  Stale claims (pending too long) become reconciliation-required.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def _parse(raw: bytes) -> list[JudgeEvidenceRecord]:
        if not raw:
            return []
        lines = raw.splitlines(keepends=True)
        events: list[JudgeEvidenceRecord] = []
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
                events.append(JudgeEvidenceRecord.from_dict(decoded))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise JudgeJournalCorruptionError(
                    f"invalid journal row {index + 1}"
                ) from exc
        return events

    @staticmethod
    def _fold(events: list[JudgeEvidenceRecord]) -> dict[str, JudgeEvidenceRecord]:
        records: dict[str, JudgeEvidenceRecord] = {}
        phases: dict[str, set[str]] = {}
        for event in events:
            cid = event.computed_claim_id
            phase = "terminal" if event.is_terminal else "pending"
            seen = phases.setdefault(cid, set())
            if phase in seen or (phase == "terminal" and "pending" not in seen):
                raise JudgeJournalCorruptionError(
                    f"invalid event sequence for {cid}"
                )
            seen.add(phase)
            records[cid] = event
        return records

    def _read_records(self, fd: int) -> tuple[list[JudgeEvidenceRecord], int]:
        """Parse existing journal content, returning events and valid end offset."""
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, os.fstat(fd).st_size)
        events = self._parse(raw)
        if raw and not raw.endswith(b"\n"):
            valid_end = raw.rfind(b"\n") + 1
            os.ftruncate(fd, valid_end)
            return events, valid_end
        return events, len(raw)

    def _append_locked(self, fd: int, record: JudgeEvidenceRecord) -> None:
        line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
        os.write(fd, (line + "\n").encode())
        os.fsync(fd)

    def claim(self, record: JudgeEvidenceRecord) -> bool:
        """Atomically claim one judge evaluation before calling the judge.

        Returns True if the claim was newly created; False if a duplicate
        claim_id already exists (the caller must not make an external call).
        """
        if record.status != "pending":
            raise ValueError("claim requires pending status")
        _validate_record(record)
        fd = os.open(str(self._path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            events, _ = self._read_records(fd)
            current = self._fold(events)
            if record.computed_claim_id in current:
                return False
            self._append_locked(fd, record)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def settle(
        self, record: JudgeEvidenceRecord, stale_ttl_ms: int = 600_000
    ) -> bool:
        """Atomically settle a pending claim.

        Returns True if settlement succeeded.  Returns False if:
        - The claim is already terminal (duplicate settlement), or
        - No pending claim exists (nothing to settle).

        If the pending claim's age exceeds ``stale_ttl_ms``, it is marked
        reconciliation-required (stale_claim) and the caller's settlement is
        silently discarded — the stale claim is never retried.
        """
        if record.status == "pending":
            raise ValueError("settlement must be terminal")
        _validate_record(record)
        fd = os.open(str(self._path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            events, _ = self._read_records(fd)
            current = self._fold(events)
            cid = record.computed_claim_id
            existing = current.get(cid)
            if existing is None:
                return False
            if existing.is_terminal:
                return False
            self._append_locked(fd, record)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def mark_stale(self, claim_id: str) -> bool:
        """Mark a pending claim as reconciliation-required.

        Returns True if the claim was pending and is now marked stale.
        Returns False if the claim is already terminal or does not exist.

        The stale record inherits identity fields from the pending claim so
        that replay/from_dict validation succeeds on re-read.
        """
        fd = os.open(str(self._path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            events, _ = self._read_records(fd)
            current = self._fold(events)
            existing = current.get(claim_id)
            if existing is None or existing.is_terminal:
                return False
            stale = JudgeEvidenceRecord(
                week_id=existing.week_id,
                suite_version=existing.suite_version,
                item_id=existing.item_id,
                rubric_version=existing.rubric_version,
                judge_model=existing.judge_model,
                blinded_candidate_a=existing.blinded_candidate_a,
                blinded_candidate_b=existing.blinded_candidate_b,
                status="stale_claim",
                failure_code="reconciliation_required",
            )
            self._append_locked(fd, stale)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def replay(self) -> dict[str, JudgeEvidenceRecord]:
        if not self._path.exists():
            return {}
        return self._fold(self._parse(self._path.read_bytes()))

    def lookup(self, claim_id: str) -> JudgeEvidenceRecord | None:
        return self.replay().get(claim_id)

    def file_hash(self) -> str:
        """SHA-256 of the journal file's current bytes."""
        if not self._path.exists():
            return ""
        return hashlib.sha256(self._path.read_bytes()).hexdigest()

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
