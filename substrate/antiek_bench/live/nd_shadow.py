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
        records: list[NDShadowRecord] = []
        for line in raw.splitlines():
            data = json.loads(line)
            data["candidates"] = tuple(data["candidates"])
            records.append(NDShadowRecord(**data))
        return records

    def _append_locked(self, fd: int, record: NDShadowRecord) -> None:
        line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
        os.write(fd, (line + "\n").encode())
        os.fsync(fd)

    def claim(self, record: NDShadowRecord) -> bool:
        """Atomically claim one external recommendation before calling it."""
        if record.status != "pending":
            raise ValueError("claim requires pending status")
        fd = os.open(str(self.path), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.lseek(fd, 0, os.SEEK_SET)
            existing = self._decode(os.read(fd, os.fstat(fd).st_size))
            if any(row.shadow_id == record.shadow_id for row in existing):
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
            os.lseek(fd, 0, os.SEEK_SET)
            existing = self._decode(os.read(fd, os.fstat(fd).st_size))
            matching = [row for row in existing if row.shadow_id == record.shadow_id]
            if any(row.status != "pending" for row in matching):
                return False
            if len(matching) != 1:
                raise ValueError("settlement requires exactly one pending claim")
            self._append_locked(fd, record)
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def list_records(self) -> list[NDShadowRecord]:
        if not self.path.exists():
            return []
        folded: dict[str, NDShadowRecord] = {}
        for record in self._decode(self.path.read_bytes()):
            folded[record.shadow_id] = record
        return list(folded.values())

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
