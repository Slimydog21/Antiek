from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from substrate.midnight_oil.private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256,
    PRIVATE_OUTPUT_CHECKER_SHA256,
    PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256,
    PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256,
    PRIVATE_OUTPUT_HTML_RENDERER_SHA256,
    PRIVATE_OUTPUT_NORMALIZER_SHA256,
    PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    PRIVATE_OUTPUT_THRESHOLD_SHA256,
    PRIVATE_OUTPUT_UNICODE_TABLE_SHA256,
    PRIVATE_OUTPUT_UNICODE_VERSION,
    OwnerPrivateOutputPolicyV2,
    OwnerPrivateOverlapCheckerContractV1,
    build_owner_private_output_policy_v2,
    build_owner_private_overlap_checker_contract_v1,
    owner_private_output_policy_v2_sha256,
    require_private_output_unicode_runtime,
)
from substrate.midnight_oil.private_provider_policy import (
    OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "midnight_oil_private_overlap_v1.json"


def test_literal_golden_corpus_hash_and_runtime_are_frozen() -> None:
    assert hashlib.sha256(_FIXTURE.read_bytes()).hexdigest() == (
        PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256
    )
    assert PRIVATE_OUTPUT_UNICODE_VERSION == "16.0.0"
    require_private_output_unicode_runtime()


def test_golden_corpus_has_unique_complete_laundering_and_bound_matrix() -> None:
    corpus = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    vectors = corpus["vectors"]
    ids = [vector["id"] for vector in vectors]
    assert len(ids) == len(set(ids))
    assert {vector["kind"] for vector in vectors}.issuperset(
        {
            "utf8",
            "normalization",
            "extraction",
            "laundering",
            "matching",
            "threshold",
            "mosaic",
            "planner",
            "gatherer",
            "bound",
        }
    )
    expected_bounds = {
        "output_bytes": 1_000_000,
        "sources": 8,
        "source_bytes": 32_000,
        "leaves": 256,
        "depth": 32,
        "output_tokens": 200_000,
        "source_tokens": 256_000,
        "match_rows": 100_000,
        "candidate_comparisons": 25_000_000,
        "ledger_bytes": 1_000_000,
    }
    bound_rows = [vector for vector in vectors if vector["kind"] == "bound"]
    for measure, limit in expected_bounds.items():
        observed = {
            row["observed"]: row["verdict"]
            for row in bound_rows
            if row["measure"] == measure
        }
        assert observed == {
            limit - 1: "pass",
            limit: "pass",
            limit + 1: "reject",
        }
    required_ids = {
        "strict-utf8-invalid-reject",
        "nul-control-reject",
        "c1-control-reject",
        "json-pointer-order",
        "json-pointer-escape",
        "raw-html-tag-lexical",
        "raw-html-attribute-lexical",
        "raw-html-comment-lexical",
        "raw-code-lexical",
        "overlap-preserved",
        "repetition-coverage-dedup",
        "duplicate-source-lowest-representative",
        "multi-source-union",
        "ordinal-substitution-reject",
        "empty-after-normalization",
    }
    assert required_ids.issubset(ids)


def test_checker_contract_and_policy_v2_are_content_addressed() -> None:
    checker = build_owner_private_overlap_checker_contract_v1()
    policy = build_owner_private_output_policy_v2()
    assert checker.checker_sha256 == PRIVATE_OUTPUT_CHECKER_SHA256
    assert checker.source_extractor_sha256 == PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
    assert checker.normalizer_sha256 == PRIVATE_OUTPUT_NORMALIZER_SHA256
    assert checker.threshold_sha256 == PRIVATE_OUTPUT_THRESHOLD_SHA256
    assert policy.predecessor_policy_sha256 == OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
    assert policy.policy_sha256 == owner_private_output_policy_v2_sha256(policy)
    assert policy.public_serving_authorized is False
    assert policy.portable_export_authorized is False
    assert policy.training_authorized is False


def test_policy_v2_components_have_literal_golden_vectors() -> None:
    assert PRIVATE_OUTPUT_NORMALIZER_SHA256 == (
        "a9642d20c5a5355530ac4720ac1f7717db5033f2d5e2180a9cf39d822b7e719b"
    )
    assert PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256 == (
        "0b8547770ec7bcd7881240eb34cfb038d4895b975a1209b89bf52514f11fcd35"
    )
    assert PRIVATE_OUTPUT_THRESHOLD_SHA256 == (
        "db4285406c9faaaa56a90d1205531772024eb7df818cbfe942af92342e4f594c"
    )
    assert PRIVATE_OUTPUT_CHECKER_SHA256 == (
        "75218053de0e98351dd7eae794d18f7a3f98e2cc4984d117fb48dd2a36ddc6b5"
    )
    assert PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256 == (
        "c2e5bcff18d858827c76c8b2b586624120aa4972ecec17603ceb92b1b817923e"
    )
    assert PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256 == (
        "794e3d3d639e2104e4bfb51f7395ad729ff129670403f86e8d6690e7e93233bd"
    )
    assert PRIVATE_OUTPUT_ROLE_PARSER_SHA256 == (
        "305cb34279dd8b8fdc4a467eea2d046958f33c407733e0ada2cdbc6324e0f7f6"
    )
    assert PRIVATE_OUTPUT_HTML_RENDERER_SHA256 == (
        "d06b340c008390be2837cc4c2eb58c27eec157b6a09501115f4a07aad41ed1a4"
    )
    assert PRIVATE_OUTPUT_UNICODE_TABLE_SHA256 == (
        "af0ad93f2f73bbb6c257ef487864ee0b4b86670455be07a989f3c8771acf6b10"
    )
    assert OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256 == (
        "d3baceda5c2ec2f9eab0e11d5ac70288d579b04ab1549dcc229ca5337392383d"
    )


@pytest.mark.parametrize(
    ("model", "field"),
    (
        (OwnerPrivateOverlapCheckerContractV1, "checker_sha256"),
        (OwnerPrivateOverlapCheckerContractV1, "normalizer_sha256"),
        (OwnerPrivateOverlapCheckerContractV1, "golden_corpus_sha256"),
        (OwnerPrivateOutputPolicyV2, "predecessor_policy_sha256"),
        (OwnerPrivateOutputPolicyV2, "checker_sha256"),
        (OwnerPrivateOutputPolicyV2, "adapter_registry_sha256"),
        (OwnerPrivateOutputPolicyV2, "policy_sha256"),
    ),
)
def test_contract_identity_mutations_reject(
    model: type[BaseModel], field: str
) -> None:
    value: BaseModel = (
        build_owner_private_overlap_checker_contract_v1()
        if model is OwnerPrivateOverlapCheckerContractV1
        else build_owner_private_output_policy_v2()
    )
    raw = value.model_dump(mode="python")
    raw[field] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        model.model_validate(raw)


def test_policy_v2_sink_rosters_are_closed_sorted_and_disjoint() -> None:
    policy = build_owner_private_output_policy_v2()
    assert policy.candidate_sinks == tuple(sorted(policy.candidate_sinks))
    assert policy.forbidden_sinks == tuple(sorted(policy.forbidden_sinks))
    assert set(policy.candidate_sinks).isdisjoint(policy.forbidden_sinks)
    assert "authenticated_owner_html" in policy.candidate_sinks
    assert {"portable_export", "public_serve", "training_rl"}.issubset(
        policy.forbidden_sinks
    )


def test_unknown_and_duplicate_contract_fields_reject() -> None:
    policy = build_owner_private_output_policy_v2()
    with pytest.raises(ValidationError):
        OwnerPrivateOutputPolicyV2.model_validate(
            {**policy.model_dump(mode="python"), "ambient_allow": True}
        )
