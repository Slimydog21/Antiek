"""Canonical, non-conferring Cycle-35 policy for the quarantined V4/V7 lane."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_checker_v2 import (
    PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    PRIVATE_OUTPUT_LEDGER_V2_SHA256,
    PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256,
)
from .private_output_compliance import (
    PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256,
    PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    PRIVATE_OUTPUT_THRESHOLD_SHA256,
)
from .private_output_policy_v3 import OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256
from .private_output_source_adapter_v1 import (
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256,
)

_POLICY_V4_DOMAIN = b"antiek.midnight-oil.owner-private-output-policy.v4\x00"
_CONTRACT_DOMAIN = b"antiek.midnight-oil.cycle-35-pure-contract.v1\x00"
_HEX64 = r"^[0-9a-f]{64}$"
_MAX_CANONICAL_DOCUMENT_BYTES = 10_500_000
_MAX_CANONICAL_DOCUMENT_NESTING = 32
_MAX_CANONICAL_CONTAINER_ITEMS = 100_000


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical_json(value)).hexdigest()


def parse_cycle_35_canonical_document(document: bytes) -> object:
    """Parse one exact canonical JSON document and reject duplicate/noncanonical input."""
    if (
        type(document) is not bytes
        or not document
        or len(document) > _MAX_CANONICAL_DOCUMENT_BYTES
    ):
        raise ValueError("Cycle 35 canonical document is unavailable")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        row: dict[str, object] = {}
        for key, value in pairs:
            if key in row:
                raise ValueError("duplicate key")
            row[key] = value
        return row

    try:
        value = json.loads(
            document.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("constant")),
        )
        pending: list[tuple[object, int]] = [(value, 1)]
        items = 0
        while pending:
            current, depth = pending.pop()
            if depth > _MAX_CANONICAL_DOCUMENT_NESTING:
                raise ValueError("nesting")
            if isinstance(current, dict):
                items += len(current)
                pending.extend((child, depth + 1) for child in current.values())
            elif isinstance(current, list):
                items += len(current)
                pending.extend((child, depth + 1) for child in current)
            if items > _MAX_CANONICAL_CONTAINER_ITEMS:
                raise ValueError("items")
        if _canonical_json(value) != document:
            raise ValueError("noncanonical")
        return value
    except (RecursionError, UnicodeError, ValueError, json.JSONDecodeError):
        raise ValueError("Cycle 35 canonical document is unavailable") from None


_CONTRACT_DOMAINS = MappingProxyType(
    {
        "capability_v4": "antiek.midnight-oil.private-provider-capability.v4\u0000",
        "capability_signature_v4": (
            "antiek.midnight-oil.private-provider-capability-signature.v4\u0000"
        ),
        "request_core_v4": "antiek.midnight-oil.owner-private-request-core.v4\u0000",
        "receipt_v7": (
            "antiek.midnight-oil.owner-private-publication-source-receipt.v7\u0000"
        ),
        "envelope_v4": "antiek.midnight-oil.owner-private-prepared-envelope.v4\u0000",
        "admission_candidate_v2": (
            "antiek.midnight-oil.private-paid-admission-candidate.v2\u0000"
        ),
        "attempt_claim_v1": "antiek.midnight-oil.private-paid-attempt-claim.v1\u0000",
        "test_transport_permit_v1": (
            "antiek.midnight-oil.private-paid-test-transport-permit.v1\u0000"
        ),
        "transport_outcome_v1": (
            "antiek.midnight-oil.private-paid-transport-outcome.v1\u0000"
        ),
        "test_transport_outcome_receipt_v1": (
            "antiek.midnight-oil.private-paid-test-transport-outcome-receipt.v1\u0000"
        ),
    }
)

_QUARANTINE_SCHEMA = (
    "synthetic_fixture_eligibility_only:Literal[True],required,default=True",
    "live_migration_verified:Literal[False],required,default=False",
    "user_accounting_effect:Literal[False],required,default=False",
    "transport_reachable:Literal[False],required,default=False",
    "confers_execution_authority:Literal[False],required,default=False",
    "confers_checkpoint_authority:Literal[False],required,default=False",
    "confers_sink_authority:Literal[False],required,default=False",
    "confers_transition_authority:Literal[False],required,default=False",
    "production_consumer_enabled:Literal[False],required,default=False",
)

_EXACT_SCHEMAS = MappingProxyType(
    {
        "capability_v4": {
            "fields": (
                "schema_version:Literal[4],required,default=4",
                "capability_id:str,required,pattern=^ppcap4_[0-9a-f]{24}$",
                "purpose:Literal[midnight_oil_owner_private_paid_research_v4],required",
                "owner_path_discriminator:str,required,pattern=^opspd1_[0-9a-f]{64}$",
                "provider_id:str,required,length=1..128",
                "model_id:str,required,length=1..256",
                "route_key:str,required,length=3..385,equals=provider_id/model_id",
                "api_mode:Literal[responses_no_store|messages_no_store],required",
                "processing_region:str,required,length=1..64",
                "output_schema:Literal[midnight-oil.gather-output/v1|midnight-oil.planner-output/v1|midnight-oil.synthesizer-output/v1|midnight-oil.verifier-output/v1],required",
                "router_role:Literal[gatherer|planner|synthesizer|verifier],required",
                "account_scope_blind_id:bytes,required,length=32,canonical=lowercase_hex",
                "project_scope_blind_id:bytes,required,length=32,canonical=lowercase_hex",
                "output_policy_v4_sha256:str,required,pattern=^[0-9a-f]{64}$",
                "cycle_35_contract_sha256:str,required,pattern=^[0-9a-f]{64}$",
                "revocation_registry_id:str,required,length=1..128",
                "revocation_trusted_floor_sha256:str,required,pattern=^[0-9a-f]{64}$",
                "approved_max_cents:int,required,range=1..1000000000,bool_rejected",
                "max_private_input_bytes:int,required,range=1..32000,bool_rejected",
                "max_output_bytes:int,required,range=1..1000000,bool_rejected",
                "issued_at_ms:int,required,range=0..2^63-1,bool_rejected",
                "not_before_ms:int,required,range=0..2^63-1,bool_rejected",
                "expires_at_ms:int,required,range=1..2^63-1,bool_rejected",
                "key_id:str,required,pattern=^[A-Za-z0-9._-]{1,128}$",
                "issuer_role:Literal[private_provider_capability_issuer],required",
                "key_purpose:Literal[owner_private_provider_capability_v4],required",
                "signature_scheme:Literal[ed25519],required",
                "capability_sha256:str,required,pattern=^[0-9a-f]{64}$",
                "signature_ed25519:str,required,pattern=^[0-9a-f]{128}$",
            ) + _QUARANTINE_SCHEMA,
            "validators": (
                "strict_frozen_extra_forbid_redacted_repr",
                "issued_at_ms<=not_before_ms<expires_at_ms",
                "output_schema_exact_for_router_role",
                "policy_and_cycle_contract_exact",
                "id=ppcap4_+digest[:24]",
                "hash_excludes=id,hash,signature",
                "signature=ed25519(domain+raw_digest_bytes)",
                "verify_failure=private_provider_capability_v4_unavailable",
            ),
        },
        "request_core_v4": {
            "fields": (
                "schema_version:Literal[4],required,default=4",
                "request_core_id:str,required,pattern=^oprc4_[0-9a-f]{24}$",
                "request_core_sha256:str,required,pattern=^[0-9a-f]{64}$",
                "owner_path_discriminator:str,required,pattern=^opspd1_[0-9a-f]{64}$",
                "operation_id:str,required,length=1..256",
                "job_id:str,required,length=1..256",
                "execution_id:str,required,length=1..256",
                "stage_key:str,required,pattern=^[0-9a-f]{64}$",
                "router_role:Literal[gatherer|planner|synthesizer|verifier],required",
                "output_schema:role_exact_literal,required",
                "capability_id:str,required,pattern=^ppcap4_[0-9a-f]{24}$",
                "capability_v4_sha256:str,required,hex64",
                "output_policy_v4_sha256:str,required,hex64",
                "cycle_35_contract_sha256:str,required,hex64",
                "provider_id:str,required,length=1..128",
                "model_id:str,required,length=1..256",
                "route_key:str,required,length=3..385",
                "api_mode:Literal[responses_no_store|messages_no_store],required",
                "processing_region:str,required,length=1..64",
                "account_scope_blind_id:bytes,required,length=32,canonical=lowercase_hex",
                "project_scope_blind_id:bytes,required,length=32,canonical=lowercase_hex",
                "provider_request_bytes:bytes,required,length=1..10000000,repr=False",
                "provider_request_sha256:str,required,hex64,recomputed",
                "provider_request_bytes_count:int,required,range=1..10000000",
                "private_input_commitment_sha256:str,required,hex64",
                "private_input_bytes:int,required,range=0..32000",
                "source_registry_id:str,required,length=1..128",
                "source_head_sha256:str,required,hex64",
                "source_epoch:int,required,range=0..2^63-1",
                "opaque_source_bundle_id:str,required,length=1..128",
                "source_row_version:Literal[1],required",
                "source_selector:str,required,length=1..256",
                "source_receipt_pairs:tuple[Cycle32Pair],required,length=0..8,repr=False",
                "required_until_ms:int,required,range=1..2^63-1",
                "projected_max_cents:int,required,range=1..1000000000",
                "max_output_bytes:int,required,range=1..1000000",
                "provider_scoped_idempotency_sha256:str,required,hex64",
            ) + _QUARANTINE_SCHEMA,
            "validators": (
                "strict_frozen_extra_forbid_redacted_repr",
                "planner_pairs=0;nonplanner_pairs=1..8_contiguous_unique",
                "route_scope_policy_limits_horizon_equal_or_narrower_than_capability",
                "request_digest_and_count_recomputed_from_exact_bytes",
                "private_input_commitment_recomputed_from_ordered_pairs",
                "id=oprc4_+digest[:24];hash_excludes=id,hash",
            ),
        },
        "receipt_v7": {
            "fields": (
                "schema_version:Literal[7],required,default=7",
                "authority_kind:Literal[owner_private_sealed_source_v7],required",
                "receipt_id:str,required,pattern=^opsr7_[0-9a-f]{24}$",
                "receipt_sha256:str,required,hex64",
                "owner_path_discriminator:str,required,pattern=^opspd1_[0-9a-f]{64}$",
                "operation_id|job_id|execution_id:str,required,length=1..256",
                "stage_key:str,required,hex64",
                "router_role:Literal[gatherer|synthesizer|verifier],required",
                "request_core_v4_sha256|output_policy_v4_sha256|capability_v4_sha256:str,required,hex64",
                "capability_id:str,required,pattern=^ppcap4_[0-9a-f]{24}$",
                "required_until_ms:int,required,range=1..2^63-1",
                "private_input_commitment_sha256:str,required,hex64",
                "private_input_bytes:int,required,range=1..32000",
                "private_source_ordinal:int,required,range=1..8",
                "source_receipt_id:str,required,pattern=^opsr5_[0-9a-f]{24}$",
                "source_receipt_sha256|source_head_sha256:str,required,hex64",
                "source_registry_id|opaque_source_bundle_id:str,required,length=1..128",
                "source_epoch:int,required,range=0..2^63-1",
                "source_row_version:Literal[1],required",
                "source_selector:str,required,length=1..256",
                "source_authority_kind:Literal[cycle32_receipt_pair_nonconferring_evidence],required",
                "source_authority_confers_sink_authority:Literal[False],required",
            ) + _QUARANTINE_SCHEMA,
            "validators": (
                "strict_frozen_extra_forbid_redacted_repr",
                "all_lineage_current_provenance_and_pair_equal_indexed_core_member",
                "planner_forbidden",
                "id=opsr7_+digest[:24];hash_excludes=id,hash",
            ),
        },
        "envelope_v4": {
            "fields": (
                "schema_version:Literal[4],required,default=4",
                "envelope_id:str,required,pattern=^openv4_[0-9a-f]{24}$",
                "envelope_sha256|request_core_v4_sha256|output_policy_v4_sha256|capability_v4_sha256:str,required,hex64",
                "request_core:PreparedOwnerPrivateRequestCoreV4,required,repr=False",
                "receipt_v7_roster:tuple[RosterMember],required,length=0..8,repr=False",
                "capability_id:str,required,pattern=^ppcap4_[0-9a-f]{24}$",
                "provider_id:str,required,length=1..128",
                "model_id:str,required,length=1..256",
                "route_key:str,required,length=3..385",
                "api_mode:Literal[responses_no_store|messages_no_store],required",
                "processing_region:str,required,length=1..64",
                "output_schema:role_exact_literal,required",
                "provider_request_sha256|provider_scoped_idempotency_sha256:str,required,hex64",
                "provider_request_bytes_count:int,required,range=1..10000000",
                "projected_max_cents:int,required,range=1..1000000000",
                "max_output_bytes:int,required,range=1..1000000",
            ) + _QUARANTINE_SCHEMA,
            "validators": (
                "strict_frozen_extra_forbid_redacted_repr",
                "nested_core_hash_recomputed",
                "planner_roster=0;nonplanner_roster=core_pairs_exact_count_order_unique",
                "every_roster_identity_recomputed_from_full_builder_receipts",
                "all_direct_route_request_limit_policy_capability_fields_equal_core",
                "id=openv4_+digest[:24];hash_excludes=id,hash",
            ),
        },
    }
)

_PURE_CONTRACTS = MappingProxyType(
    {
        "policy_v4": {
            "fields": (
                "schema_version:Literal[4]=4", "policy_id:Literal[antiek-owner-private-provider-output-v4]",
                "predecessor_kind:Literal[policy_v3_nonconferring_evidence]", "predecessor_policy_v3_sha256:hex64",
                "content_class:Literal[personal_reading]", "certified_operation:Literal[quarantined_cycle_35_fixture_eligibility_only]",
                "source_adapter_contract_sha256:hex64", "source_adapter_implementation_sha256:hex64",
                "source_adapter_source_set_sha256:hex64", "checker_v2_contract_sha256:hex64",
                "checker_v2_sha256:hex64", "checker_v2_corpus_sha256:hex64", "checker_v2_ledger_sha256:hex64",
                "checker_v2_module_sha256:hex64", "checker_v2_normalizer_sha256:hex64",
                "role_parser_sha256:hex64", "role_schema_sha256:hex64", "live_roles_code_sha256:hex64",
                "source_extractor_sha256:hex64", "threshold_sha256:hex64", "invocation_adapter_registry_sha256:hex64",
                "cycle_35_contract_sha256:hex64", "capability_v4_contract_sha256:hex64",
                "request_core_v4_contract_sha256:hex64", "receipt_v7_contract_sha256:hex64",
                "envelope_v4_contract_sha256:hex64", "checkpoint_v1_contract_sha256:hex64",
                "test_acceptor_v1_contract_sha256:hex64", "capability_v4_domain_sha256:hex64",
                "request_core_v4_domain_sha256:hex64", "receipt_v7_domain_sha256:hex64", "envelope_v4_domain_sha256:hex64",
                "encrypted_admission_candidate_required:Literal[True]", "test_acceptor_one_shot_required:Literal[True]",
                "unknown_is_absorbing:Literal[True]", "attempt_limit:Literal[1]",
                "admission_linearization:Literal[admission_commit]", "network_locking:Literal[forbidden]",
                "durable_attempt_state:Literal[attempt_started]", "durable_return_state:Literal[returned]",
                "authorized_sinks:tuple[()]=()", "unknown_sink:Literal[deny]",
                "declassification_authorized:Literal[False]", "public_serving_authorized:Literal[False]",
                "portable_export_authorized:Literal[False]", "training_authorized:Literal[False]",
            ) + _QUARANTINE_SCHEMA + (
                "policy_sha256:hex64",
            ),
            "identity_excludes": ("policy_sha256",),
            "builder": "zero_argument_exact_material",
        },
        "capability_v4": {
            "fields": (
                "schema_version", "capability_id", "purpose",
                "owner_path_discriminator", "provider_id", "model_id", "route_key",
                "api_mode", "processing_region", "output_schema", "router_role",
                "account_scope_blind_id", "project_scope_blind_id",
                "output_policy_v4_sha256", "cycle_35_contract_sha256",
                "revocation_registry_id", "revocation_trusted_floor_sha256",
                "approved_max_cents", "max_private_input_bytes", "max_output_bytes",
                "issued_at_ms", "not_before_ms", "expires_at_ms", "key_id",
                "issuer_role", "key_purpose", "signature_scheme",
                "capability_sha256", "signature_ed25519", "quarantine_literals",
            ),
            "bounds": {
                "approved_max_cents": (1, 1_000_000_000),
                "max_private_input_bytes": (1, 32_000),
                "max_output_bytes": (1, 1_000_000),
            },
            "time": "issued_at_ms<=not_before_ms<expires_at_ms",
            "blind_bytes_canonical_encoding": "lowercase_hex_32_bytes",
            "signature": "ed25519_raw_32_byte_digest_domain_separated",
            "identity_excludes": (
                "capability_id", "capability_sha256", "signature_ed25519"
            ),
            "closed_schema": _EXACT_SCHEMAS["capability_v4"],
        },
        "request_core_v4": {
            "fields": (
                "schema_version", "request_core_id", "request_core_sha256",
                "owner_path_discriminator", "operation_id", "job_id", "execution_id",
                "stage_key", "router_role", "output_schema", "capability_id",
                "capability_v4_sha256", "output_policy_v4_sha256",
                "cycle_35_contract_sha256", "provider_id", "model_id", "route_key",
                "api_mode", "processing_region", "account_scope_blind_id",
                "project_scope_blind_id", "provider_request_bytes",
                "provider_request_sha256", "provider_request_bytes_count",
                "private_input_commitment_sha256", "private_input_bytes",
                "source_registry_id", "source_head_sha256", "source_epoch",
                "opaque_source_bundle_id", "source_row_version", "source_selector",
                "source_receipt_pairs", "required_until_ms", "projected_max_cents",
                "max_output_bytes", "provider_scoped_idempotency_sha256",
                "quarantine_literals",
            ),
            "source_cardinality": "planner=0;other_roles=1..8_contiguous_unique",
            "request_hash": "sha256_exact_provider_request_bytes",
            "identity_excludes": ("request_core_id", "request_core_sha256"),
            "closed_schema": _EXACT_SCHEMAS["request_core_v4"],
        },
        "receipt_v7": {
            "fields": (
                "schema_version", "authority_kind", "receipt_id", "receipt_sha256",
                "owner_path_discriminator", "operation_id", "job_id", "execution_id",
                "stage_key", "router_role", "request_core_v4_sha256",
                "output_policy_v4_sha256", "capability_id", "capability_v4_sha256",
                "required_until_ms", "private_input_commitment_sha256",
                "private_input_bytes", "private_source_ordinal", "source_receipt_id",
                "source_receipt_sha256", "source_registry_id", "source_head_sha256",
                "source_epoch", "opaque_source_bundle_id", "source_row_version",
                "source_selector", "source_authority_kind", "quarantine_literals",
            ),
            "acyclicity": "core_binds_cycle32_pairs;receipt_binds_completed_core",
            "identity_excludes": ("receipt_id", "receipt_sha256"),
            "closed_schema": _EXACT_SCHEMAS["receipt_v7"],
        },
        "envelope_v4": {
            "fields": (
                "schema_version", "envelope_id", "envelope_sha256", "request_core",
                "request_core_v4_sha256", "receipt_v7_roster",
                "output_policy_v4_sha256", "capability_id", "capability_v4_sha256",
                "provider_id", "model_id", "route_key", "api_mode",
                "processing_region", "output_schema", "provider_request_sha256",
                "provider_request_bytes_count", "provider_scoped_idempotency_sha256",
                "projected_max_cents", "max_output_bytes", "quarantine_literals",
            ),
            "roster": "planner=0;other_roles=core_pairs_exact_order_and_count",
            "identity_excludes": ("envelope_id", "envelope_sha256"),
            "closed_schema": _EXACT_SCHEMAS["envelope_v4"],
        },
        "admission_candidate_v2": {
            "fields": (
                "schema_version:Literal[2]", "owner_path_discriminator:opspd1_hex64",
                "policy_v4:OwnerPrivateOutputPolicyV4", "capability_v4:PrivateProviderProcessingCapabilityV4",
                "core_v4:PreparedOwnerPrivateRequestCoreV4", "receipts_v7:tuple[ReceiptV7,0..8]",
                "envelope_v4:PreparedOwnerPrivateEnvelopeV4", "operation_id:str[1..256]",
                "operation_expected_state_version:int[1..2^63-1]", "consent_blind_id:bytes32",
                "consent_expected_version:int[1..2^63-1]", "lease_identity:owner+generation+cursor_blind_id",
                "composite_budget_identity:account_blind_id+project_blind_id+row_version",
                "projected_max_cents:int[1..1000000000]", "provider_request_bytes:bytes[1..10000000]",
                "provider_idempotency_material:bytes[1..4096]", "claim_expires_at_ms:int[1..2^63-1]",
                "candidate_sha256:hex64",
            ) + _QUARANTINE_SCHEMA,
            "validators": (
                "all_nested_exact_types_and_hashes_recomputed",
                "all_owner_route_scope_source_operation_consent_lease_budget_fields_equal",
                "claim_expiry=min_individually_frozen_validity_bounds;lease_half_open",
                "request_and_idempotency_material_match_core_envelope",
                "canonical_candidate_encrypted_by_store;plaintext_never_persisted",
            ),
        },
        "attempt_claim_v1": {
            "fields": (
                "schema_version:Literal[1]", "admission_id:str[1..128]", "effect_blind_id:bytes32",
                "expected_effect_state:Literal[admission_committed]", "expected_state_version:int[1..2^63-1]",
                "request_material_blind_id:bytes32", "provider_idempotency_blind_id:bytes32",
                "attempt_ordinal:Literal[1]",
            ),
            "validators": (
                "BEGIN_IMMEDIATE_CAS_with_exact_owner_operation_cancel_state",
                "commit_attempt_started_before_permit_mint",
                "open_to_unknown_budget_transition_atomic",
                "replay_exact_or_reject_divergence",
            ),
        },
        "test_transport_permit_v1": {
            "kind": "non_DTO_narrow_synthetic_test_transport_authority",
            "bindings": (
                "exact_store_object", "store_boot_nonce", "process_id", "permit_nonce",
                "admission_id", "effect_blind_id", "attempt_id", "attempt_ordinal=1",
                "request_and_idempotency_blind_ids", "exact_route", "exact_request_bytes",
            ),
            "states": ("issued", "consumed_pre_entry", "adapter_entered", "closed"),
            "guards": (
                "closed_constructor", "nonserializable", "noncopyable", "final", "immutable",
                "redacted_repr", "fork_rejected", "one_shot_registry_CAS",
            ),
        },
        "transport_outcome_v1": {
            "fields": (
                "schema_version:Literal[1],required,default=1",
                "admission_id:str,required,length=1..128",
                "effect_blind_id:bytes,required,length=32,canonical=lowercase_hex",
                "attempt_id:str,required,length=1..128", "attempt_ordinal:Literal[1],required",
                "expected_effect_state:Literal[attempt_started|returned],required",
                "expected_state_version:int,required,range=1..2^63-1,bool_rejected",
                "outcome_receipt:QuarantinedTestTransportOutcomeReceiptV1,required",
                "disposition:Literal[proven_no_network|returned|paid_unknown],required",
                "response_bytes:bytes|null,required,max_length=67108864,repr=False",
                "response_sha256:str|null,required,hex64_when_returned",
                "response_bytes_count:int|null,required,range=0..67108864_when_returned",
                "authenticated_charge_cents:int|null,required,range=0..1000000000",
                "occurred_at_ms:int,required,range=0..2^63-1,bool_rejected",
            ) + _QUARANTINE_SCHEMA,
            "validators": (
                "strict_frozen_extra_forbid_redacted_repr",
                "all_attempt_admission_effect_receipt_identities_exact",
                "receipt_disposition_response_charge_time_equal_command",
                "proven_no_network:response=null,charge=null,receipt_pre_entry",
                "returned:response_bytes+sha256+count_required_and_recomputed",
                "paid_unknown:response=null;charge_optional_authenticated_only",
                "BEGIN_IMMEDIATE_expected_state_version_CAS",
                "exact_replay_returns_original_transition;divergence_rejects",
                "paid_unknown_absorbing;no_retry_after_claim",
            ),
            "transition_matrix": {
                "attempt_started": {
                    "proven_no_network": "new_terminal_transition",
                    "returned": "new_transition_with_encrypted_response",
                    "paid_unknown": "new_absorbing_transition",
                },
                "returned": {
                    "returned": "exact_replay_only_no_new_transition",
                    "paid_unknown": "new_absorbing_transition",
                },
                "forbidden": (
                    "returned->proven_no_network",
                    "terminal->any_new_transition",
                    "any_state->returned_with_divergent_receipt_or_response",
                ),
            },
        },
        "test_transport_outcome_receipt_v1": {
            "fields": (
                "schema_version:Literal[1],required,default=1",
                "store_id:str,required,pattern=^pplacs1_[0-9a-f]{32}$",
                "boot_nonce:bytes,required,length=32,canonical=lowercase_hex",
                "permit_nonce:bytes,required,length=32,canonical=lowercase_hex",
                "admission_id:str,required,length=1..128", "effect_blind_id:bytes,required,length=32",
                "attempt_id:str,required,length=1..128", "attempt_ordinal:Literal[1],required",
                "request_material_blind_id:bytes,required,length=32",
                "provider_idempotency_blind_id:bytes,required,length=32",
                "adapter_entry_sequence:int,required,range=0..1",
                "disposition:Literal[proven_no_network|returned|paid_unknown],required",
                "response_sha256:str|null,required,hex64_when_returned",
                "response_length:int|null,required,range=0..67108864_when_returned",
                "charge_cents:int|null,required,range=0..1000000000",
                "occurred_at_ms:int,required,range=0..2^63-1",
                "mac_sha256:str,required,hex64",
            ),
            "issuer": "store_boot_memory_only_random_256_bit_HMAC_key",
            "mac_material": "canonical_all_fields_except_mac_sha256;domain_separated;bytes_lowercase_hex",
            "nullability": (
                "proven_no_network:entry_sequence=0,response=null,charge=null",
                "returned:entry_sequence=1,response_hash+length_required,charge_required",
                "paid_unknown:entry_sequence=0|1,response=null,charge=null|authenticated",
            ),
            "verification": "exact_live_store_boot_registry_state+constant_time_MAC+one_shot_unconsumed_to_consumed_CAS",
        },
        "checkpoint_v1": {
            "contract_sha256": (
                "482ab934c724f6f4cc5efa36dad75e89314f4c25a11f78cc17b3ddf90696e757"
            ),
            "semantic_sha256": (
                "a21550642f926069ab730e849fe0ac10718a114f0adb2242e9552a6c0124c7eb"
            ),
            "table_count": 18,
            "admission_transaction": "BEGIN IMMEDIATE",
            "authority_graph": (
                "provider_revocation", "source_current", "owner_operation_cancel",
                "consent", "queue_lease", "composite_budget", "logical_effect",
                "paid_admission", "budget_hold", "paid_attempt", "append_only_events",
            ),
            "transition_graph": (
                "admission_committed->cancellation_committed->cancelled_proven_not_dispatched",
                "admission_committed->attempt_started",
                "attempt_started->proven_no_network|returned|paid_unknown",
                "returned->settled|private_rejected_paid|paid_unknown",
                "terminal=cancelled_proven_not_dispatched|proven_no_network|settled|private_rejected_paid|paid_unknown",
            ),
            "budget": (
                "admit:open+=P", "cancel_before_claim:open-=P", "claim:open-=P;unknown+=P",
                "proven_no_network:unknown-=P", "settle:unknown-=P;confirmed+=A",
                "all_bucket_mutations_same_transaction_row_version_CAS_exact_replay",
            ),
            "trusted_time": "store_injected_contract_bound_monotonic;lease_now<exclusive_until",
            "failure": "indistinguishable_rejection;rollback_mints_no_authority",
        },
        "test_acceptor_v1": {
            "permit_states": ("issued", "consumed_pre_entry", "adapter_entered"),
            "permit": "process_boot_store_object_bound_nonserializable_one_shot",
            "receipt_mac": "hmac_sha256_memory_only_256_bit_store_boot_key",
            "outcomes": ("proven_no_network", "returned", "paid_unknown"),
            "no_retry_after_claim": True,
            "no_lock_across_adapter": True,
        },
        "canonical_helpers": {
            "json": "utf8_sorted_keys_compact_no_nan",
            "wire_parser": "parse_cycle_35_canonical_document_exact_reencoding",
            "models": "pydantic_strict_frozen_extra_forbid_redacted_repr",
            "max_document_bytes": _MAX_CANONICAL_DOCUMENT_BYTES,
            "max_nesting": _MAX_CANONICAL_DOCUMENT_NESTING,
            "max_container_items": _MAX_CANONICAL_CONTAINER_ITEMS,
        },
    }
)

_PURE_CONTRACT_SHA256S = MappingProxyType(
    {
        name: _digest(_CONTRACT_DOMAIN + name.encode("ascii") + b"\x00", material)
        for name, material in _PURE_CONTRACTS.items()
    }
)

PRIVATE_CYCLE_35_CONTRACT_SHA256 = _digest(
    _CONTRACT_DOMAIN,
    {
        "schema_version": 1,
        "canonical_json": "utf8_sorted_keys_compact_allow_nan_false",
        "domains": dict(_CONTRACT_DOMAINS),
        "contract_sha256s": dict(_PURE_CONTRACT_SHA256S),
        "durable_state_aliases": {
            "attempt_claimed": "attempt_started",
            "returned_pending_validation": "returned",
        },
        "attempt_limit": 1,
        "unknown_is_absorbing": True,
        "production_consumer_enabled": False,
    },
)

_POLICY_V4_MATERIAL = MappingProxyType({
    "schema_version": 4,
    "policy_id": "antiek-owner-private-provider-output-v4",
    "predecessor_kind": "policy_v3_nonconferring_evidence",
    "predecessor_policy_v3_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256,
    "content_class": "personal_reading",
    "certified_operation": "quarantined_cycle_35_fixture_eligibility_only",
    "source_adapter_contract_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
    "source_adapter_implementation_sha256": (
        PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256
    ),
    "source_adapter_source_set_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256,
    "checker_v2_contract_sha256": PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    "checker_v2_sha256": PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    "checker_v2_corpus_sha256": PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    "checker_v2_ledger_sha256": PRIVATE_OUTPUT_LEDGER_V2_SHA256,
    "checker_v2_module_sha256": PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256,
    "checker_v2_normalizer_sha256": PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    "role_parser_sha256": PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    "role_schema_sha256": PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    "live_roles_code_sha256": PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "threshold_sha256": PRIVATE_OUTPUT_THRESHOLD_SHA256,
    "invocation_adapter_registry_sha256": PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256,
    "cycle_35_contract_sha256": PRIVATE_CYCLE_35_CONTRACT_SHA256,
    "capability_v4_contract_sha256": _PURE_CONTRACT_SHA256S["capability_v4"],
    "request_core_v4_contract_sha256": _PURE_CONTRACT_SHA256S["request_core_v4"],
    "receipt_v7_contract_sha256": _PURE_CONTRACT_SHA256S["receipt_v7"],
    "envelope_v4_contract_sha256": _PURE_CONTRACT_SHA256S["envelope_v4"],
    "checkpoint_v1_contract_sha256": _PURE_CONTRACT_SHA256S["checkpoint_v1"],
    "test_acceptor_v1_contract_sha256": _PURE_CONTRACT_SHA256S["test_acceptor_v1"],
    "capability_v4_domain_sha256": hashlib.sha256(
        _CONTRACT_DOMAINS["capability_v4"].encode("utf-8")
    ).hexdigest(),
    "request_core_v4_domain_sha256": hashlib.sha256(
        _CONTRACT_DOMAINS["request_core_v4"].encode("utf-8")
    ).hexdigest(),
    "receipt_v7_domain_sha256": hashlib.sha256(
        _CONTRACT_DOMAINS["receipt_v7"].encode("utf-8")
    ).hexdigest(),
    "envelope_v4_domain_sha256": hashlib.sha256(
        _CONTRACT_DOMAINS["envelope_v4"].encode("utf-8")
    ).hexdigest(),
    "encrypted_admission_candidate_required": True,
    "test_acceptor_one_shot_required": True,
    "unknown_is_absorbing": True,
    "attempt_limit": 1,
    "admission_linearization": "admission_commit",
    "network_locking": "forbidden",
    "durable_attempt_state": "attempt_started",
    "durable_return_state": "returned",
    "authorized_sinks": (),
    "unknown_sink": "deny",
    "declassification_authorized": False,
    "public_serving_authorized": False,
    "portable_export_authorized": False,
    "training_authorized": False,
    "synthetic_fixture_eligibility_only": True,
    "live_migration_verified": False,
    "user_accounting_effect": False,
    "transport_reachable": False,
    "confers_execution_authority": False,
    "confers_checkpoint_authority": False,
    "confers_sink_authority": False,
    "confers_transition_authority": False,
    "production_consumer_enabled": False,
})


def _policy_v4_digest(value: object) -> str:
    material = dict(value) if isinstance(value, Mapping) else value
    return _digest(_POLICY_V4_DOMAIN, material)


OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256 = _policy_v4_digest(_POLICY_V4_MATERIAL)


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class OwnerPrivateOutputPolicyV4(_Closed):
    schema_version: Literal[4] = 4
    policy_id: Literal["antiek-owner-private-provider-output-v4"] = (
        "antiek-owner-private-provider-output-v4"
    )
    predecessor_kind: Literal["policy_v3_nonconferring_evidence"] = (
        "policy_v3_nonconferring_evidence"
    )
    predecessor_policy_v3_sha256: str = Field(pattern=_HEX64)
    content_class: Literal["personal_reading"] = "personal_reading"
    certified_operation: Literal[
        "quarantined_cycle_35_fixture_eligibility_only"
    ] = "quarantined_cycle_35_fixture_eligibility_only"
    source_adapter_contract_sha256: str = Field(pattern=_HEX64)
    source_adapter_implementation_sha256: str = Field(pattern=_HEX64)
    source_adapter_source_set_sha256: str = Field(pattern=_HEX64)
    checker_v2_contract_sha256: str = Field(pattern=_HEX64)
    checker_v2_sha256: str = Field(pattern=_HEX64)
    checker_v2_corpus_sha256: str = Field(pattern=_HEX64)
    checker_v2_ledger_sha256: str = Field(pattern=_HEX64)
    checker_v2_module_sha256: str = Field(pattern=_HEX64)
    checker_v2_normalizer_sha256: str = Field(pattern=_HEX64)
    role_parser_sha256: str = Field(pattern=_HEX64)
    role_schema_sha256: str = Field(pattern=_HEX64)
    live_roles_code_sha256: str = Field(pattern=_HEX64)
    source_extractor_sha256: str = Field(pattern=_HEX64)
    threshold_sha256: str = Field(pattern=_HEX64)
    invocation_adapter_registry_sha256: str = Field(pattern=_HEX64)
    cycle_35_contract_sha256: str = Field(pattern=_HEX64)
    capability_v4_contract_sha256: str = Field(pattern=_HEX64)
    request_core_v4_contract_sha256: str = Field(pattern=_HEX64)
    receipt_v7_contract_sha256: str = Field(pattern=_HEX64)
    envelope_v4_contract_sha256: str = Field(pattern=_HEX64)
    checkpoint_v1_contract_sha256: str = Field(pattern=_HEX64)
    test_acceptor_v1_contract_sha256: str = Field(pattern=_HEX64)
    capability_v4_domain_sha256: str = Field(pattern=_HEX64)
    request_core_v4_domain_sha256: str = Field(pattern=_HEX64)
    receipt_v7_domain_sha256: str = Field(pattern=_HEX64)
    envelope_v4_domain_sha256: str = Field(pattern=_HEX64)
    encrypted_admission_candidate_required: Literal[True] = True
    test_acceptor_one_shot_required: Literal[True] = True
    unknown_is_absorbing: Literal[True] = True
    attempt_limit: Literal[1] = 1
    admission_linearization: Literal["admission_commit"] = "admission_commit"
    network_locking: Literal["forbidden"] = "forbidden"
    durable_attempt_state: Literal["attempt_started"] = "attempt_started"
    durable_return_state: Literal["returned"] = "returned"
    authorized_sinks: tuple[()] = ()
    unknown_sink: Literal["deny"] = "deny"
    declassification_authorized: Literal[False] = False
    public_serving_authorized: Literal[False] = False
    portable_export_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    policy_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOutputPolicyV4:
        if (
            self.model_dump(mode="python", exclude={"policy_sha256"})
            != dict(_POLICY_V4_MATERIAL)
            or not hmac.compare_digest(
                owner_private_output_policy_v4_sha256(self), self.policy_sha256
            )
            or not hmac.compare_digest(
                self.policy_sha256, OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256
            )
        ):
            raise ValueError("owner-private output policy v4 conflicts")
        return self


def owner_private_output_policy_v4_sha256(
    policy: OwnerPrivateOutputPolicyV4 | Mapping[str, object],
) -> str:
    raw = policy.model_dump(mode="json") if isinstance(policy, BaseModel) else dict(policy)
    return _policy_v4_digest(
        {key: value for key, value in raw.items() if key != "policy_sha256"}
    )


def build_owner_private_output_policy_v4() -> OwnerPrivateOutputPolicyV4:
    return OwnerPrivateOutputPolicyV4.model_validate(
        {**_POLICY_V4_MATERIAL, "policy_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256}
    )


__all__ = [
    "OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256",
    "PRIVATE_CYCLE_35_CONTRACT_SHA256",
    "OwnerPrivateOutputPolicyV4",
    "build_owner_private_output_policy_v4",
    "owner_private_output_policy_v4_sha256",
    "parse_cycle_35_canonical_document",
]
