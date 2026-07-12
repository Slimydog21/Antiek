"""Crash-recoverable idempotency receipts for confirmed session merges."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_RECEIPT_ID = re.compile(r"^mrcpt_[0-9a-f]{24}$")


def merge_material_sha256(material: dict[str, Any]) -> str:
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(b"antiek.session-merge.material.v1\0" + encoded).hexdigest()


def merge_receipt_id(owner_id: str, idempotency_key: str) -> str:
    encoded = f"antiek.session-merge.receipt.v1\0{owner_id}\0{idempotency_key}".encode()
    return f"mrcpt_{hashlib.sha256(encoded).hexdigest()[:24]}"


@runtime_checkable
class MergeReceiptStore(Protocol):
    def claim(self, receipt: dict[str, Any]) -> tuple[dict[str, Any], bool]: ...
    def prepare(
        self, receipt_id: str, material_sha256: str, result: dict[str, Any]
    ) -> dict[str, Any]: ...
    def settle(
        self, receipt_id: str, material_sha256: str, result_sha256: str
    ) -> dict[str, Any]: ...


def _validate_existing(
    existing: dict[str, Any], receipt_id: str, material_sha256: str
) -> None:
    if existing.get("receipt_id") != receipt_id:
        raise ValueError("merge receipt identity conflicts with storage key")
    if not hmac.compare_digest(
        str(existing.get("material_sha256") or ""), material_sha256
    ):
        raise ValueError("idempotency key was already used for different merge material")


def _prepared(
    existing: dict[str, Any], material_sha256: str, result: dict[str, Any]
) -> dict[str, Any]:
    receipt_id = str(existing["receipt_id"])
    _validate_existing(existing, receipt_id, material_sha256)
    result_sha = str(result.get("document_sha256") or "")
    if len(result_sha) != 64:
        raise ValueError("prepared merge result requires an exact document revision")
    if existing.get("state") in ("prepared", "applied"):
        prior = str(existing.get("result_sha256") or "")
        if not hmac.compare_digest(prior, result_sha):
            raise ValueError("prepared merge result conflicts with its receipt")
        return existing
    if existing.get("state") != "claimed":
        raise ValueError("merge receipt has an invalid state")
    return {
        **existing,
        "state": "prepared",
        "result_sha256": result_sha,
        "result": result,
    }


def _settled(
    existing: dict[str, Any], material_sha256: str, result_sha256: str
) -> dict[str, Any]:
    receipt_id = str(existing["receipt_id"])
    _validate_existing(existing, receipt_id, material_sha256)
    if existing.get("state") == "applied":
        if not hmac.compare_digest(
            str(existing.get("result_sha256") or ""), result_sha256
        ):
            raise ValueError("settled merge revision conflicts with its receipt")
        return existing
    if existing.get("state") != "prepared" or not hmac.compare_digest(
        str(existing.get("result_sha256") or ""), result_sha256
    ):
        raise ValueError("merge receipt must be prepared before settlement")
    return {**existing, "state": "applied"}


@dataclass
class InMemoryMergeReceiptStore:
    _rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def claim(self, receipt: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        receipt_id = str(receipt["receipt_id"])
        with self._lock:
            existing = self._rows.get(receipt_id)
            if existing is not None:
                _validate_existing(existing, receipt_id, str(receipt["material_sha256"]))
                return dict(existing), False
            self._rows[receipt_id] = dict(receipt)
            return dict(receipt), True

    def prepare(
        self, receipt_id: str, material_sha256: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            existing = self._rows.get(receipt_id)
            if existing is None:
                raise KeyError(receipt_id)
            updated = _prepared(existing, material_sha256, result)
            self._rows[receipt_id] = dict(updated)
            return dict(updated)

    def settle(
        self, receipt_id: str, material_sha256: str, result_sha256: str
    ) -> dict[str, Any]:
        with self._lock:
            existing = self._rows.get(receipt_id)
            if existing is None:
                raise KeyError(receipt_id)
            updated = _settled(existing, material_sha256, result_sha256)
            self._rows[receipt_id] = dict(updated)
            return dict(updated)


@dataclass
class FileMergeReceiptStore:
    root: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, receipt_id: str) -> Path:
        if _RECEIPT_ID.fullmatch(receipt_id) is None:
            raise ValueError("invalid merge receipt identity")
        return self.root / f"{receipt_id}.json"

    def _mutate(self, receipt_id: str, mutation: Any) -> tuple[dict[str, Any], bool]:
        path = self._path(receipt_id)
        lock_path = path.with_suffix(".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            existing = None
            if path.is_file():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    raise ValueError("durable merge receipt must be a JSON object")
            updated, created = mutation(existing)
            temp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                with temp.open("w", encoding="utf-8") as handle:
                    json.dump(updated, handle, sort_keys=True, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, path)
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                temp.unlink(missing_ok=True)
            return dict(updated), created

    def claim(self, receipt: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        receipt_id = str(receipt["receipt_id"])

        def mutate(existing: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
            if existing is not None:
                _validate_existing(existing, receipt_id, str(receipt["material_sha256"]))
                return existing, False
            return dict(receipt), True

        return self._mutate(receipt_id, mutate)

    def prepare(
        self, receipt_id: str, material_sha256: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        def mutate(existing: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
            if existing is None:
                raise KeyError(receipt_id)
            return _prepared(existing, material_sha256, result), False

        return self._mutate(receipt_id, mutate)[0]

    def settle(
        self, receipt_id: str, material_sha256: str, result_sha256: str
    ) -> dict[str, Any]:
        def mutate(existing: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
            if existing is None:
                raise KeyError(receipt_id)
            return _settled(existing, material_sha256, result_sha256), False

        return self._mutate(receipt_id, mutate)[0]
