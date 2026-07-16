from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator, Mapping

import pytest
from pydantic import ValidationError

from substrate.midnight_oil.private_output_policy_v4 import (
    _CONTRACT_DOMAIN,
    _CONTRACT_DOMAINS,
    _POLICY_V4_DOMAIN,
    _POLICY_V4_MATERIAL,
    _PURE_CONTRACT_SHA256S,
    _PURE_CONTRACTS,
    OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256,
    OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256_V1,
    OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256_V2,
    PRIVATE_CYCLE_35_CONTRACT_SHA256,
    PRIVATE_CYCLE_35_CONTRACT_SHA256_V1,
    PRIVATE_CYCLE_35_CONTRACT_SHA256_V2,
    OwnerPrivateOutputPolicyV4,
    _digest,
    build_owner_private_output_policy_v4,
    owner_private_output_policy_v4_sha256,
    parse_cycle_35_canonical_document,
)
from substrate.midnight_oil.private_paid_lane_authority_checkpoint import (
    PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1,
    PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1,
)
from substrate.midnight_oil.private_provider_capability_v4 import (
    _CAPABILITY_V4_DOMAIN,
    _SIGNATURE_V4_DOMAIN,
    PrivateProviderProcessingCapabilityV4,
    parse_private_provider_capability_v4_document,
    private_provider_capability_v4_sha256,
    verify_private_provider_capability_v4,
)
from substrate.midnight_oil.private_provider_receipt_v7 import (
    _RECEIPT_V7_DOMAIN,
    OwnerPrivatePublicationSourceReceiptV7,
    build_owner_private_source_receipt_v7,
    owner_private_source_receipt_v7_sha256,
    verify_owner_private_source_receipt_v7,
)
from substrate.midnight_oil.private_provider_request_core_v4 import (
    _IDEMPOTENCY_V4_DOMAIN,
    _PRIVATE_INPUT_COMMITMENT_V4_DOMAIN,
    _REQUEST_CORE_V4_DOMAIN,
    Cycle32SourceReceiptPairV1,
    PreparedOwnerPrivateRequestCoreV4,
    build_owner_private_request_core_v4,
    owner_private_request_core_v4_sha256,
    private_input_commitment_v4_sha256,
    provider_scoped_idempotency_v4_sha256,
    verify_owner_private_request_core_v4,
)
from tests.support.owner_private_v4 import (
    V4_KEY_ID,
    V4_PRIVATE,
    capability_v4,
    core_v4,
    public_key,
    receipt_v7,
    source_pair,
)


def _capability_v4_document(
    capability: PrivateProviderProcessingCapabilityV4,
) -> bytes:
    raw = capability.model_dump(mode="python")
    raw["account_scope_blind_id"] = capability.account_scope_blind_id.hex()
    raw["project_scope_blind_id"] = capability.project_scope_blind_id.hex()
    return json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def test_policy_v4_canonical_identity_domains_and_quarantine() -> None:
    policy = build_owner_private_output_policy_v4()
    assert OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256 == (
        "cab91cbdea5fc07f130945da5dc5569aade7e10ae425ba71df02383fa0e77a8f"
    )
    assert PRIVATE_CYCLE_35_CONTRACT_SHA256 == (
        "ceaa329b59dc70304f904b42cf756e334da35475a611ab5d0ba74f0fd179a63d"
    )
    assert _POLICY_V4_DOMAIN == b"antiek.midnight-oil.owner-private-output-policy.v4\x00"
    assert tuple(_CONTRACT_DOMAINS) == (
        "capability_v4",
        "capability_signature_v4",
        "request_core_v4",
        "receipt_v7",
        "envelope_v4",
        "admission_candidate_v2",
        "attempt_claim_v1",
        "test_transport_permit_v1",
        "transport_outcome_v1",
        "test_transport_outcome_receipt_v1",
    )
    assert policy.policy_sha256 == OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256
    assert policy.contract_revision == 3
    assert policy.predecessor_policy_v4_sha256 == OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256_V2
    assert OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256_V1 == (
        "7d4551f30ec2a25c60ad114a9cfa67df6ae279de5dab2559e83a7bcea080e339"
    )
    assert PRIVATE_CYCLE_35_CONTRACT_SHA256_V1 == (
        "09885cb78fdc7f54198c90240c61c7901a2f7e87c590a12543f2bf827b344711"
    )
    assert OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256_V2 == (
        "c0a87c11c60ffce36364f6d9a665052396e7a2ff80830a836f3bf680e7677a73"
    )
    assert PRIVATE_CYCLE_35_CONTRACT_SHA256_V2 == (
        "eb013373d470199e2850e2608eac3f67bdf5ecb138193afb80f2fd05921bc47f"
    )
    assert policy.policy_sha256 == owner_private_output_policy_v4_sha256(policy)
    assert policy.cycle_35_contract_sha256 == PRIVATE_CYCLE_35_CONTRACT_SHA256
    assert policy.attempt_limit == 1
    assert policy.unknown_is_absorbing is True
    assert policy.authorized_sinks == ()
    assert "redacted=True" in repr(policy)
    for field in (
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(policy, field) is False


@pytest.mark.parametrize(
    "field",
    (
        "predecessor_policy_v3_sha256",
        "predecessor_policy_v4_sha256",
        "source_adapter_contract_sha256",
        "source_adapter_implementation_sha256",
        "source_adapter_source_set_sha256",
        "checker_v2_contract_sha256",
        "checker_v2_sha256",
        "checker_v2_corpus_sha256",
        "checker_v2_ledger_sha256",
        "checker_v2_module_sha256",
        "checker_v2_normalizer_sha256",
        "role_parser_sha256",
        "role_schema_sha256",
        "live_roles_code_sha256",
        "source_extractor_sha256",
        "threshold_sha256",
        "invocation_adapter_registry_sha256",
        "cycle_35_contract_sha256",
        "capability_v4_contract_sha256",
        "request_core_v4_contract_sha256",
        "receipt_v7_contract_sha256",
        "envelope_v4_contract_sha256",
        "checkpoint_v1_contract_sha256",
        "test_acceptor_v1_contract_sha256",
        "capability_v4_domain_sha256",
        "request_core_v4_domain_sha256",
        "receipt_v7_domain_sha256",
        "envelope_v4_domain_sha256",
        "policy_sha256",
    ),
)
def test_policy_v4_identity_substitution_rejects(field: str) -> None:
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw[field] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivateOutputPolicyV4.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    (
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
        "declassification_authorized",
        "public_serving_authorized",
        "portable_export_authorized",
        "training_authorized",
    ),
)
def test_policy_v4_authority_substitution_rejects(field: str) -> None:
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw[field] = True
    with pytest.raises(ValidationError):
        OwnerPrivateOutputPolicyV4.model_validate(raw)


def test_policy_v4_extra_and_predecessor_promotion_reject() -> None:
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw["provider_execution_authorized"] = True
    with pytest.raises(ValidationError):
        OwnerPrivateOutputPolicyV4.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("synthetic_fixture_eligibility_only", False),
        ("contract_revision", 1),
        ("encrypted_admission_candidate_required", False),
        ("test_acceptor_one_shot_required", False),
        ("unknown_is_absorbing", False),
        ("attempt_limit", 2),
        ("authorized_sinks", ("provider",)),
        ("unknown_sink", "allow"),
        ("admission_linearization", "last_reread"),
        ("network_locking", "allowed"),
        ("durable_attempt_state", "attempt_claimed"),
        ("durable_return_state", "returned_pending_validation"),
    ),
)
def test_policy_v4_positive_contract_mutations_reject(field: str, value: object) -> None:
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw[field] = value
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivateOutputPolicyV4.model_validate(raw)


def test_cycle_35_manifest_mutation_propagates_to_root_and_policy_identity() -> None:
    changed = copy.deepcopy(dict(_PURE_CONTRACTS))
    capability = dict(changed["capability_v4"])
    schema = copy.deepcopy(capability["closed_schema"])
    schema["fields"] = (*schema["fields"], "forged_optional_authority:bool=False")
    capability["closed_schema"] = schema
    changed["capability_v4"] = capability
    changed_subhash = _digest(
        _CONTRACT_DOMAIN + b"capability_v4\x00", changed["capability_v4"]
    )
    assert changed_subhash != _PURE_CONTRACT_SHA256S["capability_v4"]
    changed_hashes = dict(_PURE_CONTRACT_SHA256S)
    changed_hashes["capability_v4"] = changed_subhash
    root_material = {
        "schema_version": 3,
        "predecessor_contract_sha256": PRIVATE_CYCLE_35_CONTRACT_SHA256_V2,
        "canonical_json": "utf8_sorted_keys_compact_allow_nan_false",
        "domains": dict(_CONTRACT_DOMAINS),
        "contract_sha256s": changed_hashes,
        "durable_state_aliases": {
            "attempt_claimed": "attempt_started",
            "returned_pending_validation": "returned",
        },
        "attempt_limit": 1,
        "unknown_is_absorbing": True,
        "production_consumer_enabled": False,
    }
    changed_root = _digest(_CONTRACT_DOMAIN, root_material)
    assert changed_root != PRIVATE_CYCLE_35_CONTRACT_SHA256
    changed_policy = dict(_POLICY_V4_MATERIAL)
    changed_policy["cycle_35_contract_sha256"] = changed_root
    changed_policy["capability_v4_contract_sha256"] = changed_subhash
    assert _digest(_POLICY_V4_DOMAIN, changed_policy) != OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256


def test_checkpoint_predecessor_literals_match_actual_exports() -> None:
    contract = _PURE_CONTRACTS["checkpoint_v1"]
    assert contract["contract_sha256"] == PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1
    assert contract["semantic_sha256"] == PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1


def test_outcome_matrix_matches_checkpoint_graph_and_mutates_root_identity() -> None:
    outcome = _PURE_CONTRACTS["transport_outcome_v1"]
    matrix = outcome["transition_matrix"]
    assert tuple(matrix["attempt_started"]) == (
        "proven_no_network",
        "returned",
        "paid_unknown",
    )
    assert tuple(matrix["returned"]) == ("returned", "paid_unknown")
    assert matrix["returned"]["returned"] == "exact_replay_only_no_new_transition"
    assert "returned->proven_no_network" in matrix["forbidden"]
    graph = _PURE_CONTRACTS["checkpoint_v1"]["transition_graph"]
    assert "attempt_started->proven_no_network|returned|paid_unknown" in graph
    assert "returned->settled|private_rejected_paid|paid_unknown" in graph

    changed = copy.deepcopy(dict(outcome))
    changed["transition_matrix"]["returned"]["proven_no_network"] = (
        "forged_new_transition"
    )
    changed_subhash = _digest(
        _CONTRACT_DOMAIN + b"transport_outcome_v1\x00", changed
    )
    assert changed_subhash != _PURE_CONTRACT_SHA256S["transport_outcome_v1"]
    changed_hashes = dict(_PURE_CONTRACT_SHA256S)
    changed_hashes["transport_outcome_v1"] = changed_subhash
    changed_root = _digest(
        _CONTRACT_DOMAIN,
        {
            "schema_version": 3,
            "predecessor_contract_sha256": PRIVATE_CYCLE_35_CONTRACT_SHA256_V2,
            "canonical_json": "utf8_sorted_keys_compact_allow_nan_false",
            "domains": dict(_CONTRACT_DOMAINS),
            "contract_sha256s": changed_hashes,
            "durable_state_aliases": {
                "attempt_claimed": "attempt_started",
                "returned_pending_validation": "returned",
            },
            "attempt_limit": 1,
            "unknown_is_absorbing": True,
            "production_consumer_enabled": False,
        },
    )
    assert changed_root != PRIVATE_CYCLE_35_CONTRACT_SHA256


def test_outcome_receipt_nullability_contract_is_closed_by_disposition() -> None:
    receipt = _PURE_CONTRACTS["test_transport_outcome_receipt_v1"]
    assert receipt["nullability"] == (
        "proven_no_network:entry_sequence=0,response=null,charge=null",
        "returned:entry_sequence=1,response_hash+length_required,charge_required",
        "paid_unknown:entry_sequence=0|1,response=null,charge=null|authenticated",
    )


def test_cycle_35_wire_parser_requires_exact_canonical_json_and_no_duplicates() -> None:
    document = b'{"a":{"b":1},"z":[true,false,null]}'
    assert parse_cycle_35_canonical_document(document) == {
        "a": {"b": 1},
        "z": [True, False, None],
    }
    for invalid in (
        b'{"a":1,"a":2}',
        b'{"a":{"b":1,"b":2}}',
        b'{"n":NaN}',
        b'{ "a":1}',
        b'{"z":1,"a":2}',
        b'\xff',
        b'',
        b"[" * 33 + b"0" + b"]" * 33,
        b"[" + b",".join([b"0"] * 100_001) + b"]",
        b"[0]" + b" " * 10_500_000,
    ):
        with pytest.raises(ValueError, match="unavailable"):
            parse_cycle_35_canonical_document(invalid)


def test_policy_material_mapping_is_immutable_and_digest_is_recomputed() -> None:
    with pytest.raises(TypeError):
        _POLICY_V4_MATERIAL["checker_v2_sha256"] = "0" * 64  # type: ignore[index]
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw["checker_v2_sha256"] = "0" * 64
    raw["policy_sha256"] = OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivateOutputPolicyV4.model_validate(raw)


def test_capability_v4_golden_identity_signature_domains_and_quarantine() -> None:
    capability = capability_v4()
    assert _CAPABILITY_V4_DOMAIN == (
        b"antiek.midnight-oil.private-provider-capability.v4\x00"
    )
    assert _SIGNATURE_V4_DOMAIN == (
        b"antiek.midnight-oil.private-provider-capability-signature.v4\x00"
    )
    assert capability.capability_id == "ppcap4_" + capability.capability_sha256[:24]
    assert capability.capability_sha256 == private_provider_capability_v4_sha256(
        capability
    )
    assert capability.capability_sha256 == (
        "55014baf39f88b2f6df6dcde873dc534c5bcac77c4379dca059935d72a0c320b"
    )
    assert capability.signature_ed25519 == (
        "793d38f3c604228598bb38614b4c4fc32c2edb4518a85739556e96bbe90d5ffe"
        "933e1afc7adcf2e6397a42e4f1907960f6838e9beeafbd34a002a7a861cf2b03"
    )
    verify_private_provider_capability_v4(
        capability, verification_keys={V4_KEY_ID: public_key()}
    )
    assert "redacted=True" in repr(capability)
    assert capability.account_scope_blind_id.hex() == "".join(
        f"{value:02x}" for value in range(32)
    )
    for field in (
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(capability, field) is False


@pytest.mark.parametrize(
    "field",
    (
        "owner_path_discriminator",
        "provider_id",
        "model_id",
        "route_key",
        "processing_region",
        "account_scope_blind_id",
        "project_scope_blind_id",
        "output_policy_v4_sha256",
        "cycle_35_contract_sha256",
        "revocation_registry_id",
        "revocation_trusted_floor_sha256",
        "approved_max_cents",
        "max_private_input_bytes",
        "max_output_bytes",
        "issued_at_ms",
        "not_before_ms",
        "expires_at_ms",
        "key_id",
        "capability_sha256",
    ),
)
def test_capability_v4_identity_substitution_rejects(field: str) -> None:
    raw = capability_v4().model_dump(mode="python")
    original = raw[field]
    if isinstance(original, bytes):
        raw[field] = bytes([original[0] ^ 1]) + original[1:]
    elif isinstance(original, int):
        raw[field] = original + 1
    else:
        raw[field] = "0" * 64 if str(original).startswith(("opspd1_", "f")) else f"x{original}"
    with pytest.raises((ValidationError, ValueError)):
        PrivateProviderProcessingCapabilityV4.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    (
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ),
)
def test_capability_v4_authority_substitution_rejects(field: str) -> None:
    raw = capability_v4().model_dump(mode="python")
    raw[field] = True
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV4.model_validate(raw)


def test_capability_v4_positive_fixture_literal_rejects_false() -> None:
    raw = capability_v4().model_dump(mode="python")
    raw["synthetic_fixture_eligibility_only"] = False
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV4.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("purpose", "midnight_oil_owner_private_research_v3"),
        ("api_mode", "responses_store"),
        ("issuer_role", "provider"),
        ("key_purpose", "owner_private_provider_capability_v3"),
        ("signature_scheme", "hmac-sha256"),
    ),
)
def test_capability_v4_closed_literal_mutations_reject(field: str, value: str) -> None:
    raw = capability_v4().model_dump(mode="python")
    raw[field] = value
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV4.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    (
        "approved_max_cents",
        "max_private_input_bytes",
        "max_output_bytes",
        "issued_at_ms",
        "not_before_ms",
        "expires_at_ms",
    ),
)
def test_capability_v4_bool_for_integer_rejects(field: str) -> None:
    raw = capability_v4().model_dump(mode="python")
    raw[field] = True
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV4.model_validate(raw)


def test_capability_v4_wrong_key_domain_signature_and_exact_type_reject() -> None:
    capability = capability_v4()
    for keys in (
        {},
        {V4_KEY_ID: public_key(bytes(reversed(V4_PRIVATE)))},
        {V4_KEY_ID: b"short"},
    ):
        with pytest.raises(ValueError, match="unavailable"):
            verify_private_provider_capability_v4(capability, verification_keys=keys)
    forged = capability.model_copy(update={"signature_ed25519": "0" * 128})
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_capability_v4(
            forged, verification_keys={V4_KEY_ID: public_key()}
        )


def test_capability_v4_hostile_key_mapping_failure_is_indistinguishable() -> None:
    class HostileKeys(Mapping[str, bytes]):
        def __getitem__(self, key: str) -> bytes:
            del key
            raise RuntimeError("attacker-controlled detail")

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

        def get(self, key: str, default: bytes | None = None) -> bytes | None:
            del key, default
            raise RuntimeError("attacker-controlled detail")

    capability = capability_v4()
    for operation in (
        lambda: verify_private_provider_capability_v4(
            capability, verification_keys=HostileKeys()
        ),
        lambda: parse_private_provider_capability_v4_document(
            _capability_v4_document(capability), verification_keys=HostileKeys()
        ),
    ):
        with pytest.raises(ValueError, match="^private provider capability v4 is unavailable$"):
            operation()


@pytest.mark.parametrize("role", ("gatherer", "planner", "synthesizer", "verifier"))
def test_capability_v4_role_schema_is_exact(role: str) -> None:
    capability = capability_v4(role=role)
    assert capability.router_role == role
    raw = capability.model_dump(mode="python")
    raw["output_schema"] = "midnight-oil.gather-output/v1"
    if role == "gatherer":
        raw["output_schema"] = "midnight-oil.verifier-output/v1"
    with pytest.raises((ValidationError, ValueError)):
        PrivateProviderProcessingCapabilityV4.model_validate(raw)


@pytest.mark.parametrize(
    ("issued", "not_before", "expires"),
    ((2_002, 2_001, 90_000), (2_000, 2_001, 2_001), (-1, 0, 1)),
)
def test_capability_v4_time_order_rejects(
    issued: int, not_before: int, expires: int
) -> None:
    with pytest.raises((ValidationError, ValueError)):
        capability_v4(
            issued_at_ms=issued,
            not_before_ms=not_before,
            expires_at_ms=expires,
        )


def test_capability_v4_wire_parser_is_canonical_signed_and_duplicate_safe() -> None:
    capability = capability_v4()
    document = _capability_v4_document(capability)
    parsed = parse_private_provider_capability_v4_document(
        document, verification_keys={V4_KEY_ID: public_key()}
    )
    assert parsed == capability
    duplicate = document[:-1] + b',"schema_version":4}'
    for invalid in (
        duplicate,
        b" " + document,
        document.replace(
            capability.signature_ed25519.encode("ascii"), b"0" * 128, 1
        ),
    ):
        with pytest.raises(ValueError, match="unavailable"):
            parse_private_provider_capability_v4_document(
                invalid, verification_keys={V4_KEY_ID: public_key()}
            )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("provider_id", "open/ai"),
        ("provider_id", "open\nai"),
        ("provider_id", "opénai"),
        ("model_id", "gpt\x005"),
        ("model_id", "gpt 5"),
        ("processing_region", "us/east"),
        ("processing_region", "us\neast"),
        ("processing_region", "ús"),
    ),
)
def test_capability_v4_route_identity_requires_canonical_ascii(
    field: str, value: str
) -> None:
    raw = capability_v4().model_dump(mode="python")
    raw[field] = value
    if field == "provider_id":
        raw["route_key"] = f"{value}/{raw['model_id']}"
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV4.model_validate(raw)


def test_core_v4_identity_domains_request_commitment_and_quarantine() -> None:
    core = core_v4()
    assert core.request_core_sha256 == (
        "ff0e6f2032a038f786bbb037c656fe196b2c8b9f717da7c798f352290347700d"
    )
    assert core.private_input_commitment_sha256 == (
        "bbce5bd8c53848314a86abf3f89af43db7f2b69981b130e5d7fb07d68125bbf4"
    )
    assert core.provider_scoped_idempotency_sha256 == (
        "e704b0d31d3b3dc0dab0bb7a3a6625de3ab14a73cc5966a31c065f14b5d5ad94"
    )
    assert _REQUEST_CORE_V4_DOMAIN == (
        b"antiek.midnight-oil.owner-private-request-core.v4\x00"
    )
    assert _PRIVATE_INPUT_COMMITMENT_V4_DOMAIN.endswith(b"commitment.v4\x00")
    assert _IDEMPOTENCY_V4_DOMAIN.endswith(b"idempotency.v4\x00")
    assert core.request_core_id == "oprc4_" + core.request_core_sha256[:24]
    assert core.request_core_sha256 == owner_private_request_core_v4_sha256(core)
    assert core.provider_request_sha256 == hashlib.sha256(core.provider_request_bytes).hexdigest()
    assert core.private_input_commitment_sha256 == private_input_commitment_v4_sha256(
        core.source_receipt_pairs
    )
    assert core.provider_scoped_idempotency_sha256 == (
        provider_scoped_idempotency_v4_sha256(core)
    )
    assert "redacted=True" in repr(core)
    for field in (
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(core, field) is False


@pytest.mark.parametrize(("role", "count"), (("planner", 0), ("gatherer", 1), ("verifier", 8)))
def test_core_v4_source_cardinality_boundaries(role: str, count: int) -> None:
    core = core_v4(role=role, pair_count=count)
    assert len(core.source_receipt_pairs) == count
    assert tuple(pair.ordinal for pair in core.source_receipt_pairs) == tuple(
        range(1, count + 1)
    )


@pytest.mark.parametrize(
    "field",
    (
        "owner_path_discriminator",
        "operation_id",
        "job_id",
        "execution_id",
        "stage_key",
        "capability_id",
        "capability_v4_sha256",
        "output_policy_v4_sha256",
        "cycle_35_contract_sha256",
        "provider_id",
        "model_id",
        "route_key",
        "processing_region",
        "account_scope_blind_id",
        "project_scope_blind_id",
        "provider_request_bytes",
        "provider_request_sha256",
        "provider_request_bytes_count",
        "private_input_commitment_sha256",
        "private_input_bytes",
        "source_registry_id",
        "source_head_sha256",
        "source_epoch",
        "opaque_source_bundle_id",
        "source_selector",
        "required_until_ms",
        "projected_max_cents",
        "max_output_bytes",
        "provider_scoped_idempotency_sha256",
        "request_core_sha256",
    ),
)
def test_core_v4_identity_substitution_rejects(field: str) -> None:
    raw = core_v4().model_dump(mode="python")
    original = raw[field]
    if isinstance(original, bytes):
        raw[field] = original + b"x" if field == "provider_request_bytes" else bytes(
            [original[0] ^ 1]
        ) + original[1:]
    elif isinstance(original, int):
        raw[field] = original + 1
    else:
        raw[field] = f"x{original}"
    with pytest.raises((ValidationError, ValueError)):
        PreparedOwnerPrivateRequestCoreV4.model_validate(raw)


def test_core_v4_pair_gap_duplicate_and_coordinated_rehash_reject() -> None:
    core = core_v4(pair_count=2)
    raw = core.model_dump(mode="python")
    first = raw["source_receipt_pairs"][0]
    second = dict(raw["source_receipt_pairs"][1])
    second["ordinal"] = 3
    raw["source_receipt_pairs"] = (first, second)
    with pytest.raises((ValidationError, ValueError)):
        PreparedOwnerPrivateRequestCoreV4.model_validate(raw)
    raw = core.model_dump(mode="python")
    raw["source_receipt_pairs"] = (first, first)
    with pytest.raises((ValidationError, ValueError)):
        PreparedOwnerPrivateRequestCoreV4.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value", "paired_field", "paired_value"),
    (
        ("projected_max_cents", 999_999_999, None, None),
        ("required_until_ms", 90_001, None, None),
        ("provider_id", "anthropic", "route_key", "anthropic/gpt-5.6"),
        ("capability_id", "ppcap4_" + "0" * 24, "capability_v4_sha256", "0" * 64),
    ),
)
def test_core_v4_coordinated_rehash_remains_nonconferring_without_signed_join(
    field: str, value: object, paired_field: str | None, paired_value: object
) -> None:
    cap = capability_v4()
    raw = core_v4(capability=cap).model_dump(mode="python")
    raw[field] = value
    if paired_field is not None:
        raw[paired_field] = paired_value
    raw["provider_scoped_idempotency_sha256"] = provider_scoped_idempotency_v4_sha256(raw)
    digest = owner_private_request_core_v4_sha256(raw)
    raw["request_core_sha256"] = digest
    raw["request_core_id"] = "oprc4_" + digest[:24]
    internally_canonical = PreparedOwnerPrivateRequestCoreV4.model_validate(raw)
    with pytest.raises(ValueError, match="unavailable"):
        verify_owner_private_request_core_v4(
            internally_canonical,
            capability=cap,
            capability_verification_keys={V4_KEY_ID: public_key()},
        )
@pytest.mark.parametrize(
    ("role", "count"),
    (("planner", 1), ("gatherer", 0), ("gatherer", 9)),
)
def test_core_v4_invalid_source_cardinality_rejects(role: str, count: int) -> None:
    with pytest.raises((ValidationError, ValueError)):
        core_v4(role=role, pair_count=count)


@pytest.mark.parametrize(
    ("required_until_ms", "projected_max_cents", "max_output_bytes"),
    ((2_001, 1_250, 500_000), (80_000, 2_501, 500_000), (80_000, 1_250, 1_000_001)),
)
def test_core_v4_builder_cannot_widen_capability_bounds(
    required_until_ms: int, projected_max_cents: int, max_output_bytes: int
) -> None:
    cap = capability_v4()
    with pytest.raises(ValueError, match="unavailable"):
        build_owner_private_request_core_v4(
            capability=cap,
            capability_verification_keys={V4_KEY_ID: public_key()},
            operation_id="operation",
            job_id="job",
            execution_id="execution",
            stage_key="2" * 64,
            provider_request_bytes=b"{}",
            source_registry_id="registry",
            source_head_sha256="3" * 64,
            source_epoch=4,
            opaque_source_bundle_id="bundle",
            source_selector="active",
            source_receipt_pairs=(source_pair(),),
            required_until_ms=required_until_ms,
            projected_max_cents=projected_max_cents,
            max_output_bytes=max_output_bytes,
        )


@pytest.mark.parametrize(
    "field",
    (
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ),
)
def test_core_v4_authority_substitution_rejects(field: str) -> None:
    raw = core_v4().model_dump(mode="python")
    raw[field] = True
    with pytest.raises(ValidationError):
        PreparedOwnerPrivateRequestCoreV4.model_validate(raw)


def test_core_v4_expiry_equality_is_a_nonempty_narrow_horizon() -> None:
    cap = capability_v4()
    core = build_owner_private_request_core_v4(
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
        operation_id="operation",
        job_id="job",
        execution_id="execution",
        stage_key="2" * 64,
        provider_request_bytes=b"{}",
        source_registry_id="registry",
        source_head_sha256="3" * 64,
        source_epoch=4,
        opaque_source_bundle_id="bundle",
        source_selector="active",
        source_receipt_pairs=(source_pair(),),
        required_until_ms=cap.expires_at_ms,
        projected_max_cents=1,
        max_output_bytes=1,
    )
    assert core.required_until_ms == cap.expires_at_ms


def test_cycle32_pair_id_must_match_receipt_digest() -> None:
    raw = source_pair().model_dump(mode="python")
    raw["receipt_id"] = "opsr5_" + "0" * 24
    with pytest.raises((ValidationError, ValueError)):
        Cycle32SourceReceiptPairV1.model_validate(raw)


def test_core_v4_source_collection_is_bounded_before_iteration() -> None:
    class HostileList(list[Cycle32SourceReceiptPairV1]):
        def __iter__(self) -> Iterator[Cycle32SourceReceiptPairV1]:
            raise RuntimeError("must not iterate")

    cap = capability_v4()
    base = dict(
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
        operation_id="operation",
        job_id="job",
        execution_id="execution",
        stage_key="2" * 64,
        provider_request_bytes=b"{}",
        source_registry_id="registry",
        source_head_sha256="3" * 64,
        source_epoch=4,
        opaque_source_bundle_id="bundle",
        source_selector="active",
        required_until_ms=80_000,
        projected_max_cents=1,
        max_output_bytes=1,
    )
    for hostile in (
        HostileList([source_pair()]),
        (source_pair(),) * 9,
        (source_pair() for _ in iter(int, 1)),
    ):
        with pytest.raises(ValueError, match="unavailable"):
            build_owner_private_request_core_v4(
                **base,
                source_receipt_pairs=hostile,  # type: ignore[arg-type]
            )
    with pytest.raises(ValueError, match="commitment v4 is unavailable"):
        private_input_commitment_v4_sha256([source_pair()])  # type: ignore[arg-type]


def test_receipt_v7_identity_domain_lineage_and_quarantine() -> None:
    receipt = receipt_v7()
    assert receipt.receipt_sha256 == (
        "d5045e68735ba6ae435c8cbf67e06c3e6e0da20146805dddfc14a88e0def1163"
    )
    assert _RECEIPT_V7_DOMAIN == (
        b"antiek.midnight-oil.owner-private-publication-source-receipt.v7\x00"
    )
    assert receipt.receipt_id == "opsr7_" + receipt.receipt_sha256[:24]
    assert receipt.receipt_sha256 == owner_private_source_receipt_v7_sha256(receipt)
    assert receipt.source_receipt_id == "opsr5_" + receipt.source_receipt_sha256[:24]
    assert receipt.authority_kind == "owner_private_sealed_source_claim_v7"
    assert receipt.source_current_verified is False
    assert receipt.admission_live_resolution_required is True
    assert "redacted=True" in repr(receipt)
    for field in (
        "source_authority_confers_sink_authority",
        "source_current_verified",
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(receipt, field) is False


@pytest.mark.parametrize(
    "field",
    (
        "owner_path_discriminator",
        "operation_id",
        "job_id",
        "execution_id",
        "stage_key",
        "request_core_v4_sha256",
        "output_policy_v4_sha256",
        "capability_id",
        "capability_v4_sha256",
        "required_until_ms",
        "private_input_commitment_sha256",
        "private_input_bytes",
        "private_source_ordinal",
        "source_receipt_id",
        "source_receipt_sha256",
        "source_registry_id",
        "source_head_sha256",
        "source_epoch",
        "opaque_source_bundle_id",
        "source_selector",
        "receipt_sha256",
    ),
)
def test_receipt_v7_identity_substitution_rejects(field: str) -> None:
    raw = receipt_v7().model_dump(mode="python")
    original = raw[field]
    if isinstance(original, int):
        raw[field] = original + 1
    else:
        raw[field] = f"x{original}"
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivatePublicationSourceReceiptV7.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    (
        "source_authority_confers_sink_authority",
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ),
)
def test_receipt_v7_authority_substitution_rejects(field: str) -> None:
    raw = receipt_v7().model_dump(mode="python")
    raw[field] = True
    with pytest.raises(ValidationError):
        OwnerPrivatePublicationSourceReceiptV7.model_validate(raw)


def test_receipt_v7_cannot_claim_live_resolution_inside_pure_model() -> None:
    raw = receipt_v7().model_dump(mode="python")
    raw["source_current_verified"] = True
    with pytest.raises(ValidationError):
        OwnerPrivatePublicationSourceReceiptV7.model_validate(raw)
    raw = receipt_v7().model_dump(mode="python")
    raw["admission_live_resolution_required"] = False
    with pytest.raises(ValidationError):
        OwnerPrivatePublicationSourceReceiptV7.model_validate(raw)


@pytest.mark.parametrize("ordinal", (0, 2, True))
def test_receipt_v7_builder_requires_exact_existing_nonplanner_ordinal(
    ordinal: object,
) -> None:
    cap = capability_v4()
    core = core_v4(capability=cap)
    with pytest.raises(ValueError, match="unavailable"):
        build_owner_private_source_receipt_v7(
            core=core,
            capability=cap,
            capability_verification_keys={V4_KEY_ID: public_key()},
            private_source_ordinal=ordinal,  # type: ignore[arg-type]
        )


def test_receipt_v7_planner_has_no_source_receipt() -> None:
    cap = capability_v4(role="planner")
    core = core_v4(role="planner", capability=cap)
    with pytest.raises(ValueError, match="unavailable"):
        build_owner_private_source_receipt_v7(
            core=core,
            capability=cap,
            capability_verification_keys={V4_KEY_ID: public_key()},
            private_source_ordinal=1,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_head_sha256", "9" * 64),
        ("source_epoch", 99),
        ("opaque_source_bundle_id", "other-bundle"),
        ("source_receipt_sha256", "8" * 64),
        ("request_core_v4_sha256", "7" * 64),
    ),
)
def test_receipt_v7_coordinated_rehash_rejects_signed_core_join(
    field: str, value: object
) -> None:
    cap = capability_v4()
    core = core_v4(capability=cap)
    raw = receipt_v7(core=core, capability=cap).model_dump(mode="python")
    raw[field] = value
    if field == "source_receipt_sha256":
        raw["source_receipt_id"] = "opsr5_" + str(value)[:24]
    digest = owner_private_source_receipt_v7_sha256(raw)
    raw["receipt_sha256"] = digest
    raw["receipt_id"] = "opsr7_" + digest[:24]
    internally_canonical = OwnerPrivatePublicationSourceReceiptV7.model_validate(raw)
    with pytest.raises(ValueError, match="unavailable"):
        verify_owner_private_source_receipt_v7(
            internally_canonical,
            core=core,
            capability=cap,
            capability_verification_keys={V4_KEY_ID: public_key()},
        )


def test_coordinated_core_receipt_source_rehash_remains_explicit_unverified_claim() -> None:
    cap = capability_v4()
    core_raw = core_v4(capability=cap).model_dump(mode="python")
    core_raw["source_head_sha256"] = "9" * 64
    core_raw["source_epoch"] = 99
    core_raw["opaque_source_bundle_id"] = "fabricated-but-syntactic-bundle"
    core_raw["provider_scoped_idempotency_sha256"] = (
        provider_scoped_idempotency_v4_sha256(core_raw)
    )
    core_digest = owner_private_request_core_v4_sha256(core_raw)
    core_raw["request_core_sha256"] = core_digest
    core_raw["request_core_id"] = "oprc4_" + core_digest[:24]
    claimed_core = PreparedOwnerPrivateRequestCoreV4.model_validate(core_raw)
    verify_owner_private_request_core_v4(
        claimed_core,
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
    )
    claim = build_owner_private_source_receipt_v7(
        core=claimed_core,
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
        private_source_ordinal=1,
    )
    verify_owner_private_source_receipt_v7(
        claim,
        core=claimed_core,
        capability=cap,
        capability_verification_keys={V4_KEY_ID: public_key()},
    )
    assert claim.source_current_verified is False
    assert claim.admission_live_resolution_required is True
    assert claim.transport_reachable is False
    assert claim.confers_execution_authority is False
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw["predecessor_kind"] = "policy_v3_execution_authority"
    with pytest.raises(ValidationError):
        OwnerPrivateOutputPolicyV4.model_validate(raw)
