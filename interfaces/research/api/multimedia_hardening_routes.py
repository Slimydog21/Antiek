"""Runtime authority for multimedia hardening cost evidence."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from fastapi import HTTPException

from substrate.multimedia.local_zero_cost_evidence import LocalZeroExternalCostEvidenceV1
from substrate.multimedia.production_cost_projection import ProductionByteProjectionV1


class LocalZeroEvidenceBackend(Protocol):
    def __call__(
        self,
        *,
        owner_id: str,
        asset_id: str,
        revision_id: str,
        now: datetime,
    ) -> LocalZeroExternalCostEvidenceV1: ...


class ProductionByteEvidenceBackend(Protocol):
    def __call__(
        self,
        *,
        owner_id: str,
        asset_id: str,
        revision_id: str,
        now: datetime,
    ) -> ProductionByteProjectionV1: ...


@dataclass(frozen=True)
class MultimediaHardeningRuntime:
    db_path: str
    signing_key: bytes
    snapshot_key: bytes
    production_snapshot_key: bytes | None = None
    local_zero_snapshot_key: bytes | None = None
    production_video_backend: ProductionByteEvidenceBackend | None = None
    local_video_backend: LocalZeroEvidenceBackend | None = None
    local_audio_backend: LocalZeroEvidenceBackend | None = None
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
    production_hex = values.get(
        "ANTIEK_MULTIMEDIA_HARDENING_PRODUCTION_KEY_HEX", ""
    ).strip()
    local_zero_hex = values.get(
        "ANTIEK_MULTIMEDIA_HARDENING_LOCAL_ZERO_KEY_HEX", ""
    ).strip()
    if not any(
        (enabled, db_path, signing_hex, snapshot_hex, production_hex, local_zero_hex)
    ):
        return None
    if enabled not in {"1", "true"} or not all((db_path, signing_hex, snapshot_hex)):
        raise RuntimeError("multimedia hardening configuration is incomplete")
    try:
        signing_key = bytes.fromhex(signing_hex)
        snapshot_key = bytes.fromhex(snapshot_hex)
        production_key = bytes.fromhex(production_hex) if production_hex else None
        local_zero_key = bytes.fromhex(local_zero_hex) if local_zero_hex else None
    except ValueError as exc:
        raise RuntimeError("multimedia hardening keys must be hexadecimal") from exc
    if len(signing_key) < 32 or len(snapshot_key) < 32:
        raise RuntimeError("multimedia hardening keys must contain at least 32 bytes")
    if signing_key == snapshot_key:
        raise RuntimeError("multimedia hardening signing keys must be independent")
    optional_keys = tuple(
        key for key in (production_key, local_zero_key) if key is not None
    )
    if any(len(key) < 32 for key in optional_keys) or len(
        {signing_key, snapshot_key, *optional_keys}
    ) != 2 + len(optional_keys):
        raise RuntimeError("multimedia hardening signing keys must be independent")
    return MultimediaHardeningRuntime(
        db_path=db_path,
        signing_key=signing_key,
        snapshot_key=snapshot_key,
        production_snapshot_key=production_key,
        local_zero_snapshot_key=local_zero_key,
    )


__all__ = [
    "LocalZeroEvidenceBackend",
    "MultimediaHardeningRuntime",
    "ProductionByteEvidenceBackend",
    "get_multimedia_hardening_runtime",
    "multimedia_hardening_runtime_from_environment",
]
