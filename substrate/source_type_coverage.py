r"""Source-type coverage — does the research reference diverse publication TYPES?

Operator vision (ask #7): *"I want to be able to simply call arxiv, substack, and
other knowledge-dense publications to be referenced when I do my deep researches."*
The operator explicitly wants the research to draw from DIVERSE PUBLICATION TYPES
(preprints, newsletters, journals, blogs) — the multi-perspective evidence base
that distinguishes a deep research from a single-source summary.

**Genuinely distinct (different dimension):**

* ``source_diversity`` (#1921): how broad + even is the evidence base across
  source INSTANCES? (Gini-Simpson: P(two random cited insights differ in source) +
  Pielou evenness — a DISTRIBUTION measure across individual sources)
* ``source_authority`` (#1956): is the evidence base reputable? (per-source
  authority/reputation — a QUALITY measure)
* ``source_recency`` (#1951): is the evidence base current? (a TEMPORAL measure)
* ``source_corroboration`` (#1966): do independent sources converge? (a
  TRIANGULATION measure)
* THIS (``source_type_coverage``): are diverse PUBLICATION TYPES represented?
  (a TAXONOMIC measure — across the types {arxiv, substack, journal, blog, ...},
  how many are present?)

``source_diversity`` and this are genuinely different axes that can disagree:
- A research citing 5 distinct arxiv papers has **high source_diversity** (5
  individual sources, decent evenness) but **low type-coverage** (1 type —
  monoculture of TYPE, even if diverse in instance).
- A research citing 1 arxiv + 1 substack + 1 journal has **lower source_diversity**
  (3 sources) but **high type-coverage** (3 types — the multi-perspective base the
  operator asked for).

``source_diversity`` cannot see a TYPE monoculture (5 arxiv papers all register as
distinct sources). ``source_type_coverage`` cannot see instance monoculture (1
paper cited 5 times registers as 1 source AND 1 type). They measure different
monoculture failure modes; both are needed.

**The measurement (hard to vary):**

Each cited source carries a ``source_type`` label (the route layer derives it from
the source's origin: arxiv.org -> ``arxiv``, substack.com -> ``substack``, etc.).
The caller-provided ``known_types`` is the catalog of publication types the
platform recognizes (e.g. {arxiv, substack, journal, blog, report}).

* ``present_types`` = the SET of types that appear in at least one cited source
* ``coverage_ratio = |present_types| / |known_types|`` in ``[0,1]`` — the share of
  the recognized type catalog the research drew from
* ``missing_types = known_types \ present_types`` — the types NOT referenced
  (carried for the operator — "you could draw from these too")

**Verdict:**

* ``unknown`` — no cited sources (defer; cannot assess type coverage of nothing —
  never fabricated as covered or monoculture)
* ``type_monoculture`` — ``|present_types| == 1`` (every cited source is the same
  type — the monoculture failure mode source_diversity cannot see)
* ``broad_coverage`` — ``coverage_ratio >= broad_threshold`` (default ``0.60`` —
  drew from most recognized types; boundary inclusive)
* ``partial_coverage`` — multiple types but below the threshold (some diversity)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when there are no cited sources — defer rather than
  assert coverage.
* ``type_monoculture`` is a REAL verdict distinct from ``unknown``: N cited sources
  all of one type IS measured monoculture, not "no sources."
* a source with an empty/unrecognized ``source_type`` is ``untyped`` (carried as a
  count — it is not forced into a known type, and it does not count toward
  ``present_types``; honest — an unknown type is not fabricated as a known one).
* ``known_types`` must be non-empty (raises otherwise — no catalog means no
  denominator; defer via raise, never via a fabricated verdict).
* ``coverage_ratio`` is ``None`` when ``unknown`` (defer, never ``0.0``).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** No source/typing substrate is on frozen
``origin/main``; this defines its own ``TypedSource`` input shape (the route layer
adapts 1:1 from the citation records + the source-type classifier). Pure-Python:
stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_BROAD_THRESHOLD: float = 0.60


@dataclass(frozen=True)
class TypedSource:
    """One cited source with its publication type label. Pure input.

    ``source_type`` is caller-derived (the route layer classifies the source
    origin: arxiv.org -> "arxiv", substack.com -> "substack", etc.). An empty/
    whitespace type means the source is ``untyped`` (carried, not forced into a
    known type).
    """

    source_id: str
    source_type: str


@dataclass(frozen=True)
class SourceTypeCoverageReport:
    """The source-type coverage verdict. Advisory, pure."""

    cited_source_count: int  # total cited sources (incl untyped)
    untyped_count: int  # sources with empty/unrecognized type
    known_type_count: int  # size of the recognized type catalog
    present_type_count: int  # distinct types appearing in cited sources
    coverage_ratio: float | None  # present/known; None when unknown
    broad_threshold: float
    verdict: str  # unknown | type_monoculture | partial_coverage | broad_coverage
    notes: tuple[str, ...]
    authority: str = "advisory"


class SourceTypeCoverageError(ValueError):
    """A source-type-coverage input violates a load-bearing invariant."""


def measure_source_type_coverage(
    sources: Sequence[TypedSource],
    known_types: Sequence[str],
    *,
    broad_threshold: float = _DEFAULT_BROAD_THRESHOLD,
) -> SourceTypeCoverageReport:
    """Measure how many publication types the research drew from.

    ``sources`` are the cited sources with their type labels.
    ``known_types`` is the recognized publication-type catalog.
    ``broad_threshold`` is the coverage_ratio at/above which coverage is broad
    (default 0.60).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= broad_threshold <= 1.0:
        raise SourceTypeCoverageError(
            f"broad_threshold must be in [0,1], got {broad_threshold!r}"
        )

    # Normalize + validate the known-type catalog.
    known: set[str] = set()
    for t in known_types:
        if not t.strip():
            raise SourceTypeCoverageError(
                "known_types must not contain empty/whitespace entries"
            )
        known.add(t.strip())
    if not known:
        raise SourceTypeCoverageError(
            "known_types must be non-empty (no catalog = no denominator)"
        )

    # Validate source ids (non-empty; duplicates ambiguous).
    seen_ids: set[str] = set()
    for src in sources:
        if not src.source_id.strip():
            raise SourceTypeCoverageError(
                f"source_id must be non-empty, got {src.source_id!r}"
            )
        if src.source_id in seen_ids:
            raise SourceTypeCoverageError(
                f"duplicate source_id {src.source_id!r}"
            )
        seen_ids.add(src.source_id)

    cited_count = len(sources)
    untyped = sum(1 for s in sources if not s.source_type.strip())
    present: set[str] = set()
    for src in sources:
        stype = src.source_type.strip()
        if stype and stype in known:
            present.add(stype)

    # No cited sources -> unknown (defer; cannot assess type coverage of nothing).
    if cited_count == 0:
        return _report(
            0, 0, len(known), 0, None, broad_threshold, "unknown",
            [
                "source-type coverage measures how many PUBLICATION TYPES the "
                "research drew from (arxiv, substack, journal, ...); distinct from "
                "source_diversity #1921 (distribution across source INSTANCES via "
                "Gini-Simpson), source_authority #1956 (reputation), source_recency "
                "#1951 (currency), source_corroboration #1966 (triangulation)",
                "verdict unknown — no cited sources (defer; coverage_ratio is None, "
                "never fabricated)",
            ],
        )

    present_count = len(present)
    coverage_ratio = present_count / len(known)

    # One-type monoculture (even with many sources) — the failure mode
    # source_diversity cannot see (5 arxiv papers register as 5 distinct sources).
    if present_count <= 1:
        verdict = "type_monoculture"
    elif coverage_ratio >= broad_threshold:
        verdict = "broad_coverage"
    else:
        verdict = "partial_coverage"

    missing = sorted(known - present)

    notes: list[str] = [
        "source-type coverage measures how many PUBLICATION TYPES the research "
        "drew from; distinct from source_diversity #1921 (distribution across "
        "source INSTANCES via Gini-Simpson) — 5 arxiv papers have high "
        "source_diversity (5 distinct instances) but low type-coverage (1 type); "
        "a TYPE monoculture source_diversity cannot see",
        "coverage_ratio = present_type_count / known_type_count in [0,1] (the "
        "share of the recognized type catalog drawn from); untyped sources "
        "(empty/unrecognized type) carried as untyped_count, not forced into a "
        "known type",
        "verdict: type_monoculture (present_types <= 1 — all one type, even with "
        "many sources), broad_coverage (coverage_ratio >= broad_threshold, "
        "boundary inclusive), partial_coverage (multiple types but below "
        "threshold)",
        "unknown when no cited sources (defer — never fabricated as covered); "
        "type_monoculture is a REAL verdict (N sources all one type), NOT unknown",
    ]
    notes.append(
        f"verdict {verdict}: {present_count} present type(s) of {len(known)} "
        f"known, coverage {coverage_ratio:.0%}, {cited_count} cited source(s) "
        f"({untyped} untyped); broad_threshold {broad_threshold:.0%}"
    )
    if missing:
        notes.append(f"missing types (not referenced): {', '.join(missing)}")

    return _report(
        cited_count, untyped, len(known), present_count,
        coverage_ratio, broad_threshold, verdict, notes,
    )


def _report(
    cited_count: int,
    untyped_count: int,
    known_type_count: int,
    present_type_count: int,
    coverage_ratio: float | None,
    broad_threshold: float,
    verdict: str,
    notes: list[str],
) -> SourceTypeCoverageReport:
    return SourceTypeCoverageReport(
        cited_source_count=cited_count,
        untyped_count=untyped_count,
        known_type_count=known_type_count,
        present_type_count=present_type_count,
        coverage_ratio=coverage_ratio,
        broad_threshold=broad_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
