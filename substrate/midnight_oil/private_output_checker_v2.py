"""Executable, non-conferring owner-private overlap checker primitives.

This module is deliberately absent from application composition and package exports.
It performs deterministic in-memory parsing, normalization, matching, and PASS-ledger
construction only.  It grants no provider, persistence, receipt, taint, or sink authority.
"""

from __future__ import annotations

import ast
import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import private_output_compliance as predecessor
from .live_roles import GathererOutput, PlannerOutput, SynthesizerOutput, VerifierOutput

_HEX64 = r"^[0-9a-f]{64}$"
_COMPOSITION_DOMAIN = b"antiek.midnight-oil.unicode16-composition-pairs.v2\x00"
_UNICODE_DOMAIN = b"antiek.midnight-oil.unicode16-attributed-data.v2\x00"
_NORMALIZER_DOMAIN = b"antiek.midnight-oil.owner-private-attributed-normalizer.v2\x00"
_LEDGER_DOMAIN = b"antiek.midnight-oil.owner-private-overlap-ledger.v2\x00"
_CHECKER_DOMAIN = b"antiek.midnight-oil.owner-private-overlap-algorithm.v2\x00"
_CONTRACT_DOMAIN = b"antiek.midnight-oil.owner-private-overlap-contract.v2\x00"

_SBASE = 0xAC00
_LBASE = 0x1100
_VBASE = 0x1161
_TBASE = 0x11A7
_LCOUNT = 19
_VCOUNT = 21
_TCOUNT = 28
_NCOUNT = _VCOUNT * _TCOUNT
_SCOUNT = _LCOUNT * _NCOUNT


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _digest(domain: bytes, material: object) -> str:
    return hashlib.sha256(domain + _canonical_json(material)).hexdigest()


class OwnerPrivateOverlapCheckRejected(ValueError):
    """The sole content-free failure visible outside the checker boundary."""

    def __init__(self) -> None:
        super().__init__("owner-private overlap check rejected")

    def __repr__(self) -> str:
        return "OwnerPrivateOverlapCheckRejected()"


class _PrivateValue:
    def __repr__(self) -> str:
        return f"{type(self).__name__}(<owner-private>)"

    def __str__(self) -> str:
        return self.__repr__()


OriginSpans = tuple[tuple[int, int], ...]
OwnerPrivateOverlapResourceMeasureV2 = Literal[
    "output_bytes",
    "sources",
    "source_bytes",
    "leaves",
    "depth",
    "output_tokens",
    "source_tokens",
    "match_rows",
    "candidate_comparisons",
    "ledger_bytes",
]

_RESOURCE_LIMITS_V2: Mapping[OwnerPrivateOverlapResourceMeasureV2, int] = {
    "output_bytes": predecessor.MAX_PRIVATE_OUTPUT_BYTES,
    "sources": predecessor.MAX_PRIVATE_OUTPUT_SOURCES,
    "source_bytes": predecessor.MAX_PRIVATE_SOURCE_BYTES,
    "leaves": predecessor.MAX_PRIVATE_OUTPUT_LEAVES,
    "depth": predecessor.MAX_PRIVATE_OUTPUT_DEPTH,
    "output_tokens": predecessor.MAX_PRIVATE_OUTPUT_TOKENS,
    "source_tokens": predecessor.MAX_PRIVATE_SOURCE_TOKENS,
    "match_rows": predecessor.MAX_PRIVATE_MATCH_ROWS,
    "candidate_comparisons": predecessor.MAX_PRIVATE_MATCH_COMPARISONS,
    "ledger_bytes": predecessor.MAX_PRIVATE_MATCH_LEDGER_BYTES,
}


def owner_private_overlap_resource_limit_v2(
    measure: OwnerPrivateOverlapResourceMeasureV2,
) -> int:
    if type(measure) is not str or measure not in _RESOURCE_LIMITS_V2:
        raise ValueError("owner-private resource measure conflicts")
    return _RESOURCE_LIMITS_V2[measure]


def owner_private_overlap_resource_allows_v2(
    measure: OwnerPrivateOverlapResourceMeasureV2, observed: int
) -> bool:
    if type(observed) is not int or observed < 0:
        raise ValueError("owner-private resource observation conflicts")
    return observed <= owner_private_overlap_resource_limit_v2(measure)


def guard_owner_private_overlap_resource_v2(
    measure: OwnerPrivateOverlapResourceMeasureV2, observed: int
) -> None:
    if not owner_private_overlap_resource_allows_v2(measure, observed):
        raise ValueError("owner-private resource bound conflicts")


@dataclass(frozen=True, repr=False)
class OwnerPrivateNormalizedTokenV2(_PrivateValue):
    value: str
    origin_spans: OriginSpans


@dataclass(frozen=True, repr=False)
class OwnerPrivateContentLeafV2(_PrivateValue):
    pointer: str
    tokens: tuple[OwnerPrivateNormalizedTokenV2, ...]


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapSourceV2(_PrivateValue):
    ordinal: int
    exact_bytes: bytes


@dataclass(frozen=True, repr=False)
class _AttributedScalar(_PrivateValue):
    codepoint: int
    origins: OriginSpans


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerSourceV2(_PrivateValue):
    ordinal: int
    source_byte_count: int
    source_token_count: int
    representative_ordinal: int


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerRowV2(_PrivateValue):
    output_start: int
    output_end: int
    output_pointer: str
    output_origin_spans: OriginSpans
    source_ordinal: int
    source_start: int
    source_end: int
    source_origin_spans: OriginSpans
    run_tokens: int


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerMetricsV2(_PrivateValue):
    max_contiguous_tokens: int
    per_source_fragmented_tokens: tuple[tuple[int, int], ...]
    all_source_fragmented_tokens: int
    isolated_union_tokens: int
    match_row_count: int


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapLedgerV2(_PrivateValue):
    checker_sha256: str
    output_byte_count: int
    output_token_count: int
    sources: tuple[OwnerPrivateOverlapLedgerSourceV2, ...]
    candidate_pair_count: int
    rows: tuple[OwnerPrivateOverlapLedgerRowV2, ...]
    metrics: OwnerPrivateOverlapLedgerMetricsV2
    schema_version: Literal[2] = 2
    verdict: Literal["pass"] = "pass"


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapPassV2(_PrivateValue):
    ledger: OwnerPrivateOverlapLedgerV2
    ledger_bytes: bytes
    ledger_sha256: str
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False


@dataclass(frozen=True, repr=False)
class OwnerPrivateOverlapNotApplicableV2(_PrivateValue):
    role: Literal["planner"] = "planner"
    source_overlap: Literal["not_applicable"] = "not_applicable"
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False


def _coalesce_spans(spans: Sequence[tuple[int, int]]) -> OriginSpans:
    if not spans:
        raise ValueError("attributed scalar lost provenance")
    ordered = sorted(spans)
    result: list[tuple[int, int]] = []
    for start, end in ordered:
        if type(start) is not int or type(end) is not int or start < 0 or end <= start:
            raise ValueError("invalid attributed origin")
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return tuple(result)


def _union_origins(*values: OriginSpans) -> OriginSpans:
    return _coalesce_spans([span for origins in values for span in origins])


def _is_noncharacter(codepoint: int) -> bool:
    return 0xFDD0 <= codepoint <= 0xFDEF or codepoint & 0xFFFF in {0xFFFE, 0xFFFF}


def _is_interval_member(codepoint: int, intervals: Sequence[tuple[int, int]]) -> bool:
    return any(start <= codepoint <= end for start, end in intervals)


def _validate_input_scalar(codepoint: int) -> None:
    permitted_control_whitespace = _is_interval_member(
        codepoint, predecessor._WHITESPACE_INTERVALS
    )
    if (
        0xD800 <= codepoint <= 0xDFFF
        or _is_noncharacter(codepoint)
        or ((codepoint <= 0x1F or 0x7F <= codepoint <= 0x9F) and not permitted_control_whitespace)
    ):
        raise ValueError("owner-private input scalar is unavailable")


@lru_cache(maxsize=1)
def _composition_pairs() -> tuple[tuple[tuple[int, int], int], ...]:
    pairs: dict[tuple[int, int], int] = {}
    for codepoint in range(0x110000):
        raw = unicodedata.decomposition(chr(codepoint))
        if not raw or raw.startswith("<"):
            continue
        parts = tuple(int(part, 16) for part in raw.split())
        if len(parts) != 2:
            continue
        pair = (parts[0], parts[1])
        if unicodedata.normalize("NFC", "".join(chr(part) for part in pair)) != chr(codepoint):
            continue
        previous = pairs.setdefault(pair, codepoint)
        if previous != codepoint:
            raise RuntimeError("Unicode composition pair is ambiguous")
    return tuple(sorted(pairs.items()))


def private_output_composition_pairs_v2_sha256() -> str:
    digest = hashlib.sha256(_COMPOSITION_DOMAIN)
    for (first, second), composite in _composition_pairs():
        digest.update(first.to_bytes(4, "big"))
        digest.update(second.to_bytes(4, "big"))
        digest.update(composite.to_bytes(4, "big"))
    return digest.hexdigest()


PRIVATE_OUTPUT_COMPOSITION_PAIR_COUNT_V2 = 1_360
PRIVATE_OUTPUT_COMPOSITION_PAIRS_V2_SHA256 = (
    "e999a2b6a856b647618bf6fab6ce16b06427ef36a65f85f4d4516b5e7b5247d6"
)


@lru_cache(maxsize=1)
def _verify_frozen_unicode_tables_v2() -> None:
    predecessor.require_private_output_unicode_runtime()
    if (
        len(_composition_pairs()) != PRIVATE_OUTPUT_COMPOSITION_PAIR_COUNT_V2
        or private_output_composition_pairs_v2_sha256()
        != PRIVATE_OUTPUT_COMPOSITION_PAIRS_V2_SHA256
    ):
        raise RuntimeError("owner-private executable Unicode runtime is unavailable")


def _require_frozen_unicode_runtime_v2() -> None:
    if unicodedata.unidata_version != predecessor.PRIVATE_OUTPUT_UNICODE_VERSION:
        raise RuntimeError("owner-private executable Unicode runtime is unavailable")
    _verify_frozen_unicode_tables_v2()


def _hangul_decomposition(codepoint: int) -> tuple[int, ...] | None:
    index = codepoint - _SBASE
    if not 0 <= index < _SCOUNT:
        return None
    leading = _LBASE + index // _NCOUNT
    vowel = _VBASE + (index % _NCOUNT) // _TCOUNT
    trailing_index = index % _TCOUNT
    if trailing_index == 0:
        return (leading, vowel)
    return (leading, vowel, _TBASE + trailing_index)


@cache
def _recursive_compatibility_decomposition(codepoint: int) -> tuple[int, ...]:
    hangul = _hangul_decomposition(codepoint)
    if hangul is not None:
        return tuple(
            child
            for part in hangul
            for child in _recursive_compatibility_decomposition(part)
        )
    raw = unicodedata.decomposition(chr(codepoint))
    if not raw:
        return (codepoint,)
    parts = raw.split()
    if parts[0].startswith("<"):
        parts = parts[1:]
    if not parts:
        return (codepoint,)
    mapped = tuple(int(part, 16) for part in parts)
    if codepoint in mapped:
        raise RuntimeError("Unicode decomposition cycle")
    return tuple(
        child
        for part in mapped
        for child in _recursive_compatibility_decomposition(part)
    )


def _canonical_order(scalars: Sequence[_AttributedScalar]) -> list[_AttributedScalar]:
    ordered: list[_AttributedScalar] = []
    segment_start = 0
    for scalar in scalars:
        ccc = unicodedata.combining(chr(scalar.codepoint))
        if ccc == 0:
            ordered.append(scalar)
            segment_start = len(ordered)
            continue
        position = len(ordered)
        while (
            position > segment_start
            and unicodedata.combining(chr(ordered[position - 1].codepoint)) > ccc
        ):
            position -= 1
        ordered.insert(position, scalar)
    return ordered


def _hangul_composite(first: int, second: int) -> int | None:
    leading_index = first - _LBASE
    if 0 <= leading_index < _LCOUNT and _VBASE <= second < _VBASE + _VCOUNT:
        return _SBASE + (leading_index * _VCOUNT + second - _VBASE) * _TCOUNT
    syllable_index = first - _SBASE
    if (
        0 <= syllable_index < _SCOUNT
        and syllable_index % _TCOUNT == 0
        and _TBASE < second < _TBASE + _TCOUNT
    ):
        return first + second - _TBASE
    return None


@lru_cache(maxsize=1)
def _composition_map() -> Mapping[tuple[int, int], int]:
    return dict(_composition_pairs())


def _compose(scalars: Sequence[_AttributedScalar]) -> list[_AttributedScalar]:
    if not scalars:
        return []
    result = [scalars[0]]
    starter_index: int | None = 0 if unicodedata.combining(chr(scalars[0].codepoint)) == 0 else None
    last_ccc = unicodedata.combining(chr(scalars[0].codepoint))
    for scalar in scalars[1:]:
        ccc = unicodedata.combining(chr(scalar.codepoint))
        composite: int | None = None
        if starter_index is not None and (last_ccc == 0 or last_ccc < ccc):
            starter = result[starter_index]
            composite = _hangul_composite(starter.codepoint, scalar.codepoint)
            if composite is None:
                composite = _composition_map().get((starter.codepoint, scalar.codepoint))
        if composite is not None and starter_index is not None:
            starter = result[starter_index]
            result[starter_index] = _AttributedScalar(
                composite, _union_origins(starter.origins, scalar.origins)
            )
            continue
        result.append(scalar)
        if ccc == 0:
            starter_index = len(result) - 1
        last_ccc = ccc
    return result


def _attributed_nfkc(scalars: Sequence[_AttributedScalar]) -> list[_AttributedScalar]:
    source_text = "".join(chr(scalar.codepoint) for scalar in scalars)
    decomposed = [
        _AttributedScalar(codepoint, scalar.origins)
        for scalar in scalars
        for codepoint in _recursive_compatibility_decomposition(scalar.codepoint)
    ]
    result = _compose(_canonical_order(decomposed))
    if "".join(chr(scalar.codepoint) for scalar in result) != unicodedata.normalize(
        "NFKC", source_text
    ):
        raise RuntimeError("attributed NFKC diverged from Unicode runtime")
    return result


def _decode_attributed(raw: bytes) -> list[_AttributedScalar]:
    if type(raw) is not bytes or not raw:
        raise ValueError("owner-private UTF-8 input shape conflicts")
    text = raw.decode("utf-8", errors="strict")
    offset = 0
    result: list[_AttributedScalar] = []
    for character in text:
        codepoint = ord(character)
        _validate_input_scalar(codepoint)
        encoded = character.encode("utf-8")
        result.append(_AttributedScalar(codepoint, ((offset, offset + len(encoded)),)))
        offset += len(encoded)
    return result


def _mapped_scalars(scalars: Sequence[_AttributedScalar]) -> list[_AttributedScalar]:
    quote_map = dict(predecessor._QUOTE_MAP)
    dash_codepoints = set(predecessor._DASH_CODEPOINTS)
    result: list[_AttributedScalar] = []
    for scalar in scalars:
        codepoint = scalar.codepoint
        if _is_interval_member(codepoint, predecessor._REMOVED_INTERVALS):
            continue
        mapped: str
        if _is_interval_member(codepoint, predecessor._WHITESPACE_INTERVALS):
            mapped = " "
        elif codepoint in quote_map:
            mapped = quote_map[codepoint]
        elif codepoint in dash_codepoints:
            mapped = "-"
        else:
            mapped = chr(codepoint)
        result.extend(_AttributedScalar(ord(character), scalar.origins) for character in mapped)
    return result


def _normalize_utf8(raw: bytes) -> tuple[OwnerPrivateNormalizedTokenV2, ...]:
    scalars = _attributed_nfkc(_decode_attributed(raw))
    folded = [
        _AttributedScalar(ord(character), scalar.origins)
        for scalar in scalars
        for character in chr(scalar.codepoint).casefold()
    ]
    if "".join(chr(scalar.codepoint) for scalar in folded) != "".join(
        chr(scalar.codepoint) for scalar in scalars
    ).casefold():
        raise RuntimeError("attributed casefold diverged from Unicode runtime")
    mapped = _mapped_scalars(_attributed_nfkc(folded))
    tokens: list[OwnerPrivateNormalizedTokenV2] = []
    current: list[_AttributedScalar] = []
    for scalar in mapped:
        if unicodedata.category(chr(scalar.codepoint))[0] in {"L", "N"}:
            current.append(scalar)
        elif current:
            tokens.append(
                OwnerPrivateNormalizedTokenV2(
                    "".join(chr(item.codepoint) for item in current),
                    _union_origins(*(item.origins for item in current)),
                )
            )
            current = []
    if current:
        tokens.append(
            OwnerPrivateNormalizedTokenV2(
                "".join(chr(item.codepoint) for item in current),
                _union_origins(*(item.origins for item in current)),
            )
        )
    return tuple(tokens)


def normalize_owner_private_utf8_v2(raw: bytes) -> tuple[OwnerPrivateNormalizedTokenV2, ...]:
    """Normalize exact UTF-8 bytes while retaining disjoint contributor spans."""
    try:
        _require_frozen_unicode_runtime_v2()
        return _normalize_utf8(raw)
    except Exception:
        pass
    raise OwnerPrivateOverlapCheckRejected() from None


_ROLE_MODELS: Mapping[str, type[BaseModel]] = {
    "planner": PlannerOutput,
    "gatherer": GathererOutput,
    "verifier": VerifierOutput,
    "synthesizer": SynthesizerOutput,
}


def _reject_json_constant(_: str) -> None:
    raise ValueError("non-finite JSON is unavailable")


def _reject_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON name")
        result[key] = value
    return result


def _parse_role_output(raw: bytes) -> BaseModel:
    if type(raw) is not bytes or not raw:
        raise ValueError("role output byte bound conflicts")
    guard_owner_private_overlap_resource_v2("output_bytes", len(raw))
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("role output BOM conflicts")
    text = raw.decode("utf-8", errors="strict")
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_object,
        parse_constant=_reject_json_constant,
    )
    if type(value) is not dict or type(value.get("role")) is not str:
        raise ValueError("role discriminator conflicts")
    model_type = _ROLE_MODELS.get(value["role"])
    if model_type is None:
        raise ValueError("role discriminator conflicts")
    # JSON has no tuple token; Pydantic's JSON path preserves strict scalar
    # validation while admitting JSON arrays for the role models' frozen tuples.
    model = model_type.model_validate_json(raw)
    if _canonical_json(model.model_dump(mode="json")) != raw:
        raise ValueError("role output is not canonical")
    return model


def _pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer_segments(pointer: str) -> tuple[str, ...]:
    return tuple(pointer[1:].split("/")) if pointer else ()


def _matches_exemption(role: str, pointer: str) -> bool:
    actual = _pointer_segments(pointer)
    for pattern in predecessor._EXEMPT_POINTER_PATTERNS[role]:
        expected = _pointer_segments(pattern)
        if len(actual) != len(expected):
            continue
        if all(
            wanted == observed or (wanted == "*" and observed.isdecimal())
            for wanted, observed in zip(expected, actual, strict=True)
        ):
            return True
    return False


def _schema_order_key(pointer: str) -> str:
    segments = tuple("*" if segment.isdecimal() else segment for segment in _pointer_segments(pointer))
    return "/" if not segments else "/" + "/".join(segments)


def _extract_content_leaves(model: BaseModel) -> tuple[OwnerPrivateContentLeafV2, ...]:
    role_value = model.model_dump(mode="python").get("role")
    if type(role_value) is not str:
        raise ValueError("role discriminator conflicts")
    role = role_value
    order_map = dict(predecessor._ROLE_SCHEMA_FIELD_ORDER[role])
    leaves: list[OwnerPrivateContentLeafV2] = []
    maximum_depth = 0

    def visit(value: object, pointer: str, depth: int) -> None:
        nonlocal maximum_depth
        maximum_depth = max(maximum_depth, depth)
        guard_owner_private_overlap_resource_v2("depth", maximum_depth)
        if type(value) is dict:
            expected = order_map.get(_schema_order_key(pointer))
            if expected is None or set(value) != set(expected):
                raise ValueError("declared role field order conflicts")
            for key in expected:
                child = pointer + "/" + _pointer_segment(key)
                visit(value[key], child, depth + 1)
        elif type(value) in {list, tuple}:
            for index, child_value in enumerate(cast(Sequence[object], value)):
                visit(child_value, pointer + f"/{index}", depth + 1)
        elif type(value) is str and not _matches_exemption(role, pointer):
            guard_owner_private_overlap_resource_v2("leaves", len(leaves) + 1)
            leaves.append(OwnerPrivateContentLeafV2(pointer, _normalize_utf8(value.encode("utf-8"))))

    visit(model.model_dump(mode="python"), "", 0)
    return tuple(leaves)


def _interval_union_count(intervals: Sequence[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    result = 0
    current_start, current_end = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start > current_end:
            result += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    return result + current_end - current_start


def owner_private_overlap_threshold_failed_v2(
    *,
    output_token_count: int,
    max_contiguous_tokens: int,
    per_source_fragmented_tokens: tuple[tuple[int, int], ...],
    all_source_fragmented_tokens: int,
    isolated_union_tokens: int,
) -> bool:
    """Evaluate the exact production threshold predicates over content-free counts."""
    if (
        not _closed_int(output_token_count, 1, predecessor.MAX_PRIVATE_OUTPUT_TOKENS)
        or not _closed_int(max_contiguous_tokens, 0, output_token_count)
        or type(per_source_fragmented_tokens) is not tuple
        or not 1 <= len(per_source_fragmented_tokens) <= predecessor.MAX_PRIVATE_OUTPUT_SOURCES
        or not _closed_int(all_source_fragmented_tokens, 0, output_token_count)
        or not _closed_int(isolated_union_tokens, 0, output_token_count)
    ):
        raise ValueError("owner-private threshold observation conflicts")
    for expected_ordinal, pair in enumerate(per_source_fragmented_tokens, start=1):
        if (
            type(pair) is not tuple
            or len(pair) != 2
            or not _closed_int(pair[0], expected_ordinal, expected_ordinal)
            or not _closed_int(pair[1], 0, output_token_count)
        ):
            raise ValueError("owner-private threshold source observation conflicts")
    return (
        max_contiguous_tokens >= 12
        or any(
            covered >= 24 or 5 * covered >= output_token_count
            for _, covered in per_source_fragmented_tokens
        )
        or all_source_fragmented_tokens >= 32
        or 5 * all_source_fragmented_tokens >= output_token_count
        or (
            output_token_count >= 12
            and 5 * isolated_union_tokens >= 3 * output_token_count
        )
    )


PRIVATE_OUTPUT_EXECUTABLE_UNICODE_TABLE_V2_SHA256: str
PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256: str
PRIVATE_OUTPUT_LEDGER_V2_SHA256: str
PRIVATE_OUTPUT_CHECKER_V2_SHA256: str
PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256: str


def _build_match_rows(
    leaves: Sequence[OwnerPrivateContentLeafV2],
    sources: Sequence[tuple[OwnerPrivateOverlapSourceV2, tuple[OwnerPrivateNormalizedTokenV2, ...], int]],
) -> tuple[OwnerPrivateOverlapLedgerRowV2, ...]:
    rows: list[OwnerPrivateOverlapLedgerRowV2] = []
    output_base = 0
    for leaf in leaves:
        output_values = tuple(token.value for token in leaf.tokens)
        for source, source_tokens, _representative in sources:
            source_values = tuple(token.value for token in source_tokens)
            next_lengths = [0] * (len(source_values) + 1)
            for output_index in range(len(output_values) - 1, -1, -1):
                current_lengths = [0] * (len(source_values) + 1)
                for source_index in range(len(source_values) - 1, -1, -1):
                    if output_values[output_index] != source_values[source_index]:
                        continue
                    run_tokens = 1 + next_lengths[source_index + 1]
                    current_lengths[source_index] = run_tokens
                    rows.append(
                        OwnerPrivateOverlapLedgerRowV2(
                            output_start=output_base + output_index,
                            output_end=output_base + output_index + run_tokens,
                            output_pointer=leaf.pointer,
                            output_origin_spans=_union_origins(
                                *(token.origin_spans for token in leaf.tokens[output_index : output_index + run_tokens])
                            ),
                            source_ordinal=source.ordinal,
                            source_start=source_index,
                            source_end=source_index + run_tokens,
                            source_origin_spans=_union_origins(
                                *(token.origin_spans for token in source_tokens[source_index : source_index + run_tokens])
                            ),
                            run_tokens=run_tokens,
                        )
                    )
                    guard_owner_private_overlap_resource_v2("match_rows", len(rows))
                next_lengths = current_lengths
        output_base += len(leaf.tokens)
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.output_start,
                row.source_ordinal,
                row.source_start,
                -row.run_tokens,
            ),
        )
    )


def _build_ledger(
    *,
    output_bytes: bytes,
    leaves: Sequence[OwnerPrivateContentLeafV2],
    sources: Sequence[tuple[OwnerPrivateOverlapSourceV2, tuple[OwnerPrivateNormalizedTokenV2, ...], int]],
) -> OwnerPrivateOverlapLedgerV2:
    output_token_count = sum(len(leaf.tokens) for leaf in leaves)
    if (
        output_token_count == 0
        or output_token_count > len(output_bytes)
    ):
        raise ValueError("owner-private output has no comparable tokens")
    guard_owner_private_overlap_resource_v2("output_tokens", output_token_count)
    aggregate_source_tokens = sum(len(tokens) for _, tokens, _ in sources)
    candidate_pairs = sum(
        len(leaf.tokens) * len(tokens) for leaf in leaves for _, tokens, _ in sources
    )
    guard_owner_private_overlap_resource_v2("source_tokens", aggregate_source_tokens)
    guard_owner_private_overlap_resource_v2("candidate_comparisons", candidate_pairs)
    rows = _build_match_rows(leaves, sources)
    ordinals = tuple(source.ordinal for source, _, _ in sources)
    per_source = tuple(
        (
            ordinal,
            _interval_union_count(
                [
                    (row.output_start, row.output_end)
                    for row in rows
                    if row.source_ordinal == ordinal and row.run_tokens >= 2
                ]
            ),
        )
        for ordinal in ordinals
    )
    representatives = {representative for _, _, representative in sources}
    all_fragmented = _interval_union_count(
        [
            (row.output_start, row.output_end)
            for row in rows
            if row.source_ordinal in representatives and row.run_tokens >= 2
        ]
    )
    isolated = _interval_union_count(
        [
            (row.output_start, row.output_end)
            for row in rows
            if row.source_ordinal in representatives and row.run_tokens == 1
        ]
    )
    maximum = max((row.run_tokens for row in rows), default=0)
    if owner_private_overlap_threshold_failed_v2(
        output_token_count=output_token_count,
        max_contiguous_tokens=maximum,
        per_source_fragmented_tokens=per_source,
        all_source_fragmented_tokens=all_fragmented,
        isolated_union_tokens=isolated,
    ):
        raise ValueError("owner-private overlap threshold failed")
    return OwnerPrivateOverlapLedgerV2(
        checker_sha256=PRIVATE_OUTPUT_CHECKER_V2_SHA256,
        output_byte_count=len(output_bytes),
        output_token_count=output_token_count,
        sources=tuple(
            OwnerPrivateOverlapLedgerSourceV2(
                source.ordinal, len(source.exact_bytes), len(tokens), representative
            )
            for source, tokens, representative in sources
        ),
        candidate_pair_count=candidate_pairs,
        rows=rows,
        metrics=OwnerPrivateOverlapLedgerMetricsV2(
            maximum,
            per_source,
            all_fragmented,
            isolated,
            len(rows),
        ),
    )


def _closed_int(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _valid_spans(value: object, maximum: int) -> bool:
    if type(value) is not tuple or not value:
        return False
    previous_end = -1
    for span in value:
        if type(span) is not tuple or len(span) != 2:
            return False
        start, end = span
        if (
            not _closed_int(start, 0, maximum)
            or not _closed_int(end, 1, maximum)
            or end <= start
            or start <= previous_end
        ):
            return False
        previous_end = end
    return True


def _validate_ledger(ledger: OwnerPrivateOverlapLedgerV2) -> None:
    if (
        type(ledger) is not OwnerPrivateOverlapLedgerV2
        or not _closed_int(ledger.schema_version, 2, 2)
        or type(ledger.verdict) is not str
        or ledger.verdict != "pass"
        or type(ledger.checker_sha256) is not str
        or ledger.checker_sha256 != PRIVATE_OUTPUT_CHECKER_V2_SHA256
        or not _closed_int(ledger.output_byte_count, 1, predecessor.MAX_PRIVATE_OUTPUT_BYTES)
        or not _closed_int(
            ledger.output_token_count,
            1,
            min(ledger.output_byte_count, predecessor.MAX_PRIVATE_OUTPUT_TOKENS),
        )
        or type(ledger.sources) is not tuple
        or not 1 <= len(ledger.sources) <= predecessor.MAX_PRIVATE_OUTPUT_SOURCES
        or type(ledger.rows) is not tuple
        or len(ledger.rows) > predecessor.MAX_PRIVATE_MATCH_ROWS
        or type(ledger.metrics) is not OwnerPrivateOverlapLedgerMetricsV2
    ):
        raise ValueError("owner-private ledger v2 shape conflicts")
    source_by_ordinal: dict[int, OwnerPrivateOverlapLedgerSourceV2] = {}
    for ordinal, source in enumerate(ledger.sources, start=1):
        if (
            type(source) is not OwnerPrivateOverlapLedgerSourceV2
            or not _closed_int(source.ordinal, ordinal, ordinal)
            or not _closed_int(source.source_byte_count, 1, predecessor.MAX_PRIVATE_SOURCE_BYTES)
            or not _closed_int(source.source_token_count, 1, source.source_byte_count)
            or not _closed_int(source.representative_ordinal, 1, ordinal)
        ):
            raise ValueError("owner-private ledger v2 source conflicts")
        source_by_ordinal[ordinal] = source
    aggregate = sum(source.source_token_count for source in ledger.sources)
    if (
        aggregate > predecessor.MAX_PRIVATE_SOURCE_TOKENS
        or not _closed_int(
            ledger.candidate_pair_count, 0, predecessor.MAX_PRIVATE_MATCH_COMPARISONS
        )
        or ledger.candidate_pair_count != ledger.output_token_count * aggregate
    ):
        raise ValueError("owner-private ledger v2 candidate conflicts")
    for row in ledger.rows:
        if type(row) is not OwnerPrivateOverlapLedgerRowV2:
            raise ValueError("owner-private ledger v2 row conflicts")
        row_source = source_by_ordinal.get(row.source_ordinal)
        if (
            row_source is None
            or not _closed_int(row.source_ordinal, 1, len(ledger.sources))
            or not _closed_int(row.output_start, 0, ledger.output_token_count - 1)
            or not _closed_int(row.output_end, 1, ledger.output_token_count)
            or type(row.output_pointer) is not str
            or not row.output_pointer.startswith("/")
            or not 1 <= len(row.output_pointer) <= 16_384
            or not _closed_int(row.source_start, 0, row_source.source_token_count - 1)
            or not _closed_int(row.source_end, 1, row_source.source_token_count)
            or not _closed_int(row.run_tokens, 1, ledger.output_token_count)
            or row.output_end - row.output_start != row.run_tokens
            or row.source_end - row.source_start != row.run_tokens
            or not _valid_spans(row.output_origin_spans, ledger.output_byte_count)
            or not _valid_spans(row.source_origin_spans, row_source.source_byte_count)
        ):
            raise ValueError("owner-private ledger v2 row conflicts")
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
        raise ValueError("owner-private ledger v2 row order conflicts")
    ordinals = tuple(range(1, len(ledger.sources) + 1))
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
    maximum = max((row.run_tokens for row in ledger.rows), default=0)
    metrics = ledger.metrics
    if (
        not _closed_int(metrics.max_contiguous_tokens, 0, ledger.output_token_count)
        or type(metrics.per_source_fragmented_tokens) is not tuple
        or len(metrics.per_source_fragmented_tokens) != len(ordinals)
        or not _closed_int(
            metrics.all_source_fragmented_tokens, 0, ledger.output_token_count
        )
        or not _closed_int(metrics.isolated_union_tokens, 0, ledger.output_token_count)
        or metrics.per_source_fragmented_tokens != per_source
        or metrics.max_contiguous_tokens != maximum
        or metrics.all_source_fragmented_tokens != all_fragmented
        or metrics.isolated_union_tokens != isolated
        or not _closed_int(metrics.match_row_count, len(ledger.rows), len(ledger.rows))
    ):
        raise ValueError("owner-private ledger v2 metric conflicts")
    for expected_ordinal, pair in zip(
        ordinals, metrics.per_source_fragmented_tokens, strict=True
    ):
        if (
            type(pair) is not tuple
            or len(pair) != 2
            or not _closed_int(pair[0], expected_ordinal, expected_ordinal)
            or not _closed_int(pair[1], 0, ledger.output_token_count)
        ):
            raise ValueError("owner-private ledger v2 metric pair conflicts")
    if owner_private_overlap_threshold_failed_v2(
        output_token_count=ledger.output_token_count,
        max_contiguous_tokens=metrics.max_contiguous_tokens,
        per_source_fragmented_tokens=metrics.per_source_fragmented_tokens,
        all_source_fragmented_tokens=metrics.all_source_fragmented_tokens,
        isolated_union_tokens=metrics.isolated_union_tokens,
    ):
        raise ValueError("owner-private ledger v2 threshold conflicts")


def _canonical_owner_private_overlap_ledger_v2(
    ledger: OwnerPrivateOverlapLedgerV2,
) -> bytes:
    """Validate and encode a checker-internal PASS ledger."""
    _validate_ledger(ledger)
    encoded = _canonical_json(asdict(ledger))
    guard_owner_private_overlap_resource_v2("ledger_bytes", len(encoded))
    return encoded


def _check(
    *, output_bytes: bytes, sources: tuple[OwnerPrivateOverlapSourceV2, ...]
) -> OwnerPrivateOverlapPassV2 | OwnerPrivateOverlapNotApplicableV2:
    if type(sources) is not tuple:
        raise ValueError("owner-private source roster shape conflicts")
    model = _parse_role_output(output_bytes)
    leaves = _extract_content_leaves(model)
    if sum(len(leaf.tokens) for leaf in leaves) == 0:
        raise ValueError("owner-private output has no comparable tokens")
    role_value = model.model_dump(mode="python").get("role")
    if type(role_value) is not str:
        raise ValueError("role discriminator conflicts")
    role = role_value
    if role == "planner":
        if sources:
            raise ValueError("planner source roster conflicts")
        return OwnerPrivateOverlapNotApplicableV2()
    if type(sources) is not tuple or not sources:
        raise ValueError("non-planner source roster conflicts")
    guard_owner_private_overlap_resource_v2("sources", len(sources))
    normalized: list[
        tuple[OwnerPrivateOverlapSourceV2, tuple[OwnerPrivateNormalizedTokenV2, ...], int]
    ] = []
    representative_by_bytes: dict[bytes, int] = {}
    for expected_ordinal, source in enumerate(sources, start=1):
        if (
            type(source) is not OwnerPrivateOverlapSourceV2
            or type(source.ordinal) is not int
            or source.ordinal != expected_ordinal
            or type(source.exact_bytes) is not bytes
            or not source.exact_bytes
        ):
            raise ValueError("owner-private source shape conflicts")
        guard_owner_private_overlap_resource_v2("source_bytes", len(source.exact_bytes))
        tokens = _normalize_utf8(source.exact_bytes)
        if not tokens:
            raise ValueError("owner-private source has no comparable tokens")
        representative = representative_by_bytes.setdefault(source.exact_bytes, source.ordinal)
        normalized.append((source, tokens, representative))
    ledger = _build_ledger(output_bytes=output_bytes, leaves=leaves, sources=normalized)
    ledger_bytes = _canonical_owner_private_overlap_ledger_v2(ledger)
    return OwnerPrivateOverlapPassV2(
        ledger,
        ledger_bytes,
        hashlib.sha256(_LEDGER_DOMAIN + ledger_bytes).hexdigest(),
    )


def check_owner_private_overlap_v2(
    *, output_bytes: bytes, sources: tuple[OwnerPrivateOverlapSourceV2, ...]
) -> OwnerPrivateOverlapPassV2 | OwnerPrivateOverlapNotApplicableV2:
    """Run the non-conferring checker and expose only PASS/N-A or one opaque failure."""
    try:
        _require_frozen_unicode_runtime_v2()
        return _check(output_bytes=output_bytes, sources=sources)
    except Exception:
        pass
    raise OwnerPrivateOverlapCheckRejected() from None


def private_output_module_source_v2_sha256() -> str:
    """Bind the whole implementation without binding the external corpus literal.

    The corpus is bound separately by the checker contract and contains checker-derived
    ledger bytes, so including its literal here would create a checker/corpus cycle.
    Canonical AST encoding makes the identity insensitive only to formatting/comments
    and the two independently bound identity literal values.
    """
    tree = ast.parse(Path(__file__).read_bytes(), filename=__file__)
    sentinels = {
        "PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256": "<bound-executable-corpus-sha256>",
        "PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256": "<self-module-source-sha256>",
    }
    assignment_count = dict.fromkeys(sentinels, 0)
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                continue
            name = statement.targets[0].id
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            name = statement.target.id
            if name in sentinels and (
                statement.simple != 1
                or statement.value is None
                or not isinstance(statement.annotation, ast.Name)
                or statement.annotation.id != "str"
            ):
                raise RuntimeError("owner-private checker identity assignment shape conflicts")
            if statement.value is None:
                continue
            value = statement.value
        else:
            continue
        if name not in sentinels:
            continue
        if (
            not isinstance(value, ast.Constant)
            or type(value.value) is not str
            or len(value.value) != 64
            or any(character not in "0123456789abcdef" for character in value.value)
        ):
            raise RuntimeError("owner-private checker identity literal shape conflicts")
        assignment_count[name] += 1
        statement.value = ast.Constant(value=sentinels[name])
    store_count = {
        name: sum(
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == name
            for node in ast.walk(tree)
        )
        for name in sentinels
    }
    if any(
        assignment_count[name] != 1 or store_count[name] != 1 for name in sentinels
    ):
        raise RuntimeError("owner-private checker identity assignment shape conflicts")
    material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode("utf-8")
    return hashlib.sha256(
        b"antiek.midnight-oil.python-module-semantic-source.v2\x00" + material
    ).hexdigest()


PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256 = (
    "55b09753fd05e9d56f31401eb20e21fae0c017612d11741b1fdb5a6cc03d067e"
)


def require_private_output_module_source_v2() -> None:
    """Explicitly verify the source identity without adding checker-path filesystem I/O."""
    if private_output_module_source_v2_sha256() != PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256:
        raise RuntimeError("owner-private checker module source identity conflicts")


_UNICODE_MATERIAL_V2 = {
    "schema_version": 2,
    "unicode_version": predecessor.PRIVATE_OUTPUT_UNICODE_VERSION,
    "predecessor_table_sha256": predecessor.PRIVATE_OUTPUT_UNICODE_TABLE_SHA256,
    "composition_pairs_sha256": PRIVATE_OUTPUT_COMPOSITION_PAIRS_V2_SHA256,
    "composition_pair_count": PRIVATE_OUTPUT_COMPOSITION_PAIR_COUNT_V2,
    "hangul_constants": (
        _SBASE,
        _LBASE,
        _VBASE,
        _TBASE,
        _LCOUNT,
        _VCOUNT,
        _TCOUNT,
        _NCOUNT,
        _SCOUNT,
    ),
    "composition_exclusions": "canonical_pair_included_only_when_runtime_nfc_recomposes",
}
PRIVATE_OUTPUT_EXECUTABLE_UNICODE_TABLE_V2_SHA256 = _digest(
    _UNICODE_DOMAIN, _UNICODE_MATERIAL_V2
)

_NORMALIZER_MATERIAL_V2 = {
    "schema_version": 2,
    "normalizer_id": "antiek-owner-private-attributed-normalizer-v2",
    "unicode_table_sha256": PRIVATE_OUTPUT_EXECUTABLE_UNICODE_TABLE_V2_SHA256,
    "predecessor_normalizer_sha256": predecessor.PRIVATE_OUTPUT_NORMALIZER_SHA256,
    "implementation_sha256": PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256,
    "control_policy": "reject_non_whitespace_c0_del_c1_surrogate_noncharacter_before_nfkc",
    "origin_union": "sorted_disjoint_coalesce_overlap_or_adjacency_never_bridge_gap",
    "tokenization": "maximal_unicode16_general_category_L_or_N_runs",
}
PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256 = _digest(
    _NORMALIZER_DOMAIN, _NORMALIZER_MATERIAL_V2
)

_LEDGER_MATERIAL_V2 = {
    "schema_version": 2,
    "predecessor_ledger_sha256": predecessor.PRIVATE_OUTPUT_LEDGER_SHA256,
    "domain": _LEDGER_DOMAIN.decode("ascii"),
    "wire": "canonical_json_sorted_compact_unicode_unescaped_pass_only",
    "checker_field": "executable_checker_algorithm_sha256",
    "source_token_count": "positive_nonplanner_source_only",
    "output_token_count": "positive_all_roles_before_planner_not_applicable",
    "privacy": "stdlib_frozen_redacted_no_failure_ledger",
}
PRIVATE_OUTPUT_LEDGER_V2_SHA256 = _digest(_LEDGER_DOMAIN, _LEDGER_MATERIAL_V2)

PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256 = (
    "5e397f5c3377ee76eff90826ae5d0941b999d7ba9a66382b8aee7c106ecbcf40"
)

_CHECKER_MATERIAL_V2 = {
    "schema_version": 2,
    "checker_id": "antiek-owner-private-verbatim-overlap-v2",
    "predecessor_checker_sha256": predecessor.PRIVATE_OUTPUT_CHECKER_SHA256,
    "normalizer_sha256": PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    "ledger_sha256": PRIVATE_OUTPUT_LEDGER_V2_SHA256,
    "extractor_sha256": predecessor.PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "threshold_sha256": predecessor.PRIVATE_OUTPUT_THRESHOLD_SHA256,
    "role_parser_sha256": predecessor.PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    "role_schema_sha256": predecessor.PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    "live_roles_code_sha256": predecessor.PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    "implementation_sha256": PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256,
    "enumeration": "one_longest_equal_prefix_for_every_equal_start_pair_per_leaf",
    "duplicates": (
        "exact_bytes_every_ordinal_rows_and_per_source_coverage_"
        "lowest_ordinal_representative_only_aggregate_union_all_ordinals_charged"
    ),
    "confers_execution_authority": False,
    "confers_sink_authority": False,
    "production_consumer_enabled": False,
}
PRIVATE_OUTPUT_CHECKER_V2_SHA256 = _digest(_CHECKER_DOMAIN, _CHECKER_MATERIAL_V2)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class OwnerPrivateOverlapCheckerContractV2(_Closed):
    schema_version: Literal[2] = 2
    checker_id: Literal["antiek-owner-private-verbatim-overlap-v2"] = (
        "antiek-owner-private-verbatim-overlap-v2"
    )
    unicode_version: Literal["16.0.0"] = "16.0.0"
    primitive_execution_ready: Literal[True] = True
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    predecessor_checker_sha256: str = Field(pattern=_HEX64)
    unicode_table_sha256: str = Field(pattern=_HEX64)
    normalizer_sha256: str = Field(pattern=_HEX64)
    ledger_sha256: str = Field(pattern=_HEX64)
    executable_corpus_sha256: str = Field(pattern=_HEX64)
    checker_sha256: str = Field(pattern=_HEX64)
    contract_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOverlapCheckerContractV2:
        if (
            self.predecessor_checker_sha256 != predecessor.PRIVATE_OUTPUT_CHECKER_SHA256
            or self.unicode_table_sha256 != PRIVATE_OUTPUT_EXECUTABLE_UNICODE_TABLE_V2_SHA256
            or self.normalizer_sha256 != PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256
            or self.ledger_sha256 != PRIVATE_OUTPUT_LEDGER_V2_SHA256
            or self.executable_corpus_sha256 != PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256
            or self.checker_sha256 != PRIVATE_OUTPUT_CHECKER_V2_SHA256
            or self.contract_sha256 != owner_private_overlap_checker_contract_v2_sha256(self)
        ):
            raise ValueError("owner-private checker v2 contract conflicts")
        return self


def owner_private_overlap_checker_contract_v2_sha256(
    contract: OwnerPrivateOverlapCheckerContractV2 | Mapping[str, object],
) -> str:
    raw = contract.model_dump(mode="json") if isinstance(contract, BaseModel) else dict(contract)
    return _digest(_CONTRACT_DOMAIN, {key: value for key, value in raw.items() if key != "contract_sha256"})


def build_owner_private_overlap_checker_contract_v2() -> OwnerPrivateOverlapCheckerContractV2:
    material: dict[str, object] = {
        "schema_version": 2,
        "checker_id": "antiek-owner-private-verbatim-overlap-v2",
        "unicode_version": "16.0.0",
        "primitive_execution_ready": True,
        "confers_execution_authority": False,
        "confers_sink_authority": False,
        "production_consumer_enabled": False,
        "predecessor_checker_sha256": predecessor.PRIVATE_OUTPUT_CHECKER_SHA256,
        "unicode_table_sha256": PRIVATE_OUTPUT_EXECUTABLE_UNICODE_TABLE_V2_SHA256,
        "normalizer_sha256": PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
        "ledger_sha256": PRIVATE_OUTPUT_LEDGER_V2_SHA256,
        "executable_corpus_sha256": PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
        "checker_sha256": PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    }
    digest = owner_private_overlap_checker_contract_v2_sha256(material)
    return OwnerPrivateOverlapCheckerContractV2.model_validate(
        {**material, "contract_sha256": digest}
    )


PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256 = (
    build_owner_private_overlap_checker_contract_v2().contract_sha256
)


__all__ = [
    "PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256",
    "PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256",
    "PRIVATE_OUTPUT_CHECKER_V2_SHA256",
    "PRIVATE_OUTPUT_COMPOSITION_PAIRS_V2_SHA256",
    "PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256",
    "PRIVATE_OUTPUT_EXECUTABLE_UNICODE_TABLE_V2_SHA256",
    "PRIVATE_OUTPUT_LEDGER_V2_SHA256",
    "PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256",
    "OwnerPrivateOverlapCheckerContractV2",
    "OwnerPrivateOverlapResourceMeasureV2",
    "build_owner_private_overlap_checker_contract_v2",
    "guard_owner_private_overlap_resource_v2",
    "owner_private_overlap_resource_allows_v2",
    "owner_private_overlap_resource_limit_v2",
    "owner_private_overlap_threshold_failed_v2",
    "private_output_module_source_v2_sha256",
    "require_private_output_module_source_v2",
]
