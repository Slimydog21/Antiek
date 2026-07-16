"""Test-only builders and signing custody for the Cycle-35 V4/V7 chain."""

from __future__ import annotations

import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from substrate.midnight_oil.private_output_policy_v4 import (
    OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256,
    PRIVATE_CYCLE_35_CONTRACT_SHA256,
)
from substrate.midnight_oil.private_provider_capability_v4 import (
    _SIGNATURE_V4_DOMAIN,
    PrivateProviderProcessingCapabilityV4,
    private_provider_capability_v4_sha256,
)
from substrate.midnight_oil.private_provider_envelope_v4 import (
    PreparedOwnerPrivateEnvelopeV4,
    build_prepared_owner_private_envelope_v4,
)
from substrate.midnight_oil.private_provider_receipt_v7 import (
    OwnerPrivatePublicationSourceReceiptV7,
    build_owner_private_source_receipt_v7,
)
from substrate.midnight_oil.private_provider_request_core_v4 import (
    Cycle32SourceReceiptPairV1,
    PreparedOwnerPrivateRequestCoreV4,
    build_owner_private_request_core_v4,
)

V4_KEY_ID = "private-capability-v4-fixture-issuer"
V4_PRIVATE = bytes(value ^ 0xA7 for value in range(32))
OWNER_PATH_DISCRIMINATOR = "opspd1_" + "1" * 64
ACCOUNT_SCOPE_BLIND_ID = bytes(range(32))
PROJECT_SCOPE_BLIND_ID = bytes(reversed(range(32)))


def public_key(private_key: bytes = V4_PRIVATE) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private_key).public_key().public_bytes_raw()


def capability_v4(
    *,
    role: str = "gatherer",
    owner_path_discriminator: str = OWNER_PATH_DISCRIMINATOR,
    key_id: str = V4_KEY_ID,
    signing_key: bytes = V4_PRIVATE,
    issued_at_ms: int = 2_000,
    not_before_ms: int = 2_001,
    expires_at_ms: int = 90_000,
) -> PrivateProviderProcessingCapabilityV4:
    output_schemas = {
        "gatherer": "midnight-oil.gather-output/v1",
        "planner": "midnight-oil.planner-output/v1",
        "synthesizer": "midnight-oil.synthesizer-output/v1",
        "verifier": "midnight-oil.verifier-output/v1",
    }
    material: dict[str, object] = {
        "schema_version": 4,
        "purpose": "midnight_oil_owner_private_paid_research_v4",
        "owner_path_discriminator": owner_path_discriminator,
        "provider_id": "openai",
        "model_id": "gpt-5.6",
        "route_key": "openai/gpt-5.6",
        "api_mode": "responses_no_store",
        "processing_region": "us",
        "output_schema": output_schemas[role],
        "router_role": role,
        "account_scope_blind_id": ACCOUNT_SCOPE_BLIND_ID,
        "project_scope_blind_id": PROJECT_SCOPE_BLIND_ID,
        "output_policy_v4_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256,
        "cycle_35_contract_sha256": PRIVATE_CYCLE_35_CONTRACT_SHA256,
        "revocation_registry_id": "antiek-private-provider-revocations-v1",
        "revocation_trusted_floor_sha256": "f" * 64,
        "approved_max_cents": 2_500,
        "max_private_input_bytes": 32_000,
        "max_output_bytes": 1_000_000,
        "issued_at_ms": issued_at_ms,
        "not_before_ms": not_before_ms,
        "expires_at_ms": expires_at_ms,
        "key_id": key_id,
        "issuer_role": "private_provider_capability_issuer",
        "key_purpose": "owner_private_provider_capability_v4",
        "signature_scheme": "ed25519",
        "synthetic_fixture_eligibility_only": True,
        "live_migration_verified": False,
        "user_accounting_effect": False,
        "transport_reachable": False,
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    digest = private_provider_capability_v4_sha256(material)
    signature = Ed25519PrivateKey.from_private_bytes(signing_key).sign(
        _SIGNATURE_V4_DOMAIN + bytes.fromhex(digest)
    )
    return PrivateProviderProcessingCapabilityV4.model_validate(
        {
            **material,
            "capability_id": "ppcap4_" + digest[:24],
            "capability_sha256": digest,
            "signature_ed25519": signature.hex(),
        }
    )


def source_pair(ordinal: int = 1) -> Cycle32SourceReceiptPairV1:
    marker = f"cycle32-source-{ordinal}".encode("ascii")
    digest = hashlib.sha256(marker).hexdigest()
    return Cycle32SourceReceiptPairV1(
        ordinal=ordinal,
        receipt_id=f"opsr5_{digest[:24]}",
        receipt_sha256=digest,
        private_input_member_sha256=hashlib.sha256(b"private-input:" + marker).hexdigest(),
        private_input_member_bytes=128 * ordinal,
    )


def core_v4(
    *,
    role: str = "gatherer",
    pair_count: int | None = None,
    capability: PrivateProviderProcessingCapabilityV4 | None = None,
) -> PreparedOwnerPrivateRequestCoreV4:
    cap = capability or capability_v4(role=role)
    count = (0 if role == "planner" else 1) if pair_count is None else pair_count
    pairs = tuple(source_pair(ordinal) for ordinal in range(1, count + 1))
    request = {
        "question": "What follows from the sealed source evidence?",
        "role": role,
        "schema_version": 4,
        "source_count": count,
        "tools_enabled": False,
    }
    request_bytes = json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return build_owner_private_request_core_v4(
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
        operation_id="operation-v4-fixture",
        job_id="job-v4-fixture",
        execution_id="execution-v4-fixture",
        stage_key="2" * 64,
        provider_request_bytes=request_bytes,
        source_registry_id="owner-private-source-registry-v1",
        source_head_sha256="3" * 64,
        source_epoch=4,
        opaque_source_bundle_id="opaque-source-bundle-v4-fixture",
        source_selector="active-revision",
        source_receipt_pairs=pairs,
        required_until_ms=80_000,
        projected_max_cents=1_250,
        max_output_bytes=500_000,
    )


def receipt_v7(
    *,
    core: PreparedOwnerPrivateRequestCoreV4 | None = None,
    capability: PrivateProviderProcessingCapabilityV4 | None = None,
    ordinal: int = 1,
) -> OwnerPrivatePublicationSourceReceiptV7:
    cap = capability or capability_v4()
    request_core = core or core_v4(capability=cap)
    return build_owner_private_source_receipt_v7(
        core=request_core,
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
        private_source_ordinal=ordinal,
    )


def envelope_v4(
    *,
    core: PreparedOwnerPrivateRequestCoreV4 | None = None,
    capability: PrivateProviderProcessingCapabilityV4 | None = None,
) -> PreparedOwnerPrivateEnvelopeV4:
    cap = capability or capability_v4()
    request_core = core or core_v4(capability=cap)
    receipts = tuple(
        receipt_v7(core=request_core, capability=cap, ordinal=ordinal)
        for ordinal in range(1, len(request_core.source_receipt_pairs) + 1)
    )
    return build_prepared_owner_private_envelope_v4(
        request_core=request_core,
        receipts=receipts,
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
    )


__all__ = [
    "ACCOUNT_SCOPE_BLIND_ID",
    "OWNER_PATH_DISCRIMINATOR",
    "PROJECT_SCOPE_BLIND_ID",
    "V4_KEY_ID",
    "V4_PRIVATE",
    "capability_v4",
    "core_v4",
    "envelope_v4",
    "public_key",
    "receipt_v7",
    "source_pair",
]
