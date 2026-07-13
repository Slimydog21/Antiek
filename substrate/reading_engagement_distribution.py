r"""Reading engagement distribution — is attention spread or clustered?

Operator vision (ask #2, reading=research): *"...I want to read books or papers
(and engage with it in the same way I would the research workstation)..."* The
reader's engagement with a document is not just BREADTH (how many sections touched —
``reading_passage_coverage`` #1987) but DISTRIBUTION: is the engagement mass spread
evenly across the sections the reader touched, or clustered on one hot spot? Two
readers can both touch every section (breadth 100%) yet differ completely: one read
evenly (each section got similar attention), the other skimmed 90% and obsessively
re-engaged one section. The distribution tells the platform WHERE the reader's
attention concentrates — the section they are "interrogating and wrestling with" —
which is exactly the operator's stated mode. A skewed distribution flags the hot
spot for the thought-partner surface (offer a deep-research branch off the
highlighted passage); an even distribution signals a balanced read.

**Genuinely distinct from the reading surface:**

* ``reading_passage_coverage`` (#1987): BREADTH — what FRACTION of sections were
  touched at all (binary per-section flag).
* ``highlight_density`` (#1973): how DENSELY a reader marks WITHIN a passage.
* ``annotation_substantiveness`` (#1978): how much INFORMATION a note carries.
* ``reading_flow_continuity`` (#1983): positional PROGRESSION (linear vs jumping).

NONE measures the DISTRIBUTION of engagement mass across sections. Breadth (#1987)
is a binary touch flag per section — it cannot tell even-spread from one-hot-spot
(both touch every section → breadth 100%). THIS computes a concentration coefficient
(Gini) over per-section touch COUNTS: 0.0 = perfectly even (every touched section got
equal attention), 1.0 = maximally concentrated (all attention on one section).
Orthogonal to breadth: a reader can touch every section (breadth 100%) yet be
maximally concentrated (all touches on one section), or touch every section evenly
(breadth 100%, concentration 0.0). Breadth says "did they reach it?"; distribution
says "how did they spend their attention?" Both matter for understanding how the
reader engaged.

**The measurement (hard to vary).** Given a touch count per section (the number of
engagement events — highlights + annotations + dwells — the route layer aggregates
per section), compute the Gini coefficient over the non-zero counts:

``G = (sum_i sum_j |x_i - x_j|) / (2 * n * n * mean(x))``

where the sum is over all ORDERED pairs of the ``n`` touched sections. ``G`` in
``[0, 1]``: ``0.0`` = every touched section has equal touches (even spread), ``1.0``
= all touches in one section (maximal concentration). Gini is the canonical
inequality statistic — invariant to total touch count (a reader who touches each
section 10 times evenly has the same Gini as one who touches each once evenly).

* ``touched_section_count`` — sections with >= 1 touch.
* ``total_touches`` — sum of all per-section touch counts.
* ``mean_touches_per_section`` — average touches across touched sections.
* ``max_touches`` — the hot-spot section's touch count.
* ``hot_spot_sections`` — sections whose touch count >= ``hot_spot_threshold`` (a
  multiple of the mean, default 2.0 — auditable: where the reader concentrated).
* ``gini`` — the concentration coefficient in ``[0, 1]``; ``None`` when not
  measurable (defer — see honesty rules).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero touched sections (no engagement events) -> ``unread`` (defer — no distribution
  to measure; never fabricated ``even``). Distinct from the empty-document case
  (#1987's ``unknown``) — here we know the document exists, the reader just did not
  engage it.
* exactly one touched section -> ``focused`` (all attention on one section — a
  legitimate deep-dive, not "concentrated" which implies a spread to compare
  against; honest base case).
* ``gini >= high_concentration`` (default ``0.60``) -> ``concentrated`` (engagement
  mass clustered on a hot spot — the "interrogating one section" shape).
* ``gini <= low_concentration`` (default ``0.20``) -> ``even`` (engagement spread
  uniformly — a balanced read). A REAL measured verdict, NOT the default.
* otherwise -> ``moderate`` (some clustering but not extreme — the common shape).

DESCRIPTIVE NOT NORMATIVE: ``concentrated`` does NOT mean "bad" — clustering on one
section may be exactly the operator's "wrestle with the information in front of me"
deep-dive. The platform uses the hot-spot to OFFER a deep-research branch, not to
penalize. ``even`` is not "good" — it may signal a shallow skim with no focal point.
The verdict describes distribution; the operator judges value.

**Honesty rules (load-bearing):**

* ``unread`` never fabricates a distribution when there are zero touches (no events
  to distribute).
* ``focused`` (one touched section) is its own base case: Gini over a single value
  is degenerate (0/0) — never fabricated as ``even`` (0.0) or ``concentrated``.
* ``even`` is a REAL measured verdict (>= 2 touched sections, low Gini), NOT the
  default — ``unread`` and ``focused`` are the defer states; ``even`` means
  measured-and-spread. Never collapsed.
* ``gini`` / ``mean_touches_per_section`` / ``max_touches`` are ``None`` when
  ``unread`` (defer — never ``0.0``).
* hot-spot sections surfaced as ``hot_spot_sections`` (auditable — the operator sees
  exactly where attention concentrated).
* touch counts must be non-negative integers (raises on negative / NaN).
* ``hot_spot_threshold`` must be >= 1.0 (raises); concentration thresholds in
  ``[0, 1]`` with ``low < high`` (raises).
* Gini requires >= 2 touched sections (the pairwise difference sum needs two values;
  one section is the ``focused`` base case).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; sorted sections, reproducible output).
* import-free of off-main siblings (own ``SectionTouches`` shape; route layer adapts
  1:1 from aggregated per-section engagement events).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "SectionTouches",
    "EngagementDistributionReport",
    "measure_engagement_distribution",
]

_DEFAULT_HOT_SPOT_MULTIPLE = 2.0
_DEFAULT_HIGH_CONCENTRATION = 0.60
_DEFAULT_LOW_CONCENTRATION = 0.20


@dataclass(frozen=True)
class SectionTouches:
    """The engagement-event count for one document section.

    Attributes:
        section_id: stable section identifier (for provenance / audit).
        touch_count: number of engagement events (highlights + annotations +
            dwells) in this section; non-negative integer.
    """

    section_id: str
    touch_count: int


@dataclass(frozen=True)
class EngagementDistributionReport:
    """The reading engagement-distribution verdict. Advisory, pure.

    Attributes:
        touched_section_count: sections with >= 1 touch.
        total_touches: sum of all touch counts.
        mean_touches_per_section: average across touched sections; ``None`` when
            ``unread``.
        max_touches: the hot-spot's touch count; ``None`` when ``unread``.
        hot_spot_sections: sections at >= hot_spot_threshold * mean, sorted by
            touch count descending then id.
        gini: concentration coefficient in [0,1]; ``None`` when deferred.
        hot_spot_threshold: hot-spot multiple of the mean.
        high_concentration: Gini floor for ``concentrated``.
        low_concentration: Gini ceiling for ``even``.
        verdict: ``concentrated`` / ``moderate`` / ``even`` / ``focused`` /
            ``unread``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    touched_section_count: int
    total_touches: int
    mean_touches_per_section: float | None
    max_touches: int | None
    hot_spot_sections: tuple[str, ...]
    gini: float | None
    hot_spot_threshold: float
    high_concentration: float
    low_concentration: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _gini(values: Sequence[int]) -> float:
    """Gini coefficient over non-negative ints. Requires len >= 2."""
    n = len(values)
    mean = sum(values) / n
    if mean == 0:
        return 0.0
    abs_diff_sum = 0
    for i in range(n):
        for j in range(n):
            abs_diff_sum += abs(values[i] - values[j])
    return abs_diff_sum / (2 * n * n * mean)


def measure_engagement_distribution(
    section_touches: Sequence[SectionTouches],
    *,
    hot_spot_threshold: float = _DEFAULT_HOT_SPOT_MULTIPLE,
    high_concentration: float = _DEFAULT_HIGH_CONCENTRATION,
    low_concentration: float = _DEFAULT_LOW_CONCENTRATION,
) -> EngagementDistributionReport:
    r"""Measure how the reader's engagement is distributed across sections.

    ``section_touches`` are the per-section engagement-event counts. Returns an
    :class:`EngagementDistributionReport` with the Gini concentration, hot-spot
    detection, and verdict.

    Raises:
        ValueError: if thresholds are out of range or ``low >= high`` or any touch
            count is negative.
    """
    if hot_spot_threshold < 1.0:
        raise ValueError(
            f"hot_spot_threshold must be >= 1.0; got {hot_spot_threshold}"
        )
    for label, val in (
        ("high_concentration", high_concentration),
        ("low_concentration", low_concentration),
    ):
        if not 0.0 <= val <= 1.0:
            raise ValueError(f"{label} must be in [0.0, 1.0]; got {val}")
    if low_concentration >= high_concentration:
        raise ValueError(
            f"low_concentration ({low_concentration}) must be < "
            f"high_concentration ({high_concentration})"
        )

    # Filter to touched sections (>= 1 touch); validate non-negative.
    touched: list[tuple[str, int]] = []
    for st in section_touches:
        if st.touch_count < 0:
            raise ValueError(
                f"section {st.section_id!r} has negative touch count "
                f"{st.touch_count}"
            )
        if st.touch_count > 0:
            touched.append((st.section_id, st.touch_count))

    touched_section_count = len(touched)

    if touched_section_count == 0:
        return EngagementDistributionReport(
            touched_section_count=0,
            total_touches=0,
            mean_touches_per_section=None,
            max_touches=None,
            hot_spot_sections=(),
            gini=None,
            hot_spot_threshold=hot_spot_threshold,
            high_concentration=high_concentration,
            low_concentration=low_concentration,
            verdict="unread",
            notes=("no engagement events — no distribution to measure",),
        )

    counts = [c for _, c in touched]
    total_touches = sum(counts)
    max_touches = max(counts)
    mean_touches = total_touches / touched_section_count

    if touched_section_count == 1:
        return EngagementDistributionReport(
            touched_section_count=1,
            total_touches=total_touches,
            mean_touches_per_section=mean_touches,
            max_touches=max_touches,
            hot_spot_sections=tuple(sid for sid, _ in touched),
            gini=None,
            hot_spot_threshold=hot_spot_threshold,
            high_concentration=high_concentration,
            low_concentration=low_concentration,
            verdict="focused",
            notes=("single touched section — deep-dive, Gini degenerate",),
        )

    gini = _gini(counts)

    hot_spots = sorted(
        (sid for sid, c in touched if c >= hot_spot_threshold * mean_touches),
        key=lambda s: (
            -dict(touched)[s],
            s,
        ),
    )

    note_parts = [
        f"{touched_section_count} touched section(s); Gini {gini:.4f}",
    ]
    if hot_spots:
        note_parts.append(
            f"{len(hot_spots)} hot-spot section(s) at >= {hot_spot_threshold:.1f}x mean"
        )

    if gini >= high_concentration:
        verdict = "concentrated"
    elif gini <= low_concentration:
        verdict = "even"
    else:
        verdict = "moderate"

    return EngagementDistributionReport(
        touched_section_count=touched_section_count,
        total_touches=total_touches,
        mean_touches_per_section=mean_touches,
        max_touches=max_touches,
        hot_spot_sections=tuple(hot_spots),
        gini=gini,
        hot_spot_threshold=hot_spot_threshold,
        high_concentration=high_concentration,
        low_concentration=low_concentration,
        verdict=verdict,
        notes=tuple(note_parts),
    )
