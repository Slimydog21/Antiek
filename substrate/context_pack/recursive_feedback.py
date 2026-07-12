"""Owner-isolated explicit outcome receipts for recursive prompt context."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .recursive_notes import MAX_ID_BYTES, account_scope_digest

RecursiveOutcome = Literal[
    "saved",
    "cited",
    "merged",
    "followed_up",
    "abandoned",
    "contradicted",
    "no_signal",
]
RecursiveTaskClass = Literal[
    "distill",
    "synthesize",
    "wrestle",
    "book_qa",
    "research_reasoning",
]
SignalSource = Literal["explicit_user"]

FEEDBACK_SCHEMA_VERSION = 1
FEEDBACK_POLICY_VERSION = "recursive-feedback-v1"
MAX_UNITS_PER_RECEIPT = 64
MAX_RECEIPTS_PER_OWNER_DAY = 100
MAX_OWNER_RECEIPTS = 10_000
_PROCESS_LOCK = threading.RLock()


def _bounded(value: str, field: str, limit: int = MAX_ID_BYTES) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned.encode("utf-8")) > limit:
        raise ValueError(f"{field} is invalid")
    return cleaned


def _digest(value: str, field: str) -> str:
    cleaned = value.strip().lower()
    if len(cleaned) != 64 or any(character not in "0123456789abcdef" for character in cleaned):
        raise ValueError(f"{field} is invalid")
    return cleaned


@dataclass(frozen=True)
class FeedbackUnitRef:
    unit_id: str
    text_digest: str

    def __post_init__(self) -> None:
        _bounded(self.unit_id, "unit_id")
        _digest(self.text_digest, "text_digest")


@dataclass(frozen=True)
class RecursiveOutcomeReceipt:
    receipt_id: str
    observation_id: str
    owner_scope_digest: str
    context_pack_event_id: str
    dispatch_event_id: str | None
    units: tuple[FeedbackUnitRef, ...]
    task_class: RecursiveTaskClass
    model_policy_id: str
    outcome: RecursiveOutcome
    signal_source: SignalSource
    observed_at_ms: int
    policy_version: str = FEEDBACK_POLICY_VERSION

    def __post_init__(self) -> None:
        _bounded(self.receipt_id, "receipt_id")
        _bounded(self.observation_id, "observation_id")
        _digest(self.owner_scope_digest, "owner_scope_digest")
        _bounded(self.context_pack_event_id, "context_pack_event_id")
        if self.dispatch_event_id is not None:
            _bounded(self.dispatch_event_id, "dispatch_event_id")
        if not 1 <= len(self.units) <= MAX_UNITS_PER_RECEIPT:
            raise ValueError("feedback receipt unit count is invalid")
        if self.task_class not in {
            "distill",
            "synthesize",
            "wrestle",
            "book_qa",
            "research_reasoning",
        }:
            raise ValueError("feedback task_class is invalid")
        _bounded(self.model_policy_id, "model_policy_id", 256)
        if self.outcome not in {
            "saved",
            "cited",
            "merged",
            "followed_up",
            "abandoned",
            "contradicted",
            "no_signal",
        }:
            raise ValueError("feedback outcome is invalid")
        if self.signal_source != "explicit_user":
            raise ValueError("only explicit user feedback is accepted")
        if self.observed_at_ms < 0:
            raise ValueError("observed_at_ms is invalid")
        if self.policy_version != FEEDBACK_POLICY_VERSION:
            raise ValueError("feedback policy version is invalid")


def build_outcome_receipt(
    *,
    owner_user_id: str,
    observation_id: str,
    context_pack_event_id: str,
    dispatch_event_id: str | None,
    units: Sequence[FeedbackUnitRef],
    task_class: RecursiveTaskClass,
    model_policy_id: str,
    outcome: RecursiveOutcome,
    observed_at_ms: int,
    signal_source: SignalSource = "explicit_user",
) -> RecursiveOutcomeReceipt:
    scope = account_scope_digest(owner_user_id)
    observation = _bounded(observation_id, "observation_id")
    context_event = _bounded(context_pack_event_id, "context_pack_event_id")
    material = json.dumps(
        {
            "scope": scope,
            "observation": observation,
            "context": context_event,
            "policy": FEEDBACK_POLICY_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    receipt_id = "recursive-feedback-" + hashlib.sha256(material.encode()).hexdigest()
    return RecursiveOutcomeReceipt(
        receipt_id=receipt_id,
        observation_id=observation,
        owner_scope_digest=scope,
        context_pack_event_id=context_event,
        dispatch_event_id=dispatch_event_id,
        units=tuple(units),
        task_class=task_class,
        model_policy_id=model_policy_id,
        outcome=outcome,
        signal_source=signal_source,
        observed_at_ms=observed_at_ms,
    )


class FileRecursiveFeedbackStore:
    """One opaque file per owner scope with cross-process serialized updates."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, owner_user_id: str) -> Path:
        return self.root / f"{account_scope_digest(owner_user_id)}.json"

    def _lock_path(self, owner_user_id: str) -> Path:
        return self.root / f"{account_scope_digest(owner_user_id)}.lock"

    def _read(self, owner_user_id: str) -> dict[str, Any]:
        path = self._path(owner_user_id)
        if not path.exists():
            return {
                "schema_version": FEEDBACK_SCHEMA_VERSION,
                "opted_out": False,
                "receipts": [],
            }
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("recursive feedback store is unreadable") from exc
        if not isinstance(value, dict) or value.get("schema_version") != FEEDBACK_SCHEMA_VERSION:
            raise RuntimeError("recursive feedback store schema is invalid")
        return value

    def _write(self, owner_user_id: str, value: dict[str, Any]) -> None:
        path = self._path(owner_user_id)
        temporary = path.with_suffix(f".tmp-{os.getpid()}-{threading.get_ident()}")
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        temporary.write_text(encoded, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    @contextmanager
    def _locked(self, owner_user_id: str) -> Iterator[None]:
        import fcntl

        with _PROCESS_LOCK, self._lock_path(owner_user_id).open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def append(
        self, owner_user_id: str, receipt: RecursiveOutcomeReceipt
    ) -> RecursiveOutcomeReceipt:
        expected_scope = account_scope_digest(owner_user_id)
        if receipt.owner_scope_digest != expected_scope:
            raise PermissionError("feedback receipt owner scope does not match")
        with self._locked(owner_user_id):
            state = self._read(owner_user_id)
            if state.get("opted_out") is True:
                raise PermissionError("recursive feedback is opted out")
            receipts = list(state.get("receipts") or [])
            known_digests: dict[str, str] = {}
            for raw in receipts:
                if not isinstance(raw, dict):
                    raise RuntimeError("recursive feedback receipt row is invalid")
                for unit in list(raw.get("units") or []):
                    if not isinstance(unit, dict):
                        raise RuntimeError("recursive feedback unit row is invalid")
                    known_digests[str(unit.get("unit_id") or "")] = str(
                        unit.get("text_digest") or ""
                    )
            if any(
                unit.unit_id in known_digests and known_digests[unit.unit_id] != unit.text_digest
                for unit in receipt.units
            ):
                raise ValueError("feedback unit digest conflicts with prior receipt")
            for raw in receipts:
                if raw.get("receipt_id") == receipt.receipt_id:
                    existing = _receipt_from_dict(raw)
                    if not _same_observation(existing, receipt):
                        raise ValueError("feedback observation conflicts with prior receipt")
                    return existing
                if raw.get("context_pack_event_id") == receipt.context_pack_event_id:
                    raise ValueError("feedback already recorded for context pack")
            day = receipt.observed_at_ms // 86_400_000
            daily = sum(
                1
                for raw in receipts
                if int(raw["observed_at_ms"] if raw.get("observed_at_ms") is not None else -1)
                // 86_400_000
                == day
            )
            if daily >= MAX_RECEIPTS_PER_OWNER_DAY:
                raise ValueError("recursive feedback daily rate limit reached")
            if len(receipts) >= MAX_OWNER_RECEIPTS:
                raise ValueError("recursive feedback retention limit reached")
            receipts.append(asdict(receipt))
            self._write(
                owner_user_id,
                {
                    "schema_version": FEEDBACK_SCHEMA_VERSION,
                    "opted_out": False,
                    "receipts": receipts,
                },
            )
            return receipt

    def list(self, owner_user_id: str) -> tuple[RecursiveOutcomeReceipt, ...]:
        with self._locked(owner_user_id):
            state = self._read(owner_user_id)
            if state.get("opted_out") is True:
                return ()
            return tuple(_receipt_from_dict(raw) for raw in list(state.get("receipts") or []))

    def delete_and_opt_out(self, owner_user_id: str) -> int:
        with self._locked(owner_user_id):
            state = self._read(owner_user_id)
            deleted = len(list(state.get("receipts") or []))
            self._write(
                owner_user_id,
                {
                    "schema_version": FEEDBACK_SCHEMA_VERSION,
                    "opted_out": True,
                    "receipts": [],
                },
            )
            return deleted


def _receipt_from_dict(raw: dict[str, Any]) -> RecursiveOutcomeReceipt:
    if not isinstance(raw, dict):
        raise RuntimeError("recursive feedback receipt row is invalid")
    return RecursiveOutcomeReceipt(
        receipt_id=str(raw.get("receipt_id") or ""),
        observation_id=str(raw.get("observation_id") or ""),
        owner_scope_digest=str(raw.get("owner_scope_digest") or ""),
        context_pack_event_id=str(raw.get("context_pack_event_id") or ""),
        dispatch_event_id=(str(raw["dispatch_event_id"]) if raw.get("dispatch_event_id") else None),
        units=tuple(
            FeedbackUnitRef(
                unit_id=str(unit.get("unit_id") or ""),
                text_digest=str(unit.get("text_digest") or ""),
            )
            for unit in list(raw.get("units") or [])
            if isinstance(unit, dict)
        ),
        task_class=str(raw.get("task_class") or ""),  # type: ignore[arg-type]
        model_policy_id=str(raw.get("model_policy_id") or ""),
        outcome=str(raw.get("outcome") or ""),  # type: ignore[arg-type]
        signal_source=str(raw.get("signal_source") or ""),  # type: ignore[arg-type]
        observed_at_ms=int(raw.get("observed_at_ms") or 0),
        policy_version=str(raw.get("policy_version") or ""),
    )


def _same_observation(left: RecursiveOutcomeReceipt, right: RecursiveOutcomeReceipt) -> bool:
    return (
        left.receipt_id == right.receipt_id
        and left.observation_id == right.observation_id
        and left.owner_scope_digest == right.owner_scope_digest
        and left.context_pack_event_id == right.context_pack_event_id
        and left.dispatch_event_id == right.dispatch_event_id
        and left.units == right.units
        and left.task_class == right.task_class
        and left.model_policy_id == right.model_policy_id
        and left.outcome == right.outcome
        and left.signal_source == right.signal_source
        and left.policy_version == right.policy_version
    )
