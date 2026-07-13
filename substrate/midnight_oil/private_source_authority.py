"""Verifier-only contracts for quarantined owner-private source authority.

This module deliberately has no creation-anchor signer, storage implementation,
generic decrypt surface, provider integration, or production consumer.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_provider_dispatch import _private_input_commitment_from_members
from .private_provider_envelope_v2 import (
    PreparedOwnerPrivateEnvelopeV2,
    prepared_owner_private_envelope_v2_sha256,
)
from .private_provider_receipt_v5 import (
    OwnerPrivatePublicationSourceReceiptV5,
    owner_private_source_receipt_v5_sha256,
)
from .private_provider_request_core_v2 import (
    PreparedOwnerPrivateRequestCoreV2,
    owner_private_request_core_v2_sha256,
)

_SOURCE_CREATION_ANCHOR_DOMAIN = b"antiek.midnight-oil.owner-private-source-creation-anchor.v1\x00"
_SOURCE_CREATION_SIGNATURE_DOMAIN = (
    b"antiek.midnight-oil.owner-private-source-creation-signature.v1\x00"
)
_SEALED_SOURCE_RECORD_DOMAIN = b"antiek.midnight-oil.owner-private-sealed-source-record.v1\x00"
_SOURCE_AEAD_DOMAIN = b"antiek.midnight-oil.owner-private-source-aead.v1\x00"
_SOURCE_AUTHORITY_CONTRACT_DOMAIN = (
    b"antiek.midnight-oil.owner-private-source-authority-contract.v1\x00"
)
_MODULE_SOURCE_DOMAIN = b"antiek.midnight-oil.owner-private-source-authority-semantic-source.v1\x00"
_HEX64 = r"^[0-9a-f]{64}$"
_KEY_ID = r"^[A-Za-z0-9._-]{1,128}$"
_ANCHOR_ID = r"^opsca1_[0-9a-f]{24}$"
_BUNDLE_ID = r"^opsb1_[0-9a-f]{24}$"
_ROLES = ("gatherer", "planner", "synthesizer", "verifier")


def _wire_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _wire_value(value.model_dump(mode="python"))
    if isinstance(value, bytes):
        return {"$bytes_hex": value.hex()}
    if isinstance(value, Mapping):
        return {str(key): _wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_value(item) for item in value]
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _wire_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical_json(value)).hexdigest()


def _same(first: str, second: str) -> bool:
    return hmac.compare_digest(first, second)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class OwnerPrivateExactSourceV1(_Closed):
    ordinal: int = Field(ge=1, le=8)
    exact_source_sha256: str = Field(pattern=_HEX64)
    exact_source_bytes: int = Field(ge=1, le=32_000)
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class SourceCreationAnchorV1(_Closed):
    """Externally issued evidence; this module can only parse and verify it."""

    schema_version: Literal[1] = 1
    anchor_id: str = Field(pattern=_ANCHOR_ID)
    anchor_sha256: str = Field(pattern=_HEX64)
    purpose: Literal["owner_private_source_creation_anchor_v1"] = (
        "owner_private_source_creation_anchor_v1"
    )
    envelope_v2_sha256: str = Field(pattern=_HEX64)
    request_core_v2_sha256: str = Field(pattern=_HEX64)
    source_receipt_v5: OwnerPrivatePublicationSourceReceiptV5 = Field(repr=False)
    source_receipt_v5_sha256: str = Field(pattern=_HEX64)
    private_source_ordinal: int = Field(ge=1, le=8)
    exact_source_sha256: str = Field(pattern=_HEX64)
    exact_source_bytes: int = Field(ge=1, le=32_000)
    issued_at_ms: int = Field(ge=0)
    key_id: str = Field(pattern=_KEY_ID)
    issuer_role: Literal["owner_private_source_creation_issuer"] = (
        "owner_private_source_creation_issuer"
    )
    key_purpose: Literal["owner_private_source_creation_issuer_v1"] = (
        "owner_private_source_creation_issuer_v1"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> SourceCreationAnchorV1:
        receipt = self.source_receipt_v5
        digest = source_creation_anchor_v1_sha256(self)
        if (
            type(receipt) is not OwnerPrivatePublicationSourceReceiptV5
            or not _same(
                owner_private_source_receipt_v5_sha256(receipt),
                receipt.receipt_sha256,
            )
            or not _same(self.source_receipt_v5_sha256, receipt.receipt_sha256)
            or self.private_source_ordinal != receipt.private_source_ordinal
            or not _same(self.anchor_sha256, digest)
            or self.anchor_id != "opsca1_" + digest[:24]
        ):
            raise ValueError("owner-private source creation anchor conflicts")
        return self


def _anchor_material(
    anchor: SourceCreationAnchorV1 | Mapping[str, object],
) -> dict[str, object]:
    raw = anchor.model_dump(mode="python") if isinstance(anchor, BaseModel) else dict(anchor)
    return {
        key: value
        for key, value in raw.items()
        if key not in {"anchor_id", "anchor_sha256", "signature_ed25519"}
    }


def source_creation_anchor_v1_sha256(
    anchor: SourceCreationAnchorV1 | Mapping[str, object],
) -> str:
    return _digest(_SOURCE_CREATION_ANCHOR_DOMAIN, _anchor_material(anchor))


class SourceCreationAnchorV1Rejected(ValueError):
    def __init__(self) -> None:
        super().__init__("owner-private source creation anchor rejected")

    def __repr__(self) -> str:
        return "SourceCreationAnchorV1Rejected()"


def verify_source_creation_anchor_v1(
    anchor: SourceCreationAnchorV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    try:
        if type(anchor) is not SourceCreationAnchorV1:
            raise ValueError
        canonical = SourceCreationAnchorV1.model_validate(anchor.model_dump(mode="python"))
        if canonical != anchor:
            raise ValueError
        key = verification_keys.get(canonical.key_id)
        if type(key) is not bytes or len(key) != 32:
            raise ValueError
        digest = source_creation_anchor_v1_sha256(canonical)
        if not _same(digest, canonical.anchor_sha256):
            raise ValueError
        Ed25519PublicKey.from_public_bytes(key).verify(
            bytes.fromhex(canonical.signature_ed25519),
            _SOURCE_CREATION_SIGNATURE_DOMAIN + digest.encode("ascii"),
        )
    except Exception:
        raise SourceCreationAnchorV1Rejected() from None


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_source_creation_anchor_v1_json(value: bytes) -> SourceCreationAnchorV1:
    try:
        if type(value) is not bytes or not value or len(value) > 1_000_000:
            raise ValueError
        raw = json.loads(value.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
        return SourceCreationAnchorV1.model_validate(raw)
    except Exception:
        raise SourceCreationAnchorV1Rejected() from None


class OwnerPrivateEncryptedSourceBundleV1(_Closed):
    """Canonical plaintext that a future 31B store must seal as one record."""

    schema_version: Literal[1] = 1
    bundle_id: str = Field(pattern=_BUNDLE_ID)
    bundle_sha256: str = Field(pattern=_HEX64)
    envelope_v2: PreparedOwnerPrivateEnvelopeV2 = Field(repr=False)
    request_core_v2: PreparedOwnerPrivateRequestCoreV2 = Field(repr=False)
    receipt_v5_roster: tuple[OwnerPrivatePublicationSourceReceiptV5, ...] = Field(
        max_length=8, repr=False
    )
    exact_sources: tuple[OwnerPrivateExactSourceV1, ...] = Field(max_length=8, repr=False)
    creation_anchors: tuple[SourceCreationAnchorV1, ...] = Field(max_length=8, repr=False)
    private_input_commitment_sha256: str | None = Field(default=None, pattern=_HEX64)
    private_input_bytes: int = Field(ge=0, le=256_000)
    created_at_ms: int = Field(ge=0)
    required_until_ms: int = Field(ge=0)
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateEncryptedSourceBundleV1:
        envelope = self.envelope_v2
        core = self.request_core_v2
        receipts = self.receipt_v5_roster
        sources = self.exact_sources
        anchors = self.creation_anchors
        if (
            type(envelope) is not PreparedOwnerPrivateEnvelopeV2
            or type(core) is not PreparedOwnerPrivateRequestCoreV2
            or any(type(row) is not OwnerPrivatePublicationSourceReceiptV5 for row in receipts)
            or any(type(row) is not OwnerPrivateExactSourceV1 for row in sources)
            or any(type(row) is not SourceCreationAnchorV1 for row in anchors)
            or envelope.request_core != core
            or envelope.request_core_v2_sha256 != core.request_core_sha256
            or prepared_owner_private_envelope_v2_sha256(envelope) != envelope.envelope_sha256
            or owner_private_request_core_v2_sha256(core) != core.request_core_sha256
            or self.required_until_ms != core.required_until_ms
            or self.created_at_ms > self.required_until_ms
        ):
            raise ValueError("owner-private encrypted source bundle conflicts")
        roster = tuple(
            (member.ordinal, member.receipt_id, member.receipt_sha256)
            for member in envelope.receipt_v5_roster
        )
        supplied = tuple(
            (row.private_source_ordinal, row.receipt_id, row.receipt_sha256) for row in receipts
        )
        if roster != supplied:
            raise ValueError("owner-private encrypted source roster conflicts")
        if core.router_role == "planner":
            if (
                receipts
                or sources
                or anchors
                or core.private_sources
                or self.private_input_commitment_sha256 is not None
                or self.private_input_bytes != 0
            ):
                raise ValueError("owner-private encrypted planner bundle conflicts")
        else:
            expected_ordinals = tuple(range(1, len(receipts) + 1))
            if (
                core.router_role not in _ROLES
                or not receipts
                or len(receipts) != len(sources)
                or len(receipts) != len(anchors)
                or tuple(source.ordinal for source in sources) != expected_ordinals
                or tuple(source.ordinal for source in core.private_sources) != expected_ordinals
                or self.private_input_commitment_sha256 is None
            ):
                raise ValueError("owner-private encrypted source members conflict")
            members: list[tuple[str, str, bytes]] = []
            for receipt, exact, anchor, core_source in zip(
                receipts, sources, anchors, core.private_sources, strict=True
            ):
                raw = core_source.text.encode("utf-8")
                source_v4 = receipt.source_authority_v4
                if (
                    receipt.request_core_v2_sha256 != core.request_core_sha256
                    or receipt.owner_scope_sha256 != core.owner_scope_sha256
                    or receipt.operation_id != core.operation_id
                    or receipt.job_id != core.job_id
                    or receipt.execution_id != core.execution_id
                    or receipt.stage_key != core.stage_key
                    or receipt.router_role != core.router_role
                    or receipt.provider_capability_v2_sha256 != core.provider_capability_v2_sha256
                    or receipt.swarm_plan_sha256 != core.swarm_plan_sha256
                    or receipt.stage_plan_sha256 != core.stage_plan_sha256
                    or receipt.route_plan_sha256 != core.route_plan_sha256
                    or receipt.publication_manifest_sha256 != core.publication_manifest_sha256
                    or receipt.required_until_ms != core.required_until_ms
                    or receipt.output_policy_v2_sha256 != core.output_policy_v2_sha256
                    or receipt.checker_sha256 != core.checker_sha256
                    or receipt.source_extractor_sha256 != core.source_extractor_sha256
                    or receipt.source_evidence_v1_request_sha256
                    != core.route_source_evidence_v1_request_sha256
                    or source_v4.provider_request_sha256
                    != core.route_source_evidence_v1_request_sha256
                    or source_v4.owner_scope_sha256 != core.owner_scope_sha256
                    or source_v4.operation_id != core.operation_id
                    or source_v4.job_id != core.job_id
                    or source_v4.execution_id != core.execution_id
                    or source_v4.stage_key != core.stage_key
                    or source_v4.router_role != core.router_role
                    or source_v4.swarm_plan_sha256 != core.swarm_plan_sha256
                    or source_v4.stage_plan_sha256 != core.stage_plan_sha256
                    or source_v4.route_plan_sha256 != core.route_plan_sha256
                    or source_v4.publication_manifest_sha256 != core.publication_manifest_sha256
                    or source_v4.required_until_ms != core.required_until_ms
                    or source_v4.provider_id != core.provider_id
                    or source_v4.model_id != core.model_id
                    or source_v4.route_key != core.route_key
                    or source_v4.api_mode != core.api_mode
                    or source_v4.processing_region != core.processing_region
                    or source_v4.endpoint_origin_sha256 != core.endpoint_origin_sha256
                    or source_v4.account_project_scope_sha256 != core.account_project_scope_sha256
                    or source_v4.adapter_contract_sha256 != core.adapter_contract_sha256
                    or source_v4.dispatch_config_sha256 != core.dispatch_config_sha256
                    or core.max_output_bytes > source_v4.max_output_bytes
                    or source_v4.private_input_commitment_sha256
                    != receipt.private_input_commitment_sha256
                    or source_v4.private_input_bytes != receipt.private_input_bytes
                    or exact.ordinal != receipt.private_source_ordinal
                    or exact.exact_source_bytes != len(raw)
                    or not _same(exact.exact_source_sha256, hashlib.sha256(raw).hexdigest())
                    or source_v4.excerpt_bytes != len(raw)
                    or not _same(source_v4.excerpt_sha256, exact.exact_source_sha256)
                    or source_v4.source_byte_start < 0
                    or source_v4.source_byte_start >= source_v4.source_byte_end
                    or source_v4.source_byte_end > source_v4.source_representation_bytes
                    or source_v4.source_byte_end - source_v4.source_byte_start != len(raw)
                    or anchor.source_receipt_v5 != receipt
                    or not _same(anchor.source_receipt_v5_sha256, receipt.receipt_sha256)
                    or anchor.envelope_v2_sha256 != envelope.envelope_sha256
                    or anchor.request_core_v2_sha256 != core.request_core_sha256
                    or anchor.private_source_ordinal != receipt.private_source_ordinal
                    or anchor.issued_at_ms > self.created_at_ms
                    or anchor.exact_source_bytes != len(raw)
                    or not _same(anchor.exact_source_sha256, exact.exact_source_sha256)
                ):
                    raise ValueError("owner-private encrypted source binding conflicts")
                members.append((source_v4.ref_id, source_v4.source_receipt_id, raw))
            commitment, total = _private_input_commitment_from_members(tuple(members))
            if (
                not _same(self.private_input_commitment_sha256, commitment)
                or self.private_input_bytes != total
                or any(row.private_input_commitment_sha256 != commitment for row in receipts)
                or any(row.private_input_bytes != total for row in receipts)
            ):
                raise ValueError("owner-private encrypted source commitment conflicts")
        digest = owner_private_encrypted_source_bundle_v1_sha256(self)
        if not _same(self.bundle_sha256, digest) or self.bundle_id != ("opsb1_" + digest[:24]):
            raise ValueError("owner-private encrypted source bundle identity conflicts")
        return self


def owner_private_encrypted_source_bundle_v1_sha256(
    bundle: OwnerPrivateEncryptedSourceBundleV1 | Mapping[str, object],
) -> str:
    raw = bundle.model_dump(mode="python") if isinstance(bundle, BaseModel) else dict(bundle)
    material = {
        key: value for key, value in raw.items() if key not in {"bundle_id", "bundle_sha256"}
    }
    return _digest(_SEALED_SOURCE_RECORD_DOMAIN, material)


class OwnerPrivateSourceBundleV1Rejected(ValueError):
    def __init__(self) -> None:
        super().__init__("owner-private encrypted source bundle rejected")

    def __repr__(self) -> str:
        return "OwnerPrivateSourceBundleV1Rejected()"


def validate_owner_private_encrypted_source_bundle_v1(
    bundle: OwnerPrivateEncryptedSourceBundleV1,
    *,
    anchor_verification_keys: Mapping[str, bytes],
) -> None:
    try:
        if type(bundle) is not OwnerPrivateEncryptedSourceBundleV1:
            raise ValueError
        for anchor in bundle.creation_anchors:
            verify_source_creation_anchor_v1(anchor, verification_keys=anchor_verification_keys)
        OwnerPrivateEncryptedSourceBundleV1.model_validate(bundle.model_dump(mode="python"))
    except Exception:
        raise OwnerPrivateSourceBundleV1Rejected() from None


_SOURCE_AEAD_AAD_FIELDS = (
    "schema_version",
    "opaque_source_bundle_id",
    "owner_path_discriminator",
    "categorical_state",
    "aead_suite",
    "key_version",
    "nonce_length",
    "ciphertext_schema",
    "ciphertext_type",
    "ciphertext_length",
    "row_revision",
)
_SOURCE_VAULT_CONTRACT_MATERIAL = {
    "schema_version": 1,
    "contract_id": "antiek-owner-private-source-vault-v1",
    "aead_suite": "aes-256-gcm",
    "key_bytes": 32,
    "nonce_bytes": 12,
    "tag_bytes": 16,
    "nonce_source": "csprng",
    "nonce_uniqueness": "per_owner_path_and_key_version",
    "aad_domain": _SOURCE_AEAD_DOMAIN.decode("ascii"),
    "aad_fields": _SOURCE_AEAD_AAD_FIELDS,
    "first_writer_wins": True,
    "exact_replay": "return_original_randomized_ciphertext_without_rewrite",
    "pair_lookup": "opaque_selector_then_bounded_internal_exact_pair_comparison",
    "generic_decrypt": False,
    "confers_execution_authority": False,
    "confers_checkpoint_authority": False,
    "confers_sink_authority": False,
    "confers_transition_authority": False,
    "production_consumer_enabled": False,
}
OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256 = _digest(
    _SOURCE_AUTHORITY_CONTRACT_DOMAIN, _SOURCE_VAULT_CONTRACT_MATERIAL
)


class OwnerPrivateSourceVaultContractV1(_Closed):
    schema_version: Literal[1] = 1
    contract_id: Literal["antiek-owner-private-source-vault-v1"] = (
        "antiek-owner-private-source-vault-v1"
    )
    aead_suite: Literal["aes-256-gcm"] = "aes-256-gcm"
    key_bytes: Literal[32] = 32
    nonce_bytes: Literal[12] = 12
    tag_bytes: Literal[16] = 16
    nonce_source: Literal["csprng"] = "csprng"
    nonce_uniqueness: Literal["per_owner_path_and_key_version"] = "per_owner_path_and_key_version"
    aad_domain: Literal["antiek.midnight-oil.owner-private-source-aead.v1\x00"]
    aad_fields: tuple[str, ...]
    first_writer_wins: Literal[True] = True
    exact_replay: Literal["return_original_randomized_ciphertext_without_rewrite"]
    pair_lookup: Literal["opaque_selector_then_bounded_internal_exact_pair_comparison"]
    generic_decrypt: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    contract_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateSourceVaultContractV1:
        raw = self.model_dump(mode="python", exclude={"contract_sha256"})
        if (
            raw != _SOURCE_VAULT_CONTRACT_MATERIAL
            or self.contract_sha256 != OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256
        ):
            raise ValueError("owner-private source vault contract conflicts")
        return self


def build_owner_private_source_vault_contract_v1() -> OwnerPrivateSourceVaultContractV1:
    return OwnerPrivateSourceVaultContractV1.model_validate(
        {
            **_SOURCE_VAULT_CONTRACT_MATERIAL,
            "contract_sha256": OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256,
        }
    )


def private_source_authority_module_source_sha256() -> str:
    """Attest this module AST while excluding only its self identity literal."""
    source = Path(__file__).read_bytes()
    tree = ast.parse(source, filename=str(Path(__file__)))
    name = "PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256"
    assignments = 0
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
        ):
            value = statement.value
            if (
                not isinstance(value, ast.Constant)
                or type(value.value) is not str
                or len(value.value) != 64
                or any(character not in "0123456789abcdef" for character in value.value)
            ):
                raise RuntimeError("private source authority source identity conflicts")
            assignments += 1
            statement.value = ast.Constant(value="<self-semantic-module-source-sha256>")
    stores = sum(
        isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name
        for node in ast.walk(tree)
    )
    if assignments != 1 or stores != 1:
        raise RuntimeError("private source authority source assignment conflicts")
    material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode("utf-8")
    return hashlib.sha256(_MODULE_SOURCE_DOMAIN + material).hexdigest()


PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256 = (
    "c7ee39e5619e771b3351549aacffb1d71281d577f845ae6e5bed7008341884ae"
)


def require_private_source_authority_module_source() -> None:
    if (
        private_source_authority_module_source_sha256()
        != PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256
    ):
        raise RuntimeError("private source authority implementation conflicts")


__all__ = [
    "OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256",
    "PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256",
    "OwnerPrivateEncryptedSourceBundleV1",
    "OwnerPrivateExactSourceV1",
    "OwnerPrivateSourceBundleV1Rejected",
    "OwnerPrivateSourceVaultContractV1",
    "SourceCreationAnchorV1",
    "SourceCreationAnchorV1Rejected",
    "build_owner_private_source_vault_contract_v1",
    "owner_private_encrypted_source_bundle_v1_sha256",
    "parse_source_creation_anchor_v1_json",
    "private_source_authority_module_source_sha256",
    "require_private_source_authority_module_source",
    "source_creation_anchor_v1_sha256",
    "validate_owner_private_encrypted_source_bundle_v1",
    "verify_source_creation_anchor_v1",
]
