"""Privacy-bounded NotDiamond recommendations with no execution authority."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

ANTIEK_NOTDIAMOND_ENV = "ANTIEK_NOTDIAMOND"
ShadowStatus = Literal["pending", "ok", "failed", "timeout"]


class NDShadowJournalCorruptionError(RuntimeError):
    """The advisory journal contains an invalid durable row or sequence."""


@dataclass(frozen=True)
class NDShadowResponse:
    recommendation: str
    session_id: str
    latency_ms: int


class NDShadowClient(Protocol):
    def model_select(
        self,
        *,
        messages: Sequence[Mapping[str, str]],
        llm_providers: tuple[str, str],
        hash_content: bool,
        tradeoff: str,
    ) -> NDShadowResponse: ...


@dataclass(frozen=True)
class NDShadowConfig:
    enabled: bool
    week_id: str
    suite_version: str
    candidates: tuple[str, str]
    tradeoff: str = "quality"
    pending_ttl_ms: int = 300_000

    def __post_init__(self) -> None:
        if len(self.candidates) != 2 or len(set(self.candidates)) != 2:
            raise ValueError("NotDiamond shadow requires two distinct candidates")
        if not all(candidate.strip() for candidate in self.candidates):
            raise ValueError("NotDiamond shadow candidates must be non-empty")
        if not self.week_id.strip() or not self.suite_version.strip():
            raise ValueError("week_id and suite_version are required")
        if not self.tradeoff.strip():
            raise ValueError("tradeoff is required")
        if self.pending_ttl_ms <= 0:
            raise ValueError("pending_ttl_ms must be positive")


@dataclass(frozen=True)
class NDShadowRecord:
    shadow_id: str
    week_id: str
    suite_version: str
    item_id_hash: str
    task_class: str
    prompt_hash: str
    candidates: tuple[str, str]
    tradeoff: str
    status: ShadowStatus
    recommendation: str = ""
    session_id: str = ""
    latency_ms: int = 0
    failure_code: str = ""
    claimed_at_ms: int = 0
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NDShadowJournal:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _decode(raw: bytes) -> list[NDShadowRecord]:
        if not raw:
            return []
        lines = raw.splitlines(keepends=True)
        records: list[NDShadowRecord] = []
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                break
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    raise ValueError("shadow journal row must be an object")
                data["candidates"] = tuple(data["candidates"])
                record = NDShadowRecord(**data)
                NDShadowJournal._validate(record)
                records.append(record)
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise NDShadowJournalCorruptionError(
                    f"invalid shadow journal row {index + 1}"
                ) from exc
        return records

    @staticmethod
    def _validate(record: NDShadowRecord) -> None:
        if record.schema_version != 1:
            raise ValueError("unsupported shadow schema_version")
        if record.status not in {"pending", "ok", "failed", "timeout"}:
            raise ValueError("invalid shadow status")
        for name in (
            "shadow_id",
            "week_id",
            "suite_version",
            "item_id_hash",
            "task_class",
            "prompt_hash",
            "tradeoff",
        ):
            if not str(getattr(record, name)).strip():
                raise ValueError(f"{name} must not be blank")
        if not record.shadow_id.startswith("nds_"):
            raise ValueError("invalid shadow_id")
        if not record.item_id_hash.startswith("sha256:"):
            raise ValueError("invalid item_id_hash")
        if not record.prompt_hash.startswith("sha256:"):
            raise ValueError("invalid prompt_hash")
        if len(record.candidates) != 2 or len(set(record.candidates)) != 2:
            raise ValueError("shadow candidates must be two distinct values")
        if min(record.latency_ms, record.claimed_at_ms) < 0:
            raise ValueError("shadow timing values must be non-negative")

    @staticmethod
    def _identity(record: NDShadowRecord) -> tuple[Any, ...]:
        return (
            record.shadow_id,
            record.week_id,
            record.suite_version,
            record.item_id_hash,
            record.task_class,
            record.prompt_hash,
            record.candidates,
            record.tradeoff,
            record.schema_version,
        )

    @classmethod
    def _fold(cls, events: Sequence[NDShadowRecord]) -> dict[str, NDShadowRecord]:
        folded: dict[str, NDShadowRecord] = {}
        for record in events:
            current = folded.get(record.shadow_id)
            if current is None:
                if record.status != "pending":
                    raise NDShadowJournalCorruptionError(
                        f"terminal shadow without claim: {record.shadow_id}"
                    )
            elif current.status != "pending" or record.status == "pending":
                raise NDShadowJournalCorruptionError(
                    f"invalid shadow event sequence: {record.shadow_id}"
                )
            elif cls._identity(current) != cls._identity(record):
                raise NDShadowJournalCorruptionError(
                    f"shadow settlement identity mismatch: {record.shadow_id}"
                )
            folded[record.shadow_id] = record
        return folded

    @staticmethod
    def _read_fd(fd: int) -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    @classmethod
    def _repair_and_fold_locked(
        cls, fd: int
    ) -> dict[str, NDShadowRecord]:
        raw = cls._read_fd(fd)
        events = cls._decode(raw)
        if raw and not raw.endswith(b"\n"):
            os.ftruncate(fd, raw.rfind(b"\n") + 1)
            os.fsync(fd)
        return cls._fold(events)

    def _append_locked(self, fd: int, record: NDShadowRecord) -> None:
        self._validate(record)
        line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
        payload = memoryview((line + "\n").encode())
        written = 0
        while written < len(payload):
            count = os.write(fd, payload[written:])
            if count <= 0:
                raise OSError("shadow journal write made no progress")
            written += count
        os.fsync(fd)

    def claim(self, record: NDShadowRecord) -> bool:
        """Atomically claim one external recommendation before calling it."""
        if record.status != "pending":
            raise ValueError("claim requires pending status")
        fd = os.open(str(self.path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            existing = self._repair_and_fold_locked(fd)
            if record.shadow_id in existing:
                return False
            self._append_locked(fd, record)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def settle(self, record: NDShadowRecord) -> bool:
        if record.status == "pending":
            raise ValueError("settlement must be terminal")
        fd = os.open(str(self.path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            existing = self._repair_and_fold_locked(fd)
            current = existing.get(record.shadow_id)
            if current is None:
                raise ValueError("settlement requires exactly one pending claim")
            if current.status != "pending":
                return False
            if self._identity(current) != self._identity(record):
                raise ValueError("settlement identity does not match pending claim")
            self._append_locked(fd, record)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def list_records(self) -> list[NDShadowRecord]:
        try:
            fd = os.open(str(self.path), os.O_RDONLY)
        except FileNotFoundError:
            return []
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            return list(self._fold(self._decode(self._read_fd(fd))).values())
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def lookup(self, shadow_id: str) -> NDShadowRecord | None:
        return next(
            (record for record in self.list_records() if record.shadow_id == shadow_id),
            None,
        )


def _truthy(environ: Mapping[str, str]) -> bool:
    raw = (environ.get(ANTIEK_NOTDIAMOND_ENV) or "").strip().lower()
    return raw not in {"", "0", "false", "off", "no", "disabled"}


def _shadow_id(
    config: NDShadowConfig, item_id: str, task_class: str, prompt_hash: str
) -> str:
    material = json.dumps(
        [
            config.week_id,
            config.suite_version,
            config.candidates,
            config.tradeoff,
            item_id,
            task_class,
            prompt_hash,
        ],
        separators=(",", ":"),
    )
    return "nds_" + hashlib.sha256(material.encode()).hexdigest()


def _safe_session_id(value: str) -> str:
    return "session_sha256:" + hashlib.sha256(value.encode()).hexdigest()


def collect_nd_shadow(
    *,
    config: NDShadowConfig,
    items: Sequence[tuple[str, str, str]],
    client: NDShadowClient,
    journal: NDShadowJournal,
    environ: Mapping[str, str] | None = None,
    now_ms: int | None = None,
) -> tuple[NDShadowRecord, ...]:
    """Collect inert recommendations; failures never affect benchmark execution."""
    env = os.environ if environ is None else environ
    if not config.enabled or not _truthy(env):
        return ()
    records: list[NDShadowRecord] = []
    current_ms = int(time.time() * 1000) if now_ms is None else now_ms
    for item_id, task_class, prompt in items:
        prompt_hash = "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()
        item_id_hash = "sha256:" + hashlib.sha256(item_id.encode()).hexdigest()
        base: dict[str, Any] = {
            "shadow_id": _shadow_id(config, item_id, task_class, prompt_hash),
            "week_id": config.week_id,
            "suite_version": config.suite_version,
            "item_id_hash": item_id_hash,
            "task_class": task_class,
            "prompt_hash": prompt_hash,
            "candidates": config.candidates,
            "tradeoff": config.tradeoff,
        }
        pending = NDShadowRecord(**base, status="pending", claimed_at_ms=current_ms)
        if not journal.claim(pending):
            existing = journal.lookup(pending.shadow_id)
            if existing is not None:
                if (
                    existing.status == "pending"
                    and current_ms - existing.claimed_at_ms >= config.pending_ttl_ms
                ):
                    abandoned = NDShadowRecord(
                        **base,
                        status="failed",
                        failure_code="abandoned_shadow_claim",
                        claimed_at_ms=existing.claimed_at_ms,
                    )
                    journal.settle(abandoned)
                    existing = journal.lookup(pending.shadow_id) or abandoned
                records.append(existing)
            continue
        try:
            response = client.model_select(
                messages=({"role": "user", "content": prompt},),
                llm_providers=config.candidates,
                hash_content=True,
                tradeoff=config.tradeoff,
            )
            recommendation = response.recommendation.strip()
            status: ShadowStatus = "ok"
            failure_code = ""
            if recommendation not in config.candidates:
                recommendation = ""
                status = "failed"
                failure_code = "invalid_recommendation"
            record = NDShadowRecord(
                **base,
                status=status,
                recommendation=recommendation,
                session_id=_safe_session_id(response.session_id),
                latency_ms=max(0, response.latency_ms),
                failure_code=failure_code,
            )
        except TimeoutError:
            record = NDShadowRecord(
                **base, status="timeout", failure_code="notdiamond_timeout"
            )
        except Exception:
            record = NDShadowRecord(
                **base, status="failed", failure_code="notdiamond_failure"
            )
        if journal.settle(record):
            records.append(record)
        else:
            records.append(journal.lookup(record.shadow_id) or record)
    return tuple(records)
