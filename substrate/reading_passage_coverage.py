r"""Reading passage coverage — what fraction of the document did the reader engage?

Operator vision (asks #2/#6): *"I want to read books or papers (and engage with
it in the same way I would the research workstation)."* The fourth reading-side
measurement axis. After highlight_density (how DENSELY the reader marks a passage),
annotation_substantiveness (how much INFORMATION each note carries), and
reading_flow_continuity (the PATH SHAPE of the reader's progression): THIS
measures BREADTH — what fraction of the document's passages did the reader
actually touch (highlight, annotate, or dwell on) at all?

**Genuinely distinct (different object):**

* ``highlight_density`` (#1973): mark INTENSITY within touched passages (how thick
  a region is marked — spatial, per-touched-passage).
* ``annotation_substantiveness`` (#1978): note CONTENT quality (text — how much
  information the reader put into each note).
* ``reading_flow_continuity`` (#1983): PATH SHAPE (the reader's progression
  through positions over time — did they advance linearly or jump around?).
* THIS (``reading_passage_coverage``): BREADTH (what fraction of the document's
  passages were touched AT ALL — the share of the document the reader engaged).

They are independent. A reader can mark DENSELY within 5 passages (#1973 high)
while leaving the other 95 untouched (coverage 5%), and trace a perfectly LINEAR
path (#1983 high) through those 5 — deep, substantive, but NARROW engagement.
Conversely a reader can touch every passage once (coverage 100%) but mark each
sparingly (#1973 low) with thin notes (#1978 low). Depth (density/content) and
breadth (coverage) are opposite dimensions of reading engagement; a complete
reading-quality picture needs both, plus the path between them (continuity).
Coverage tells the platform whether the reader engaged with the WHOLE document or
skipped large sections — informing reading UX (surface an untouched TOC section,
flag a partial read).

**The measurement (hard to vary).** Given the document's total passage count and
the set of passage indices the reader touched (any highlight, annotation, or
dwell event landing in that passage):

* ``touched_count`` — distinct passages touched.
* ``coverage_ratio = touched_count / total_passages`` — in ``[0, 1]`` (0 = nothing
  touched; 1 = the entire document engaged).
* ``untouched_count = total_passages - touched_count`` — the complement, carried
  for the reading UX (the specific count of skipped sections).
* ``gaps`` — contiguous runs of untouched passage indices, auditable (so the
  platform can surface WHERE the reader skipped, not just how much). Each gap
  carries its start index, end index, and length.

**Verdict (distinct honest states, never collapsed):**

* ``total_passages == 0`` -> ``unknown`` (defer — an empty document has no passages
  to engage; never fabricated as fully-covered).
* ``total_passages > 0`` AND ``touched_count == 0`` -> ``unread`` (the document
  was opened but nothing was touched — a REAL measured verdict, distinct from
  ``unknown``; the reader did not engage at all).
* ``coverage_ratio >= thorough_threshold`` (default ``0.85``) -> ``thorough``
  (near-complete breadth — the reader engaged with most of the document).
* ``0 < coverage_ratio < thorough_threshold`` -> ``partial`` (engaged some
  sections but left meaningful gaps).
* ``coverage_ratio == 0`` (handled by ``unread`` above).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict on an empty document.
* ``unread`` never collapses with ``unknown``: an empty document is ``unknown``
  (nothing to read); a non-empty document with zero touches is ``unread`` (the
  reader chose to engage with nothing — a measured verdict).
* ``coverage_ratio`` is a real measured fraction, carried even when ``0.0`` (the
  reader touched nothing — a real signal, not deferred).
* Touched indices must be in ``[0, total_passages)`` (raises otherwise — an index
  outside the document is a recording error). Duplicate indices are de-duplicated
  (touching the same passage twice is one touched passage).
* ``total_passages`` must be non-negative (raises).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own plain numeric input
(passages + touched indices); the route layer adapts 1:1 from the reader's
highlight/annotation/dwell stream, mapping each event to its passage index.
Pure-Python: stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_THOROUGH_THRESHOLD: float = 0.85


class ReadingPassageCoverageError(ValueError):
    """A reading-passage-coverage input violates a load-bearing invariant."""


@dataclass(frozen=True)
class CoverageGap:
    """One contiguous run of untouched passages. Auditable."""

    start_index: int  # inclusive
    end_index: int  # inclusive
    length: int  # end - start + 1


@dataclass(frozen=True)
class ReadingPassageCoverageReport:
    """The reading-breadth verdict. Advisory, pure."""

    total_passages: int
    touched_count: int
    untouched_count: int
    coverage_ratio: float | None  # touched/total; None when unknown (empty doc)
    gaps: tuple[CoverageGap, ...]  # contiguous untouched runs, sorted
    thorough_threshold: float
    verdict: str  # thorough | partial | unread | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _compute_gaps(
    touched_sorted: list[int], total: int
) -> tuple[CoverageGap, ...]:
    """Find contiguous untouched runs given sorted unique touched indices."""
    gaps: list[CoverageGap] = []
    cursor = 0  # next expected untouched index
    for idx in touched_sorted:
        if idx > cursor:
            gaps.append(
                CoverageGap(
                    start_index=cursor, end_index=idx - 1, length=idx - cursor
                )
            )
        cursor = idx + 1
    if cursor < total:
        gaps.append(
            CoverageGap(
                start_index=cursor, end_index=total - 1, length=total - cursor
            )
        )
    return tuple(gaps)


def measure_reading_passage_coverage(
    total_passages: int,
    touched_indices: Sequence[int],
    *,
    thorough_threshold: float = _DEFAULT_THOROUGH_THRESHOLD,
) -> ReadingPassageCoverageReport:
    """Measure what fraction of a document the reader engaged with.

    ``total_passages`` is the document's passage count.
    ``touched_indices`` is the set of passage indices the reader touched
    (any highlight, annotation, or dwell event). Returns a
    :class:`ReadingPassageCoverageReport`.

    Raises:
        ReadingPassageCoverageError: if ``total_passages`` is negative, any
            touched index is outside ``[0, total_passages)``, or
            ``thorough_threshold`` is outside ``(0, 1]``.
    """
    if total_passages < 0:
        raise ReadingPassageCoverageError(
            f"total_passages must be non-negative; got {total_passages}"
        )
    if not 0.0 < thorough_threshold <= 1.0:
        raise ReadingPassageCoverageError(
            "thorough_threshold must be in the open-closed interval (0.0, 1.0]; "
            f"got {thorough_threshold!r}"
        )

    for idx in touched_indices:
        if not 0 <= idx < total_passages:
            raise ReadingPassageCoverageError(
                f"touched index {idx} out of range [0, {total_passages})"
            )

    if total_passages == 0:
        return ReadingPassageCoverageReport(
            total_passages=0,
            touched_count=0,
            untouched_count=0,
            coverage_ratio=None,
            gaps=(),
            thorough_threshold=thorough_threshold,
            verdict="unknown",
            notes=("empty document — no passages to engage",),
        )

    touched_sorted = sorted(set(touched_indices))
    touched_count = len(touched_sorted)
    untouched_count = total_passages - touched_count
    coverage_ratio = touched_count / total_passages
    gaps = _compute_gaps(touched_sorted, total_passages)

    if touched_count == 0:
        verdict = "unread"
    elif coverage_ratio >= thorough_threshold:
        verdict = "thorough"
    else:
        verdict = "partial"

    notes = (
        f"{touched_count} of {total_passages} passage(s) touched "
        f"({coverage_ratio:.4f}); {len(gaps)} gap run(s)",
    )

    return ReadingPassageCoverageReport(
        total_passages=total_passages,
        touched_count=touched_count,
        untouched_count=untouched_count,
        coverage_ratio=coverage_ratio,
        gaps=gaps,
        thorough_threshold=thorough_threshold,
        verdict=verdict,
        notes=notes,
    )
