"""Bounded, provenance-preserving evidence spans from a read-only corpus."""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from dataclasses import dataclass

from substrate.corpus_contract import (
    CorpusAdapter,
    CorpusContractError,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    Provenance,
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")
_AGGREGATOR_TIERS = {"semantic_scholar": 5, "openalex": 5, "core": 5}


@dataclass(frozen=True)
class EvidenceSpan:
    span_id: str
    corpus_id: str
    text: str
    start_char: int
    end_char: int
    source_kind: str
    origin_ref: str
    retrieved_at: datetime.datetime
    license_class: str
    source_tier: int | None

    def __post_init__(self) -> None:
        if re.fullmatch(r"span_[0-9a-f]{32}", self.span_id) is None:
            raise CorpusContractError("span_id must be a deterministic span digest")
        if type(self.corpus_id) is not str or _ID.fullmatch(self.corpus_id) is None:
            raise CorpusContractError("corpus_id must be a bounded qualified id")
        if type(self.text) is not str or not self.text:
            raise CorpusContractError("span text must be a nonempty exact str")
        if (
            type(self.start_char) is not int
            or type(self.end_char) is not int
            or isinstance(self.start_char, bool)
            or isinstance(self.end_char, bool)
            or not 0 <= self.start_char < self.end_char
            or self.end_char - self.start_char != len(self.text)
        ):
            raise CorpusContractError("span offsets must exactly bound span text")
        Provenance(
            source_kind=self.source_kind,
            origin_ref=self.origin_ref,
            retrieved_at=self.retrieved_at,
            license_class=self.license_class,
        )
        if self.source_kind.splitlines() != [self.source_kind] or self.license_class.splitlines() != [
            self.license_class
        ]:
            raise CorpusContractError("span source and rights fields must be single-line")
        if self.source_tier is not None and (
            type(self.source_tier) is not int
            or isinstance(self.source_tier, bool)
            or not 1 <= self.source_tier <= 5
        ):
            raise CorpusContractError("source_tier must be null or an exact int in 1..5")


def _window(content: str, query: str, max_chars: int) -> tuple[int, int]:
    # Regex match offsets are indices into the ORIGINAL string. Searching a
    # separately casefolded string is unsafe because Unicode folds such as
    # `ß -> ss` expand length and shift offsets away from source content.
    match = re.search(re.escape(query), content, flags=re.IGNORECASE)
    at = match.start() if match is not None else -1
    if match is None:
        # Ignore 1–2 character fallback tokens: they are too noisy to choose a
        # defensible evidence window. If no meaningful token matches, start at 0.
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", query):
            token_match = re.search(re.escape(token), content, flags=re.IGNORECASE)
            if token_match is not None:
                at = token_match.start()
                break
    if at < 0:
        at = 0
    start = max(0, at - max_chars // 4)
    end = min(len(content), start + max_chars)
    start = max(0, end - max_chars)
    return start, end


def select_evidence_spans(
    adapter: CorpusAdapter,
    query: str,
    *,
    max_spans: int = 5,
    max_chars: int = 1200,
) -> tuple[EvidenceSpan, ...]:
    if not isinstance(adapter, CorpusAdapter):
        raise CorpusContractError("adapter must satisfy CorpusAdapter")
    if (
        type(query) is not str
        or not query.strip()
        or query != query.strip()
        or query.splitlines() != [query]
    ):
        raise CorpusContractError("query must be trimmed, nonempty, and single-line")
    if type(max_spans) is not int or isinstance(max_spans, bool) or not 1 <= max_spans <= 50:
        raise CorpusContractError("max_spans must be an exact int in 1..50")
    if type(max_chars) is not int or isinstance(max_chars, bool) or not 200 <= max_chars <= 4000:
        raise CorpusContractError("max_chars must be an exact int in 200..4000")
    hits = adapter.search(query)
    if type(hits) is not tuple or any(type(hit) is not CorpusHit for hit in hits):
        raise CorpusContractError("corpus search must return an exact tuple of CorpusHit values")
    ids = tuple(hit.id for hit in hits)
    if len(ids) != len(set(ids)):
        raise CorpusContractError("corpus search must not return duplicate ids")
    spans: list[EvidenceSpan] = []
    for hit in hits[:max_spans]:
        result = adapter.fetch(hit.id)
        if type(result) is CorpusMiss:
            raise CorpusContractError("search hit did not fetch coherently")
        if type(result) is not CorpusDocument:
            raise CorpusContractError("corpus fetch returned an unsupported result")
        start, end = _window(result.content, query, max_chars)
        text = result.content[start:end]
        digest_input = "\0".join(
            (
                hit.id,
                hashlib.sha256(result.content.encode("utf-8")).hexdigest(),
                str(start),
                str(end),
            )
        )
        spans.append(
            EvidenceSpan(
                span_id="span_" + hashlib.sha256(digest_input.encode()).hexdigest()[:32],
                corpus_id=hit.id,
                text=text,
                start_char=start,
                end_char=end,
                source_kind=result.provenance.source_kind,
                origin_ref=result.provenance.origin_ref,
                retrieved_at=result.provenance.retrieved_at,
                license_class=result.provenance.license_class,
                source_tier=_AGGREGATOR_TIERS.get(result.provenance.source_kind),
            )
        )
    return tuple(spans)


def render_chunks_block(spans: tuple[EvidenceSpan, ...]) -> str:
    if type(spans) is not tuple or any(type(span) is not EvidenceSpan for span in spans):
        raise CorpusContractError("spans must be an exact tuple of EvidenceSpan values")
    blocks: list[str] = []
    for span in spans:
        # ASCII JSON encoding escapes every Unicode line separator recognized
        # by `str.splitlines()` (including NEL, U+2028, and U+2029). Source text
        # therefore cannot mint a canonical `### chunk_id:` or `[id]` line.
        source_text = json.dumps(span.text, ensure_ascii=True)
        tier = str(span.source_tier) if span.source_tier is not None else "unknown"
        blocks.append(
            f"### chunk_id: {span.span_id}\n"
            f"Source tier: {tier} | Source: {span.source_kind} | "
            f"Origin: {json.dumps(span.origin_ref, ensure_ascii=True)}\n"
            f"Rights: {span.license_class} | Retrieved: {span.retrieved_at.isoformat()} | "
            f"Range: {span.start_char}:{span.end_char}\n"
            f"Source text JSON: {source_text}"
        )
    return "\n---\n".join(blocks) if blocks else "(no corpus evidence spans)"
