"""Citation locator-precision axis — do citations point to specific passages or whole documents?

The citation surface has coverage (#1966 — how many claims are cited?), relevance (is the cited
source topically relevant?), and validate_refs (do the references resolve — existence?). THIS
axis measures a different question: the **precision of the citation LOCATOR** — does a citation
point to a SPECIFIC anchor inside the source (a quoted passage, a paragraph, a page, a section)
or only to the whole document ("see Smith 2023")? Precise, sub-document locators are what make a
research asset genuinely *traceable* in the operator's HTML-native vision — the operator can click
straight to the supporting passage. Document-level citations force the reader to hunt, defeating
traceability.

This is genuinely distinct from the other citation axes: coverage asks *how many*, relevance asks
*is it the right source*, validate asks *does it exist* — THIS asks *how precisely does it
locate the evidence within the source*. Four different questions.

**Locator granularity (5 canonical levels, most -> least precise; route layer normalizes aliases):**

* ``quote`` — exact quoted text (rank 4; the locator IS the evidence).
* ``paragraph`` — a paragraph/passage anchor (rank 3).
* ``page`` — a page reference (rank 2).
* ``section`` — a section/chapter anchor (rank 1).
* ``document`` — whole-document reference, no internal anchor (rank 0; the coarse/vague case).
* anything else (empty, ``unknown``, unrecognized) -> **unlocated** (no locator at all; distinct
  honest state, never forced into document or anchor).

**Measured fields:**

* ``citation_count`` — total citations.
* ``anchor_count`` — citations with a sub-document locator (quote/paragraph/page/section) — the
  traceable, click-to-passage citations.
* ``document_count`` — citations pointing to the whole document (coarse, hunt-required).
* ``unlocated_count`` — citations with no/unknown locator (data gap, distinct from document-level).
* ``located_count`` = ``anchor_count + document_count``.
* ``locator_distribution`` — per-type ``(locator_type, count, precision_rank)`` sorted by precision
  rank desc then type (auditable: the operator sees the full granularity mix, not a black-box
  fraction).
* ``located_precise_fraction`` = ``anchor_count / located_count`` — the precision AMONG citations
  that HAVE locators (``None`` when zero citations are located — defer).
* ``unlocated_fraction`` = ``unlocated_count / citation_count`` — the data-completeness gap
  (``None`` for ``unknown``).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero citations -> ``unknown`` (no locator precision to measure — defer, never fabricated).
* every citation unlocated -> ``unlocated`` (no locator anywhere — a data-completeness gap distinct
  from a precision verdict; defer, never fabricated ``document_level``).
* ``located_precise_fraction >= precise_threshold`` (default ``0.60``) -> ``anchored`` (most
  located citations point to specific passages — high traceability).
* ``located_precise_fraction <= vague_threshold`` (default ``0.20``) -> ``document_level`` (most
  located citations point to whole documents — coarse, low traceability).
* otherwise -> ``mixed_precision`` (a blend of anchored and document-level locators).

**DESCRIPTIVE NOT NORMATIVE:** ``anchored`` does NOT mean "good" — over-precise micro-citations
can fragment the argument and a well-chosen document-level citation is sometimes the right call
for a foundational source. ``document_level`` does NOT mean "bad" — for a whole-source claim
("Smith's framework argues X") a document locator is honest and sufficient. The operator judges
whether the locator precision matches the CLAIM's needs. This axis surfaces the FACT of locator
granularity; it does not prescribe the right precision.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero citations are supplied.
* ``unlocated`` is its own honest state — a MISSING locator is distinct from a document-level
  locator (``located_precise_fraction`` is computed over LOCATED citations only, so missing
  locators never masquerade as vague document-level ones).
* ``located_precise_fraction`` is ``None`` only for ``unknown`` / ``unlocated``; for any located
  citation it is a measured ``[0, 1]``.
* thresholds are absolute fractions (scale-free: 60% anchored means 60% at 5 or 500 citations).
* unrecognized locator types defer to ``unlocated`` (never fabricated as a known type); every
  citation's type carried verbatim in ``locator_distribution`` (auditable, no black-box fraction).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain ``(claim_id, locator_type)`` pairs; route layer adapts
  1:1 from the citation-locator log, normalizing aliases to the 5 canonical types).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "LocatorBucket",
    "CitationLocatorPrecisionReport",
    "measure_citation_locator_precision",
]

_DEFAULT_PRECISE_THRESHOLD = 0.60
_DEFAULT_VAGUE_THRESHOLD = 0.20

# Canonical locator types -> precision rank (higher = more precise). Unrecognized -> unlocated.
_LOCATOR_RANKS: dict[str, int] = {
    "quote": 4,
    "paragraph": 3,
    "page": 2,
    "section": 1,
    "document": 0,
}
_UNLOCATED_RANK = -1
_UNLOCATED_LABEL = "unlocated"


@dataclass(frozen=True)
class LocatorBucket:
    """One locator-type's auditable count + precision rank."""

    locator_type: str  # canonical type, or "unlocated"
    count: int
    precision_rank: int  # 4 (quote) .. 0 (document); -1 for unlocated


@dataclass(frozen=True)
class CitationLocatorPrecisionReport:
    """The citation locator-precision surface for one research asset. Advisory, pure."""

    citation_count: int
    anchor_count: int
    document_count: int
    unlocated_count: int
    located_count: int
    locator_distribution: tuple[LocatorBucket, ...]
    located_precise_fraction: float | None
    unlocated_fraction: float | None
    precise_threshold: float
    vague_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_citation_locator_precision(
    citations: Sequence[tuple[str, str]],
    *,
    precise_threshold: float = _DEFAULT_PRECISE_THRESHOLD,
    vague_threshold: float = _DEFAULT_VAGUE_THRESHOLD,
) -> CitationLocatorPrecisionReport:
    r"""Measure the locator-precision of a research asset's citations.

    ``citations`` are ``(claim_id, locator_type)`` pairs (the route layer supplies these from the
    citation-locator log, normalizing aliases to the 5 canonical types: quote/paragraph/page/
    section/document). Returns a :class:`CitationLocatorPrecisionReport`.

    Raises:
        ValueError: if thresholds are out of their valid ranges.
    """
    if not 0.0 <= vague_threshold <= 1.0:
        raise ValueError(
            f"vague_threshold must be in [0.0, 1.0]; got {vague_threshold}"
        )
    if not 0.0 <= precise_threshold <= 1.0:
        raise ValueError(
            f"precise_threshold must be in [0.0, 1.0]; got {precise_threshold}"
        )
    if not vague_threshold <= precise_threshold <= 1.0:
        raise ValueError(
            f"precise_threshold ({precise_threshold}) must be in "
            f"[vague_threshold ({vague_threshold}), 1.0]"
        )

    citation_count = len(citations)

    if citation_count == 0:
        return CitationLocatorPrecisionReport(
            citation_count=0,
            anchor_count=0,
            document_count=0,
            unlocated_count=0,
            located_count=0,
            locator_distribution=(),
            located_precise_fraction=None,
            unlocated_fraction=None,
            precise_threshold=precise_threshold,
            vague_threshold=vague_threshold,
            verdict="unknown",
            notes=("no citations — locator precision unmeasurable",),
        )

    # Tally by canonical type; unrecognized -> unlocated.
    tallies: dict[str, int] = {}
    for _claim_id, raw_locator in citations:
        key = raw_locator.strip().lower() if isinstance(raw_locator, str) else ""
        if key not in _LOCATOR_RANKS:
            key = _UNLOCATED_LABEL
        tallies[key] = tallies.get(key, 0) + 1

    anchor_count = sum(
        c for t, c in tallies.items()
        if t != _UNLOCATED_LABEL and _LOCATOR_RANKS[t] >= 1
    )
    document_count = tallies.get("document", 0)
    unlocated_count = tallies.get(_UNLOCATED_LABEL, 0)
    located_count = anchor_count + document_count

    distribution = tuple(
        sorted(
            (
                LocatorBucket(locator_type=t, count=c, precision_rank=_LOCATOR_RANKS.get(t, _UNLOCATED_RANK))
                for t, c in tallies.items()
            ),
            key=lambda b: (b.precision_rank, b.locator_type),
            reverse=True,
        )
    )

    located_precise_fraction = (
        anchor_count / located_count if located_count > 0 else None
    )
    unlocated_fraction = unlocated_count / citation_count

    if located_count == 0:
        verdict = "unlocated"
        notes = ("every citation lacks a locator — precision unmeasurable (data gap)",)
    elif located_precise_fraction is not None and located_precise_fraction >= precise_threshold:
        verdict = "anchored"
        notes = (
            f"located_precise_fraction {located_precise_fraction:.4f} >= precise_threshold "
            f"{precise_threshold:.2f} — most located citations point to specific passages",
        )
    elif located_precise_fraction is not None and located_precise_fraction <= vague_threshold:
        verdict = "document_level"
        notes = (
            f"located_precise_fraction {located_precise_fraction:.4f} <= vague_threshold "
            f"{vague_threshold:.2f} — most located citations point to whole documents",
        )
    else:
        verdict = "mixed_precision"
        notes = (
            f"located_precise_fraction "
            f"{located_precise_fraction if located_precise_fraction is not None else 'n/a'} "
            "between thresholds — a blend of anchored and document-level locators",
        )

    return CitationLocatorPrecisionReport(
        citation_count=citation_count,
        anchor_count=anchor_count,
        document_count=document_count,
        unlocated_count=unlocated_count,
        located_count=located_count,
        locator_distribution=distribution,
        located_precise_fraction=located_precise_fraction,
        unlocated_fraction=unlocated_fraction,
        precise_threshold=precise_threshold,
        vague_threshold=vague_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
