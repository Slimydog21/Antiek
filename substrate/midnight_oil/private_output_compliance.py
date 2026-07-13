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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    "af0ad93f2f73bbb6c257ef487864ee0b4b86670455be07a989f3c8771acf6b10"
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
    "planner": ("/role",),
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


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(domain: bytes, material: object) -> str:
    return hashlib.sha256(domain + _canonical_json(material)).hexdigest()


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
    "stopword_removal": False,
}
PRIVATE_OUTPUT_NORMALIZER_SHA256 = _digest(
    _NORMALIZER_DOMAIN, _NORMALIZER_MATERIAL
)

_EXTRACTOR_MATERIAL = {
    "schema_version": 1,
    "extractor_id": "owner_supplied_local_excerpt_utf8_v1",
    "source_bytes": "exact_receipt_v5_committed_utf8_range",
    "refetch": "deny",
    "render": "deny",
    "entity_decode": "deny",
    "other_media": "deny",
}
PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256 = _digest(
    _EXTRACTOR_DOMAIN, _EXTRACTOR_MATERIAL
)

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
PRIVATE_OUTPUT_THRESHOLD_SHA256 = _digest(
    _THRESHOLD_DOMAIN, _THRESHOLD_MATERIAL
)

_CHECKER_MATERIAL = {
    "schema_version": 1,
    "checker_id": "antiek-owner-private-verbatim-overlap-v1",
    "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "normalizer_sha256": PRIVATE_OUTPUT_NORMALIZER_SHA256,
    "threshold_sha256": PRIVATE_OUTPUT_THRESHOLD_SHA256,
    "output_order": "closed_role_schema_field_order_with_leaf_boundaries",
    "leaf_boundary": "break_contiguous_but_retain_fragmented_coverage",
    "enumeration": "all_maximal_equal_token_runs_length_at_least_one",
    "match_order": (
        "output_start",
        "source_ordinal",
        "source_start",
        "descending_length",
    ),
    "duplicate_source_representative": "lowest_source_ordinal",
    "overlapping_matches": "preserve_all_rows",
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
    "overflow": "content_free_fail_closed",
    "byte_offsets": "original_utf8_half_open_spans_per_output_leaf",
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
PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256 = _digest(
    _ENVELOPE_DOMAIN, _ENVELOPE_MATERIAL
)

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
    "role_parser_sha256": PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    "html_renderer_sha256": PRIVATE_OUTPUT_HTML_RENDERER_SHA256,
    "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "normalizer_sha256": PRIVATE_OUTPUT_NORMALIZER_SHA256,
    "threshold_sha256": PRIVATE_OUTPUT_THRESHOLD_SHA256,
    "golden_corpus_sha256": PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256,
    "adapter_registry_sha256": PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256,
    "encryption_envelope_sha256": PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256,
}
OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256 = _digest(
    _POLICY_DOMAIN, _POLICY_MATERIAL_V2
)


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class OwnerPrivateOverlapCheckerContractV1(_Closed):
    schema_version: Literal[1] = 1
    checker_id: Literal["antiek-owner-private-verbatim-overlap-v1"] = (
        "antiek-owner-private-verbatim-overlap-v1"
    )
    unicode_version: Literal["16.0.0"] = "16.0.0"
    source_extractor_sha256: str = Field(pattern=_HEX64)
    normalizer_sha256: str = Field(pattern=_HEX64)
    threshold_sha256: str = Field(pattern=_HEX64)
    golden_corpus_sha256: str = Field(pattern=_HEX64)
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
            or self.golden_corpus_sha256 != PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256
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
    checker_sha256: str = Field(pattern=_HEX64)
    role_parser_sha256: str = Field(pattern=_HEX64)
    html_renderer_sha256: str = Field(pattern=_HEX64)
    source_extractor_sha256: str = Field(pattern=_HEX64)
    normalizer_sha256: str = Field(pattern=_HEX64)
    threshold_sha256: str = Field(pattern=_HEX64)
    golden_corpus_sha256: str = Field(pattern=_HEX64)
    adapter_registry_sha256: str = Field(pattern=_HEX64)
    encryption_envelope_sha256: str = Field(pattern=_HEX64)
    policy_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOutputPolicyV2:
        if (
            self.predecessor_policy_sha256
            != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
            or self.candidate_sinks != _CANDIDATE_SINKS
            or self.forbidden_sinks != _FORBIDDEN_SINKS
            or self.checker_sha256 != PRIVATE_OUTPUT_CHECKER_SHA256
            or self.role_parser_sha256 != PRIVATE_OUTPUT_ROLE_PARSER_SHA256
            or self.html_renderer_sha256 != PRIVATE_OUTPUT_HTML_RENDERER_SHA256
            or self.source_extractor_sha256
            != PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256
            or self.normalizer_sha256 != PRIVATE_OUTPUT_NORMALIZER_SHA256
            or self.threshold_sha256 != PRIVATE_OUTPUT_THRESHOLD_SHA256
            or self.golden_corpus_sha256 != PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256
            or self.adapter_registry_sha256
            != PRIVATE_OUTPUT_ADAPTER_REGISTRY_SHA256
            or self.encryption_envelope_sha256
            != PRIVATE_OUTPUT_ENCRYPTION_ENVELOPE_SHA256
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


def build_owner_private_overlap_checker_contract_v1() -> OwnerPrivateOverlapCheckerContractV1:
    return OwnerPrivateOverlapCheckerContractV1(
        source_extractor_sha256=PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
        normalizer_sha256=PRIVATE_OUTPUT_NORMALIZER_SHA256,
        threshold_sha256=PRIVATE_OUTPUT_THRESHOLD_SHA256,
        golden_corpus_sha256=PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256,
        checker_sha256=PRIVATE_OUTPUT_CHECKER_SHA256,
    )


def build_owner_private_output_policy_v2() -> OwnerPrivateOutputPolicyV2:
    material = dict(_POLICY_MATERIAL_V2)
    digest = owner_private_output_policy_v2_sha256(material)
    return OwnerPrivateOutputPolicyV2.model_validate(
        {**material, "policy_sha256": digest}
    )


def require_private_output_unicode_runtime() -> None:
    if (
        unicodedata.unidata_version != PRIVATE_OUTPUT_UNICODE_VERSION
        or private_output_unicode_table_sha256()
        != PRIVATE_OUTPUT_UNICODE_TABLE_SHA256
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
        digest.update(
            unicodedata.normalize("NFKC", character).encode(
                "utf-8", errors="surrogatepass"
            )
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
    "PRIVATE_OUTPUT_NORMALIZER_SHA256",
    "PRIVATE_OUTPUT_ROLE_PARSER_SHA256",
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
