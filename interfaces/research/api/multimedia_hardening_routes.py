"""Runtime authority for multimedia hardening cost evidence."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException


@dataclass(frozen=True)
class MultimediaHardeningRuntime:
    db_path: str
    signing_key: bytes
    snapshot_key: bytes
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)


def get_multimedia_hardening_runtime() -> MultimediaHardeningRuntime:
    raise HTTPException(status_code=503, detail="multimedia hardening runtime is unavailable")


def multimedia_hardening_runtime_from_environment(
    environ: Mapping[str, str] | None = None,
) -> MultimediaHardeningRuntime | None:
    values = os.environ if environ is None else environ
    enabled = values.get("ANTIEK_MULTIMEDIA_HARDENING_ENABLED", "").strip().lower()
    db_path = values.get("ANTIEK_MULTIMEDIA_HARDENING_DB_PATH", "").strip()
    signing_hex = values.get("ANTIEK_MULTIMEDIA_HARDENING_SIGNING_KEY_HEX", "").strip()
    snapshot_hex = values.get("ANTIEK_MULTIMEDIA_HARDENING_SNAPSHOT_KEY_HEX", "").strip()
    if not any((enabled, db_path, signing_hex, snapshot_hex)):
        return None
    if enabled not in {"1", "true"} or not all((db_path, signing_hex, snapshot_hex)):
        raise RuntimeError("multimedia hardening configuration is incomplete")
    try:
        signing_key = bytes.fromhex(signing_hex)
        snapshot_key = bytes.fromhex(snapshot_hex)
    except ValueError as exc:
        raise RuntimeError("multimedia hardening keys must be hexadecimal") from exc
    if len(signing_key) < 32 or len(snapshot_key) < 32:
        raise RuntimeError("multimedia hardening keys must contain at least 32 bytes")
    if signing_key == snapshot_key:
        raise RuntimeError("multimedia hardening signing keys must be independent")
    return MultimediaHardeningRuntime(
        db_path=db_path,
        signing_key=signing_key,
        snapshot_key=snapshot_key,
    )


__all__ = [
    "MultimediaHardeningRuntime",
    "get_multimedia_hardening_runtime",
    "multimedia_hardening_runtime_from_environment",
]
