"""Citation grounding verifier — the defensibility axis of highest-quality DR.

The operator's ask: *"...I want to provide the highest quality deep research
product in the world."* A deep-research output with an unresolved citation or an
unsupported assertion (a factual claim with no citation) is not high-quality — it
is indefensible. This module is
the PURE verifier that checks a research output's citation grounding BEFORE it
reaches the operator. It is the mechanical floor of defensibility.

**Distinct from** ``gap_detection/unsupported.py``. That module is GRAPH-level +
structural (does a claim NODE in the DB have evidence-bearing edges?) and requires
a DB connection. This module is OUTPUT-level + textual (does every citation in the
research OUTPUT resolve to a caller-registered source, and does every assertion
carry one?) and is pure — no DB, no network, no LLM. The two are complementary:
the graph-level
detector finds structural gaps in stored knowledge; this finds textual gaps in
produced output. Both feed defensibility; conflating them hides one axis behind
the other.

**What this checks (and honestly does NOT check):**

  * **Citation RESOLUTION (mechanical, pure):** every citation token in the output
    (e.g., ``[src-abc]``) resolves to a caller-registered source. An unresolved
    citation is fatal because this verifier cannot establish its provenance.
    Registration alone does NOT prove that a source exists or supports a claim.
  * **Citation COVERAGE (structural, pure):** every assertion — a sentence making
    a factual claim — carries at least one citation. An uncited assertion is a
    defensibility gap (the reader cannot trace it). This check is structural
    (sentence-level citation presence), not semantic.
  * **What it does NOT check (honest scope):** citation ACCURACY — whether the
    cited source actually SUPPORTS the claim — is an LLM-judge concern (different
    lineage, out of scope for a pure function). This verifier never claims to
    verify accuracy; its ``notes`` say so explicitly. A pure function cannot read
    a source and judge support; pretending it could would be the opposite of
    defensibility.

**Honesty rules (load-bearing):**

  * **Unresolved citations are fatal.** A single unresolved citation makes the
    verdict ``ungrounded``. The report retains the historical
    ``fabricated_citations`` field name, but does not claim that registration is
    proof of existence or that an unresolved identifier is conclusively fake.
  * **Unsupported assertions are flagged, not fatal.** An uncited assertion is a
    gap (verdict ``partially_grounded``), not a fabrication — the claim might be
    common knowledge or the operator's own analysis. Each is listed with its text
    so the operator can decide whether to cite or cut.
  * **The source registry is explicit.** Only sources the caller REGISTERED are
    resolvable. A citation to an unregistered source is unresolved — even if the
    source "exists" somewhere. The verifier cannot invent sources it wasn't given.
  * **Verdicts are graduated, never vague:** ``grounded`` (zero unresolved, zero
    unsupported), ``partially_grounded`` (zero unresolved, some unsupported),
    ``ungrounded`` (any unresolved).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class CitationGroundingError(ValueError):
    """A grounding input violates a load-bearing invariant."""


_CITATION_RE = re.compile(r"\[src-([a-zA-Z0-9_-]{1,128})\]")
_CITATION_INTRO_RE = re.compile(r"\[\s*(?i:src-)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_MAX_OUTPUT_CHARS = 1_000_000
_MAX_SOURCES = 10_000
_MAX_SOURCE_ID_CHARS = 128
_MAX_SOURCE_TITLE_CHARS = 4_096
_MAX_SOURCE_URL_CHARS = 8_192
_MAX_CITATION_TOKENS = 100_000
_MAX_SENTENCES = 100_000


def _require_exact_fields(value: object, expected: frozenset[str], label: str) -> None:
    if frozenset(vars(value)) != expected:
        raise CitationGroundingError(f"{label} must contain exactly its declared fields")


@dataclass(frozen=True)
class SourceRecord:
    """A source available to cite. The caller registers these explicitly."""

    source_id: str
    title: str = ""
    url: str | None = None

    def __post_init__(self) -> None:
        _require_exact_fields(
            self, frozenset({"source_id", "title", "url"}), "SourceRecord"
        )
        if type(self.source_id) is not str:
            raise CitationGroundingError("SourceRecord.source_id must be a string")
        if not self.source_id or self.source_id != self.source_id.strip():
            raise CitationGroundingError(
                "SourceRecord.source_id must be non-empty canonical text without surrounding whitespace"
            )
        if len(self.source_id) > _MAX_SOURCE_ID_CHARS or re.fullmatch(
            r"[a-zA-Z0-9_-]+", self.source_id
        ) is None:
            raise CitationGroundingError(
                "SourceRecord.source_id must contain only letters, digits, underscores, or hyphens "
                f"and be at most {_MAX_SOURCE_ID_CHARS} characters"
            )
        if type(self.title) is not str or len(self.title) > _MAX_SOURCE_TITLE_CHARS:
            raise CitationGroundingError(
                f"SourceRecord.title must be a string of at most {_MAX_SOURCE_TITLE_CHARS} characters"
            )
        if self.url is not None and (
            type(self.url) is not str or len(self.url) > _MAX_SOURCE_URL_CHARS
        ):
            raise CitationGroundingError(
                "SourceRecord.url must be None or a string of at most "
                f"{_MAX_SOURCE_URL_CHARS} characters"
            )


@dataclass(frozen=True)
class ResolvedCitation:
    """A citation that resolved to a registered source."""

    source_id: str
    occurrences: int  # how many times [src-id] appears in the output
    source: SourceRecord

    def __post_init__(self) -> None:
        _require_exact_fields(
            self,
            frozenset({"source_id", "occurrences", "source"}),
            "ResolvedCitation",
        )
        if type(self.source) is not SourceRecord:
            raise CitationGroundingError("ResolvedCitation.source must be a SourceRecord")
        self.source.__post_init__()
        if type(self.source_id) is not str or self.source_id != self.source.source_id:
            raise CitationGroundingError(
                "ResolvedCitation.source_id must exactly match its source"
            )
        if type(self.occurrences) is not int or not 1 <= self.occurrences <= _MAX_CITATION_TOKENS:
            raise CitationGroundingError(
                "ResolvedCitation.occurrences must be a positive bounded integer"
            )


@dataclass(frozen=True)
class FabricatedCitation:
    """A citation token that does NOT resolve to any registered source."""

    source_id: str
    occurrences: int

    def __post_init__(self) -> None:
        _require_exact_fields(
            self, frozenset({"source_id", "occurrences"}), "FabricatedCitation"
        )
        if (
            type(self.source_id) is not str
            or not self.source_id
            or len(self.source_id) > _MAX_SOURCE_ID_CHARS
            or re.fullmatch(r"[a-zA-Z0-9_-]+", self.source_id) is None
        ):
            raise CitationGroundingError(
                "FabricatedCitation.source_id must be a canonical bounded source id"
            )
        if type(self.occurrences) is not int or not 1 <= self.occurrences <= _MAX_CITATION_TOKENS:
            raise CitationGroundingError(
                "FabricatedCitation.occurrences must be a positive bounded integer"
            )


@dataclass(frozen=True)
class UnsupportedAssertion:
    """A factual assertion sentence with zero citations."""

    sentence: str
    sentence_index: int

    def __post_init__(self) -> None:
        _require_exact_fields(
            self, frozenset({"sentence", "sentence_index"}), "UnsupportedAssertion"
        )
        if (
            type(self.sentence) is not str
            or not self.sentence
            or len(self.sentence) > _MAX_OUTPUT_CHARS
        ):
            raise CitationGroundingError(
                "UnsupportedAssertion.sentence must be non-empty bounded text"
            )
        if (
            type(self.sentence_index) is not int
            or not 0 <= self.sentence_index < _MAX_SENTENCES
        ):
            raise CitationGroundingError(
                "UnsupportedAssertion.sentence_index must be a bounded non-negative integer"
            )


@dataclass(frozen=True)
class GroundingReport:
    """The defensibility verdict for a research output.

    ``verdict`` is the load-bearing signal: ``grounded`` / ``partially_grounded`` /
    ``ungrounded``. The operator decides what to do with the details.
    """

    verdict: str  # "grounded" | "partially_grounded" | "ungrounded"
    resolved_citations: tuple[ResolvedCitation, ...]
    fabricated_citations: tuple[FabricatedCitation, ...]
    unsupported_assertions: tuple[UnsupportedAssertion, ...]
    total_citation_tokens: int
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_exact_fields(
            self,
            frozenset(
                {
                    "verdict",
                    "resolved_citations",
                    "fabricated_citations",
                    "unsupported_assertions",
                    "total_citation_tokens",
                    "notes",
                }
            ),
            "GroundingReport",
        )
        if self.verdict not in {"grounded", "partially_grounded", "ungrounded"}:
            raise CitationGroundingError("GroundingReport.verdict is invalid")
        collections = (
            ("resolved_citations", self.resolved_citations, ResolvedCitation),
            ("fabricated_citations", self.fabricated_citations, FabricatedCitation),
            ("unsupported_assertions", self.unsupported_assertions, UnsupportedAssertion),
        )
        for name, values, expected_type in collections:
            if type(values) is not tuple or any(type(value) is not expected_type for value in values):
                raise CitationGroundingError(
                    f"GroundingReport.{name} must be a tuple of exact {expected_type.__name__} values"
                )
            for value in values:
                value.__post_init__()
        if (
            type(self.notes) is not tuple
            or len(self.notes) > 16
            or any(type(note) is not str or len(note) > 4_096 for note in self.notes)
        ):
            raise CitationGroundingError(
                "GroundingReport.notes must be a bounded tuple of bounded strings"
            )
        if type(self.total_citation_tokens) is not int or not (
            0 <= self.total_citation_tokens <= _MAX_CITATION_TOKENS
        ):
            raise CitationGroundingError(
                "GroundingReport.total_citation_tokens must be a bounded non-negative integer"
            )
        counted_tokens = sum(value.occurrences for value in self.resolved_citations) + sum(
            value.occurrences for value in self.fabricated_citations
        )
        if counted_tokens != self.total_citation_tokens:
            raise CitationGroundingError(
                "GroundingReport.total_citation_tokens must equal reported occurrences"
            )
        expected_verdict = (
            "ungrounded"
            if self.fabricated_citations
            else "partially_grounded"
            if self.unsupported_assertions
            else "grounded"
        )
        if self.verdict != expected_verdict:
            raise CitationGroundingError(
                "GroundingReport.verdict must match its unresolved and unsupported findings"
            )

    @property
    def has_fabricated(self) -> bool:
        return len(self.fabricated_citations) > 0

    @property
    def has_unsupported(self) -> bool:
        return len(self.unsupported_assertions) > 0

    @property
    def resolved_count(self) -> int:
        return len(self.resolved_citations)


def _extract_citation_ids(text: str) -> list[str]:
    """Extract canonical citations; reject citation-like malformed tokens."""
    canonical_matches = list(_CITATION_RE.finditer(text))
    canonical_starts: set[int] = set()
    for match in canonical_matches:
        preceded_by_bracket = match.start() > 0 and text[match.start() - 1] == "["
        followed_by_suffix = match.end() < len(text) and (
            text[match.end()] == "]"
            or text[match.end()].isalnum()
            or text[match.end()] in {"_", "-"}
        )
        if preceded_by_bracket or followed_by_suffix:
            excerpt = text[max(0, match.start() - 1) : match.end() + 20].splitlines()[0]
            raise CitationGroundingError(
                "malformed citation token; expected exact '[src-ID]' syntax near "
                f"{excerpt!r}"
            )
        canonical_starts.add(match.start())
    for intro in _CITATION_INTRO_RE.finditer(text):
        if intro.start() not in canonical_starts:
            excerpt = text[intro.start() : intro.start() + 80].splitlines()[0]
            raise CitationGroundingError(
                "malformed citation token; expected exact '[src-ID]' syntax near "
                f"{excerpt!r}"
            )
    citation_ids = [match.group(1) for match in canonical_matches]
    if len(citation_ids) > _MAX_CITATION_TOKENS:
        raise CitationGroundingError(
            f"output contains more than {_MAX_CITATION_TOKENS} citation tokens"
        )
    return citation_ids


def _is_assertion(sentence: str) -> bool:
    """Heuristic: does this sentence make a factual claim worth citing?

    A sentence with a verb and enough content is an assertion. Short fragments,
    questions, and headings are NOT assertions (they don't need citations). This
    is a structural heuristic — honest about being approximate, not semantic.
    """
    stripped = sentence.strip()
    if len(stripped) < 20:  # too short to be a substantive claim
        return False
    if stripped.endswith("?"):  # questions don't need citations
        return False
    # Must contain a verb-ish word (very rough). Avoids flagging headings/labels.
    return any(w in stripped.lower() for w in (
        " is ", " are ", " was ", " were ", " be ", " has ", " have ", " had ",
        " do ", " does ", " did ", " will ", " would ", " can ", " could ",
        " shows", " found", " suggests", " demonstrates", " proves", " argues",
        " states", " reports", " indicates", " reveals", " implies",
    ))


def verify_citation_grounding(
    *,
    output_text: str,
    sources: list[SourceRecord],
) -> GroundingReport:
    """Verify a research output's citation grounding. Pure, mechanical.

    Checks: (1) every ``[src-id]`` citation resolves to a registered source;
    (2) every assertion sentence carries at least one citation. Returns a
    ``GroundingReport`` with the graduated verdict. Does NOT verify citation
    ACCURACY (whether the source supports the claim) — that is an LLM-judge
    concern, honestly out of scope for a pure function.
    """
    if type(output_text) is not str:
        raise CitationGroundingError("output_text must be a string")
    if len(output_text) > _MAX_OUTPUT_CHARS:
        raise CitationGroundingError(
            f"output_text must be at most {_MAX_OUTPUT_CHARS} characters"
        )
    if not output_text.strip():
        raise CitationGroundingError(
            "output_text must be non-empty; cannot verify grounding of nothing"
        )

    if type(sources) is not list:
        raise CitationGroundingError("sources must be a list of SourceRecord values")
    if len(sources) > _MAX_SOURCES:
        raise CitationGroundingError(f"sources must contain at most {_MAX_SOURCES} records")

    registry: dict[str, SourceRecord] = {}
    for src in sources:
        if type(src) is not SourceRecord:
            raise CitationGroundingError("sources must contain exact SourceRecord values")
        src.__post_init__()
        if src.source_id in registry:
            raise CitationGroundingError(
                f"duplicate SourceRecord.source_id is ambiguous: {src.source_id!r}"
            )
        registry[src.source_id] = src

    citation_ids = _extract_citation_ids(output_text)
    total_tokens = len(citation_ids)

    # --- citation resolution ---
    resolved_map: dict[str, ResolvedCitation] = {}
    fabricated_map: dict[str, FabricatedCitation] = {}
    for cid in citation_ids:
        if cid in registry:
            if cid in resolved_map:
                resolved_map[cid] = ResolvedCitation(
                    source_id=cid,
                    occurrences=resolved_map[cid].occurrences + 1,
                    source=registry[cid],
                )
            else:
                resolved_map[cid] = ResolvedCitation(
                    source_id=cid, occurrences=1, source=registry[cid]
                )
        else:
            if cid in fabricated_map:
                fabricated_map[cid] = FabricatedCitation(
                    source_id=cid, occurrences=fabricated_map[cid].occurrences + 1
                )
            else:
                fabricated_map[cid] = FabricatedCitation(source_id=cid, occurrences=1)

    # --- citation coverage (unsupported assertions) ---
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(output_text) if s.strip()]
    if len(sentences) > _MAX_SENTENCES:
        raise CitationGroundingError(
            f"output contains more than {_MAX_SENTENCES} sentence-like segments"
        )
    unsupported: list[UnsupportedAssertion] = []
    for idx, sent in enumerate(sentences):
        if not _is_assertion(sent):
            continue
        if not _extract_citation_ids(sent):
            unsupported.append(UnsupportedAssertion(sentence=sent.strip(), sentence_index=idx))

    # --- graduated verdict ---
    notes: list[str] = [
        "verifier checks citation RESOLUTION (mechanical) + COVERAGE (structural); "
        "citation ACCURACY (does the source support the claim) is an LLM-judge "
        "concern, out of scope for this pure function"
    ]
    if fabricated_map:
        verdict = "ungrounded"
        notes.append(
            f"FATAL: {sum(f.occurrences for f in fabricated_map.values())} unresolved "
            "citation(s) to unregistered source id(s); this verifier cannot establish "
            "their provenance"
        )
    elif unsupported:
        verdict = "partially_grounded"
        notes.append(
            f"{len(unsupported)} unsupported assertion(s) — uncited factual claims; "
            "the operator should cite or cut each"
        )
    else:
        verdict = "grounded"
        if total_tokens == 0:
            notes.append(
                "no citation tokens found and no assertions detected — output may be "
                "purely structural (headings/fragments); nothing to verify"
            )

    return GroundingReport(
        verdict=verdict,
        resolved_citations=tuple(resolved_map.values()),
        fabricated_citations=tuple(fabricated_map.values()),
        unsupported_assertions=tuple(unsupported),
        total_citation_tokens=total_tokens,
        notes=tuple(notes),
    )


__all__ = [
    "CitationGroundingError",
    "SourceRecord",
    "ResolvedCitation",
    "FabricatedCitation",
    "UnsupportedAssertion",
    "GroundingReport",
    "verify_citation_grounding",
]
