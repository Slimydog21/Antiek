r"""Citation source-concentration — does one source dominate an artifact's citations?

Operator vision (asks #1, #7): a professional researcher triangulates — each finding
should rest on a DIVERSE foundation of sources, not echo a single document. When every
insight in an artifact cites the SAME source, the artifact is a single-source echo:
if that one source is wrong, stale, or retracted, the ENTIRE artifact collapses with
it. The operator needs to see, per artifact, whether its citations SPREAD across many
independent sources (a triangulated, robust substrate) or CONCENTRATE on one (a fragile
monoculture). This is the citation-distribution concentration check — the per-artifact
analogue of merge source-balance (#2015), but for a SINGLE artifact's citation set.

**Genuinely distinct from the quality surface (load-bearing):**

* ``provenance_coverage`` (#1940): does each insight HAVE a ``source_document_id`` at all
  (binary per-insight coverage). THIS measures the DISTRIBUTION of the cited sources — how
  concentrated they are. An artifact can have 100% provenance coverage (every insight cites
  something) yet be a total monoculture (every insight cites the SAME source). Coverage
  answers "is it sourced"; concentration answers "is it DIVERSIFIED."
* ``source_corroboration`` (#1966): do MULTIPLE sources AGREE on a finding (corroboration
  strength per finding). THIS measures citation SPREAD regardless of agreement — an artifact
  can cite 10 distinct sources that all DISAGREE (diverse but not corroborating) or cite 1
  source for everything (concentrated). Corroboration answers "do sources agree";
  concentration answers "how many distinct sources are there."
* ``source_type_coverage`` (#1979): diversity of source TYPES (arxiv, substack, book — the
  FORMAT mix). THIS measures diversity of source DOCUMENTS (the IDENTITY mix) — two arxiv
  papers are the same TYPE but DIFFERENT documents; this axis treats them as diverse while
  #1979 treats them as the same type. Different dimension of diversity.
* ``merge_source_balance`` (#2015): is one MERGE PARENT drowning out the others (concentration
  across PARENTS of a merge). THIS is the single-artifact analogue — concentration across
  the CITED SOURCES of one artifact. Different operation (merge vs cite) and different input
  (parent contributions vs source_document_id distribution).
* ``source_recency`` (#1951) / ``source_authority`` (#1956) / ``temporal_spread`` (#2002):
  all measure WHEN or HOW AUTHORITATIVE sources are — none measures HOW CONCENTRATED the
  citation distribution is across source identities.

**The measurement (hard to vary).** The **Herfindahl–Hirschman Index (HHI)** over the cited
source distribution — the standard, falsifiable concentration measure from economics/ecology:

    HHI = Σ (count_s / total)²

where the sum is over each distinct cited source ``s``, ``count_s`` is how many insights cite
``s``, and ``total`` is the number of insights that cite ANY source. ``HHI ∈ (0, 1]``:
``1.0`` = every cited insight names the SAME source (pure monoculture); ``1/k`` = ``k`` sources
cited perfectly evenly (maximally diverse for ``k`` sources). HHI is the probability that two
randomly drawn cited insights name the same source — a direct, interpretable concentration
read.

The module also reports the **effective source count** ``1/HHI`` (the participation ratio from
ecology): the number of equally-weighted sources the citation distribution is "equivalent to."
HHI ``0.5`` → effective ``2.0`` (as if 2 evenly-cited sources); HHI ``0.25`` → effective
``4.0``. This gives the operator an intuitive "how many real sources back this artifact" number.

**Key property (the binding distinctness):** HHI depends on the SHAPE of the citation
distribution, not on whether sources agree, what type they are, or how recent they are. Two
artifacts with identical provenance coverage can have very different concentration (one cites
10 sources evenly, the other cites only 1). This is the unique quantity that captures
citation-source DIVERSITY — it cannot be derived from coverage, corroboration, or type.

**Measured fields:**

* ``cited_insight_count`` — insights with a non-empty ``source_document_id`` (the measured set).
* ``uncited_insight_count`` — insights with NO source (excluded from HHI, carried honestly).
* ``distinct_source_count`` — how many distinct documents are cited.
* ``source_concentration_hhi`` — the HHI in ``(0, 1]`` (``None`` when nothing is cited).
* ``effective_source_count`` — ``1/HHI`` (the participation ratio; ``None`` when nothing cited).
* ``dominant_source_id`` / ``dominant_source_share`` — the most-cited source and its share
  (auditable — the operator sees exactly which document dominates).
* ``source_breakdown`` — every ``(source_id, citation_count, share)`` triple sorted by count
  desc then id asc (auditable: the full citation distribution, no black-box).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero insights cite any source -> ``unknown`` (defer — HHI ``None``, never fabricated).
* exactly one distinct source cited -> ``single_source`` (honest monoculture — HHI ``1.0``,
  the most fragile state; distinct from ``unknown`` which is deferred, and from
  ``concentrated`` which needs >= 2 sources with one dominating).
* ``HHI >= concentration_threshold`` (default ``0.50``) and ``>= 2`` sources -> ``concentrated``
  (one or few sources dominate — more concentrated than an even 50/50 split).
* ``HHI < concentration_threshold`` -> ``diverse`` (citations spread across many sources — a
  triangulated foundation).

**DESCRIPTIVE NOT NORMATIVE:** ``diverse`` does NOT mean "good" — citing 10 low-quality blogs
is diverse but not authoritative. ``concentrated`` does NOT mean "bad" — citing one canonical,
authoritative textbook for everything can be correct if that source IS the definitive
reference. The operator judges whether the concentration reflects genuine triangulation failure
or a legitimate single-source-of-truth. (``source_authority`` #1956 measures authority;
``source_recency`` #1951 measures freshness — those are the companion reads.)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates — HHI / effective_source_count / dominant_source are ``None``
  when no insight cites any source.
* ``single_source`` is an honest measured verdict (HHI ``1.0``), NOT collapsed with ``unknown``
  (deferred, ``None``) — the operator can act on a monoculture but cannot act on "nothing cited."
* Insights with NO ``source_document_id`` are ``uncited`` — excluded from HHI, carried through
  as a count (never fabricated as a source). The route layer can combine this with
  provenance_coverage (#1940) for the full picture.
* ``source_concentration_hhi`` is in ``(0, 1]``; ``effective_source_count`` is ``>= 1.0``.
* ``source_breakdown`` is the auditable citation distribution (every source, its count, its
  share — sorted deterministically).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock, no
  mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody`` and
``ArtifactInsight`` from ``substrate/research_artifact/schema.py`` (stable on origin/main).
The route layer adapts 1:1 from the artifact's insight list.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_CONCENTRATION_THRESHOLD: float = 0.50


@dataclass(frozen=True)
class SourceCitation:
    """One cited source's footprint in the artifact (auditable)."""

    source_id: str
    citation_count: int
    share: float  # citation_count / cited_insight_count, in (0.0, 1.0]


@dataclass(frozen=True)
class CitationSourceConcentrationReport:
    """The citation-source-concentration surface for one artifact. Advisory, pure."""

    artifact_id: str
    cited_insight_count: int
    uncited_insight_count: int
    distinct_source_count: int
    source_concentration_hhi: float | None  # None when no insight cites any source
    effective_source_count: float | None  # 1/HHI; None when nothing cited
    dominant_source_id: str | None
    dominant_source_share: float | None
    source_breakdown: tuple[SourceCitation, ...]
    concentration_threshold: float
    verdict: str  # unknown | single_source | concentrated | diverse
    notes: tuple[str, ...]
    authority: str = "advisory"


class CitationSourceConcentrationError(ValueError):
    """A citation-source-concentration input violates a load-bearing invariant."""


def measure_citation_source_concentration(
    artifact: ResearchArtifactBody,
    *,
    concentration_threshold: float = _DEFAULT_CONCENTRATION_THRESHOLD,
) -> CitationSourceConcentrationReport:
    """Measure how concentrated the artifact's citations are across source documents.

    ``artifact`` is the research artifact whose insights carry optional
    ``source_document_id`` values. Returns a
    :class:`CitationSourceConcentrationReport` with the HHI over the cited-source
    distribution and the concentration verdict.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 < concentration_threshold <= 1.0:
        raise CitationSourceConcentrationError(
            f"concentration_threshold must be in (0.0, 1.0], got {concentration_threshold!r}"
        )

    cited_sources: list[str] = []
    uncited = 0
    for insight in artifact.insights:
        sid = insight.source_document_id
        if sid and sid.strip():
            cited_sources.append(sid.strip())
        else:
            uncited += 1

    total_cited = len(cited_sources)

    if total_cited == 0:
        return CitationSourceConcentrationReport(
            artifact_id=artifact.investigation_id,
            cited_insight_count=0,
            uncited_insight_count=uncited,
            distinct_source_count=0,
            source_concentration_hhi=None,
            effective_source_count=None,
            dominant_source_id=None,
            dominant_source_share=None,
            source_breakdown=(),
            concentration_threshold=concentration_threshold,
            verdict="unknown",
            notes=(
                "no insight cites any source (source_document_id empty on all "
                "insights); citation concentration is not measurable (defer — "
                "never fabricated)",
            ),
        )

    counts = Counter(cited_sources)
    distinct = len(counts)

    breakdown_list = sorted(
        counts.items(), key=lambda kv: (-kv[1], kv[0])
    )
    source_breakdown = tuple(
        SourceCitation(
            source_id=sid,
            citation_count=cnt,
            share=cnt / total_cited,
        )
        for sid, cnt in breakdown_list
    )

    hhi = sum((cnt / total_cited) ** 2 for cnt in counts.values())
    effective = 1.0 / hhi
    dominant_id, dominant_count = breakdown_list[0]
    dominant_share = dominant_count / total_cited

    notes: list[str] = [
        "citation source-concentration measures whether the artifact's citations SPREAD "
        "across many independent sources (triangulated, robust) or CONCENTRATE on one "
        "(a monoculture echo — if that source is wrong, the whole artifact collapses); "
        "HHI = sum of squared source shares, 1.0 = pure monoculture, 1/k = k sources "
        "cited evenly; provenance_coverage #1940 checks IF insights are sourced, this "
        "checks HOW DIVERSIFIED the sourcing is",
        f"effective_source_count {effective:.2f} (1/HHI) — the citation distribution is "
        f"equivalent to {effective:.2f} equally-weighted sources; source_corroboration "
        f"#1966 checks source AGREEMENT (orthogonal to this spread measure)",
    ]

    if distinct == 1:
        verdict = "single_source"
        notes.append(
            f"single source '{dominant_id}' backs all {total_cited} cited insight(s) — "
            f"a monoculture (HHI 1.0); the artifact's entire evidentiary foundation "
            f"rests on one document"
        )
    elif hhi >= concentration_threshold:
        verdict = "concentrated"
        notes.append(
            f"citations concentrated (HHI {hhi:.3f} >= {concentration_threshold:.0%}) — "
            f"source '{dominant_id}' alone accounts for {dominant_share:.0%} of "
            f"{total_cited} cited insight(s) across {distinct} distinct sources"
        )
    else:
        verdict = "diverse"
        notes.append(
            f"citations diverse (HHI {hhi:.3f} < {concentration_threshold:.0%}) — "
            f"{total_cited} cited insight(s) spread across {distinct} distinct sources "
            f"(largest share {dominant_share:.0%} from '{dominant_id}')"
        )

    if uncited > 0:
        notes.append(
            f"{uncited} insight(s) have no source_document_id (excluded from HHI, "
            f"carried as uncited_count — combine with provenance_coverage #1940 for "
            f"the full sourcing picture)"
        )

    return CitationSourceConcentrationReport(
        artifact_id=artifact.investigation_id,
        cited_insight_count=total_cited,
        uncited_insight_count=uncited,
        distinct_source_count=distinct,
        source_concentration_hhi=hhi,
        effective_source_count=effective,
        dominant_source_id=dominant_id,
        dominant_source_share=dominant_share,
        source_breakdown=source_breakdown,
        concentration_threshold=concentration_threshold,
        verdict=verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "CitationSourceConcentrationError",
    "CitationSourceConcentrationReport",
    "SourceCitation",
    "measure_citation_source_concentration",
]
