"""Source recency — does the evidence base reflect current knowledge?

Operator vision (ask #7): *"provide the highest quality deep research product in
the world."* A research output that cites a 2015 source for a claim a 2024 paper
overturned is a quality defect no current axis catches. citation_grounding
(#1848) checks whether insights trace to sources at all; provenance_coverage
(#1940) checks whether sources carry provenance. Neither asks: **is the evidence
CURRENT?** A perfectly-grounded, well-provenanced finding resting on a stale
source is silently misleading. In fast-moving fields (ML, biotech), a 2-year-old
source for a state-of-the-art claim is a red flag. This axis makes source recency
MEASURABLE.

**The score (hard to vary).** For each cited source with a known publication
date, compute its AGE in years relative to a reference date (default: today).
``median_source_age`` is the median across dated sources — robust to outliers
(one ancient foundational source doesn't skew the median the way it would a mean).
``stale_source_fraction`` is the share of dated sources older than a freshness
threshold (default 3 years) — the direct "how much of the evidence is old" metric.

**Date availability is honest (load-bearing).** Not every source has a parseable
publication date (a tweet, a draft, an undated web page). Sources WITHOUT a known
date are EXCLUDED from the age computation, and the report surfaces
``undated_source_fraction`` so the operator knows how much of the evidence base
was unmeasurable. An artifact where 80% of sources are undated has
``median_source_age`` computed from the 20% that are dated — and the high
``undated_source_fraction`` tells the operator that metric is thin. Never
fabricated: undated sources defer, they don't count as fresh or stale.

**Verdict (descriptive, not normative).** The report carries the raw metrics and a
graduated verdict:
- ``current`` — median age below the threshold AND stale fraction low.
- ``aging`` — median age near the threshold OR moderate stale fraction.
- ``stale`` — median age above the threshold OR high stale fraction.
- ``unknown`` — zero dated sources (nothing to measure).

The verdict is DESCRIPTIVE. "Current" does not mean "good" (a foundational 1998
paper may be the RIGHT source for a mathematical proof); "stale" does not mean
"bad" (history research legitimately cites old sources). The operator judges
whether the recency profile fits the investigation's domain. This axis surfaces
the FACT of recency; it does not prescribe the right age.

**Import-free of off-main siblings (load-bearing).** The research_artifact schema
on origin/main carries ``source_document_id`` on insights and ``source_event_ids``
on the artifact body, but NOT publication dates. This module takes source-date
metadata as a frozen :class:`SourceDateMap` (source_id → publication_date). The
route layer fills it from the source registry when that infrastructure merges.
Mirrors the #1937/#1949/#1950 compatible-shape pattern.

**Honesty rules (load-bearing):**
* ``median_source_age`` / ``stale_source_fraction`` are ``None`` when zero dated
  sources (never fabricated 0). The verdict is ``unknown``.
* ``undated_source_fraction`` is always carried (even when 0) so the operator
  sees the measurement coverage.
* Ages are non-negative (a future-dated source clamps to 0 — a negative age is a
  data error, not a "very fresh" bonus).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock mutation (the reference date is an INPUT, defaulting to date.today() only
  at the call boundary for convenience, never read from a global).
* ``authority`` is always ``"advisory"``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

_DEFAULT_FRESHNESS_THRESHOLD_YEARS: float = 3.0
_DEFAULT_STALE_FRACTION_HIGH: float = 0.40
_DEFAULT_STALE_FRACTION_LOW: float = 0.15

_DAYS_PER_YEAR = 365.25


class SourceRecencyError(ValueError):
    """A source-recency input violates a load-bearing invariant."""


@dataclass(frozen=True)
class SourceDateMap:
    """Publication dates for cited sources. The route layer fills this.

    ``dates`` maps a source id (matching ``ArtifactInsight.source_document_id`` or
    ``ResearchArtifactBody.source_event_ids``) to its publication date. Sources
    absent from the map are treated as UNDATED (deferred, never fabricated).
    """

    dates: Mapping[str, date]


@dataclass(frozen=True)
class SourceRecencyReport:
    """The artifact's evidence-base recency surface. Advisory, pure."""

    artifact_id: str
    dated_source_count: int
    undated_source_count: int
    total_source_count: int
    undated_source_fraction: float  # [0,1]; how much of the base was unmeasurable
    median_source_age_years: float | None  # None if zero dated sources
    max_source_age_years: float | None
    stale_source_fraction: float | None  # dated sources older than threshold; None if 0 dated
    verdict: str  # current | aging | stale | unknown
    freshness_threshold_years: float
    notes: tuple[str, ...]
    authority: str = "advisory"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def measure_source_recency(
    artifact_id: str,
    cited_source_ids: list[str],
    source_dates: SourceDateMap,
    *,
    reference_date: date | None = None,
    freshness_threshold_years: float = _DEFAULT_FRESHNESS_THRESHOLD_YEARS,
    stale_fraction_high: float = _DEFAULT_STALE_FRACTION_HIGH,
    stale_fraction_low: float = _DEFAULT_STALE_FRACTION_LOW,
) -> SourceRecencyReport:
    """Measure the recency of the artifact's cited evidence base.

    ``cited_source_ids`` are the distinct source ids the artifact draws on
    (extracted from insight.source_document_id + source_event_ids by the caller).
    ``source_dates`` maps those ids to publication dates. Returns a
    :class:`SourceRecencyReport`.

    Pure: no DB, no LLM, no clock mutation. ``reference_date`` defaults to
    ``date.today()`` for convenience but is an explicit input (test-deterministic).
    """
    if freshness_threshold_years <= 0:
        raise SourceRecencyError(
            f"freshness_threshold_years must be > 0, got {freshness_threshold_years!r}"
        )
    if not 0.0 <= stale_fraction_low <= 1.0:
        raise SourceRecencyError(
            f"stale_fraction_low must be in [0,1], got {stale_fraction_low!r}"
        )
    if not stale_fraction_low <= stale_fraction_high <= 1.0:
        raise SourceRecencyError(
            f"stale_fraction_high must be in [stale_fraction_low, 1], got "
            f"{stale_fraction_high!r} (low={stale_fraction_low!r})"
        )

    ref = reference_date or date.today()

    # De-duplicate cited source ids (an artifact may cite a source multiple times).
    distinct_ids = list(dict.fromkeys(cited_source_ids))
    total = len(distinct_ids)

    ages: list[float] = []
    undated = 0
    for sid in distinct_ids:
        pub = source_dates.dates.get(sid)
        if pub is None:
            undated += 1
            continue
        delta_days = (ref - pub).days
        # Clamp negative age (future-dated source) to 0 — a data error, not a bonus.
        age_years = max(0.0, delta_days / _DAYS_PER_YEAR)
        ages.append(age_years)

    dated_count = len(ages)
    undated_fraction = undated / total if total else 0.0

    median_age = _median(ages)
    max_age = max(ages) if ages else None

    if dated_count == 0:
        stale_fraction = None
    else:
        stale = sum(1 for a in ages if a >= freshness_threshold_years)
        stale_fraction = stale / dated_count

    notes: list[str] = [
        "source recency is a FACTUAL measurement, not a quality judgment — 'current' "
        "does not mean 'good' (a foundational old paper may be the right source); "
        "'stale' does not mean 'bad' (history research legitimately cites old sources); "
        "the operator judges whether the recency profile fits the domain",
        "undated sources are EXCLUDED from age computation (defer, never fabricated "
        "as fresh or stale); the undated_source_fraction shows how much of the base "
        "was unmeasurable",
    ]

    if total == 0:
        verdict = "unknown"
        notes.append(
            "no cited sources; recency is not measurable (defer)"
        )
    elif dated_count == 0:
        verdict = "unknown"
        notes.append(
            f"{undated} cited source(s) but none have known publication dates; "
            f"recency is not measurable (defer — never fabricated)"
        )
    elif median_age is not None and stale_fraction is not None and (
        median_age >= freshness_threshold_years or stale_fraction >= stale_fraction_high
    ):
        verdict = "stale"
        notes.append(
            f"median source age {median_age:.1f} years, stale fraction "
            f"{stale_fraction:.0%} (threshold {freshness_threshold_years:.0f} years); "
            f"the evidence base is aging — verify current sources exist for "
            f"fast-moving claims"
        )
    elif median_age is not None and stale_fraction is not None and (
        median_age >= freshness_threshold_years * 0.5
        or stale_fraction >= stale_fraction_low
    ):
        verdict = "aging"
        notes.append(
            f"median source age {median_age:.1f} years, stale fraction "
            f"{stale_fraction:.0%}; the evidence base is moderately current"
        )
    else:
        verdict = "current"
        assert median_age is not None and stale_fraction is not None
        notes.append(
            f"median source age {median_age:.1f} years, stale fraction "
            f"{stale_fraction:.0%}; the evidence base is current"
        )

    return SourceRecencyReport(
        artifact_id=artifact_id,
        dated_source_count=dated_count,
        undated_source_count=undated,
        total_source_count=total,
        undated_source_fraction=undated_fraction,
        median_source_age_years=median_age,
        max_source_age_years=max_age,
        stale_source_fraction=stale_fraction,
        verdict=verdict,
        freshness_threshold_years=freshness_threshold_years,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "SourceDateMap",
    "SourceRecencyError",
    "SourceRecencyReport",
    "measure_source_recency",
]
