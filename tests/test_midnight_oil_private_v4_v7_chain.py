from __future__ import annotations

import copy

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
    PRIVATE_CYCLE_35_CONTRACT_SHA256,
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


def test_policy_v4_canonical_identity_domains_and_quarantine() -> None:
    policy = build_owner_private_output_policy_v4()
    assert OWNER_PRIVATE_OUTPUT_POLICY_V4_SHA256 == (
        "7d4551f30ec2a25c60ad114a9cfa67df6ae279de5dab2559e83a7bcea080e339"
    )
    assert PRIVATE_CYCLE_35_CONTRACT_SHA256 == (
        "09885cb78fdc7f54198c90240c61c7901a2f7e87c590a12543f2bf827b344711"
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
        "schema_version": 1,
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
            "schema_version": 1,
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
    raw = build_owner_private_output_policy_v4().model_dump(mode="python")
    raw["predecessor_kind"] = "policy_v3_execution_authority"
    with pytest.raises(ValidationError):
        OwnerPrivateOutputPolicyV4.model_validate(raw)
