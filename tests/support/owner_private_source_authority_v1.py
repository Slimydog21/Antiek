"""Test-only keys and predecessor fixtures for encrypted source authority."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.parse
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from substrate.midnight_oil.private_source_authority import (
    OwnerPrivateEncryptedSourceBundleV1,
    OwnerPrivateExactSourceV1,
    SourceCreationAnchorV1,
    owner_private_encrypted_source_bundle_v1_sha256,
    source_creation_anchor_v1_sha256,
)
from tests.support.owner_private_v2 import OwnerPrivateV2Case, owner_private_v2_case

ANCHOR_KEY_ID = "test-source-anchor-v1"
HEAD_KEY_ID = "test-source-head-v1"
ANCHOR_PRIVATE_KEY = bytes(value ^ 0xA7 for value in range(32))
HEAD_PRIVATE_KEY = bytes(value ^ 0x5D for value in range(32))
DATA_KEY_V1 = bytes(value ^ 0xE3 for value in range(32))
DATA_KEY_V2 = bytes(value ^ 0x39 for value in range(32))
KEY_VERSION_V1 = "owner-private-source-key-v1"
KEY_VERSION_V2 = "owner-private-source-key-v2"
OWNER_PATH_DISCRIMINATOR = "opd_7e6df569a125c83933475df6"
SELECTOR_ONE = "opss_4f5a0266b16bb310b20865ce"
SELECTOR_TWO = "opss_19df71042c756d828eb9ab36"
PRIVATE_CANARY = "C31_PRIVATE_SOURCE_CANARY_37e5ad"
ANCHOR_SIGNATURE_DOMAIN = b"antiek.midnight-oil.owner-private-source-creation-signature.v1\x00"


def public_key(private_key: bytes) -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(private_key)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def sign_digest(domain: bytes, digest: str, *, private_key: bytes) -> str:
    """Sign one already-domain-separated production digest in test code only."""

    return (
        Ed25519PrivateKey.from_private_bytes(private_key)
        .sign(domain + digest.encode("ascii"))
        .hex()
    )


def encoded_private_needles(case: OwnerPrivateV2Case) -> frozenset[bytes]:
    """Raw and common reversible/content-derived encodings forbidden on disk."""

    private_values = {
        PRIVATE_CANARY,
        case.core.owner_scope_sha256,
        *(receipt.private_input_commitment_sha256 for receipt in case.receipts),
        case.core.request_core_sha256,
        case.envelope.envelope_sha256,
        *(receipt.receipt_id for receipt in case.receipts),
        *(receipt.receipt_sha256 for receipt in case.receipts),
        *(source.text for source in case.core.private_sources),
    }
    needles: set[bytes] = set()
    for value in private_values:
        raw = value.encode("utf-8")
        needles.update(
            {
                raw,
                raw.hex().encode("ascii"),
                base64.b64encode(raw),
                urllib.parse.quote(value, safe="").encode("ascii"),
                json.dumps(value, ensure_ascii=True)[1:-1].encode("utf-8"),
                hashlib.sha256(raw).hexdigest().encode("ascii"),
            }
        )
    return frozenset(needles)


@dataclass(frozen=True, slots=True)
class OwnerPrivateSourceAuthorityCase:
    predecessor: OwnerPrivateV2Case
    anchor_verification_keys: dict[str, bytes]
    head_verification_keys: dict[str, bytes]


def owner_private_source_authority_case() -> OwnerPrivateSourceAuthorityCase:
    return OwnerPrivateSourceAuthorityCase(
        predecessor=owner_private_v2_case(),
        anchor_verification_keys={ANCHOR_KEY_ID: public_key(ANCHOR_PRIVATE_KEY)},
        head_verification_keys={HEAD_KEY_ID: public_key(HEAD_PRIVATE_KEY)},
    )


def creation_anchor(
    case: OwnerPrivateV2Case,
    ordinal: int,
    *,
    issued_at_ms: int = 2_000,
    key_id: str = ANCHOR_KEY_ID,
    private_key: bytes = ANCHOR_PRIVATE_KEY,
) -> SourceCreationAnchorV1:
    receipt = case.receipts[ordinal - 1]
    raw = case.core.private_sources[ordinal - 1].text.encode("utf-8")
    material: dict[str, object] = {
        "schema_version": 1,
        "purpose": "owner_private_source_creation_anchor_v1",
        "envelope_v2_sha256": case.envelope.envelope_sha256,
        "request_core_v2_sha256": case.core.request_core_sha256,
        "source_receipt_v5": receipt.model_dump(mode="python"),
        "source_receipt_v5_sha256": receipt.receipt_sha256,
        "private_source_ordinal": ordinal,
        "exact_source_sha256": sha256_bytes(raw),
        "exact_source_bytes": len(raw),
        "issued_at_ms": issued_at_ms,
        "key_id": key_id,
        "issuer_role": "owner_private_source_creation_issuer",
        "key_purpose": "owner_private_source_creation_issuer_v1",
        "signature_scheme": "ed25519",
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    digest = source_creation_anchor_v1_sha256(material)
    return SourceCreationAnchorV1.model_validate(
        {
            **material,
            "anchor_id": "opsca1_" + digest[:24],
            "anchor_sha256": digest,
            "signature_ed25519": sign_digest(
                ANCHOR_SIGNATURE_DOMAIN, digest, private_key=private_key
            ),
        }
    )


def encrypted_source_bundle(
    case: OwnerPrivateV2Case | None = None,
    *,
    created_at_ms: int = 2_000,
) -> OwnerPrivateEncryptedSourceBundleV1:
    predecessor = case or owner_private_v2_case()
    sources = tuple(
        OwnerPrivateExactSourceV1(
            ordinal=source.ordinal,
            exact_source_sha256=sha256_bytes(source.text.encode("utf-8")),
            exact_source_bytes=len(source.text.encode("utf-8")),
        )
        for source in predecessor.core.private_sources
    )
    material: dict[str, object] = {
        "schema_version": 1,
        "envelope_v2": predecessor.envelope.model_dump(mode="python"),
        "request_core_v2": predecessor.core.model_dump(mode="python"),
        "receipt_v5_roster": tuple(
            receipt.model_dump(mode="python") for receipt in predecessor.receipts
        ),
        "exact_sources": tuple(source.model_dump(mode="python") for source in sources),
        "creation_anchors": tuple(
            creation_anchor(predecessor, ordinal).model_dump(mode="python")
            for ordinal in range(1, len(predecessor.receipts) + 1)
        ),
        "private_input_commitment_sha256": (
            predecessor.receipts[0].private_input_commitment_sha256
            if predecessor.receipts
            else None
        ),
        "private_input_bytes": (
            predecessor.receipts[0].private_input_bytes if predecessor.receipts else 0
        ),
        "created_at_ms": created_at_ms,
        "required_until_ms": predecessor.core.required_until_ms,
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    digest = owner_private_encrypted_source_bundle_v1_sha256(material)
    return OwnerPrivateEncryptedSourceBundleV1.model_validate(
        {**material, "bundle_id": "opsb1_" + digest[:24], "bundle_sha256": digest}
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "ANCHOR_KEY_ID",
    "ANCHOR_PRIVATE_KEY",
    "ANCHOR_SIGNATURE_DOMAIN",
    "DATA_KEY_V1",
    "DATA_KEY_V2",
    "HEAD_KEY_ID",
    "HEAD_PRIVATE_KEY",
    "KEY_VERSION_V1",
    "KEY_VERSION_V2",
    "OWNER_PATH_DISCRIMINATOR",
    "PRIVATE_CANARY",
    "SELECTOR_ONE",
    "SELECTOR_TWO",
    "OwnerPrivateSourceAuthorityCase",
    "encoded_private_needles",
    "creation_anchor",
    "encrypted_source_bundle",
    "owner_private_source_authority_case",
    "public_key",
    "sha256_bytes",
    "sign_digest",
]
