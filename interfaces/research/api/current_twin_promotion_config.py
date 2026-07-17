"""Fail-closed production configuration for reviewed twin promotion reads."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from substrate.twin_recursion.evidence_promotion import TwinEvidencePromotionLedger
from substrate.twin_recursion.ledger import TwinRecursionLedger
from substrate.twin_recursion.read_routes import (
    CurrentTwinPromotionReadRegistry,
    QualifiedCurrentTwinPromotionRead,
)

from .current_twin_promotion_routes import CurrentTwinPromotionRouteRuntime

CONFIG_ENV = "ANTIEK_CURRENT_TWIN_PROMOTION_READ_CONFIG"
CONFIG_SCHEMA = "antiek.current-twin-promotion-read-config.v1"
_ROOT_FIELDS = frozenset({"schema", "owners"})
_OWNER_FIELDS = frozenset(
    {
        "owner_id",
        "graph_db_path",
        "promotion_ledger_path",
        "twin_ledger_path",
        "review_verify_key_hex",
    }
)
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_OWNERS = 64


class CurrentTwinPromotionConfigError(RuntimeError):
    """Configured read authority is incomplete or contradictory."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CurrentTwinPromotionConfigError("promotion read config has duplicate fields")
        result[key] = value
    return result


def _exact_fields(value: object, fields: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise CurrentTwinPromotionConfigError(f"promotion read {label} fields are invalid")
    return value


def _text(value: object, label: str, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise CurrentTwinPromotionConfigError(f"promotion read {label} is invalid")
    return value


def _private_manifest_payload(value: str) -> bytes:
    path = Path(value).expanduser()
    if not path.is_absolute() or str(path.resolve(strict=True)) != str(path):
        raise CurrentTwinPromotionConfigError("promotion read config path is not canonical")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
            or not 1 <= metadata.st_size <= _MAX_CONFIG_BYTES
        ):
            raise CurrentTwinPromotionConfigError("promotion read config file is not private")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                raise CurrentTwinPromotionConfigError("promotion read config read is incomplete")
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        if (
            (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino)
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
        ):
            raise CurrentTwinPromotionConfigError("promotion read config path changed")
        return payload
    finally:
        os.close(fd)


def current_twin_promotion_runtime_from_environment(
    values: Mapping[str, str] | None = None,
) -> CurrentTwinPromotionRouteRuntime | None:
    environment = os.environ if values is None else values
    configured = environment.get(CONFIG_ENV, "")
    if not configured:
        return None
    try:
        payload = _private_manifest_payload(_text(configured, "config path"))
        if not payload or len(payload) > _MAX_CONFIG_BYTES:
            raise CurrentTwinPromotionConfigError("promotion read config size is invalid")
        root = _exact_fields(json.loads(payload, object_pairs_hook=_object), _ROOT_FIELDS, "config")
        if root["schema"] != CONFIG_SCHEMA:
            raise CurrentTwinPromotionConfigError("promotion read config schema is invalid")
        owners = root["owners"]
        if type(owners) is not list or not 1 <= len(owners) <= _MAX_OWNERS:
            raise CurrentTwinPromotionConfigError("promotion read owner count is invalid")
        routes: list[QualifiedCurrentTwinPromotionRead] = []
        for raw_owner in owners:
            owner = _exact_fields(raw_owner, _OWNER_FIELDS, "owner")
            owner_id = _text(owner["owner_id"], "owner id", maximum=512)
            graph_path = _text(owner["graph_db_path"], "graph path")
            promotion_path = _text(owner["promotion_ledger_path"], "promotion path")
            twin_path = _text(owner["twin_ledger_path"], "twin path")
            key_hex = _text(owner["review_verify_key_hex"], "review key", maximum=64)
            if len(key_hex) != 64 or key_hex.lower() != key_hex:
                raise CurrentTwinPromotionConfigError("promotion read review key is invalid")
            try:
                review_key = bytes.fromhex(key_hex)
            except ValueError as exc:
                raise CurrentTwinPromotionConfigError(
                    "promotion read review key is invalid"
                ) from exc
            promotions = TwinEvidencePromotionLedger.open_read_only(
                promotion_path, owner_id=owner_id, review_verify_key=review_key
            )
            twins = TwinRecursionLedger.open_read_only(twin_path)
            routes.append(
                QualifiedCurrentTwinPromotionRead(owner_id, graph_path, promotions, twins)
            )
        return CurrentTwinPromotionRouteRuntime(CurrentTwinPromotionReadRegistry(tuple(routes)))
    except CurrentTwinPromotionConfigError:
        raise
    except Exception as exc:
        raise CurrentTwinPromotionConfigError(
            "configured current twin promotion authority is unavailable"
        ) from exc


__all__ = [
    "CONFIG_ENV",
    "CONFIG_SCHEMA",
    "CurrentTwinPromotionConfigError",
    "current_twin_promotion_runtime_from_environment",
]
