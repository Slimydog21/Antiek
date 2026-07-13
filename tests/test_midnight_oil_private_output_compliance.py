from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from substrate.midnight_oil import private_output_compliance as compliance
from substrate.midnight_oil.live_roles import (
    AddressedContradiction,
    AddressedGap,
    EvidenceDisposition,
    GathererOutput,
    GatherEvidence,
    PlannerOutput,
    PlanQuestion,
    SynthesisClaim,
    SynthesizerOutput,
    VerificationFinding,
    VerifierOutput,
)
from substrate.midnight_oil.private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256,
    PRIVATE_OUTPUT_CHECKER_SHA256,
    PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256,
    PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256,
    PRIVATE_OUTPUT_HTML_RENDERER_SHA256,
    PRIVATE_OUTPUT_LEDGER_SHA256,
    PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    PRIVATE_OUTPUT_NORMALIZER_SHA256,
    PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    PRIVATE_OUTPUT_THRESHOLD_SHA256,
    PRIVATE_OUTPUT_UNICODE_TABLE_SHA256,
    PRIVATE_OUTPUT_UNICODE_VERSION,
    OwnerPrivateOutputPolicyV2,
    OwnerPrivateOverlapCheckerContractV1,
    OwnerPrivateOverlapLedgerMetricsV1,
    OwnerPrivateOverlapLedgerRejected,
    OwnerPrivateOverlapLedgerRowV1,
    OwnerPrivateOverlapLedgerSourceV1,
    OwnerPrivateOverlapLedgerV1,
    build_owner_private_output_policy_v2,
    build_owner_private_overlap_checker_contract_v1,
    canonical_owner_private_overlap_ledger_v1,
    owner_private_output_policy_v2_sha256,
    owner_private_overlap_ledger_v1_sha256,
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
            row["observed"]: row["verdict"] for row in bound_rows if row["measure"] == measure
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
    assert checker.execution_ready is False
    assert checker.executable_corpus_sha256 is None
    assert checker.source_extractor_sha256 == PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
    assert checker.normalizer_sha256 == PRIVATE_OUTPUT_NORMALIZER_SHA256
    assert checker.threshold_sha256 == PRIVATE_OUTPUT_THRESHOLD_SHA256
    assert policy.predecessor_policy_sha256 == OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
    assert policy.policy_sha256 == owner_private_output_policy_v2_sha256(policy)
    assert policy.public_serving_authorized is False
    assert policy.portable_export_authorized is False
    assert policy.training_authorized is False
    assert policy.checker_execution_ready is False
    assert policy.executable_corpus_sha256 is None


def test_policy_v2_components_have_literal_golden_vectors() -> None:
    assert PRIVATE_OUTPUT_NORMALIZER_SHA256 == (
        "315aa4670d9cd228abe03417aeebdeb9ec08f4a3f024921b46b8a17280fedb1d"
    )
    assert PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256 == (
        "0b8547770ec7bcd7881240eb34cfb038d4895b975a1209b89bf52514f11fcd35"
    )
    assert PRIVATE_OUTPUT_THRESHOLD_SHA256 == (
        "db4285406c9faaaa56a90d1205531772024eb7df818cbfe942af92342e4f594c"
    )
    assert PRIVATE_OUTPUT_CHECKER_SHA256 == (
        "2569707d79a668273ac3958ddcb80963b812995cf90d316b69bde5c989431a63"
    )
    assert PRIVATE_OUTPUT_LEDGER_SHA256 == (
        "e332df6e7b19e92895fe7e06318d7ed9b9670e99a8af26ce964d6a7cf1bd7307"
    )
    assert PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256 == (
        "c2e5bcff18d858827c76c8b2b586624120aa4972ecec17603ceb92b1b817923e"
    )
    assert PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256 == (
        "794e3d3d639e2104e4bfb51f7395ad729ff129670403f86e8d6690e7e93233bd"
    )
    assert PRIVATE_OUTPUT_ROLE_PARSER_SHA256 == (
        "7adbc2e6242d5b77a5f243e97d7c5bc62fa7af57a39adcb1acd3414e5b1dfc0f"
    )
    assert PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256 == (
        "a5827624593d21ab9f3ae50d28a966bd2f1e164f6ae68cdb34fe824573288c13"
    )
    assert PRIVATE_OUTPUT_HTML_RENDERER_SHA256 == (
        "d06b340c008390be2837cc4c2eb58c27eec157b6a09501115f4a07aad41ed1a4"
    )
    assert PRIVATE_OUTPUT_UNICODE_TABLE_SHA256 == (
        "6478877b8fef49aa3c9355e36788e5545012bdca4bb97297278207cebd6c235e"
    )
    assert OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256 == (
        "7e0f47fcf024428ffcd4d1c131150c49daa9516355f8a10cc9e3b7065362cfba"
    )


def test_checker_identity_binds_declared_role_schema_field_order() -> None:
    live_roles_path = Path(compliance.__file__).with_name("live_roles.py")
    assert hashlib.sha256(live_roles_path.read_bytes()).hexdigest() == (
        PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256
    )
    models = {
        "planner": (("/", PlannerOutput), ("/questions/*", PlanQuestion)),
        "gatherer": (("/", GathererOutput), ("/evidence/*", GatherEvidence)),
        "verifier": (
            ("/", VerifierOutput),
            ("/findings/*", VerificationFinding),
            ("/evidence_dispositions/*", EvidenceDisposition),
        ),
        "synthesizer": (
            ("/", SynthesizerOutput),
            ("/claims/*", SynthesisClaim),
            ("/addressed_contradictions/*", AddressedContradiction),
            ("/addressed_gaps/*", AddressedGap),
        ),
    }
    observed = {
        role: tuple((pointer, tuple(model.model_fields)) for pointer, model in rows)
        for role, rows in models.items()
    }
    assert observed == compliance._ROLE_SCHEMA_FIELD_ORDER


def test_private_overlap_ledger_has_one_literal_wire_and_digest() -> None:
    ledger = OwnerPrivateOverlapLedgerV1(
        checker_sha256=PRIVATE_OUTPUT_CHECKER_SHA256,
        output_byte_count=100,
        output_token_count=20,
        sources=(
            OwnerPrivateOverlapLedgerSourceV1(
                ordinal=1,
                source_byte_count=10,
                source_token_count=2,
                representative_ordinal=1,
            ),
        ),
        candidate_pair_count=40,
        rows=(
            OwnerPrivateOverlapLedgerRowV1(
                output_start=0,
                output_end=2,
                output_pointer="/research_frame",
                output_origin_spans=((0, 2), (3, 4)),
                source_ordinal=1,
                source_start=0,
                source_end=2,
                source_origin_spans=((0, 4),),
                run_tokens=2,
            ),
        ),
        metrics=OwnerPrivateOverlapLedgerMetricsV1(
            max_contiguous_tokens=2,
            per_source_fragmented_tokens=((1, 2),),
            all_source_fragmented_tokens=2,
            isolated_union_tokens=0,
            match_row_count=1,
        ),
    )
    assert canonical_owner_private_overlap_ledger_v1(ledger) == (
        b'{"candidate_pair_count":40,"checker_sha256":"2569707d79a668273ac3958ddcb80963b812995cf90d316b69bde5c989431a63",'
        b'"metrics":{"all_source_fragmented_tokens":2,"isolated_union_tokens":0,"match_row_count":1,"max_contiguous_tokens":2,'
        b'"per_source_fragmented_tokens":[[1,2]]},"output_byte_count":100,"output_token_count":20,"rows":'
        b'[{"output_end":2,"output_origin_spans":[[0,2],[3,4]],"output_pointer":"/research_frame","output_start":0,"run_tokens":2,'
        b'"source_end":2,"source_ordinal":1,"source_origin_spans":[[0,4]],"source_start":0}],"schema_version":1,'
        b'"sources":[{"ordinal":1,"representative_ordinal":1,"source_byte_count":10,"source_token_count":2}],"verdict":"pass"}'
    )
    assert owner_private_overlap_ledger_v1_sha256(ledger) == (
        "acda9f028d15bca98eb93f76caa26573bebd17e250fc9d5cf350d8cdecae3f3d"
    )
    mutated = replace(ledger, candidate_pair_count=39)
    with pytest.raises(OwnerPrivateOverlapLedgerRejected):
        canonical_owner_private_overlap_ledger_v1(mutated)


def test_private_overlap_ledger_enforces_aggregate_and_wire_bounds() -> None:
    sources = tuple(
        OwnerPrivateOverlapLedgerSourceV1(
            ordinal=ordinal,
            source_byte_count=32_000,
            source_token_count=32_000,
            representative_ordinal=ordinal,
        )
        for ordinal in range(1, 9)
    )
    boundary = OwnerPrivateOverlapLedgerV1(
        checker_sha256=PRIVATE_OUTPUT_CHECKER_SHA256,
        output_byte_count=1,
        output_token_count=1,
        sources=sources,
        candidate_pair_count=256_000,
        rows=(),
        metrics=OwnerPrivateOverlapLedgerMetricsV1(
            max_contiguous_tokens=0,
            per_source_fragmented_tokens=tuple((ordinal, 0) for ordinal in range(1, 9)),
            all_source_fragmented_tokens=0,
            isolated_union_tokens=0,
            match_row_count=0,
        ),
    )
    assert len(canonical_owner_private_overlap_ledger_v1(boundary)) < 1_000_000
    invalid_source = OwnerPrivateOverlapLedgerSourceV1(
        ordinal=1,
        source_byte_count=31_999,
        source_token_count=32_000,
        representative_ordinal=1,
    )
    with pytest.raises(OwnerPrivateOverlapLedgerRejected):
        canonical_owner_private_overlap_ledger_v1(
            replace(boundary, sources=(invalid_source, *boundary.sources[1:]))
        )

    rows = tuple(
        OwnerPrivateOverlapLedgerRowV1(
            output_start=index,
            output_end=index + 1,
            output_pointer="/" + "x" * 16_379 + f"{index:04d}",
            output_origin_spans=((index, index + 1),),
            source_ordinal=1,
            source_start=index,
            source_end=index + 1,
            source_origin_spans=((index, index + 1),),
            run_tokens=1,
        )
        for index in range(100)
    )
    oversized = OwnerPrivateOverlapLedgerV1(
        checker_sha256=PRIVATE_OUTPUT_CHECKER_SHA256,
        output_byte_count=1_000_000,
        output_token_count=200,
        sources=(
            OwnerPrivateOverlapLedgerSourceV1(
                ordinal=1,
                source_byte_count=32_000,
                source_token_count=100,
                representative_ordinal=1,
            ),
        ),
        candidate_pair_count=20_000,
        rows=rows,
        metrics=OwnerPrivateOverlapLedgerMetricsV1(
            max_contiguous_tokens=1,
            per_source_fragmented_tokens=((1, 0),),
            all_source_fragmented_tokens=0,
            isolated_union_tokens=100,
            match_row_count=100,
        ),
    )
    with pytest.raises(OwnerPrivateOverlapLedgerRejected):
        canonical_owner_private_overlap_ledger_v1(oversized)


def test_private_overlap_ledger_repr_and_errors_are_content_free() -> None:
    canary = "/SECRET-CANARY"
    invalid_row = OwnerPrivateOverlapLedgerRowV1(
        output_start=0,
        output_end=1,
        output_pointer=canary,
        output_origin_spans=((2, 1),),
        source_ordinal=1,
        source_start=0,
        source_end=1,
        source_origin_spans=((0, 1),),
        run_tokens=1,
    )
    invalid_ledger = OwnerPrivateOverlapLedgerV1(
        checker_sha256=PRIVATE_OUTPUT_CHECKER_SHA256,
        output_byte_count=10,
        output_token_count=2,
        sources=(
            OwnerPrivateOverlapLedgerSourceV1(
                ordinal=1,
                source_byte_count=2,
                source_token_count=2,
                representative_ordinal=1,
            ),
        ),
        candidate_pair_count=4,
        rows=(invalid_row,),
        metrics=OwnerPrivateOverlapLedgerMetricsV1(
            max_contiguous_tokens=1,
            per_source_fragmented_tokens=((1, 0),),
            all_source_fragmented_tokens=0,
            isolated_union_tokens=1,
            match_row_count=1,
        ),
    )
    with pytest.raises(OwnerPrivateOverlapLedgerRejected) as caught:
        canonical_owner_private_overlap_ledger_v1(invalid_ledger)
    error = caught.value
    assert canary not in str(error)
    assert canary not in repr(error)
    assert error.args == ("owner-private overlap ledger rejected",)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert not hasattr(error, "errors")

    row = OwnerPrivateOverlapLedgerRowV1(
        output_start=0,
        output_end=1,
        output_pointer=canary,
        output_origin_spans=((0, 1),),
        source_ordinal=1,
        source_start=0,
        source_end=1,
        source_origin_spans=((0, 1),),
        run_tokens=1,
    )
    assert repr(row) == "OwnerPrivateOverlapLedgerRowV1(<owner-private>)"
    assert canary not in repr(row)


def test_private_overlap_ledger_rejects_boolean_integer_smuggling() -> None:
    source = OwnerPrivateOverlapLedgerSourceV1(1, 10, 1, 1)
    row = OwnerPrivateOverlapLedgerRowV1(
        output_start=0,
        output_end=1,
        output_pointer="/research_frame",
        output_origin_spans=((0, 1),),
        source_ordinal=1,
        source_start=0,
        source_end=1,
        source_origin_spans=((0, 1),),
        run_tokens=1,
    )
    metrics = OwnerPrivateOverlapLedgerMetricsV1(1, ((1, 0),), 0, 1, 1)
    ledger = OwnerPrivateOverlapLedgerV1(
        checker_sha256=PRIVATE_OUTPUT_CHECKER_SHA256,
        output_byte_count=10,
        output_token_count=10,
        sources=(source,),
        candidate_pair_count=10,
        rows=(row,),
        metrics=metrics,
    )
    source_variants = (
        replace(source, ordinal=True),
        replace(source, source_byte_count=True),
        replace(source, source_token_count=True),
        replace(source, representative_ordinal=True),
    )
    row_variants = (
        replace(row, output_start=False),
        replace(row, output_end=True),
        replace(row, output_origin_spans=((False, 1),)),
        replace(row, output_origin_spans=((0, True),)),
        replace(row, source_ordinal=True),
        replace(row, source_start=False),
        replace(row, source_end=True),
        replace(row, source_origin_spans=((False, 1),)),
        replace(row, source_origin_spans=((0, True),)),
        replace(row, run_tokens=True),
    )
    metric_variants = (
        replace(metrics, max_contiguous_tokens=True),
        replace(metrics, per_source_fragmented_tokens=((True, 0),)),
        replace(metrics, per_source_fragmented_tokens=((1, False),)),
        replace(metrics, all_source_fragmented_tokens=False),
        replace(metrics, isolated_union_tokens=True),
        replace(metrics, match_row_count=True),
    )
    variants = [
        replace(ledger, schema_version=True),
        replace(ledger, output_byte_count=True),
        replace(ledger, output_token_count=True),
        replace(ledger, candidate_pair_count=True),
        *(replace(ledger, sources=(variant,)) for variant in source_variants),
        *(replace(ledger, rows=(variant,)) for variant in row_variants),
        *(replace(ledger, metrics=variant) for variant in metric_variants),
    ]
    for variant in variants:
        with pytest.raises(OwnerPrivateOverlapLedgerRejected):
            canonical_owner_private_overlap_ledger_v1(variant)


@pytest.mark.parametrize(
    ("model", "field"),
    (
        (OwnerPrivateOverlapCheckerContractV1, "checker_sha256"),
        (OwnerPrivateOverlapCheckerContractV1, "normalizer_sha256"),
        (OwnerPrivateOverlapCheckerContractV1, "ledger_sha256"),
        (OwnerPrivateOverlapCheckerContractV1, "golden_corpus_sha256"),
        (OwnerPrivateOutputPolicyV2, "predecessor_policy_sha256"),
        (OwnerPrivateOutputPolicyV2, "checker_sha256"),
        (OwnerPrivateOutputPolicyV2, "adapter_registry_sha256"),
        (OwnerPrivateOutputPolicyV2, "ledger_sha256"),
        (OwnerPrivateOutputPolicyV2, "policy_sha256"),
    ),
)
def test_contract_identity_mutations_reject(model: type[BaseModel], field: str) -> None:
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
    assert {"portable_export", "public_serve", "training_rl"}.issubset(policy.forbidden_sinks)


def test_unknown_and_duplicate_contract_fields_reject() -> None:
    policy = build_owner_private_output_policy_v2()
    with pytest.raises(ValidationError):
        OwnerPrivateOutputPolicyV2.model_validate(
            {**policy.model_dump(mode="python"), "ambient_allow": True}
        )
