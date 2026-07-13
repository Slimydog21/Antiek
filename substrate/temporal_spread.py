r"""Temporal source spread — does the evidence base triangulate across time?

Operator vision (ask #7): *"provide the highest quality deep research product in
the world."* The best professional research TRIANGULATES ACROSS TIME — it grounds
claims in foundational earlier work AND confirms them with current sources. An
evidence base that clusters at a single moment (every source from last quarter)
is a TEMPORAL MONOCULTURE: it captures one snapshot, blind to how the field
evolved, and fragile to a single batch of work being retracted or overturned.
Recency alone cannot see this failure: a perfectly ``current`` evidence base (ask
#1951) can be a monoculture (all 2024 — fresh but no historical depth), while a
``stale`` base can be genuinely broad (2014-2024 span — old but triangulated).
The breadth of the TIME RANGE the evidence spans is a distinct quality axis, and
nothing measures it.

**Genuinely distinct from every temporal/evidence axis (load-bearing):**

* ``source_recency`` (#1951): HOW OLD is the evidence (median/max AGE, stale
  fraction). This measures the RANGE of dates (how BROAD across time). A base of
  all-2024 sources is ``current`` (#1951) yet ``single_moment`` (this) — fresh but
  monocultural. A base spanning 2014-2024 is ``broad_spectrum`` (this) regardless
  of its median age. Recency and spread are independent: the operator needs both
  (fresh AND broad is the gold standard).
* ``source_diversity`` (#1921): breadth+evenness of source IDENTITIES (distinct
  source ids). This measures breadth across TIME (the date dimension). A base of
  10 distinct sources all from 2024 is source-diverse (#1921 high) yet temporally
  monocultural (this ``single_moment``).
* ``source_type_coverage`` (#1979): diversity of publication TYPES (arxiv vs
  substack vs report). This measures diversity of publication DATES.

**The measurement (hard to vary).** Given the publication dates of the dated
cited sources (the route layer supplies these from the source registry, mirroring
#1951's ``SourceDateMap`` pattern):

* ``date_span_years`` = (latest_date - earliest_date) in years — the raw width of
  the probed time band.
* ``earliest_date`` / ``latest_date`` — the bounding publications (auditable).
* ``distinct_year_count`` — how many distinct calendar years the evidence spans.
* ``year_histogram`` — per-calendar-year source counts, sorted by year (auditable:
  the operator sees the full temporal distribution, no black-box spread).
* ``max_year_share`` — the largest single year's fraction of dated sources (the
  temporal CONCENTRATION — does one year dominate, or is the evidence spread?).
* ``dominant_years`` — years whose share >= ``concentration_threshold`` (default
  ``0.50`` — the monocultural cohorts; auditable).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero dated sources -> ``unknown`` (nothing to measure — defer, never fabricated).
* ``date_span_years == 0`` (all dated sources share one date) -> ``single_moment``
  (a measured zero span — one temporal cohort; honest base case distinct from
  ``unknown`` which has no sources at all).
* ``0 < date_span_years <= broad_span_years`` (default ``5.0``) -> ``narrow_window``
  (a recent burst — the evidence spans a short band, no historical depth; even a
  fresh monoculture fits here).
* ``date_span_years > broad_span_years`` AND ``max_year_share >= concentration_threshold``
  -> ``anchored_spectrum`` (a wide span but one year DOMINATES — the "token old
  source" pattern: one 2014 outlier inflates the span while 90% of evidence is
  2024. NOT real breadth — the span is a mirage created by a single outlier).
* ``date_span_years > broad_span_years`` AND ``max_year_share < concentration_threshold``
  -> ``broad_spectrum`` (wide span AND distributed across years — the evidence
  genuinely triangulates across time; the gold-standard temporal shape. A REAL
  measured verdict, NOT the default).

**The load-bearing craftsmanship (anchored vs broad).** Two evidence bases can
share an identical 10-year span yet differ wholly in temporal integrity:

* Base A: 1 source in 2014, 9 sources in 2024 -> span 10 years, but max_year_share
  0.90 -> ``anchored_spectrum`` (the 2014 source is a token outlier; the span is a
  mirage; the research is effectively monocultural).
* Base B: sources spread 2014, 2016, 2018, 2020, 2022, 2024 -> span 10 years,
  max_year_share ~0.17 -> ``broad_spectrum`` (genuine temporal triangulation).

Naive span alone would score both identically (10 years); the concentration check
separates the mirage from the real breadth. This is the hard-to-vary distinction
that makes the axis honest.

**DESCRIPTIVE NOT NORMATIVE:** ``single_moment`` does NOT mean "bad" — a
breaking-news investigation or a single-experiment replication is legitimately a
temporal monoculture (it SHOULD be recent-only). ``broad_spectrum`` does NOT mean
"good" — irrelevant old sources inflate span without adding value. The operator
judges whether the temporal profile fits the investigation's domain (a fast-moving
field needs recency; a foundational survey needs breadth). This axis surfaces the
FACT of temporal spread; it does not prescribe the right span.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when no dated sources are supplied.
* ``single_moment`` is its own honest base case (span 0 WITH sources present —
  distinct from ``unknown`` which has none). ``date_span_years`` is ``0.0`` here
  (an honest measured zero, never fabricated as ``unknown``).
* ``broad_spectrum`` is a REAL measured verdict (wide span AND distributed), never
  the default — ``unknown`` and ``single_moment`` are the defer/zero states.
* ``earliest_date`` / ``latest_date`` / ``distinct_year_count`` / ``year_histogram``
  / ``max_year_share`` are carried in every measurable state (auditable); they are
  ``None`` ONLY in ``unknown``.
* dates are clamped: a future-dated source is treated as the reference present
  (negative span is a data error, not a "very broad" bonus); the earliest/latest
  are honest min/max of the supplied dates.
* absolute thresholds in YEARS (not normalized to source count): temporal breadth
  is an absolute property — a 5-year span is 5 years whether the base has 6 or 600
  sources; normalizing would obscure it.
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain ``date`` inputs; route layer adapts 1:1
  from the source registry's publication-date map, mirroring #1951's pattern).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

__all__ = [
    "TemporalSpreadReport",
    "measure_temporal_spread",
]

_DEFAULT_BROAD_SPAN_YEARS = 5.0
_DEFAULT_CONCENTRATION_THRESHOLD = 0.50
_DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class YearCount:
    """A single calendar year and how many dated sources were published in it.

    The entries of ``year_histogram`` (auditable temporal distribution).
    """

    year: int
    count: int


@dataclass(frozen=True)
class TemporalSpreadReport:
    """The temporal-spread surface of the artifact's evidence base. Advisory, pure."""

    dated_source_count: int
    earliest_date: date | None
    latest_date: date | None
    date_span_years: float | None
    distinct_year_count: int | None
    year_histogram: tuple[YearCount, ...]
    max_year_share: float | None
    dominant_years: tuple[int, ...]
    broad_span_years: float
    concentration_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_temporal_spread(
    publication_dates: Sequence[date],
    *,
    broad_span_years: float = _DEFAULT_BROAD_SPAN_YEARS,
    concentration_threshold: float = _DEFAULT_CONCENTRATION_THRESHOLD,
) -> TemporalSpreadReport:
    r"""Measure the temporal spread of the artifact's dated evidence base.

    ``publication_dates`` are the publication dates of the dated cited sources (the
    route layer supplies these from the source registry; undated sources are simply
    omitted by the caller — they defer, mirroring #1951's ``undated`` posture).
    Returns a :class:`TemporalSpreadReport` with span, distribution, and verdict.

    Raises:
        ValueError: if ``broad_span_years <= 0`` or ``concentration_threshold``
            is outside ``(0.0, 1.0]``.
    """
    if broad_span_years <= 0:
        raise ValueError(
            f"broad_span_years must be > 0; got {broad_span_years}"
        )
    if not 0.0 < concentration_threshold <= 1.0:
        raise ValueError(
            f"concentration_threshold must be in (0.0, 1.0]; got "
            f"{concentration_threshold}"
        )

    dates = list(publication_dates)
    dated_count = len(dates)

    if dated_count == 0:
        return TemporalSpreadReport(
            dated_source_count=0,
            earliest_date=None,
            latest_date=None,
            date_span_years=None,
            distinct_year_count=None,
            year_histogram=(),
            max_year_share=None,
            dominant_years=(),
            broad_span_years=broad_span_years,
            concentration_threshold=concentration_threshold,
            verdict="unknown",
            notes=("no dated sources — temporal spread unmeasurable",),
        )

    earliest = min(dates)
    latest = max(dates)
    span_years = max(0.0, (latest - earliest).days / _DAYS_PER_YEAR)

    year_counter: Counter[int] = Counter(d.year for d in dates)
    histogram = tuple(
        YearCount(year=yr, count=year_counter[yr])
        for yr in sorted(year_counter)
    )
    distinct_year_count = len(year_counter)
    max_year_count = max(year_counter.values())
    max_year_share = max_year_count / dated_count
    dominant_years = tuple(
        sorted(
            yr
            for yr, cnt in year_counter.items()
            if cnt / dated_count >= concentration_threshold
        )
    )

    if span_years == 0.0:
        verdict = "single_moment"
    elif span_years <= broad_span_years:
        verdict = "narrow_window"
    elif max_year_share >= concentration_threshold:
        verdict = "anchored_spectrum"
    else:
        verdict = "broad_spectrum"

    note_parts: list[str] = [
        f"{dated_count} dated source(s); span {span_years:.2f} year(s) "
        f"({earliest.isoformat()} to {latest.isoformat()}), "
        f"{distinct_year_count} distinct year(s), max_year_share "
        f"{max_year_share:.2f}",
        "temporal spread measures the RANGE of publication dates (how broad "
        "across time the evidence spans) — ORTHOGONAL to source_recency #1951 "
        "(HOW OLD the evidence is) and source_diversity #1921 (source-identity "
        "breadth): an all-2024 base is current #1951 yet single_moment (this); "
        "a 2014-2024 base is broad_spectrum regardless of median age",
    ]
    if verdict == "single_moment":
        note_parts.append(
            "single_moment: all dated sources share one date — a measured zero "
            "span (distinct from unknown which has no sources); may be a "
            "legitimate recent-only investigation"
        )
    elif verdict == "anchored_spectrum":
        note_parts.append(
            "anchored_spectrum: wide span but one year DOMINATES — the 'token old "
            "source' pattern where a single outlier inflates the span without real "
            "temporal triangulation; dominant year(s): "
            + ", ".join(str(y) for y in dominant_years)
        )
    elif verdict == "broad_spectrum":
        note_parts.append(
            "broad_spectrum: wide span AND distributed across years — the evidence "
            "genuinely triangulates across time (the gold-standard temporal shape); "
            "DESCRIPTIVE not normative (irrelevant old sources can inflate span "
            "without adding value)"
        )
    else:  # narrow_window
        note_parts.append(
            "narrow_window: evidence spans a short band — no historical depth; "
            "may fit a fast-moving field where recency is correct"
        )
    note_parts.append(
        f"verdict {verdict}: broad_span_years {broad_span_years}, "
        f"concentration_threshold {concentration_threshold}; "
        "year_histogram carries the full temporal distribution (auditable)"
    )

    return TemporalSpreadReport(
        dated_source_count=dated_count,
        earliest_date=earliest,
        latest_date=latest,
        date_span_years=span_years,
        distinct_year_count=distinct_year_count,
        year_histogram=histogram,
        max_year_share=max_year_share,
        dominant_years=dominant_years,
        broad_span_years=broad_span_years,
        concentration_threshold=concentration_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
