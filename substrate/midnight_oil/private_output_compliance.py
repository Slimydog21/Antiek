"""Frozen, non-executable contracts for owner-private output compliance v2.

This module deliberately performs no provider, storage, sink, graph, or network
I/O.  V1 remains the deny-all authority.  These additive identities are the
first implementation slice of FSW-SPR-11B-E and have no production consumer.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .live_roles import GathererOutput, PlannerOutput, SynthesizerOutput, VerifierOutput
from .private_provider_policy import OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256

_HEX64 = r"^[0-9a-f]{64}$"
_CHECKER_DOMAIN = b"antiek.midnight-oil.owner-private-overlap-checker.v1\x00"
_THRESHOLD_DOMAIN = b"antiek.midnight-oil.owner-private-overlap-thresholds.v1\x00"
_NORMALIZER_DOMAIN = b"antiek.midnight-oil.owner-private-normalizer.v1\x00"
_EXTRACTOR_DOMAIN = b"antiek.midnight-oil.owner-private-source-extractor.v1\x00"
_ADAPTER_DOMAIN = b"antiek.midnight-oil.owner-private-sink-adapters.v1\x00"
_ENVELOPE_DOMAIN = b"antiek.midnight-oil.owner-private-encryption-envelope.v1\x00"
_PARSER_DOMAIN = b"antiek.midnight-oil.owner-private-role-parser.v1\x00"
_RENDERER_DOMAIN = b"antiek.midnight-oil.owner-private-html-renderer.v1\x00"
_UNICODE_TABLE_DOMAIN = b"antiek.midnight-oil.unicode-tables.v16\x00"
_LEDGER_DOMAIN = b"antiek.midnight-oil.owner-private-overlap-ledger.v1\x00"
_ROLE_SCHEMA_DOMAIN = b"antiek.midnight-oil.owner-private-role-schemas.v1\x00"
_POLICY_DOMAIN = b"antiek.midnight-oil.owner-private-output-policy.v2\x00"

MAX_PRIVATE_OUTPUT_BYTES = 1_000_000
MAX_PRIVATE_OUTPUT_SOURCES = 8
MAX_PRIVATE_SOURCE_BYTES = 32_000
MAX_PRIVATE_OUTPUT_LEAVES = 256
MAX_PRIVATE_OUTPUT_DEPTH = 32
MAX_PRIVATE_OUTPUT_TOKENS = 200_000
MAX_PRIVATE_SOURCE_TOKENS = 256_000
MAX_PRIVATE_MATCH_ROWS = 100_000
MAX_PRIVATE_MATCH_COMPARISONS = 25_000_000
MAX_PRIVATE_MATCH_LEDGER_BYTES = 1_000_000
PRIVATE_OUTPUT_UNICODE_VERSION = "16.0.0"
PRIVATE_OUTPUT_UNICODE_TABLE_SHA256 = (
    "6478877b8fef49aa3c9355e36788e5545012bdca4bb97297278207cebd6c235e"
)
PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256 = (
    "db809c219a5d0ba65f472dcad164d2fdaed79cc3cfe7c0fac86fa3c63e3f5468"
)

_CANDIDATE_SINKS: tuple[str, ...] = (
    "authenticated_owner_html",
    "owner_engagement_document",
    "owner_job_evidence",
    "owner_private_graph",
    "owner_private_prompt_context",
    "owner_spawn",
    "owner_stage_checkpoint",
    "owner_twin",
)
_FORBIDDEN_SINKS: tuple[str, ...] = (
    "ads",
    "analytics_payload",
    "attribution",
    "benchmark_content_dataset",
    "cache",
    "cross_owner_merge",
    "error_payload",
    "federation",
    "general_depth_graph",
    "log_payload",
    "marketplace",
    "monetization",
    "portable_export",
    "public_retrieval",
    "public_serve",
    "public_share",
    "shared_graph",
    "training_rl",
    "webhook",
)

_WHITESPACE_INTERVALS: tuple[tuple[int, int], ...] = (
    (0x0009, 0x000D),
    (0x0020, 0x0020),
    (0x0085, 0x0085),
    (0x00A0, 0x00A0),
    (0x1680, 0x1680),
    (0x2000, 0x200A),
    (0x2028, 0x2029),
    (0x202F, 0x202F),
    (0x205F, 0x205F),
    (0x3000, 0x3000),
)
_QUOTE_MAP: tuple[tuple[int, str], ...] = (
    (0x2018, "'"),
    (0x2019, "'"),
    (0x201A, "'"),
    (0x201B, "'"),
    (0x201C, '"'),
    (0x201D, '"'),
    (0x201E, '"'),
    (0x201F, '"'),
    (0x2032, "'"),
    (0x2033, '"'),
)
_DASH_CODEPOINTS: tuple[int, ...] = (
    0x058A,
    0x05BE,
    0x1400,
    0x1806,
    0x2010,
    0x2011,
    0x2012,
    0x2013,
    0x2014,
    0x2015,
    0x2E17,
    0x2E1A,
    0x2E3A,
    0x2E3B,
    0x2E40,
    0x301C,
    0x3030,
    0x30A0,
    0xFE31,
    0xFE32,
    0xFE58,
    0xFE63,
    0xFF0D,
)
_REMOVED_INTERVALS: tuple[tuple[int, int], ...] = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)

_EXEMPT_POINTER_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "planner": ("/role", "/questions/*/question_id"),
    "gatherer": (
        "/role",
        "/question_id",
        "/evidence/*/evidence_id",
        "/evidence/*/source_receipt_id",
        "/evidence/*/document_id",
        "/evidence/*/chunk_id",
        "/evidence/*/excerpt_sha256",
    ),
    "verifier": (
        "/role",
        "/findings/*/finding_id",
        "/findings/*/proposition_id",
        "/findings/*/question_id",
        "/findings/*/status",
        "/findings/*/evidence_ids/*",
        "/evidence_dispositions/*/evidence_id",
        "/evidence_dispositions/*/question_id",
        "/evidence_dispositions/*/disposition",
    ),
    "synthesizer": (
        "/role",
        "/claims/*/claim_id",
        "/claims/*/proposition_id",
        "/claims/*/finding_id",
        "/claims/*/evidence_ids/*",
        "/claims/*/confidence",
        "/summary_claim_ids/*",
        "/addressed_contradictions/*/finding_id",
        "/addressed_contradictions/*/treatment",
        "/addressed_gaps/*/finding_id",
    ),
}

_ROLE_SCHEMA_FIELD_ORDER: Mapping[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "planner": (
        ("/", ("schema_version", "role", "research_frame", "questions")),
        (
            "/questions/*",
            (
                "question_id",
                "question",
                "inclusion_criteria",
                "exclusion_criteria",
                "expected_evidence_types",
                "falsifiers",
            ),
        ),
    ),
    "gatherer": (
        ("/", ("schema_version", "role", "question_id", "evidence", "search_limitations")),
        (
            "/evidence/*",
            (
                "evidence_id",
                "source_receipt_id",
                "document_id",
                "chunk_id",
                "excerpt_sha256",
                "claim",
                "relevance",
                "limitations",
            ),
        ),
    ),
    "verifier": (
        ("/", ("schema_version", "role", "findings", "evidence_dispositions")),
        (
            "/findings/*",
            (
                "finding_id",
                "proposition_id",
                "question_id",
                "claim",
                "status",
                "evidence_ids",
                "rationale",
                "missing_evidence",
            ),
        ),
        (
            "/evidence_dispositions/*",
            ("evidence_id", "question_id", "disposition", "rationale"),
        ),
    ),
    "synthesizer": (
        (
            "/",
            (
                "schema_version",
                "role",
                "claims",
                "summary_claim_ids",
                "addressed_contradictions",
                "addressed_gaps",
                "limitations",
                "open_questions",
            ),
        ),
        (
            "/claims/*",
            (
                "claim_id",
                "proposition_id",
                "text",
                "finding_id",
                "evidence_ids",
                "confidence",
            ),
        ),
        (
            "/addressed_contradictions/*",
            ("finding_id", "treatment", "explanation"),
        ),
        ("/addressed_gaps/*", ("finding_id", "explanation")),
    ),
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _digest(domain: bytes, material: object) -> str:
    return hashlib.sha256(domain + _canonical_json(material)).hexdigest()


_ROLE_SCHEMA_MODELS: Mapping[str, type[BaseModel]] = {
    "planner": PlannerOutput,
    "gatherer": GathererOutput,
    "verifier": VerifierOutput,
    "synthesizer": SynthesizerOutput,
}
_ROLE_SCHEMA_JSON_SHA256 = {
    role: _digest(
        _ROLE_SCHEMA_DOMAIN,
        {"role": role, "json_schema": model.model_json_schema(mode="validation")},
    )
    for role, model in _ROLE_SCHEMA_MODELS.items()
}
PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256 = _digest(_ROLE_SCHEMA_DOMAIN, _ROLE_SCHEMA_JSON_SHA256)


_NORMALIZER_MATERIAL = {
    "schema_version": 1,
    "normalizer_id": "antiek-owner-private-normalizer-v1",
    "unicode_version": PRIVATE_OUTPUT_UNICODE_VERSION,
    "unicode_table_sha256": PRIVATE_OUTPUT_UNICODE_TABLE_SHA256,
    "order": (
        "NFKC",
        "full_casefold",
        "NFKC",
        "crlf_to_space",
        "frozen_maps",
        "remove_frozen_default_ignorables_and_bidi",
        "unicode_letter_number_tokens",
    ),
    "whitespace_intervals": _WHITESPACE_INTERVALS,
    "quote_map": _QUOTE_MAP,
    "dash_codepoints": _DASH_CODEPOINTS,
    "removed_intervals": _REMOVED_INTERVALS,
    "provenance": {
        "algorithm": "unicode16_uax15_attributed_scalar_v1",
        "decomposition": "recursive_compatibility_including_algorithmic_hangul",
        "reordering": "stable_canonical_combining_class",
        "composition": "uax15_blocking_and_hangul_union_origins",
        "expansion": "inherit_input_origin_span_set",
        "removal": "drop_origin_without_covering_gap",
        "coordinates": "decoded_leaf_or_exact_source_utf8_half_open_disjoint_spans",
        "whole_string_runtime_equality": "required_each_nfkc_stage",
        "per_codepoint_normalize": "deny",
        "prefix_quadratic_normalize": "deny",
    },
    "stopword_removal": False,
}
PRIVATE_OUTPUT_NORMALIZER_SHA256 = _digest(_NORMALIZER_DOMAIN, _NORMALIZER_MATERIAL)

_EXTRACTOR_MATERIAL = {
    "schema_version": 1,
    "extractor_id": "owner_supplied_local_excerpt_utf8_v1",
    "source_bytes": "exact_receipt_v5_committed_utf8_range",
    "refetch": "deny",
    "render": "deny",
    "entity_decode": "deny",
    "other_media": "deny",
}
PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256 = _digest(_EXTRACTOR_DOMAIN, _EXTRACTOR_MATERIAL)

_THRESHOLD_MATERIAL = {
    "schema_version": 1,
    "max_contiguous_tokens_exclusive": 12,
    "fragmented_min_run_tokens": 2,
    "per_source_fragmented_tokens_exclusive": 24,
    "all_source_fragmented_tokens_exclusive": 32,
    "fragmented_ratio_numerator": 1,
    "fragmented_ratio_denominator": 5,
    "isolated_ratio_min_output_tokens": 12,
    "isolated_ratio_numerator": 3,
    "isolated_ratio_denominator": 5,
}
PRIVATE_OUTPUT_THRESHOLD_SHA256 = _digest(_THRESHOLD_DOMAIN, _THRESHOLD_MATERIAL)

_LEDGER_MATERIAL = {
    "schema_version": 1,
    "domain": _LEDGER_DOMAIN.decode("ascii"),
    "encoding": "canonical_json_sorted_compact_unicode_unescaped",
    "fields": (
        "schema_version",
        "checker_sha256",
        "output_byte_count",
        "output_token_count",
        "sources",
        "candidate_pair_count",
        "rows",
        "metrics",
        "verdict",
    ),
    "source_fields": (
        "ordinal",
        "source_byte_count",
        "source_token_count",
        "representative_ordinal",
    ),
    "row_fields": (
        "output_start",
        "output_end",
        "output_pointer",
        "output_origin_spans",
        "source_ordinal",
        "source_start",
        "source_end",
        "source_origin_spans",
        "run_tokens",
    ),
    "span_encoding": "array_of_strictly_ordered_disjoint_start_end_arrays",
    "row_span_semantics": "coalesced_union_of_all_token_origins_in_the_row",
    "metrics_fields": (
        "max_contiguous_tokens",
        "per_source_fragmented_tokens",
        "all_source_fragmented_tokens",
        "isolated_union_tokens",
        "match_row_count",
    ),
    "per_source_metric_encoding": "source_ordered_array_of_ordinal_count_arrays",
    "integer_encoding": "nonnegative_json_integer_never_float_or_string",
    "verdict": "pass",
    "digest_preimage": "domain_bytes_directly_concatenated_with_canonical_ledger_bytes",
    "size_cap_scope": "ledger_bytes_only",
    "validation": (
        "contiguous_source_ordinals_and_metrics",
        "source_tokens_le_source_bytes",
        "aggregate_source_tokens_le_256000_including_duplicates",
        "candidate_pairs_eq_output_tokens_times_aggregate_source_tokens",
        "unique_rows_sorted_by_frozen_match_order",
        "row_ranges_and_disjoint_origins_within_declared_counts",
        "metrics_recomputed_by_interval_union_over_rows",
        "pass_thresholds_recomputed_from_metrics",
        "canonical_ledger_bytes_le_1000000",
    ),
    "rejection_ledger": "absent",
}
PRIVATE_OUTPUT_LEDGER_SHA256 = _digest(_LEDGER_DOMAIN, _LEDGER_MATERIAL)

_CHECKER_MATERIAL = {
    "schema_version": 1,
    "checker_id": "antiek-owner-private-verbatim-overlap-v1",
    "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "normalizer_sha256": PRIVATE_OUTPUT_NORMALIZER_SHA256,
    "threshold_sha256": PRIVATE_OUTPUT_THRESHOLD_SHA256,
    "ledger_sha256": PRIVATE_OUTPUT_LEDGER_SHA256,
    "wire_validation": "exact_canonical_role_bytes_after_closed_semantic_join",
    "output_order": "declared_role_schema_field_order_then_numeric_tuple_index",
    "role_schema_field_order": _ROLE_SCHEMA_FIELD_ORDER,
    "role_schema_sha256": PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    "live_roles_code_sha256": PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    "pointer_encoding": "rfc6901_segment_structural_numeric_wildcard",
    "depth": "root_zero_each_field_or_index_edge_increments",
    "leaf_boundary": "normalize_independently_break_contiguous_no_marker_token",
    "enumeration": "longest_equal_prefix_for_every_equal_start_pair",
    "match_order": (
        "output_start",
        "source_ordinal",
        "source_start",
        "descending_length",
    ),
    "repetition_oracle": (
        (0, 1, 0, 2),
        (0, 1, 1, 1),
        (1, 1, 0, 2),
        (1, 1, 1, 1),
        (2, 1, 0, 1),
        (2, 1, 1, 1),
    ),
    "duplicate_source_representative": "exact_bytes_lowest_ordinal_aggregate_only",
    "duplicate_source_resource_accounting": "every_ordinal",
    "overlapping_matches": "preserve_all_rows_including_left_extendable_and_subsumed",
    "coverage_deduplication": "count_each_output_token_once_per_measure",
    "per_source_fragmented_coverage": "union_of_runs_length_at_least_two",
    "all_source_fragmented_coverage": "union_of_runs_length_at_least_two",
    "isolated_token_coverage": "union_of_all_length_one_matches",
    "threshold_predicates": {
        "contiguous_fail": "max_run_gte_12",
        "per_source_fail": "covered_gte_24_or_5xcovered_gte_output_tokens",
        "all_source_fail": "covered_gte_32_or_5xcovered_gte_output_tokens",
        "isolated_fail": "output_tokens_gte_12_and_5xcovered_gte_3xoutput_tokens",
    },
    "candidate_pairs": "sum_each_content_leaf_tokens_times_each_ordinal_source_tokens",
    "overflow": "single_content_free_rejection_no_partial_result",
    "byte_offsets": "disjoint_original_utf8_half_open_spans_per_output_leaf_and_source",
    "bounds": {
        "output_bytes": MAX_PRIVATE_OUTPUT_BYTES,
        "sources": MAX_PRIVATE_OUTPUT_SOURCES,
        "source_bytes": MAX_PRIVATE_SOURCE_BYTES,
        "output_leaves": MAX_PRIVATE_OUTPUT_LEAVES,
        "output_depth": MAX_PRIVATE_OUTPUT_DEPTH,
        "output_tokens": MAX_PRIVATE_OUTPUT_TOKENS,
        "source_tokens": MAX_PRIVATE_SOURCE_TOKENS,
        "match_rows": MAX_PRIVATE_MATCH_ROWS,
        "candidate_comparisons": MAX_PRIVATE_MATCH_COMPARISONS,
        "ledger_bytes": MAX_PRIVATE_MATCH_LEDGER_BYTES,
    },
    "exempt_pointer_patterns": _EXEMPT_POINTER_PATTERNS,
    "planner_source_overlap": "not_applicable_exactly_zero_sources",
    "nonplanner_sources": "one_through_eight_exact_ordered_resolved_receipt_v5",
    "corpus_status": "predecessor_declarative_not_executable",
    "executable_corpus_sha256": None,
    "execution_ready": False,
}
PRIVATE_OUTPUT_CHECKER_SHA256 = _digest(_CHECKER_DOMAIN, _CHECKER_MATERIAL)

# Literal hash of tests/fixtures/midnight_oil_private_overlap_v1.json.  The
# fixture-to-constant test prevents either side from drifting independently.
PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256 = (
    "cdb2ff31ee24e83e788123a99d74a09f2ca1da2f3671cee528f19da358d0d978"
)

_ADAPTER_MATERIAL = {
    "schema_version": 1,
    "registry_id": "antiek-owner-private-terminal-sink-adapters-v1",
    "caller_callable": "deny",
    "plaintext_return": "deny",
    "proof_return": "closed_content_free_v1",
    "purposes": _CANDIDATE_SINKS,
}
PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256 = _digest(_ADAPTER_DOMAIN, _ADAPTER_MATERIAL)

_PARSER_MATERIAL = {
    "schema_version": 1,
    "parser_id": "midnight-oil-closed-role-output-parser-v1",
    "schemas": (
        "midnight-oil.planner-output/v1",
        "midnight-oil.gather-output/v1",
        "midnight-oil.verifier-output/v1",
        "midnight-oil.synthesizer-output/v1",
    ),
    "role_schema_field_order": _ROLE_SCHEMA_FIELD_ORDER,
    "role_schema_sha256": PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    "live_roles_code_sha256": PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    "json_duplicate_keys": "reject",
    "unknown_fields": "reject",
    "utf8": "strict",
    "canonical_json": "sort_keys_compact_utf8_unescaped_no_trailing_bytes",
    "max_bytes": MAX_PRIVATE_OUTPUT_BYTES,
}
PRIVATE_OUTPUT_ROLE_PARSER_SHA256 = _digest(_PARSER_DOMAIN, _PARSER_MATERIAL)

_RENDERER_MATERIAL = {
    "schema_version": 1,
    "renderer_id": "owner-private-html-renderer-v1",
    "input": "verified_canonical_role_output_v1",
    "escaping": "html5_text_and_attribute_contextual",
    "script_style_external_resource": "deny",
    "response_body": "store_owned_terminal_stream_only",
    "cache_control": "private,no-store,max-age=0",
    "csp": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox",
    "x_content_type_options": "nosniff",
    "referrer_policy": "no-referrer",
}
PRIVATE_OUTPUT_HTML_RENDERER_SHA256 = _digest(_RENDERER_DOMAIN, _RENDERER_MATERIAL)

_ENVELOPE_MATERIAL = {
    "schema_version": 1,
    "envelope_id": "antiek-owner-private-aead-envelope-v1",
    "aead_suite": "aes-256-gcm",
    "key_bytes": 32,
    "nonce_bytes": 12,
    "nonce_source": "csprng",
    "nonce_uniqueness": "per_key_version",
    "tag_bytes": 16,
    "ciphertext_framing": "version_u8_nonce12_ciphertext_and_tag",
    "aad_domain": "antiek.midnight-oil.owner-private-aead-envelope.v1",
    "aad_field_order": (
        "schema_version",
        "opaque_row_id",
        "owner_scope_sha256",
        "operation_id",
        "job_id",
        "execution_id",
        "stage_key",
        "provider_effect_key",
        "sink_purpose",
        "row_revision",
        "policy_v2_sha256",
        "capability_v2_sha256",
        "provider_request_core_sha256",
        "output_schema",
        "compliance_receipt_sha256",
        "verified_taint_sha256",
        "key_version",
    ),
    "aad_encoding": "domain_plus_length_prefixed_utf8_and_u64be",
    "first_writer_wins": True,
    "exact_replay": "return_original_nonce_and_ciphertext",
    "key_rotation": "distinct_versioned_cas_preserves_compliance_identity",
    "plaintext_columns": (
        "opaque_row_id",
        "owner_path_discriminator",
        "categorical_state",
        "aead_suite",
        "key_version",
        "bounded_non_content_timing_cost",
        "ciphertext_length",
        "nonce",
        "ciphertext",
    ),
}
PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256 = _digest(_ENVELOPE_DOMAIN, _ENVELOPE_MATERIAL)

_POLICY_MATERIAL_V2: dict[str, object] = {
    "schema_version": 2,
    "policy_id": "antiek-owner-private-provider-output-v2",
    "predecessor_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    "content_class": "personal_reading",
    "candidate_sinks": _CANDIDATE_SINKS,
    "forbidden_sinks": _FORBIDDEN_SINKS,
    "unknown_sink": "deny",
    "declassification": "not_authorized",
    "public_serving_authorized": False,
    "portable_export_authorized": False,
    "training_authorized": False,
    "checker_sha256": PRIVATE_OUTPUT_CHECKER_SHA256,
    "checker_execution_ready": False,
    "role_parser_sha256": PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    "html_renderer_sha256": PRIVATE_OUTPUT_HTML_RENDERER_SHA256,
    "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "normalizer_sha256": PRIVATE_OUTPUT_NORMALIZER_SHA256,
    "threshold_sha256": PRIVATE_OUTPUT_THRESHOLD_SHA256,
    "ledger_sha256": PRIVATE_OUTPUT_LEDGER_SHA256,
    "golden_corpus_sha256": PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256,
    "executable_corpus_sha256": None,
    "adapter_registry_sha256": PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256,
    "encryption_envelope_sha256": PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256,
}
OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256 = _digest(_POLICY_DOMAIN, _POLICY_MATERIAL_V2)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class OwnerPrivateOverlapLedgerRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("owner-private overlap ledger rejected")

    def __repr__(self) -> str:
        return "OwnerPrivateOverlapLedgerRejected()"


def _interval_union_count(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    covered = 0
    current_start, current_end = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start > current_end:
            covered += current_end - current_start
            current_start, current_end = start, end
        elif end > current_end:
            current_end = end
    return covered + current_end - current_start


class _PrivateLedgerValue:
    def __repr__(self) -> str:
        return f"{type(self).__name__}(<owner-private>)"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerSourceV1(_PrivateLedgerValue):
    ordinal: int
    source_byte_count: int
    source_token_count: int
    representative_ordinal: int


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerRowV1(_PrivateLedgerValue):
    output_start: int
    output_end: int
    output_pointer: str
    output_origin_spans: tuple[tuple[int, int], ...]
    source_ordinal: int
    source_start: int
    source_end: int
    source_origin_spans: tuple[tuple[int, int], ...]
    run_tokens: int


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerMetricsV1(_PrivateLedgerValue):
    max_contiguous_tokens: int
    per_source_fragmented_tokens: tuple[tuple[int, int], ...]
    all_source_fragmented_tokens: int
    isolated_union_tokens: int
    match_row_count: int


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerV1(_PrivateLedgerValue):
    checker_sha256: str
    output_byte_count: int
    output_token_count: int
    sources: tuple[OwnerPrivateOverlapLedgerSourceV1, ...]
    candidate_pair_count: int
    rows: tuple[OwnerPrivateOverlapLedgerRowV1, ...]
    metrics: OwnerPrivateOverlapLedgerMetricsV1
    schema_version: Literal[1] = 1
    verdict: Literal["pass"] = "pass"


def _is_closed_int(value: object, *, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _valid_origin_spans(value: object, *, maximum: int) -> bool:
    if type(value) is not tuple or not value:
        return False
    previous_end = -1
    for span in value:
        if type(span) is not tuple or len(span) != 2:
            return False
        start, end = span
        if (
            not _is_closed_int(start, minimum=0, maximum=maximum)
            or not _is_closed_int(end, minimum=1, maximum=maximum)
            or end <= start
            or start <= previous_end
        ):
            return False
        previous_end = end
    return True


def _validate_owner_private_overlap_ledger_v1(
    ledger: OwnerPrivateOverlapLedgerV1,
) -> None:
    if (
        type(ledger) is not OwnerPrivateOverlapLedgerV1
        or not _is_closed_int(ledger.schema_version, minimum=1, maximum=1)
        or type(ledger.verdict) is not str
        or ledger.verdict != "pass"
        or type(ledger.checker_sha256) is not str
        or ledger.checker_sha256 != PRIVATE_OUTPUT_CHECKER_SHA256
        or len(ledger.checker_sha256) != 64
        or any(character not in "0123456789abcdef" for character in ledger.checker_sha256)
        or not _is_closed_int(ledger.output_byte_count, minimum=1, maximum=MAX_PRIVATE_OUTPUT_BYTES)
        or not _is_closed_int(
            ledger.output_token_count, minimum=1, maximum=MAX_PRIVATE_OUTPUT_TOKENS
        )
        or type(ledger.sources) is not tuple
        or not 1 <= len(ledger.sources) <= MAX_PRIVATE_OUTPUT_SOURCES
        or type(ledger.rows) is not tuple
        or len(ledger.rows) > MAX_PRIVATE_MATCH_ROWS
        or type(ledger.metrics) is not OwnerPrivateOverlapLedgerMetricsV1
    ):
        raise ValueError("owner-private overlap ledger shape conflicts")
    ordinals = tuple(range(1, len(ledger.sources) + 1))
    for expected_ordinal, source in zip(ordinals, ledger.sources, strict=True):
        if (
            type(source) is not OwnerPrivateOverlapLedgerSourceV1
            or not _is_closed_int(
                source.ordinal,
                minimum=expected_ordinal,
                maximum=expected_ordinal,
            )
            or not _is_closed_int(
                source.source_byte_count, minimum=1, maximum=MAX_PRIVATE_SOURCE_BYTES
            )
            or not _is_closed_int(
                source.source_token_count, minimum=1, maximum=MAX_PRIVATE_SOURCE_TOKENS
            )
            or source.source_token_count > source.source_byte_count
            or not _is_closed_int(
                source.representative_ordinal,
                minimum=1,
                maximum=expected_ordinal,
            )
        ):
            raise ValueError("owner-private overlap ledger source conflicts")
    aggregate_source_tokens = sum(source.source_token_count for source in ledger.sources)
    if (
        aggregate_source_tokens > MAX_PRIVATE_SOURCE_TOKENS
        or not _is_closed_int(
            ledger.candidate_pair_count,
            minimum=0,
            maximum=MAX_PRIVATE_MATCH_COMPARISONS,
        )
        or ledger.candidate_pair_count != ledger.output_token_count * aggregate_source_tokens
    ):
        raise ValueError("owner-private overlap ledger candidate conflicts")
    source_by_ordinal = {source.ordinal: source for source in ledger.sources}
    for row in ledger.rows:
        if (
            type(row) is not OwnerPrivateOverlapLedgerRowV1
            or not _is_closed_int(
                row.output_start, minimum=0, maximum=ledger.output_token_count - 1
            )
            or not _is_closed_int(row.output_end, minimum=1, maximum=ledger.output_token_count)
            or type(row.output_pointer) is not str
            or not row.output_pointer.startswith("/")
            or not 1 <= len(row.output_pointer) <= 16_384
            or not _is_closed_int(row.source_ordinal, minimum=1, maximum=len(ledger.sources))
            or row.source_ordinal not in source_by_ordinal
            or not _is_closed_int(
                row.source_start,
                minimum=0,
                maximum=source_by_ordinal[row.source_ordinal].source_token_count - 1,
            )
            or not _is_closed_int(
                row.source_end,
                minimum=1,
                maximum=source_by_ordinal[row.source_ordinal].source_token_count,
            )
            or not _is_closed_int(row.run_tokens, minimum=1, maximum=ledger.output_token_count)
            or row.output_end - row.output_start != row.run_tokens
            or row.source_end - row.source_start != row.run_tokens
            or not _valid_origin_spans(row.output_origin_spans, maximum=ledger.output_byte_count)
            or not _valid_origin_spans(
                row.source_origin_spans,
                maximum=source_by_ordinal[row.source_ordinal].source_byte_count,
            )
        ):
            raise ValueError("owner-private overlap ledger row conflicts")
    expected_rows = tuple(
        sorted(
            ledger.rows,
            key=lambda row: (
                row.output_start,
                row.source_ordinal,
                row.source_start,
                -row.run_tokens,
            ),
        )
    )
    if ledger.rows != expected_rows or len(set(ledger.rows)) != len(ledger.rows):
        raise ValueError("owner-private overlap ledger row order conflicts")
    metrics = ledger.metrics
    if (
        not _is_closed_int(
            metrics.max_contiguous_tokens,
            minimum=0,
            maximum=ledger.output_token_count,
        )
        or type(metrics.per_source_fragmented_tokens) is not tuple
        or not _is_closed_int(
            metrics.all_source_fragmented_tokens,
            minimum=0,
            maximum=ledger.output_token_count,
        )
        or not _is_closed_int(
            metrics.isolated_union_tokens,
            minimum=0,
            maximum=ledger.output_token_count,
        )
        or not _is_closed_int(
            metrics.match_row_count,
            minimum=len(ledger.rows),
            maximum=len(ledger.rows),
        )
        or len(metrics.per_source_fragmented_tokens) != len(ordinals)
    ):
        raise ValueError("owner-private overlap ledger metric shape conflicts")
    for expected_ordinal, pair in zip(ordinals, metrics.per_source_fragmented_tokens, strict=True):
        if (
            type(pair) is not tuple
            or len(pair) != 2
            or not _is_closed_int(pair[0], minimum=expected_ordinal, maximum=expected_ordinal)
            or not _is_closed_int(pair[1], minimum=0, maximum=ledger.output_token_count)
        ):
            raise ValueError("owner-private overlap ledger metric pair conflicts")
    per_source = tuple(
        (
            ordinal,
            _interval_union_count(
                [
                    (row.output_start, row.output_end)
                    for row in ledger.rows
                    if row.source_ordinal == ordinal and row.run_tokens >= 2
                ]
            ),
        )
        for ordinal in ordinals
    )
    representatives = {source.representative_ordinal for source in ledger.sources}
    all_fragmented = _interval_union_count(
        [
            (row.output_start, row.output_end)
            for row in ledger.rows
            if row.source_ordinal in representatives and row.run_tokens >= 2
        ]
    )
    isolated = _interval_union_count(
        [
            (row.output_start, row.output_end)
            for row in ledger.rows
            if row.source_ordinal in representatives and row.run_tokens == 1
        ]
    )
    max_contiguous = max((row.run_tokens for row in ledger.rows), default=0)
    if (
        metrics.max_contiguous_tokens != max_contiguous
        or metrics.per_source_fragmented_tokens != per_source
        or metrics.all_source_fragmented_tokens != all_fragmented
        or metrics.isolated_union_tokens != isolated
        or max_contiguous >= 12
        or any(count >= 24 or 5 * count >= ledger.output_token_count for _, count in per_source)
        or all_fragmented >= 32
        or 5 * all_fragmented >= ledger.output_token_count
        or (ledger.output_token_count >= 12 and 5 * isolated >= 3 * ledger.output_token_count)
    ):
        raise ValueError("owner-private overlap ledger verdict conflicts")


class OwnerPrivateOverlapCheckerContractV1(_Closed):
    schema_version: Literal[1] = 1
    checker_id: Literal["antiek-owner-private-verbatim-overlap-v1"] = (
        "antiek-owner-private-verbatim-overlap-v1"
    )
    unicode_version: Literal["16.0.0"] = "16.0.0"
    execution_ready: Literal[False] = False
    source_extractor_sha256: str = Field(pattern=_HEX64)
    normalizer_sha256: str = Field(pattern=_HEX64)
    threshold_sha256: str = Field(pattern=_HEX64)
    ledger_sha256: str = Field(pattern=_HEX64)
    golden_corpus_sha256: str = Field(pattern=_HEX64)
    executable_corpus_sha256: None = None
    max_output_bytes: Literal[1_000_000] = 1_000_000
    max_sources: Literal[8] = 8
    max_source_bytes: Literal[32_000] = 32_000
    max_output_leaves: Literal[256] = 256
    max_output_depth: Literal[32] = 32
    max_output_tokens: Literal[200_000] = 200_000
    max_source_tokens: Literal[256_000] = 256_000
    max_match_rows: Literal[100_000] = 100_000
    max_candidate_comparisons: Literal[25_000_000] = 25_000_000
    max_match_ledger_bytes: Literal[1_000_000] = 1_000_000
    checker_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOverlapCheckerContractV1:
        if (
            self.source_extractor_sha256 != PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
            or self.normalizer_sha256 != PRIVATE_OUTPUT_NORMALIZER_SHA256
            or self.threshold_sha256 != PRIVATE_OUTPUT_THRESHOLD_SHA256
            or self.ledger_sha256 != PRIVATE_OUTPUT_LEDGER_SHA256
            or self.golden_corpus_sha256 != PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256
            or self.executable_corpus_sha256 is not None
            or self.checker_sha256 != PRIVATE_OUTPUT_CHECKER_SHA256
        ):
            raise ValueError("owner-private checker contract conflicts")
        return self


class OwnerPrivateOutputPolicyV2(_Closed):
    schema_version: Literal[2] = 2
    policy_id: Literal["antiek-owner-private-provider-output-v2"] = (
        "antiek-owner-private-provider-output-v2"
    )
    predecessor_policy_sha256: str = Field(pattern=_HEX64)
    content_class: Literal["personal_reading"] = "personal_reading"
    candidate_sinks: tuple[str, ...]
    forbidden_sinks: tuple[str, ...]
    unknown_sink: Literal["deny"] = "deny"
    declassification: Literal["not_authorized"] = "not_authorized"
    public_serving_authorized: Literal[False] = False
    portable_export_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    checker_execution_ready: Literal[False] = False
    checker_sha256: str = Field(pattern=_HEX64)
    role_parser_sha256: str = Field(pattern=_HEX64)
    html_renderer_sha256: str = Field(pattern=_HEX64)
    source_extractor_sha256: str = Field(pattern=_HEX64)
    normalizer_sha256: str = Field(pattern=_HEX64)
    threshold_sha256: str = Field(pattern=_HEX64)
    ledger_sha256: str = Field(pattern=_HEX64)
    golden_corpus_sha256: str = Field(pattern=_HEX64)
    executable_corpus_sha256: None = None
    adapter_registry_sha256: str = Field(pattern=_HEX64)
    encryption_envelope_sha256: str = Field(pattern=_HEX64)
    policy_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOutputPolicyV2:
        if (
            self.predecessor_policy_sha256 != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
            or self.candidate_sinks != _CANDIDATE_SINKS
            or self.forbidden_sinks != _FORBIDDEN_SINKS
            or self.checker_sha256 != PRIVATE_OUTPUT_CHECKER_SHA256
            or self.role_parser_sha256 != PRIVATE_OUTPUT_ROLE_PARSER_SHA256
            or self.html_renderer_sha256 != PRIVATE_OUTPUT_HTML_RENDERER_SHA256
            or self.source_extractor_sha256 != PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
            or self.normalizer_sha256 != PRIVATE_OUTPUT_NORMALIZER_SHA256
            or self.threshold_sha256 != PRIVATE_OUTPUT_THRESHOLD_SHA256
            or self.ledger_sha256 != PRIVATE_OUTPUT_LEDGER_SHA256
            or self.golden_corpus_sha256 != PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256
            or self.executable_corpus_sha256 is not None
            or self.adapter_registry_sha256 != PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256
            or self.encryption_envelope_sha256 != PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256
            or self.policy_sha256 != owner_private_output_policy_v2_sha256(self)
        ):
            raise ValueError("owner-private output policy v2 conflicts")
        return self


def owner_private_output_policy_v2_sha256(
    policy: OwnerPrivateOutputPolicyV2 | Mapping[str, object],
) -> str:
    raw = policy.model_dump(mode="json") if isinstance(policy, BaseModel) else dict(policy)
    material = {key: value for key, value in raw.items() if key != "policy_sha256"}
    return _digest(_POLICY_DOMAIN, material)


def canonical_owner_private_overlap_ledger_v1(
    ledger: OwnerPrivateOverlapLedgerV1,
) -> bytes:
    """Return the sole canonical PASS-ledger wire encoding."""
    try:
        _validate_owner_private_overlap_ledger_v1(ledger)
        encoded = _canonical_json(asdict(ledger))
    except Exception:
        pass
    else:
        if len(encoded) <= MAX_PRIVATE_MATCH_LEDGER_BYTES:
            return encoded
    raise OwnerPrivateOverlapLedgerRejected() from None


def owner_private_overlap_ledger_v1_sha256(
    ledger: OwnerPrivateOverlapLedgerV1,
) -> str:
    """Digest domain bytes directly concatenated with canonical ledger bytes."""
    return hashlib.sha256(
        _LEDGER_DOMAIN + canonical_owner_private_overlap_ledger_v1(ledger)
    ).hexdigest()


def build_owner_private_overlap_checker_contract_v1() -> OwnerPrivateOverlapCheckerContractV1:
    return OwnerPrivateOverlapCheckerContractV1(
        source_extractor_sha256=PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
        normalizer_sha256=PRIVATE_OUTPUT_NORMALIZER_SHA256,
        threshold_sha256=PRIVATE_OUTPUT_THRESHOLD_SHA256,
        ledger_sha256=PRIVATE_OUTPUT_LEDGER_SHA256,
        golden_corpus_sha256=PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256,
        checker_sha256=PRIVATE_OUTPUT_CHECKER_SHA256,
    )


def build_owner_private_output_policy_v2() -> OwnerPrivateOutputPolicyV2:
    material = dict(_POLICY_MATERIAL_V2)
    digest = owner_private_output_policy_v2_sha256(material)
    return OwnerPrivateOutputPolicyV2.model_validate({**material, "policy_sha256": digest})


def require_private_output_unicode_runtime() -> None:
    if (
        unicodedata.unidata_version != PRIVATE_OUTPUT_UNICODE_VERSION
        or private_output_unicode_table_sha256() != PRIVATE_OUTPUT_UNICODE_TABLE_SHA256
    ):
        raise RuntimeError("owner-private Unicode runtime is unavailable")


def private_output_unicode_table_sha256() -> str:
    """Hash the runtime normalization, casefold, and category tables."""

    digest = hashlib.sha256(_UNICODE_TABLE_DOMAIN)
    for codepoint in range(0x110000):
        character = chr(codepoint)
        digest.update(codepoint.to_bytes(4, "big"))
        digest.update(unicodedata.category(character).encode("ascii"))
        digest.update(b"\x00")
        digest.update(unicodedata.combining(character).to_bytes(1, "big"))
        digest.update(b"\x00")
        digest.update(unicodedata.decomposition(character).encode("ascii"))
        digest.update(b"\x00")
        digest.update(
            unicodedata.normalize("NFKC", character).encode("utf-8", errors="surrogatepass")
        )
        digest.update(b"\x00")
        digest.update(character.casefold().encode("utf-8", errors="surrogatepass"))
        digest.update(b"\x00")
    return digest.hexdigest()


__all__ = [
    "MAX_PRIVATE_MATCH_COMPARISONS",
    "MAX_PRIVATE_MATCH_LEDGER_BYTES",
    "MAX_PRIVATE_MATCH_ROWS",
    "MAX_PRIVATE_OUTPUT_BYTES",
    "MAX_PRIVATE_OUTPUT_DEPTH",
    "MAX_PRIVATE_OUTPUT_LEAVES",
    "MAX_PRIVATE_OUTPUT_SOURCES",
    "MAX_PRIVATE_OUTPUT_TOKENS",
    "MAX_PRIVATE_SOURCE_BYTES",
    "MAX_PRIVATE_SOURCE_TOKENS",
    "OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256",
    "PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256",
    "PRIVATE_OUTPUT_CHECKER_SHA256",
    "PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256",
    "PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256",
    "PRIVATE_OUTPUT_HTML_RENDERER_SHA256",
    "PRIVATE_OUTPUT_LEDGER_SHA256",
    "PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256",
    "PRIVATE_OUTPUT_NORMALIZER_SHA256",
    "PRIVATE_OUTPUT_ROLE_PARSER_SHA256",
    "PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256",
    "PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256",
    "PRIVATE_OUTPUT_THRESHOLD_SHA256",
    "PRIVATE_OUTPUT_UNICODE_VERSION",
    "PRIVATE_OUTPUT_UNICODE_TABLE_SHA256",
    "OwnerPrivateOutputPolicyV2",
    "OwnerPrivateOverlapCheckerContractV1",
    "build_owner_private_output_policy_v2",
    "build_owner_private_overlap_checker_contract_v1",
    "owner_private_output_policy_v2_sha256",
    "private_output_unicode_table_sha256",
    "require_private_output_unicode_runtime",
]
