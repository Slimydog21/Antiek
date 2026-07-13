from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import pytest
from pydantic import BaseModel, ConfigDict, Discriminator, Tag

import substrate.midnight_oil.private_output_checker_v2 as checker
from substrate.midnight_oil import private_output_compliance as predecessor
from substrate.midnight_oil.private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_SHA256,
    PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/midnight_oil_private_overlap_executable_v2.json"
PREDECESSOR_CORPUS = ROOT / "tests/fixtures/midnight_oil_private_overlap_v1.json"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Span(_Closed):
    start: int
    end: int


class Token(_Closed):
    value: str
    origin_spans: tuple[tuple[int, int], ...]


class Source(_Closed):
    ordinal: int
    exact_bytes_hex: str


class ExpectedRow(_Closed):
    output_start: int
    output_end: int
    output_pointer: str
    output_origin_spans: tuple[tuple[int, int], ...]
    source_ordinal: int
    source_start: int
    source_end: int
    source_origin_spans: tuple[tuple[int, int], ...]
    run_tokens: int


class ExpectedLeaf(_Closed):
    pointer: str
    tokens: tuple[Token, ...]


class LeafInput(_Closed):
    pointer: str
    input_hex: str


class ExpectedMetrics(_Closed):
    max_contiguous_tokens: int
    per_source_fragmented_tokens: tuple[tuple[int, int], ...]
    all_source_fragmented_tokens: int
    isolated_union_tokens: int
    match_row_count: int


class NormalizationPassVector(_Closed):
    id: str
    kind: Literal["normalization"]
    input_hex: str
    status: Literal["pass"]
    expected_tokens: tuple[Token, ...]


class NormalizationRejectVector(_Closed):
    id: str
    kind: Literal["normalization"]
    input_hex: str
    status: Literal["reject"]


class MatchingVector(_Closed):
    id: str
    kind: Literal["matching"]
    output_hex: str
    source_hex: str
    expected_rows: tuple[ExpectedRow, ...]


class MatchingScenarioPassVector(_Closed):
    id: str
    kind: Literal["matching_scenario"]
    output_hex: str
    leaves: tuple[LeafInput, ...]
    sources: tuple[Source, ...]
    expected_decision: Literal["pass"]
    expected_rows: tuple[ExpectedRow, ...]
    expected_metrics: ExpectedMetrics
    expected_ledger_hex: str
    expected_ledger_sha256: str


class MatchingScenarioFailVector(_Closed):
    id: str
    kind: Literal["matching_scenario"]
    output_hex: str
    leaves: tuple[LeafInput, ...]
    sources: tuple[Source, ...]
    expected_decision: Literal["fail"]
    expected_failure_stage: Literal["threshold"]


class PointerVector(_Closed):
    id: str
    kind: Literal["pointer_unit"]
    input_segments: tuple[str, ...]
    expected_pointer: str


class RolePassVector(_Closed):
    id: str
    kind: Literal["role_e2e"]
    output_hex: str
    sources: tuple[Source, ...]
    expected_decision: Literal["pass"]
    expected_ledger_hex: str
    expected_ledger_sha256: str


class RoleFailVector(_Closed):
    id: str
    kind: Literal["role_e2e"]
    output_hex: str
    sources: tuple[Source, ...]
    expected_decision: Literal["fail"]
    expected_failure_stage: Literal["threshold"]


class RoleRejectVector(_Closed):
    id: str
    kind: Literal["role_e2e"]
    output_hex: str
    sources: tuple[Source, ...]
    expected_decision: Literal["reject"]
    expected_failure_stage: Literal["role_wire", "source_roster"]


class RoleNotApplicableVector(_Closed):
    id: str
    kind: Literal["role_e2e"]
    output_hex: str
    sources: tuple[Source, ...]
    expected_decision: Literal["not_applicable"]


class TraversalVector(_Closed):
    id: str
    kind: Literal["traversal"]
    output_hex: str
    expected_role: Literal["planner", "gatherer", "verifier", "synthesizer"]
    expected_leaves: tuple[ExpectedLeaf, ...]


class ThresholdVector(_Closed):
    id: str
    kind: Literal["threshold"]
    measure: Literal[
        "max_contiguous_tokens",
        "per_source_fragmented_tokens",
        "all_source_fragmented_tokens",
        "isolated_union_tokens",
    ]
    observed: int
    output_tokens: int
    expected_decision: Literal["pass", "fail"]


class BoundVector(_Closed):
    id: str
    kind: Literal["bound"]
    measure: Literal[
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
    observed: int
    expected_decision: Literal["pass", "reject"]
    proof_mode: Literal["guard_observation", "schema_unreachable"]


class LedgerOverflowVector(_Closed):
    id: str
    kind: Literal["ledger_overflow"]
    output_byte_count: int
    output_token_count: int
    source_byte_count: int
    source_token_count: int
    row_count: int
    pointer_bytes: int
    expected_decision: Literal["reject"]
    expected_failure_stage: Literal["ledger_bytes"]


def _vector_discriminator(value: Any) -> str:
    if isinstance(value, dict):
        kind = value.get("kind")
        decision = value.get("status", value.get("expected_decision"))
    else:
        kind = getattr(value, "kind", None)
        decision = getattr(value, "status", getattr(value, "expected_decision", None))
    if kind in {"normalization", "matching_scenario", "role_e2e"}:
        return f"{kind}:{decision}"
    return str(kind)


type Vector = Annotated[
    Annotated[NormalizationPassVector, Tag("normalization:pass")]
    | Annotated[NormalizationRejectVector, Tag("normalization:reject")]
    | Annotated[MatchingVector, Tag("matching")]
    | Annotated[MatchingScenarioPassVector, Tag("matching_scenario:pass")]
    | Annotated[MatchingScenarioFailVector, Tag("matching_scenario:fail")]
    | Annotated[PointerVector, Tag("pointer_unit")]
    | Annotated[RolePassVector, Tag("role_e2e:pass")]
    | Annotated[RoleFailVector, Tag("role_e2e:fail")]
    | Annotated[RoleRejectVector, Tag("role_e2e:reject")]
    | Annotated[RoleNotApplicableVector, Tag("role_e2e:not_applicable")]
    | Annotated[TraversalVector, Tag("traversal")]
    | Annotated[ThresholdVector, Tag("threshold")]
    | Annotated[BoundVector, Tag("bound")]
    | Annotated[LedgerOverflowVector, Tag("ledger_overflow")],
    Discriminator(_vector_discriminator),
]


class Corpus(_Closed):
    checker_algorithm_id: Literal["antiek-owner-private-verbatim-overlap-v2"]
    confers_execution_authority: Literal[False]
    confers_sink_authority: Literal[False]
    corpus_id: Literal["antiek-owner-private-overlap-executable-v2"]
    production_consumer_enabled: Literal[False]
    schema_version: Literal[2]
    unicode_version: Literal["16.0.0"]
    vectors: tuple[Vector, ...]


def _corpus() -> Corpus:
    raw = CORPUS.read_bytes()
    parsed = Corpus.model_validate_json(raw)
    assert raw == json.dumps(
        parsed.model_dump(mode="json", exclude_unset=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    ids = tuple(vector.id for vector in parsed.vectors)
    assert len(ids) == len(set(ids))
    return parsed


def _sources(rows: tuple[Source, ...]) -> tuple[checker.OwnerPrivateOverlapSourceV2, ...]:
    return tuple(
        checker.OwnerPrivateOverlapSourceV2(row.ordinal, bytes.fromhex(row.exact_bytes_hex))
        for row in rows
    )


def _expected_tokens(rows: tuple[Token, ...]) -> tuple[checker.OwnerPrivateNormalizedTokenV2, ...]:
    return tuple(checker.OwnerPrivateNormalizedTokenV2(row.value, row.origin_spans) for row in rows)


def _ledger_bytes_and_sha256(
    ledger: checker.OwnerPrivateOverlapLedgerV2,
) -> tuple[bytes, str]:
    encoded = json.dumps(
        asdict(ledger), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    digest = hashlib.sha256(
        b"antiek.midnight-oil.owner-private-overlap-ledger.v2\x00" + encoded
    ).hexdigest()
    return encoded, digest


def _matching_inputs(
    vector: MatchingScenarioPassVector | MatchingScenarioFailVector,
) -> tuple[
    tuple[checker.OwnerPrivateContentLeafV2, ...],
    tuple[
        tuple[
            checker.OwnerPrivateOverlapSourceV2,
            tuple[checker.OwnerPrivateNormalizedTokenV2, ...],
            int,
        ],
        ...,
    ],
]:
    leaves = tuple(
        checker.OwnerPrivateContentLeafV2(
            leaf.pointer,
            checker.normalize_owner_private_utf8_v2(bytes.fromhex(leaf.input_hex)),
        )
        for leaf in vector.leaves
    )
    source_rows = _sources(vector.sources)
    representatives: dict[bytes, int] = {}
    normalized = tuple(
        (
            source,
            checker.normalize_owner_private_utf8_v2(source.exact_bytes),
            representatives.setdefault(source.exact_bytes, source.ordinal),
        )
        for source in source_rows
    )
    return leaves, normalized


def _assert_threshold_failure_stage(
    *,
    output_bytes: bytes,
    leaves: tuple[checker.OwnerPrivateContentLeafV2, ...],
    sources: tuple[
        tuple[
            checker.OwnerPrivateOverlapSourceV2,
            tuple[checker.OwnerPrivateNormalizedTokenV2, ...],
            int,
        ],
        ...,
    ],
) -> tuple[str, str]:
    rows = checker._build_match_rows(leaves, sources)
    output_count = sum(len(leaf.tokens) for leaf in leaves)
    ordinals = tuple(source.ordinal for source, _, _ in sources)
    per_source = tuple(
        (
            ordinal,
            checker._interval_union_count(
                tuple(
                    (row.output_start, row.output_end)
                    for row in rows
                    if row.source_ordinal == ordinal and row.run_tokens >= 2
                )
            ),
        )
        for ordinal in ordinals
    )
    representatives = {representative for _, _, representative in sources}
    all_fragmented = checker._interval_union_count(
        tuple(
            (row.output_start, row.output_end)
            for row in rows
            if row.source_ordinal in representatives and row.run_tokens >= 2
        )
    )
    isolated = checker._interval_union_count(
        tuple(
            (row.output_start, row.output_end)
            for row in rows
            if row.source_ordinal in representatives and row.run_tokens == 1
        )
    )
    assert checker.owner_private_overlap_threshold_failed_v2(
        output_token_count=output_count,
        max_contiguous_tokens=max((row.run_tokens for row in rows), default=0),
        per_source_fragmented_tokens=per_source,
        all_source_fragmented_tokens=all_fragmented,
        isolated_union_tokens=isolated,
    )
    with pytest.raises(ValueError, match="owner-private overlap threshold failed"):
        checker._build_ledger(output_bytes=output_bytes, leaves=leaves, sources=sources)
    return "fail", "threshold"


def _execute_vector(vector: Vector) -> object:
    if isinstance(vector, (NormalizationPassVector, NormalizationRejectVector)):
        raw = bytes.fromhex(vector.input_hex)
        if vector.status == "reject":
            with pytest.raises(checker.OwnerPrivateOverlapCheckRejected) as caught:
                checker.normalize_owner_private_utf8_v2(raw)
            assert caught.value.__cause__ is None and caught.value.__context__ is None
            return "reject"
        return checker.normalize_owner_private_utf8_v2(raw)
    if isinstance(vector, MatchingVector):
        leaf = checker.OwnerPrivateContentLeafV2(
            "/fixture", checker.normalize_owner_private_utf8_v2(bytes.fromhex(vector.output_hex))
        )
        source = checker.OwnerPrivateOverlapSourceV2(1, bytes.fromhex(vector.source_hex))
        return checker._build_match_rows(
            (leaf,), ((source, checker.normalize_owner_private_utf8_v2(source.exact_bytes), 1),)
        )
    if isinstance(vector, (MatchingScenarioPassVector, MatchingScenarioFailVector)):
        leaves, normalized = _matching_inputs(vector)
        output_bytes = bytes.fromhex(vector.output_hex)
        if isinstance(vector, MatchingScenarioFailVector):
            return _assert_threshold_failure_stage(
                output_bytes=output_bytes, leaves=leaves, sources=normalized
            )
        ledger = checker._build_ledger(
            output_bytes=output_bytes,
            leaves=leaves,
            sources=normalized,
        )
        ledger_bytes, ledger_sha256 = _ledger_bytes_and_sha256(ledger)
        return ledger, ledger_bytes, ledger_sha256
    if isinstance(vector, PointerVector):
        return "/" + "/".join(checker._pointer_segment(value) for value in vector.input_segments)
    if isinstance(vector, TraversalVector):
        model = checker._parse_role_output(bytes.fromhex(vector.output_hex))
        assert model.model_dump(mode="python")["role"] == vector.expected_role
        return checker._extract_content_leaves(model)
    if isinstance(
        vector,
        (RolePassVector, RoleFailVector, RoleRejectVector, RoleNotApplicableVector),
    ):
        if isinstance(vector, RoleFailVector):
            output_bytes = bytes.fromhex(vector.output_hex)
            model = checker._parse_role_output(output_bytes)
            leaves = checker._extract_content_leaves(model)
            source_rows = _sources(vector.sources)
            normalized = tuple(
                (source, checker.normalize_owner_private_utf8_v2(source.exact_bytes), source.ordinal)
                for source in source_rows
            )
            primitive = _assert_threshold_failure_stage(
                output_bytes=output_bytes, leaves=leaves, sources=normalized
            )
            with pytest.raises(checker.OwnerPrivateOverlapCheckRejected):
                checker.check_owner_private_overlap_v2(
                    output_bytes=output_bytes, sources=source_rows
                )
            return primitive
        if isinstance(vector, RoleRejectVector):
            output_bytes = bytes.fromhex(vector.output_hex)
            source_rows = _sources(vector.sources)
            if vector.expected_failure_stage == "role_wire":
                with pytest.raises(ValueError):
                    checker._parse_role_output(output_bytes)
            else:
                checker._parse_role_output(output_bytes)
                with pytest.raises(ValueError, match="source roster conflicts"):
                    checker._check(output_bytes=output_bytes, sources=source_rows)
            with pytest.raises(checker.OwnerPrivateOverlapCheckRejected):
                checker.check_owner_private_overlap_v2(
                    output_bytes=output_bytes, sources=source_rows
                )
            return "reject", vector.expected_failure_stage
        return checker.check_owner_private_overlap_v2(
            output_bytes=bytes.fromhex(vector.output_hex), sources=_sources(vector.sources)
        )
    if isinstance(vector, ThresholdVector):
        per_source = (
            ((1, vector.observed),)
            if vector.measure == "per_source_fragmented_tokens"
            else ((1, 0),)
        )
        failed = checker.owner_private_overlap_threshold_failed_v2(
            output_token_count=vector.output_tokens,
            max_contiguous_tokens=(
                vector.observed if vector.measure == "max_contiguous_tokens" else 0
            ),
            per_source_fragmented_tokens=per_source,
            all_source_fragmented_tokens=(
                vector.observed if vector.measure == "all_source_fragmented_tokens" else 0
            ),
            isolated_union_tokens=(
                vector.observed if vector.measure == "isolated_union_tokens" else 0
            ),
        )
        return "fail" if failed else "pass"
    if isinstance(vector, LedgerOverflowVector):
        rows = tuple(
            checker.OwnerPrivateOverlapLedgerRowV2(
                output_start=0,
                output_end=1,
                output_pointer=("/" + f"{index:04d}" + "x" * vector.pointer_bytes)[
                    : vector.pointer_bytes
                ],
                output_origin_spans=((0, 1),),
                source_ordinal=1,
                source_start=0,
                source_end=1,
                source_origin_spans=((0, 1),),
                run_tokens=1,
            )
            for index in range(vector.row_count)
        )
        ledger = checker.OwnerPrivateOverlapLedgerV2(
            checker_sha256=checker.PRIVATE_OUTPUT_CHECKER_V2_SHA256,
            output_byte_count=vector.output_byte_count,
            output_token_count=vector.output_token_count,
            sources=(
                checker.OwnerPrivateOverlapLedgerSourceV2(
                    ordinal=1,
                    source_byte_count=vector.source_byte_count,
                    source_token_count=vector.source_token_count,
                    representative_ordinal=1,
                ),
            ),
            candidate_pair_count=vector.output_token_count * vector.source_token_count,
            rows=rows,
            metrics=checker.OwnerPrivateOverlapLedgerMetricsV2(
                max_contiguous_tokens=1,
                per_source_fragmented_tokens=((1, 0),),
                all_source_fragmented_tokens=0,
                isolated_union_tokens=1,
                match_row_count=vector.row_count,
            ),
        )
        encoded = json.dumps(
            asdict(ledger), sort_keys=True, separators=(",", ":")
        ).encode()
        assert len(encoded) > checker.owner_private_overlap_resource_limit_v2("ledger_bytes")
        checker._validate_ledger(ledger)
        with pytest.raises(ValueError, match="owner-private resource bound conflicts"):
            checker._canonical_owner_private_overlap_ledger_v2(ledger)
        return "reject", "ledger_bytes"
    measure = vector.measure
    limit = checker.owner_private_overlap_resource_limit_v2(measure)
    assert vector.observed in {limit - 1, limit, limit + 1}
    if vector.proof_mode == "schema_unreachable":
        assert vector.measure == "depth"
        assert max(len(pattern.split("/")) - 1 for patterns in predecessor._EXEMPT_POINTER_PATTERNS.values() for pattern in patterns) < limit
    allowed = checker.owner_private_overlap_resource_allows_v2(measure, vector.observed)
    if allowed:
        checker.guard_owner_private_overlap_resource_v2(measure, vector.observed)
    else:
        with pytest.raises(ValueError):
            checker.guard_owner_private_overlap_resource_v2(measure, vector.observed)
    return "pass" if allowed else "reject"


def _assert_oracle(vector: Vector, result: object) -> None:
    if isinstance(vector, (NormalizationPassVector, NormalizationRejectVector)):
        expected: object = (
            "reject"
            if isinstance(vector, NormalizationRejectVector)
            else _expected_tokens(vector.expected_tokens)
        )
        assert result == expected
    elif isinstance(vector, MatchingVector):
        assert tuple(asdict(row) for row in cast(tuple[checker.OwnerPrivateOverlapLedgerRowV2, ...], result)) == tuple(
            row.model_dump(mode="python") for row in vector.expected_rows
        )
    elif isinstance(vector, (MatchingScenarioPassVector, MatchingScenarioFailVector)):
        if isinstance(vector, MatchingScenarioFailVector):
            assert result == ("fail", vector.expected_failure_stage)
        else:
            ledger, ledger_bytes, ledger_sha256 = cast(
                tuple[checker.OwnerPrivateOverlapLedgerV2, bytes, str], result
            )
            assert tuple(asdict(row) for row in ledger.rows) == tuple(
                row.model_dump(mode="python") for row in vector.expected_rows
            )
            assert asdict(ledger.metrics) == vector.expected_metrics.model_dump(mode="python")
            assert ledger_bytes.hex() == vector.expected_ledger_hex
            assert ledger_sha256 == vector.expected_ledger_sha256
    elif isinstance(vector, PointerVector):
        assert result == vector.expected_pointer
    elif isinstance(vector, TraversalVector):
        leaves = cast(tuple[checker.OwnerPrivateContentLeafV2, ...], result)
        assert tuple((leaf.pointer, leaf.tokens) for leaf in leaves) == tuple(
            (leaf.pointer, _expected_tokens(leaf.tokens)) for leaf in vector.expected_leaves
        )
    elif isinstance(
        vector,
        (RolePassVector, RoleFailVector, RoleRejectVector, RoleNotApplicableVector),
    ):
        if isinstance(vector, RoleFailVector):
            assert result == ("fail", vector.expected_failure_stage)
        elif isinstance(vector, RoleRejectVector):
            assert result == ("reject", vector.expected_failure_stage)
        elif isinstance(vector, RoleNotApplicableVector):
            assert type(result) is checker.OwnerPrivateOverlapNotApplicableV2
        else:
            passed = cast(checker.OwnerPrivateOverlapPassV2, result)
            assert type(passed) is checker.OwnerPrivateOverlapPassV2
            assert passed.ledger_bytes.hex() == vector.expected_ledger_hex
            assert passed.ledger_sha256 == vector.expected_ledger_sha256
    elif isinstance(vector, ThresholdVector):
        assert result == vector.expected_decision
    elif isinstance(vector, LedgerOverflowVector):
        assert result == (vector.expected_decision, vector.expected_failure_stage)
    else:
        assert result == vector.expected_decision


def test_every_corpus_vector_executes_twice_against_its_exact_oracle() -> None:
    for vector in _corpus().vectors:
        first = _execute_vector(vector)
        second = _execute_vector(vector)
        _assert_oracle(vector, first)
        _assert_oracle(vector, second)
        assert first == second


def test_corpus_schema_is_recursively_closed_and_strict() -> None:
    corpus = _corpus()
    value: dict[str, Any] = corpus.model_dump(mode="json")
    mutations: list[dict[str, Any]] = []
    for location in ("root", "vector", "nested"):
        mutation = cast(dict[str, Any], json.loads(json.dumps(value)))
        if location == "root":
            mutation["unknown"] = True
        elif location == "vector":
            cast(dict[str, Any], mutation["vectors"][0])["unknown"] = True
        else:
            cast(dict[str, Any], mutation["vectors"][0]["expected_tokens"][0])["unknown"] = True
        mutations.append(mutation)
    wrong_type = cast(dict[str, Any], json.loads(json.dumps(value)))
    wrong_type["schema_version"] = "2"
    mutations.append(wrong_type)
    for mutation in mutations:
        with pytest.raises(ValueError):
            Corpus.model_validate_json(json.dumps(mutation))

    representatives: dict[tuple[str, ...], tuple[object, ...]] = {}

    def collect(node: object, path: tuple[object, ...]) -> None:
        if isinstance(node, dict):
            representatives.setdefault(tuple(sorted(node)), path)
            for key, child in node.items():
                collect(child, (*path, key))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                collect(child, (*path, index))

    collect(value, ())
    for keys, representative_path in representatives.items():
        for required_key in keys:
            mutation = cast(dict[str, Any], json.loads(json.dumps(value)))
            target: object = mutation
            for segment in representative_path:
                target = target[segment]  # type: ignore[index]
            del cast(dict[str, Any], target)[required_key]
            with pytest.raises(ValueError):
                Corpus.model_validate_json(json.dumps(mutation))


def test_successor_identities_are_additive_and_non_conferring() -> None:
    digest = hashlib.sha256(CORPUS.read_bytes()).hexdigest()
    assert digest == checker.PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256
    assert len(checker._composition_pairs()) == checker.PRIVATE_OUTPUT_COMPOSITION_PAIR_COUNT_V2
    assert checker.private_output_composition_pairs_v2_sha256() == checker.PRIVATE_OUTPUT_COMPOSITION_PAIRS_V2_SHA256
    contract = checker.build_owner_private_overlap_checker_contract_v2()
    assert (contract.primitive_execution_ready, contract.confers_execution_authority, contract.production_consumer_enabled) == (True, False, False)
    assert contract.executable_corpus_sha256 == digest
    assert contract.contract_sha256 == checker.PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256
    assert contract.predecessor_checker_sha256 == PRIVATE_OUTPUT_CHECKER_SHA256
    assert hashlib.sha256(PREDECESSOR_CORPUS.read_bytes()).hexdigest() == PRIVATE_OUTPUT_GOLDEN_CORPUS_SHA256
    assert OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256 == "7e0f47fcf024428ffcd4d1c131150c49daa9516355f8a10cc9e3b7065362cfba"


def test_literal_whole_module_semantic_ast_identity_is_independently_recomputed() -> None:
    module_path = ROOT / "substrate/midnight_oil/private_output_checker_v2.py"
    source = module_path.read_bytes()
    sentinels = {
        "PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256": "<bound-executable-corpus-sha256>",
        "PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256": "<self-module-source-sha256>",
    }

    def semantic_digest(raw: bytes) -> str:
        tree = ast.parse(raw, filename=str(module_path))
        assignments = dict.fromkeys(sentinels, 0)
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
                    raise RuntimeError("identity assignment shape")
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
                raise RuntimeError("identity literal shape")
            assignments[name] += 1
            statement.value = ast.Constant(value=sentinels[name])
        stores = {
            name: sum(
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id == name
                for node in ast.walk(tree)
            )
            for name in sentinels
        }
        if any(assignments[name] != 1 or stores[name] != 1 for name in sentinels):
            raise RuntimeError("identity assignment shape")
        material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode()
        return hashlib.sha256(
            b"antiek.midnight-oil.python-module-semantic-source.v2\x00" + material
        ).hexdigest()

    expected = semantic_digest(source)
    assert checker.private_output_module_source_v2_sha256() == expected
    assert expected == checker.PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256
    corpus_literal = checker.PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256.encode()
    assert semantic_digest(source.replace(corpus_literal, b"0" * 64, 1)) == expected
    with pytest.raises(RuntimeError, match="identity literal shape"):
        semantic_digest(source.replace(b'"' + corpus_literal + b'"', b'"0" * 64', 1))
    with pytest.raises(RuntimeError, match="identity assignment shape"):
        semantic_digest(
            source.replace(
                b"PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256 = (",
                b"PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256 = alias = (",
                1,
            )
        )
    assert semantic_digest(source.replace(b"Executable, non-conferring", b"Executable non-conferring", 1)) != expected


def test_composition_exclusions_hangul_controls_and_scalar_gate() -> None:
    excluded = checker._attributed_nfkc(checker._decode_attributed("क़".encode()))
    assert tuple(scalar.codepoint for scalar in excluded) == (0x0915, 0x093C)
    excluded_0344 = checker._attributed_nfkc(checker._decode_attributed("\u0344".encode()))
    assert tuple(scalar.codepoint for scalar in excluded_0344) == (0x0308, 0x0301)
    hangul = checker._attributed_nfkc(checker._decode_attributed("각".encode()))
    assert tuple(scalar.codepoint for scalar in hangul) == (0xAC01,)
    assert hangul[0].origins == ((0, 9),)
    with pytest.raises(ValueError):
        checker._validate_input_scalar(0xD800)


def test_exact_role_wire_ledger_mutations_and_redaction(capsys: pytest.CaptureFixture[str]) -> None:
    planner = next(vector for vector in _corpus().vectors if vector.id == "planner-zero-source")
    assert isinstance(planner, RoleNotApplicableVector)
    canonical = bytes.fromhex(planner.output_hex)
    for mutation in (canonical + b"\n", b"\xef\xbb\xbf" + canonical, canonical + b"{}"):
        with pytest.raises(checker.OwnerPrivateOverlapCheckRejected):
            checker.check_owner_private_overlap_v2(output_bytes=mutation, sources=())
    gatherer = next(vector for vector in _corpus().vectors if vector.id == "gatherer-pass-ledger")
    assert isinstance(gatherer, RolePassVector)
    passed = checker.check_owner_private_overlap_v2(
        output_bytes=bytes.fromhex(gatherer.output_hex), sources=_sources(gatherer.sources)
    )
    assert type(passed) is checker.OwnerPrivateOverlapPassV2
    for ledger_mutation in (
        replace(passed.ledger, output_token_count=True),
        replace(passed.ledger, candidate_pair_count=False),
        replace(passed.ledger, checker_sha256="0" * 64),
        replace(passed.ledger, rows=cast(Any, list(passed.ledger.rows))),
    ):
        with pytest.raises(ValueError):
            checker._validate_ledger(ledger_mutation)
    canary = "PRIVATE-CANARY-123"
    source = checker.OwnerPrivateOverlapSourceV2(1, canary.encode())
    assert canary not in repr(source)
    with pytest.raises(checker.OwnerPrivateOverlapCheckRejected) as caught:
        checker.check_owner_private_overlap_v2(output_bytes=canary.encode(), sources=(source,))
    assert canary not in repr(caught.value) + str(caught.value)
    assert capsys.readouterr() == ("", "")


def test_checker_is_unreachable_from_interfaces_and_real_api_app() -> None:
    occurrences = subprocess.run(
        ["rg", "-l", "private_output_checker_v2", "substrate", "services", "apps", "interfaces"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    ).stdout.splitlines()
    assert set(occurrences) == {
        "substrate/midnight_oil/private_output_policy_v3.py",
        "substrate/midnight_oil/private_output_source_adapter_v1.py",
        "substrate/midnight_oil/private_provider_capability_v3.py",
    }
    probe = subprocess.run(
        [sys.executable, "-c", "import interfaces.research.api.app; import sys; assert 'substrate.midnight_oil.private_output_checker_v2' not in sys.modules"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert probe.returncode == 0, probe.stderr
