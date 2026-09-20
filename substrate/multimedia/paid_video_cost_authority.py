"""Compound cost authority for one current registered paid video."""

from __future__ import annotations

import hmac
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .production_cost_projection import (
    ProductionByteProjectionV1,
    verify_production_byte_projection,
)
from .ship_cost_snapshot import (
    MultimediaShipCostEvidenceConflict,
    MultimediaShipCostEvidenceUnavailable,
    MultimediaShipCostSnapshotV1,
    verify_multimedia_ship_cost_snapshot,
)


class PaidRegisteredVideoCostAuthorityV1(BaseModel):
    """Two signed cost views that must be interpreted as one paid family."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["antiek.paid-registered-video-cost-authority.v1"] = (
        "antiek.paid-registered-video-cost-authority.v1"
    )
    generated_at_cutoff: str
    direct_cost_snapshot: MultimediaShipCostSnapshotV1
    production_byte_projection: ProductionByteProjectionV1

    @model_validator(mode="after")
    def children_share_identity_and_cutoff(self) -> PaidRegisteredVideoCostAuthorityV1:
        direct = self.direct_cost_snapshot
        production = self.production_byte_projection
        if (
            self.generated_at_cutoff != direct.generated_at_cutoff
            or self.generated_at_cutoff != production.generated_at_cutoff
            or direct.owner_identity_digest != production.owner_identity_digest
            or direct.asset_id != production.asset_id
            or direct.revision_id != production.revision_id
        ):
            raise ValueError("paid registered-video authority children conflict")
        return self


def build_paid_registered_video_cost_authority(
    *,
    direct_cost_snapshot: MultimediaShipCostSnapshotV1,
    production_byte_projection: ProductionByteProjectionV1,
    direct_snapshot_key: bytes,
    production_snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    production_receipt_digest: str,
) -> PaidRegisteredVideoCostAuthorityV1:
    """Verify and compose the two independently signed paid authority children."""
    try:
        authority = PaidRegisteredVideoCostAuthorityV1(
            schema_version="antiek.paid-registered-video-cost-authority.v1",
            generated_at_cutoff=direct_cost_snapshot.generated_at_cutoff,
            direct_cost_snapshot=direct_cost_snapshot,
            production_byte_projection=production_byte_projection,
        )
    except ValueError as exc:
        raise MultimediaShipCostEvidenceConflict("evidence_conflict") from exc
    verify_paid_registered_video_cost_authority(
        authority,
        direct_snapshot_key=direct_snapshot_key,
        production_snapshot_key=production_snapshot_key,
        owner_id=owner_id,
        asset_id=asset_id,
        revision_id=revision_id,
        production_receipt_digest=production_receipt_digest,
    )
    return authority


def verify_paid_registered_video_cost_authority(
    authority: PaidRegisteredVideoCostAuthorityV1,
    *,
    direct_snapshot_key: bytes,
    production_snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    production_receipt_digest: str,
) -> None:
    """Verify both children, their signing domains, and the current receipt binding."""
    _key(direct_snapshot_key)
    _key(production_snapshot_key)
    if hmac.compare_digest(direct_snapshot_key, production_snapshot_key):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    try:
        verify_multimedia_ship_cost_snapshot(
            authority.direct_cost_snapshot,
            snapshot_key=direct_snapshot_key,
            owner_id=owner_id,
            asset_id=asset_id,
            revision_id=revision_id,
        )
        verify_production_byte_projection(
            authority.production_byte_projection,
            snapshot_key=production_snapshot_key,
            owner_id=owner_id,
            asset_id=asset_id,
            revision_id=revision_id,
        )
    except (TypeError, ValueError) as exc:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable") from exc
    if not hmac.compare_digest(
        authority.production_byte_projection.production_receipt_digest,
        production_receipt_digest,
    ):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")


def _key(value: bytes) -> None:
    if not isinstance(value, bytes) or len(value) < 32:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")


__all__ = [
    "PaidRegisteredVideoCostAuthorityV1",
    "build_paid_registered_video_cost_authority",
    "verify_paid_registered_video_cost_authority",
]
