"""Test-only issuers and fixtures for opaque owner-private source heads."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from substrate.midnight_oil.private_source_head_store import (
    ZERO_SHA256,
    OpaqueSourceBundleRevisionV1,
    OwnerPrivateSourceAuthorityHeadV1,
    OwnerPrivateSourceAuthoritySnapshotV1,
    owner_private_source_authority_head_v1_sha256,
    owner_private_source_authority_snapshot_v1_sha256,
)
from tests.support.owner_private_source_authority_v1 import (
    HEAD_KEY_ID,
    HEAD_PRIVATE_KEY,
    public_key,
    sign_digest,
)

HEAD_SIGNATURE_DOMAIN = b"antiek.midnight-oil.owner-private-source-authority-signature.v1\x00"
OWNER_PATH_DISCRIMINATOR = "opspd1_" + "17" * 32
OTHER_OWNER_PATH_DISCRIMINATOR = "opspd1_" + "29" * 32
REGISTRY_ID = "opsreg1_" + "3b" * 32
OTHER_REGISTRY_ID = "opsreg1_" + "4d" * 32
SELECTOR_ONE = "opsbs1_" + "51" * 32
SELECTOR_TWO = "opsbs1_" + "63" * 32
SELECTOR_THREE = "opsbs1_" + "75" * 32


def head_verification_keys() -> dict[str, bytes]:
    return {HEAD_KEY_ID: public_key(HEAD_PRIVATE_KEY)}


def bundle_revision(
    opaque_source_bundle_id: str,
    row_revision: Literal[1] = 1,
) -> OpaqueSourceBundleRevisionV1:
    return OpaqueSourceBundleRevisionV1(
        opaque_source_bundle_id=opaque_source_bundle_id,
        row_revision=row_revision,
    )


def signed_source_head(
    *,
    epoch: int,
    issued_at_ms: int,
    previous_head_sha256: str,
    active: Sequence[OpaqueSourceBundleRevisionV1] = (),
    tombstones: Sequence[str] = (),
    registry_id: str = REGISTRY_ID,
    owner_path_discriminator: str = OWNER_PATH_DISCRIMINATOR,
    key_id: str = HEAD_KEY_ID,
    private_key: bytes = HEAD_PRIVATE_KEY,
) -> OwnerPrivateSourceAuthorityHeadV1:
    active_rows = tuple(sorted(active, key=lambda row: row.opaque_source_bundle_id))
    snapshot_material: dict[str, object] = {
        "schema_version": 1,
        "registry_id": registry_id,
        "owner_path_discriminator": owner_path_discriminator,
        "epoch": epoch,
        "issued_at_ms": issued_at_ms,
        "active_bundle_revisions": tuple(row.model_dump(mode="python") for row in active_rows),
        "tombstoned_bundle_ids": tuple(sorted(tombstones)),
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    snapshot_digest = owner_private_source_authority_snapshot_v1_sha256(snapshot_material)
    snapshot = OwnerPrivateSourceAuthoritySnapshotV1.model_validate(
        {**snapshot_material, "snapshot_sha256": snapshot_digest}
    )
    head_material: dict[str, object] = {
        "schema_version": 1,
        "registry_id": registry_id,
        "owner_path_discriminator": owner_path_discriminator,
        "epoch": epoch,
        "issued_at_ms": issued_at_ms,
        "previous_head_sha256": previous_head_sha256,
        "snapshot": snapshot.model_dump(mode="python"),
        "key_id": key_id,
        "issuer_role": "owner_private_source_head_issuer",
        "key_purpose": "owner_private_source_head_issuer_v1",
        "signature_scheme": "ed25519",
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    head_digest = owner_private_source_authority_head_v1_sha256(head_material)
    return OwnerPrivateSourceAuthorityHeadV1.model_validate(
        {
            **head_material,
            "head_sha256": head_digest,
            "signature_ed25519": sign_digest(
                HEAD_SIGNATURE_DOMAIN, head_digest, private_key=private_key
            ),
        }
    )


def empty_floor(
    *,
    issued_at_ms: int = 1_000,
) -> OwnerPrivateSourceAuthorityHeadV1:
    return signed_source_head(
        epoch=0,
        issued_at_ms=issued_at_ms,
        previous_head_sha256=ZERO_SHA256,
    )


def successor(
    current: OwnerPrivateSourceAuthorityHeadV1,
    *,
    issued_at_ms: int | None = None,
    active: Sequence[OpaqueSourceBundleRevisionV1] | None = None,
    tombstones: Sequence[str] | None = None,
) -> OwnerPrivateSourceAuthorityHeadV1:
    return signed_source_head(
        epoch=current.epoch + 1,
        issued_at_ms=(current.issued_at_ms + 1 if issued_at_ms is None else issued_at_ms),
        previous_head_sha256=current.head_sha256,
        active=(current.snapshot.active_bundle_revisions if active is None else active),
        tombstones=(current.snapshot.tombstoned_bundle_ids if tombstones is None else tombstones),
        registry_id=current.registry_id,
        owner_path_discriminator=current.owner_path_discriminator,
    )


__all__ = [
    "HEAD_KEY_ID",
    "HEAD_PRIVATE_KEY",
    "HEAD_SIGNATURE_DOMAIN",
    "OTHER_OWNER_PATH_DISCRIMINATOR",
    "OTHER_REGISTRY_ID",
    "OWNER_PATH_DISCRIMINATOR",
    "REGISTRY_ID",
    "SELECTOR_ONE",
    "SELECTOR_THREE",
    "SELECTOR_TWO",
    "bundle_revision",
    "empty_floor",
    "head_verification_keys",
    "signed_source_head",
    "successor",
]
