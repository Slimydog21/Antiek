from __future__ import annotations

import copy
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
    PRIVATE_CYCLE_35_CONTRACT_SHA256,
    PRIVATE_CYCLE_35_CONTRACT_SHA256_V1,
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
from tests.support.owner_private_v4 import (
    V4_KEY_ID,
    V4_PRIVATE,
    capability_v4,
    public_key,
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
        "c0a87c11c60ffce36364f6d9a665052396e7a2ff80830a836f3bf680e7677a73"
    )
    assert PRIVATE_CYCLE_35_CONTRACT_SHA256 == (
        "eb013373d470199e2850e2608eac3f67bdf5ecb138193afb80f2fd05921bc47f"
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
    assert policy.contract_revision == 2
    assert policy.predecessor_policy_v4_sha256 == OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256_V1
    assert OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256_V1 == (
        "7d4551f30ec2a25c60ad114a9cfa67df6ae279de5dab2559e83a7bcea080e339"
    )
    assert PRIVATE_CYCLE_35_CONTRACT_SHA256_V1 == (
        "09885cb78fdc7f54198c90240c61c7901a2f7e87c590a12543f2bf827b344711"
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
        "schema_version": 2,
        "predecessor_contract_sha256": PRIVATE_CYCLE_35_CONTRACT_SHA256_V1,
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
            "schema_version": 2,
            "predecessor_contract_sha256": PRIVATE_CYCLE_35_CONTRACT_SHA256_V1,
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
        "423aa1152c0d4d06e4036209dcc36700072c02db9f1409a38db81a5371cae8f9"
    )
    assert capability.signature_ed25519 == (
        "0982b8f28f42fdc9456adc55203cd8ad60af28b3256cba0170451a7539484629"
        "e15aed022c77971441cbd78a6d79b54897d09bfe2f243e857021b544c741ad04"
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
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw["predecessor_kind"] = "policy_v3_execution_authority"
    with pytest.raises(ValidationError):
        OwnerPrivateOutputPolicyV4.model_validate(raw)
