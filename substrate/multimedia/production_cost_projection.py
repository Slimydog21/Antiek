"""Immutable signed cost projection for the bytes in a registered video."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ship_cost_snapshot import MultimediaShipCostEvidenceUnavailable

_IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
)
_MAX_CENTS = (1 << 63) - 1


class _ProjectionModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ProductionByteConstituentV1(_ProjectionModel):
    role: Literal["visual", "narration"]
    scene_id: str | None = None
    chapter_id: str | None = None
    execution_revision: str
    execution_id: str
    authorization_id: str
    provider: str
    model: str
    capability: str
    charged_cents: int = Field(ge=0, le=_MAX_CENTS)
    settled_at: str

    @model_validator(mode="after")
    def role_has_one_source_identity(self) -> ProductionByteConstituentV1:
        if self.role == "visual":
            valid = self.scene_id is not None and self.chapter_id is None
        else:
            valid = self.chapter_id is not None and self.scene_id is None
        if not valid:
            raise ValueError("production constituent role identity conflicts")
        for name, value in (
            ("source_id", self.scene_id or self.chapter_id or ""),
            ("execution_revision", self.execution_revision),
            ("execution_id", self.execution_id),
            ("authorization_id", self.authorization_id),
            ("provider", self.provider),
            ("model", self.model),
            ("capability", self.capability),
        ):
            _identity(name, value)
        try:
            _timestamp(datetime.fromisoformat(self.settled_at.replace("Z", "+00:00")))
        except ValueError as exc:
            raise ValueError("production constituent settlement time is invalid") from exc
        return self


class ProductionByteProjectionV1(_ProjectionModel):
    schema_version: Literal["antiek.production-byte-projection.v1"] = (
        "antiek.production-byte-projection.v1"
    )
    evidence_id: str = Field(pattern=r"^mmprodbyte_[0-9a-f]{64}$")
    owner_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_id: str
    revision_id: str
    generated_at_cutoff: str
    basis: Literal["production_byte_contributing_settled_provider_executions"] = (
        "production_byte_contributing_settled_provider_executions"
    )
    production_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_set_id: str
    narration_run_id: str
    constituents: tuple[ProductionByteConstituentV1, ...]
    charged_cents: int = Field(ge=0, le=_MAX_CENTS)
    projection_mac: str = Field(pattern=r"^[0-9a-f]{64}$")


def verify_production_byte_projection(
    projection: ProductionByteProjectionV1,
    *,
    snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
) -> None:
    """Verify one immutable projection and its requested identity bindings."""
    _key(snapshot_key, "snapshot_key")
    owner = _owner_identity(owner_id)
    asset = _identity("asset_id", asset_id)
    revision = _identity("revision_id", revision_id)
    payload = projection.model_dump(mode="json", exclude={"projection_mac"})
    unsigned = dict(payload)
    unsigned.pop("evidence_id")
    expected_id = "mmprodbyte_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    expected_mac = hmac.new(snapshot_key, _canonical(payload), hashlib.sha256).hexdigest()
    ids = tuple(row.execution_id for row in projection.constituents)
    total = sum(row.charged_cents for row in projection.constituents)
    if (
        not ids
        or ids != tuple(sorted(ids))
        or len(ids) != len(set(ids))
        or total > _MAX_CENTS
        or projection.charged_cents != total
        or projection.owner_identity_digest != hashlib.sha256(owner.encode()).hexdigest()
        or projection.asset_id != asset
        or projection.revision_id != revision
        or any(
            (row.role == "narration" and row.capability != "text-to-speech")
            or (row.role == "visual" and row.capability == "text-to-speech")
            for row in projection.constituents
        )
        or not hmac.compare_digest(projection.evidence_id, expected_id)
        or not hmac.compare_digest(projection.projection_mac, expected_mac)
    ):
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    _timestamp(datetime.fromisoformat(projection.generated_at_cutoff.replace("Z", "+00:00")))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def _key(value: bytes, name: str) -> None:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError(f"{name} must contain at least 32 bytes")


def _identity(name: str, value: str, *, max_bytes: int = 128) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError(f"{name} is invalid")
    encoded = value.encode()
    if len(encoded) > max_bytes or any(char not in _IDENTIFIER_CHARS for char in value):
        raise ValueError(f"{name} is invalid")
    return value


def _owner_identity(value: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError("owner_id is invalid")
    encoded = value.encode()
    if len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise ValueError("owner_id is invalid")
    return value


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "ProductionByteConstituentV1",
    "ProductionByteProjectionV1",
    "verify_production_byte_projection",
]
