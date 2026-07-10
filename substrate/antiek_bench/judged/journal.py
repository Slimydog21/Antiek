"""Crash-safe claim/settle journal for qualitative judge evidence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from ..suite import TaskClass
from .rubric import AxisJudgment, rubric_for, validate_judgments

EvidenceStatus = Literal["pending", "ok", "failed"]
FailureCode = Literal["invalid_or_failed_response"]
FAILURE_CODES = frozenset({"invalid_or_failed_response"})
EVIDENCE_SCHEMA_VERSION = 1


class EvidenceJournalCorruptionError(RuntimeError):
    pass


def evidence_id(
    week_id: str,
    suite_version: str,
    item_id_hash: str,
    rubric_version: str,
    judge_model: str,
    candidate_hashes: tuple[str, str],
) -> str:
    material = json.dumps(
        [week_id, suite_version, item_id_hash, rubric_version, judge_model, candidate_hashes],
        separators=(",", ":"),
    )
    return "je_" + hashlib.sha256(f"judge-evidence:v1:{material}".encode()).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    week_id: str
    suite_version: str
    item_id_hash: str
    task_class: TaskClass
    rubric_version: str
    judge_model: str
    candidate_hashes: tuple[str, str]
    blinded_order: tuple[str, str]
    status: EvidenceStatus
    claimed_at_ms: int
    scores: tuple[tuple[str, int], ...] = ()
    evidence_refs: tuple[tuple[str, tuple[str, ...]], ...] = ()
    latency_ms: int = 0
    failure_code: str = ""
    schema_version: int = EVIDENCE_SCHEMA_VERSION

    @property
    def evidence_id(self) -> str:
        return evidence_id(
            self.week_id,
            self.suite_version,
            self.item_id_hash,
            self.rubric_version,
            self.judge_model,
            self.candidate_hashes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "evidence_id": self.evidence_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        values = dict(data)
        stored = str(values.pop("evidence_id"))
        for key in ("candidate_hashes", "blinded_order", "scores"):
            values[key] = tuple(
                tuple(row) if isinstance(row, list) else row for row in values.get(key, ())
            )
        values["evidence_refs"] = tuple(
            (row[0], tuple(row[1])) for row in values.get("evidence_refs", ())
        )
        record = cls(**values)
        if stored != record.evidence_id:
            raise ValueError("stored evidence_id does not match deterministic identity")
        _validate(record)
        return record


def _validate(record: EvidenceRecord) -> None:
    if record.schema_version != EVIDENCE_SCHEMA_VERSION or record.status not in {
        "pending",
        "ok",
        "failed",
    }:
        raise ValueError("invalid evidence record schema or status")
    if (
        not all(
            (
                record.week_id,
                record.suite_version,
                record.item_id_hash,
                record.rubric_version,
                record.judge_model,
            )
        )
        or len(record.candidate_hashes) != 2
    ):
        raise ValueError("evidence identity fields are required")
    if record.claimed_at_ms < 0 or record.latency_ms < 0:
        raise ValueError("timing must be non-negative")
    if record.status == "pending" and (
        record.scores or record.evidence_refs or record.failure_code
    ):
        raise ValueError("pending evidence cannot contain a settlement")
    if record.status == "failed":
        if record.failure_code not in FAILURE_CODES:
            raise ValueError("failed evidence requires a fixed failure code")
        if record.scores or record.evidence_refs:
            raise ValueError("failed evidence cannot contain judgments")
    if record.status == "ok":
        if record.failure_code:
            raise ValueError("ok evidence cannot contain a failure code")
        rubric = rubric_for(record.task_class)
        scores = dict(record.scores)
        references = dict(record.evidence_refs)
        axes = set(scores) | set(references)
        judgments = {
            axis: AxisJudgment(scores[axis], "validated-not-persisted", references[axis])
            for axis in axes
            if axis in scores and axis in references
        }
        validate_judgments(rubric, record.rubric_version, judgments)


class EvidenceJournal:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _parse(raw: bytes) -> list[EvidenceRecord]:
        rows: list[EvidenceRecord] = []
        lines = raw.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                break
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    raise ValueError("row must be object")
                rows.append(EvidenceRecord.from_dict(data))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise EvidenceJournalCorruptionError(f"invalid evidence row {index + 1}") from exc
        return rows

    @staticmethod
    def _fold(rows: list[EvidenceRecord]) -> dict[str, EvidenceRecord]:
        folded: dict[str, EvidenceRecord] = {}
        for row in rows:
            old = folded.get(row.evidence_id)
            if (old is None and row.status != "pending") or (
                old is not None and (old.status != "pending" or row.status == "pending")
            ):
                raise EvidenceJournalCorruptionError(
                    f"invalid evidence sequence for {row.evidence_id}"
                )
            if old is not None and _claim_metadata(old) != _claim_metadata(row):
                raise EvidenceJournalCorruptionError(
                    f"settlement metadata mismatch for {row.evidence_id}"
                )
            folded[row.evidence_id] = row
        return folded

    def replay(self) -> dict[str, EvidenceRecord]:
        return {} if not self.path.exists() else self._fold(self._parse(self.path.read_bytes()))

    def _mutate(self, record: EvidenceRecord, claim: bool) -> bool:
        _validate(record)
        fd = os.open(str(self.path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, os.fstat(fd).st_size)
            current = self._fold(self._parse(raw))
            if raw and not raw.endswith(b"\n"):
                os.ftruncate(fd, raw.rfind(b"\n") + 1)
            old = current.get(record.evidence_id)
            if claim:
                if record.status != "pending":
                    raise ValueError("claim requires pending evidence")
                if old is not None:
                    return False
            elif old is None or old.status != "pending" or record.status == "pending":
                raise ValueError("settlement requires exactly one pending claim")
            elif _claim_metadata(old) != _claim_metadata(record):
                raise ValueError("settlement metadata does not match claim")
            line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def claim(self, record: EvidenceRecord) -> bool:
        return self._mutate(record, True)

    def settle(self, record: EvidenceRecord) -> bool:
        return self._mutate(record, False)

    def lookup(self, identity: str) -> EvidenceRecord | None:
        return self.replay().get(identity)


def _claim_metadata(record: EvidenceRecord) -> tuple[object, ...]:
    return (
        record.week_id,
        record.suite_version,
        record.item_id_hash,
        record.task_class,
        record.rubric_version,
        record.judge_model,
        record.candidate_hashes,
        record.blinded_order,
        record.claimed_at_ms,
        record.schema_version,
    )
