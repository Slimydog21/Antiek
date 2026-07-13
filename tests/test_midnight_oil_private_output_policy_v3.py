from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import BaseModel, ValidationError

from substrate.midnight_oil.private_output_checker_v2 import (
    PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    PRIVATE_OUTPUT_LEDGER_V2_SHA256,
    PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256,
)
from substrate.midnight_oil.private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    build_owner_private_output_policy_v2,
)
from substrate.midnight_oil.private_output_policy_v3 import (
    _POLICY_V3_DOMAIN,
    OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256,
    OwnerPrivateOutputPolicyV3,
    build_owner_private_output_policy_v3,
    owner_private_output_policy_v3_sha256,
)
from substrate.midnight_oil.private_output_source_adapter_v1 import (
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256,
)
from tests.support.owner_private_v2 import (
    owner_private_v2_case,
    owner_private_v2_planner_case,
)


def _wire_sha256(value: BaseModel) -> str:
    dump = value.model_dump
    encoded = json.dumps(
        dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_policy_v3_exact_direct_identities_and_closed_authority() -> None:
    policy = build_owner_private_output_policy_v3()
    assert _POLICY_V3_DOMAIN == b"antiek.midnight-oil.owner-private-output-policy.v3\x00"
    assert OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256 == (
        "2401a45c6bac8dc0dad5ba8f1378a41d2ad9c471f6e4b7fea465b39332bdbc3a"
    )
    assert policy.policy_sha256 == OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256
    assert policy.policy_sha256 == owner_private_output_policy_v3_sha256(policy)
    assert policy.predecessor_policy_v2_sha256 == OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256
    assert policy.source_adapter_contract_sha256 == (
        PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256
    )
    assert policy.source_adapter_implementation_sha256 == (
        PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256
    )
    assert policy.source_adapter_source_set_sha256 == (
        PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256
    )
    assert policy.checker_v2_contract_sha256 == PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256
    assert policy.checker_v2_sha256 == PRIVATE_OUTPUT_CHECKER_V2_SHA256
    assert policy.checker_v2_corpus_sha256 == PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256
    assert policy.checker_v2_module_sha256 == PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256
    assert policy.checker_v2_normalizer_sha256 == (PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256)
    assert policy.checker_v2_ledger_sha256 == PRIVATE_OUTPUT_LEDGER_V2_SHA256
    assert policy.authorized_sinks == ()
    assert policy.durable_current_resolution_required is True
    assert policy.checker_evaluation_ready is True
    false_fields = {
        name
        for name, value in policy.model_dump(mode="python").items()
        if name.endswith("authorized")
        or name.startswith("confers_")
        or name == "production_consumer_enabled"
    }
    assert false_fields
    assert all(getattr(policy, name) is False for name in false_fields)


@pytest.mark.parametrize(
    "field",
    (
        "predecessor_policy_v2_sha256",
        "source_adapter_contract_sha256",
        "source_adapter_implementation_sha256",
        "source_adapter_source_set_sha256",
        "checker_v2_contract_sha256",
        "checker_v2_sha256",
        "checker_v2_corpus_sha256",
        "checker_v2_module_sha256",
        "checker_v2_normalizer_sha256",
        "checker_v2_ledger_sha256",
        "role_parser_sha256",
        "role_schema_sha256",
        "live_roles_code_sha256",
        "source_extractor_sha256",
        "threshold_sha256",
        "policy_sha256",
    ),
)
def test_policy_v3_identity_mutations_reject(field: str) -> None:
    raw = build_owner_private_output_policy_v3().model_dump(mode="python")
    raw[field] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivateOutputPolicyV3.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("authorized_sinks", ("generic_deposit",)),
        ("durable_current_resolution_required", False),
        ("checker_evaluation_ready", False),
        ("checkpoint_authorized", True),
        ("provider_execution_authorized", True),
        ("request_core_v3_authorized", True),
        ("receipt_v6_authorized", True),
        ("confers_execution_authority", True),
        ("confers_sink_authority", True),
        ("production_consumer_enabled", True),
    ),
)
def test_policy_v3_authority_or_sink_substitution_rejects(field: str, replacement: object) -> None:
    raw = build_owner_private_output_policy_v3().model_dump(mode="python")
    raw[field] = replacement
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivateOutputPolicyV3.model_validate(raw)


def test_policy_v3_is_redacted_and_predecessor_serializations_are_frozen() -> None:
    policy = build_owner_private_output_policy_v3()
    assert repr(policy) == "OwnerPrivateOutputPolicyV3(redacted=True)"
    assert OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256 == (
        "7e0f47fcf024428ffcd4d1c131150c49daa9516355f8a10cc9e3b7065362cfba"
    )
    assert _wire_sha256(build_owner_private_output_policy_v2()) == (
        "9c75cdf18a7b4a9e0b63d84effa894132d8ed6fa79bf3f0e6e6c4cf47395b0b8"
    )
    gatherer = owner_private_v2_case()
    planner = owner_private_v2_planner_case()
    assert _wire_sha256(gatherer.capability) == (
        "fa4009b5daeafd001a9b60f5bfb67e65934d94c38cc9d0f6d98ea28f81afb871"
    )
    assert _wire_sha256(gatherer.core) == (
        "ceecefc7ef2ea24abcdff7d0335f9b56e5fc8944254356829de5fddc21844052"
    )
    assert _wire_sha256(gatherer.receipts[0]) == (
        "04dcd4a413c63adfb6d64653695aec71527f5c2addb9f0b75b596c9f337fd531"
    )
    assert _wire_sha256(gatherer.envelope) == (
        "1cc666d2f456c418589bb679c2d7782fc1bf39e1e57b7ead74ce9cef14d69bf2"
    )
    assert _wire_sha256(planner.core) == (
        "6a9da2cf6ed2c3b9c102205af150c8e85b8c29532bd5f842f7f4fabe6b1f7c86"
    )
    assert _wire_sha256(planner.envelope) == (
        "37c8c19915e0ef85daffc276e93c0ab40c5688c4fd76cc4eca15dab5d4ebf082"
    )
