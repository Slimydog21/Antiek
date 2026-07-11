"""Validated replay/archive registry for rendered federated evidence spans."""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass

from substrate.corpus_contract import CorpusContractError
from substrate.corpus_evidence import EvidenceSpan
from substrate.schemas import ActionType

REGISTRY_SCHEMA_VERSION = 1
REGISTRY_KEY = "federated_span_registry"
_MAX_BLOCK_BYTES = 256_000
_MAX_SPANS = 50
_HEADING = re.compile(r"### chunk_id: (span_[0-9a-f]{32})\Z")
_SCHEMA = re.compile(r"Span schema: 1 \| Corpus ID JSON: (.+)\Z")
_SOURCE = re.compile(r"Source tier: (unknown|[1-5]) \| Source: (.+) \| Origin: (.+)\Z")
_RIGHTS = re.compile(
    r"Rights: (.+) \| Retrieved: (.+) \| Range: ([0-9]+):([0-9]+)\Z"
)


@dataclass(frozen=True)
class FederatedSpanRecord:
    span_id: str
    corpus_id: str
    text: str
    start_char: int
    end_char: int
    source_kind: str
    origin_ref: str
    retrieved_at: str
    license_class: str
    source_tier: int | None

    @classmethod
    def from_span(cls, span: EvidenceSpan) -> FederatedSpanRecord:
        return cls(
            span_id=span.span_id,
            corpus_id=span.corpus_id,
            text=span.text,
            start_char=span.start_char,
            end_char=span.end_char,
            source_kind=span.source_kind,
            origin_ref=span.origin_ref,
            retrieved_at=span.retrieved_at.isoformat(),
            license_class=span.license_class,
            source_tier=span.source_tier,
        )

    @classmethod
    def from_mapping(cls, value: object) -> FederatedSpanRecord:
        if type(value) is not dict:
            raise CorpusContractError("span registry record must be an exact object")
        raw = value
        if frozenset(raw) != {
            "span_id",
            "corpus_id",
            "text",
            "start_char",
            "end_char",
            "source_kind",
            "origin_ref",
            "retrieved_at",
            "license_class",
            "source_tier",
        }:
            raise CorpusContractError("span registry record fields are invalid")
        try:
            retrieved = datetime.datetime.fromisoformat(raw["retrieved_at"])
            span = EvidenceSpan(
                span_id=raw["span_id"],
                corpus_id=raw["corpus_id"],
                text=raw["text"],
                start_char=raw["start_char"],
                end_char=raw["end_char"],
                source_kind=raw["source_kind"],
                origin_ref=raw["origin_ref"],
                retrieved_at=retrieved,
                license_class=raw["license_class"],
                source_tier=raw["source_tier"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CorpusContractError("span registry record is invalid") from exc
        return cls.from_span(span)

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)


def _json_string(raw: str, field: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CorpusContractError(f"rendered span {field} JSON is invalid") from exc
    if type(value) is not str:
        raise CorpusContractError(f"rendered span {field} must be a JSON string")
    return value


def parse_rendered_span_registry(chunks_block: str) -> dict[str, FederatedSpanRecord]:
    """Parse only the versioned span grammar; graph chunks are ignored."""
    if type(chunks_block) is not str or len(chunks_block.encode("utf-8")) > _MAX_BLOCK_BYTES:
        raise CorpusContractError("chunks block must be a bounded exact str")
    registry: dict[str, FederatedSpanRecord] = {}
    for raw_block in chunks_block.split("\n---\n"):
        lines = raw_block.splitlines()
        if not lines or not lines[0].startswith("### chunk_id: span_"):
            continue
        if len(lines) != 5:
            raise CorpusContractError("rendered span must have exactly five structural lines")
        heading = _HEADING.fullmatch(lines[0])
        schema = _SCHEMA.fullmatch(lines[1])
        source = _SOURCE.fullmatch(lines[2])
        rights = _RIGHTS.fullmatch(lines[3])
        if heading is None or schema is None or source is None or rights is None:
            raise CorpusContractError("rendered span structural fields are invalid")
        if not lines[4].startswith("Source text JSON: "):
            raise CorpusContractError("rendered span source text field is missing")
        tier = None if source.group(1) == "unknown" else int(source.group(1))
        try:
            retrieved = datetime.datetime.fromisoformat(rights.group(2))
        except ValueError as exc:
            raise CorpusContractError("rendered span timestamp is invalid") from exc
        span = EvidenceSpan(
            span_id=heading.group(1),
            corpus_id=_json_string(schema.group(1), "corpus id"),
            text=_json_string(lines[4].removeprefix("Source text JSON: "), "text"),
            start_char=int(rights.group(3)),
            end_char=int(rights.group(4)),
            source_kind=source.group(2),
            origin_ref=_json_string(source.group(3), "origin"),
            retrieved_at=retrieved,
            license_class=rights.group(1),
            source_tier=tier,
        )
        record = FederatedSpanRecord.from_span(span)
        previous = registry.get(record.span_id)
        if previous is not None and previous != record:
            raise CorpusContractError("conflicting duplicate span registry id")
        registry[record.span_id] = record
        if len(registry) > _MAX_SPANS:
            raise CorpusContractError("span registry exceeds the record bound")
    return registry


def merge_span_registries(
    registries: list[dict[str, FederatedSpanRecord]],
) -> dict[str, FederatedSpanRecord]:
    merged: dict[str, FederatedSpanRecord] = {}
    for registry in registries:
        for span_id, record in registry.items():
            previous = merged.get(span_id)
            if previous is not None and previous != record:
                raise CorpusContractError("trajectory contains conflicting span evidence")
            merged[span_id] = record
            if len(merged) > _MAX_SPANS:
                raise CorpusContractError("trajectory span registry exceeds the record bound")
    return merged


def span_registry_from_trajectory(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> dict[str, FederatedSpanRecord]:
    from substrate.event_log import trajectory

    registries: list[dict[str, FederatedSpanRecord]] = []
    for row in trajectory(investigation_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.EVIDENCE_RETRIEVE_REQUESTED.value:
            continue
        payload = row.get("payload")
        if type(payload) is not dict or type(payload.get("chunks_block")) is not str:
            raise CorpusContractError("evidence request trajectory payload is invalid")
        registries.append(parse_rendered_span_registry(payload["chunks_block"]))
    return merge_span_registries(registries)


def registry_archive_payload(
    registry: dict[str, FederatedSpanRecord],
) -> dict[str, object]:
    if type(registry) is not dict or any(
        type(key) is not str or type(value) is not FederatedSpanRecord
        for key, value in registry.items()
    ):
        raise CorpusContractError("registry must be an exact span-record mapping")
    return {
        REGISTRY_KEY: {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "records": [registry[key].to_mapping() for key in sorted(registry)],
        }
    }


def registry_from_archive(value: object) -> dict[str, FederatedSpanRecord]:
    if value is None:
        return {}
    if type(value) is not dict:
        raise CorpusContractError("archived substrate must be an exact object")
    raw = value.get(REGISTRY_KEY)
    if raw is None:
        return {}
    if type(raw) is not dict or frozenset(raw) != {"schema_version", "records"}:
        raise CorpusContractError("archived span registry envelope is invalid")
    if raw["schema_version"] != REGISTRY_SCHEMA_VERSION or type(raw["records"]) is not list:
        raise CorpusContractError("archived span registry version or records are invalid")
    records = [FederatedSpanRecord.from_mapping(item) for item in raw["records"]]
    return merge_span_registries([{record.span_id: record} for record in records])


def composite_span_text_resolver(
    graph_resolver: Callable[[str], str | None],
    registry: dict[str, FederatedSpanRecord],
) -> Callable[[str], str | None]:
    """Resolve each id graph-first, then through exact archived span evidence."""

    def resolve(chunk_id: str) -> str | None:
        graph_text = graph_resolver(chunk_id)
        if graph_text is not None:
            return graph_text
        span = registry.get(chunk_id)
        return span.text if span is not None else None

    return resolve
