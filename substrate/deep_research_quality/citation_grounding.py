"""Citation grounding verifier — the defensibility axis of highest-quality DR.

The operator's ask: *"...I want to provide the highest quality deep research
product in the world."* A deep-research output with a fabricated citation (a
reference to a source that does not exist) or an unsupported assertion (a factual
claim with no citation) is not high-quality — it is indefensible. This module is
the PURE verifier that checks a research output's citation grounding BEFORE it
reaches the operator. It is the mechanical floor of defensibility.

**Distinct from** ``gap_detection/unsupported.py``. That module is GRAPH-level +
structural (does a claim NODE in the DB have evidence-bearing edges?) and requires
a DB connection. This module is OUTPUT-level + textual (does every citation in the
research OUTPUT resolve to a real source, and does every assertion carry one?) and
is pure — no DB, no network, no LLM. The two are complementary: the graph-level
detector finds structural gaps in stored knowledge; this finds textual gaps in
produced output. Both feed defensibility; conflating them hides one axis behind
the other.

**What this checks (and honestly does NOT check):**

  * **Citation RESOLUTION (mechanical, pure):** every citation token in the output
    (e.g., ``[src-abc]``) resolves to a registered source. A citation to a
    nonexistent source id is a FABRICATION — the cardinal sin of deep research.
    This check is deterministic and pure.
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

  * **Fabricated citations are fatal.** A single unresolved citation makes the
    verdict ``ungrounded`` — there is no "partial credit" for a fabricated
    reference. The operator must know EXACTLY which citation is fabricated.
  * **Unsupported assertions are flagged, not fatal.** An uncited assertion is a
    gap (verdict ``partially_grounded``), not a fabrication — the claim might be
    common knowledge or the operator's own analysis. Each is listed with its text
    so the operator can decide whether to cite or cut.
  * **The source registry is explicit.** Only sources the caller REGISTERED are
    resolvable. A citation to an unregistered source is unresolved — even if the
    source "exists" somewhere. The verifier cannot invent sources it wasn't given.
  * **Verdicts are graduated, never vague:** ``grounded`` (zero fabricated, zero
    unsupported), ``partially_grounded`` (zero fabricated, some unsupported),
    ``ungrounded`` (any fabricated).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class CitationGroundingError(ValueError):
    """A grounding input violates a load-bearing invariant."""


_CITATION_RE = re.compile(r"\[src-([a-zA-Z0-9_-]+)\]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class SourceRecord:
    """A source available to cite. The caller registers these explicitly."""

    source_id: str
    title: str = ""
    url: str | None = None


@dataclass(frozen=True)
class ResolvedCitation:
    """A citation that resolved to a registered source."""

    source_id: str
    occurrences: int  # how many times [src-id] appears in the output
    source: SourceRecord


@dataclass(frozen=True)
class FabricatedCitation:
    """A citation token that does NOT resolve to any registered source."""

    source_id: str
    occurrences: int


@dataclass(frozen=True)
class UnsupportedAssertion:
    """A factual assertion sentence with zero citations."""

    sentence: str
    sentence_index: int


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
    """Extract all ``src-`` citation ids from the text, in order of appearance."""
    return [m for m in _CITATION_RE.findall(text)]


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
    if not output_text.strip():
        raise CitationGroundingError(
            "output_text must be non-empty; cannot verify grounding of nothing"
        )

    registry: dict[str, SourceRecord] = {}
    for src in sources:
        if not src.source_id.strip():
            raise CitationGroundingError("every SourceRecord must have a non-empty source_id")
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
            f"FATAL: {sum(f.occurrences for f in fabricated_map.values())} fabricated "
            f"citation(s) to unregistered source(s) — these are hallucinated references"
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
