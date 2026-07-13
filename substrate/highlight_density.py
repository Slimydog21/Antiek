"""Highlight-density — how densely does the reader mark a passage?

Operator vision (asks #2/#3/#6): *"reading and research are the same thing"* and
the core reading workflow — the reader highlights a span, then spins up a deep
research instance off that highlight, optionally merges it back. The highlight is
the operator's explicit *"this is valuable — chase it"* gesture. A passage the
reader marks densely is high-engagement, high-value material (dense seed ground
for floating-window research); a passage left unmarked is passive reading (no
seed was planted). **No axis measured reading engagement before this** — the
DR-quality axes measure research ARTIFACTS (insights/synthesis/sources); this is
the first READING-side measurement axis.

**Genuinely distinct (different object measured):**

* all 28 DR-quality axes: measure the research ARTIFACT (the output of a chase).
* ``citation_density`` / ``source_diversity``: measure the evidence base of an
  artifact (how many sources / how broad).
* THIS (``highlight_density``): measures the READER's engagement with a PASSAGE
  (how much of the source text the reader marked as valuable). The reader-side
  counterpart to the artifact-side axes — it predicts how much research a passage
  will generate.

**The measurement (hard to vary):**

Given a passage of ``passage_token_count`` tokens and a set of highlight spans
(each a half-open ``[start, end)`` token-offset range into the passage):

* ``highlighted_token_count`` = the size of the UNION of all spans (distinct
  positions highlighted — overlapping highlights do NOT double-count; a reader
  who highlights a sentence then the paragraph containing it marks the paragraph
  once, not twice)
* ``coverage_ratio = highlighted_token_count / passage_token_count`` in ``[0,1]``
  — the share of the passage the reader marked
* ``highlight_count`` = number of distinct spans (carried for auditability —
  many small picks vs one big grab are different engagement shapes)
* ``density_per_100`` = ``highlight_count / passage_token_count * 100`` (carried
  for auditability — highlights per 100 tokens)

**Verdict:**

* ``unknown`` — ``passage_token_count == 0`` (no measurable passage — defer,
  never fabricate engagement)
* ``unmarked`` — passage exists, ``highlight_count == 0`` (the reader marked
  NOTHING — a REAL, measured state: passive reading or material that prompted no
  chase. Distinct from ``unknown`` — there WAS a passage, the reader just did not
  mark it)
* ``dense`` — ``coverage_ratio >= dense_threshold`` (default ``0.20`` — the
  reader marked a fifth or more; high-engagement seed ground; boundary inclusive)
* ``selective`` — ``0 < coverage_ratio < dense_threshold`` (the reader marked
  specific points — targeted engagement)

**Honesty rules (load-bearing):**

* ``unknown`` ≠ ``unmarked`` (two distinct honest states — never collapse. A
  zero-token passage cannot be measured; a real passage with zero highlights WAS
  measured and the answer is "passive").
* overlapping highlights are UNIONED, never summed (double-counting would inflate
  engagement — a reader who re-highlights is not more engaged).
* spans must be within ``[0, passage_token_count]`` and ``start < end``
  (non-empty); out-of-bounds or inverted spans raise (a recording error, not an
  input).
* ``coverage_ratio`` is ``None`` when ``passage_token_count == 0`` (defer, never
  ``0.0``).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** No reading substrate exists on frozen
``origin/main``; this defines its own ``HighlightSpan`` input shape (the route
layer adapts 1:1 from the reading app's real highlight positions). Pure-Python:
stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_DENSE_THRESHOLD: float = 0.20


@dataclass(frozen=True)
class HighlightSpan:
    """A half-open [start, end) token-offset range into the passage. Pure input."""

    start: int
    end: int


@dataclass(frozen=True)
class HighlightDensityReport:
    """The highlight-density verdict for one passage. Advisory, pure."""

    passage_token_count: int
    highlight_count: int
    highlighted_token_count: int  # union size; 0 if no highlights
    coverage_ratio: float | None  # union/passage; None when passage_token_count == 0
    density_per_100: float | None  # highlights per 100 tokens; None when passage empty
    dense_threshold: float
    verdict: str  # unknown | unmarked | dense | selective
    notes: tuple[str, ...]
    authority: str = "advisory"


class HighlightDensityError(ValueError):
    """A highlight-density input violates a load-bearing invariant."""


def measure_highlight_density(
    passage_token_count: int,
    highlights: Sequence[HighlightSpan],
    *,
    dense_threshold: float = _DEFAULT_DENSE_THRESHOLD,
) -> HighlightDensityReport:
    """Measure how densely the reader marked a passage.

    ``passage_token_count`` is the token length of the passage (>= 0).
    ``highlights`` are the reader's highlight spans (half-open token offsets).
    ``dense_threshold`` is the coverage fraction above which marking is "dense"
    (default 0.20).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if passage_token_count < 0:
        raise HighlightDensityError(
            f"passage_token_count must be >= 0, got {passage_token_count!r}"
        )
    if not 0.0 <= dense_threshold <= 1.0:
        raise HighlightDensityError(
            f"dense_threshold must be in [0,1], got {dense_threshold!r}"
        )

    # Validate every span (bounds + non-empty).
    for span in highlights:
        if span.start < 0 or span.end < 0:
            raise HighlightDensityError(
                f"span offsets must be >= 0, got ({span.start}, {span.end})"
            )
        if span.start >= span.end:
            raise HighlightDensityError(
                f"span must be non-empty (start < end), got ({span.start}, {span.end})"
            )
        if span.end > passage_token_count:
            raise HighlightDensityError(
                f"span end {span.end} exceeds passage_token_count "
                f"{passage_token_count}"
            )

    # No measurable passage -> unknown (defer, never fabricate engagement).
    if passage_token_count == 0:
        return _report(
            0, len(highlights), 0, None, None, dense_threshold, "unknown",
            [
                "highlight-density measures how densely the reader marked a passage "
                "(the engagement signal that seeds highlight->deep-research); distinct "
                "from all DR-quality axes (those measure research ARTIFACTS, this "
                "measures READER engagement with a PASSAGE)",
                "verdict unknown — passage_token_count is 0 (no measurable passage); "
                "coverage_ratio is None (defer, never fabricated)",
            ],
        )

    highlight_count = len(highlights)

    # Real passage, zero highlights -> unmarked (passive reading — a MEASURED state).
    if highlight_count == 0:
        return _report(
            passage_token_count, 0, 0, 0.0, 0.0, dense_threshold, "unmarked",
            [
                "highlight-density measures how densely the reader marked a passage "
                "(the engagement signal that seeds highlight->deep-research); distinct "
                "from all DR-quality axes (those measure research ARTIFACTS, this "
                "measures READER engagement with a PASSAGE)",
                "verdict unmarked — the passage exists but the reader marked NOTHING "
                "(passive reading, or material that prompted no chase); a REAL measured "
                "state, distinct from unknown (no passage) — never fabricated",
            ],
        )

    # Union of spans (overlapping highlights do not double-count — merge intervals).
    highlighted_token_count = _union_size(highlights)
    coverage_ratio = highlighted_token_count / passage_token_count
    density_per_100 = highlight_count / passage_token_count * 100.0

    verdict = "dense" if coverage_ratio >= dense_threshold else "selective"

    notes: list[str] = [
        "highlight-density measures how densely the reader marked a passage (the "
        "engagement signal that seeds highlight->deep-research); distinct from all "
        "DR-quality axes (those measure research ARTIFACTS, this measures READER "
        "engagement with a PASSAGE)",
        "highlighted_token_count is the UNION of spans (overlapping highlights do "
        "NOT double-count — a reader who re-highlights is not more engaged); "
        "coverage_ratio = union/passage in [0,1]; density_per_100 = highlights per "
        "100 tokens (carried for auditability)",
        "verdict: dense (coverage_ratio >= dense_threshold, boundary inclusive), "
        "selective (0 < coverage < threshold), unmarked (passage exists, zero "
        "highlights), unknown (no passage)",
        "unknown != unmarked (two distinct honest states — a zero-token passage "
        "cannot be measured; a real passage with zero highlights WAS measured and "
        "the answer is passive)",
    ]
    notes.append(
        f"verdict {verdict}: {highlight_count} highlight(s) covering "
        f"{highlighted_token_count}/{passage_token_count} tokens "
        f"(coverage {coverage_ratio:.0%}, {density_per_100:.1f}/100); "
        f"dense_threshold {dense_threshold:.0%}"
    )

    return _report(
        passage_token_count,
        highlight_count,
        highlighted_token_count,
        coverage_ratio,
        density_per_100,
        dense_threshold,
        verdict,
        notes,
    )


def _union_size(spans: Sequence[HighlightSpan]) -> int:
    """Count distinct token positions covered by the spans (merge intervals).

    Spans are validated non-empty and in-bounds by the caller; sort by start and
    merge overlapping/touching ranges.
    """
    ordered = sorted((s.start, s.end) for s in spans)
    total = 0
    current_start = -1
    current_end = -1
    for start, end in ordered:
        if start >= current_end:
            # Disjoint (or first) — close the previous, open a new one.
            total += current_end - current_start if current_start >= 0 else 0
            current_start, current_end = start, end
        else:
            # Overlapping or nested — extend the current union.
            current_end = max(current_end, end)
    total += current_end - current_start if current_start >= 0 else 0
    return total


def _report(
    passage_token_count: int,
    highlight_count: int,
    highlighted_token_count: int,
    coverage_ratio: float | None,
    density_per_100: float | None,
    dense_threshold: float,
    verdict: str,
    notes: list[str],
) -> HighlightDensityReport:
    return HighlightDensityReport(
        passage_token_count=passage_token_count,
        highlight_count=highlight_count,
        highlighted_token_count=highlighted_token_count,
        coverage_ratio=coverage_ratio,
        density_per_100=density_per_100,
        dense_threshold=dense_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
