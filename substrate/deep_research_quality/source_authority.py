"""Source authority — does the research draw from high-quality sources?

Operator vision: *"the highest quality deep research product in the world"* and
*"simply call arxiv, substack, and other knowledge-dense publications."* A
deep-research artifact is only as trustworthy as its evidence base. A finding
backed by a peer-reviewed arxiv preprint or an established journal carries more
epistemic weight than one citing an unverified blog or a content farm. The
operator, a professional technology researcher, needs to know — at a glance —
whether a piece of research rests on authoritative ground or shaky scaffolding.

This completes the source-quality triad. ``source_diversity`` (#1921) measures
BREADTH (does the research draw from many distinct sources?).
``source_recency`` (#1951) measures FRESHNESS (is the evidence base current?).
NEITHER measures AUTHORITY — the quality/reputation of the sources themselves.
THIS is that axis: of the cited sources, how many are authoritative venues?

**The measurement (hard to vary).** The cited evidence base is the union of the
artifact's ``source_event_ids`` and its insights' ``source_document_id`` values
(deduplicated). The route/acquisition layer knows each source's reputation
(arxiv is authoritative; an anonymous paste is not) and supplies it as a
``source_authority`` map: ``source_id -> reputation_score`` in ``[0.0, 1.0]``
(``1.0`` = top venue, ``0.0`` = unverified). For each cited source:

* Look up its score in the map. Present -> ``scored``; absent -> ``unscored``
  (unknown authority — tracked, never fabricated as high or low).
* Tier it: ``authoritative`` (score >= ``authoritative_threshold``, default 0.70),
  ``low_quality`` (score < ``low_quality_threshold``, default 0.30), or ``mid``.

The module reports:

* ``cited_count`` / ``scored_count`` / ``unscored_count``.
* ``authoritative_count`` / ``mid_count`` / ``low_quality_count`` (over scored).
* ``mean_authority`` over scored sources (``None`` when zero scored).
* ``authority_rate = authoritative_count / scored_count`` (``None`` when zero
  scored) — the fraction of the (known) evidence base that is top-tier.
* per-source ``SourceAuthorityAssessment`` (``source_id``, ``score``, ``tier``).

**No weighting by citation count (load-bearing).** Each UNIQUE source counts
once — this measures the authority of the EVIDENCE BASE, not how often it is
cited (citation frequency is a different signal, easily inflated by one chatty
source). This mirrors ``source_diversity`` (unique sources) and keeps the axis
hard to vary.

**Honesty rules (load-bearing):**

* No cited sources at all (empty ``source_event_ids`` and no insight provenance)
  -> all counts zero, ``mean_authority`` / ``authority_rate`` ``None``, verdict
  ``unknown`` (defer — never fabricated).
* An empty authority map -> every source ``unscored`` -> ``mean_authority`` /
  ``authority_rate`` ``None``, verdict ``unknown`` (defer). The
  ``unscored_count`` is carried through verbatim (the operator sees how much of
  the base is unmeasured — never hidden).
* ``unscored`` sources are EXCLUDED from ``mean_authority`` and ``authority_rate``
  (a source whose reputation is unknown is not counted as authoritative OR
  low-quality — that would fabricate a verdict from absence).
* ``authority_rate`` is in ``[0.0, 1.0]``; ``mean_authority`` in ``[0.0, 1.0]``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The
``source_authority`` map is a plain ``dict[str, float]`` input (the route layer
adapts the acquisition layer's venue reputation 1:1).
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_AUTHORITATIVE_THRESHOLD: float = 0.70
_DEFAULT_LOW_QUALITY_THRESHOLD: float = 0.30
_AUTHORITATIVE_RATE_RICH: float = 0.60
_AUTHORITATIVE_RATE_MID: float = 0.30


class SourceAuthorityError(ValueError):
    """A source-authority input violates a load-bearing invariant."""


@dataclass(frozen=True)
class SourceAuthorityAssessment:
    """One cited source's authority tier."""

    source_id: str
    score: float | None  # None if unscored (not in the authority map)
    tier: str  # authoritative | mid | low_quality | unscored


@dataclass(frozen=True)
class SourceAuthorityReport:
    """The evidence base's authority. Advisory, pure."""

    artifact_id: str
    cited_count: int
    scored_count: int
    unscored_count: int
    authoritative_count: int
    mid_count: int
    low_quality_count: int
    mean_authority: float | None  # over scored; None if zero scored
    authority_rate: float | None  # authoritative/scored; None if zero scored
    assessments: tuple[SourceAuthorityAssessment, ...]
    authoritative_threshold: float
    low_quality_threshold: float
    verdict: str  # authoritative | mixed | unverified | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _cited_sources(artifact: ResearchArtifactBody) -> tuple[str, ...]:
    """Deduplicated, ordered set of cited source ids (event ids + insight provenance)."""
    seen: dict[str, None] = {}
    for sid in artifact.source_event_ids:
        if sid and sid not in seen:
            seen[sid] = None
    for ins in artifact.insights:
        doc_id = ins.source_document_id
        if doc_id and doc_id not in seen:
            seen[doc_id] = None
    return tuple(seen)


def _tier(score: float, auth_thr: float, low_thr: float) -> str:
    if score >= auth_thr:
        return "authoritative"
    if score < low_thr:
        return "low_quality"
    return "mid"


def measure_source_authority(
    artifact: ResearchArtifactBody,
    source_authority: dict[str, float],
    *,
    authoritative_threshold: float = _DEFAULT_AUTHORITATIVE_THRESHOLD,
    low_quality_threshold: float = _DEFAULT_LOW_QUALITY_THRESHOLD,
) -> SourceAuthorityReport:
    """Measure whether the artifact's cited sources are authoritative.

    ``artifact`` is a completed deep-research artifact. ``source_authority`` maps
    each known source id to a reputation score in ``[0.0, 1.0]`` (supplied by the
    route/acquisition layer). Returns a :class:`SourceAuthorityReport` with the
    evidence base's authority profile.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= authoritative_threshold <= 1.0:
        raise SourceAuthorityError(
            f"authoritative_threshold must be in [0,1], got {authoritative_threshold!r}"
        )
    if not 0.0 <= low_quality_threshold <= 1.0:
        raise SourceAuthorityError(
            f"low_quality_threshold must be in [0,1], got {low_quality_threshold!r}"
        )
    if low_quality_threshold > authoritative_threshold:
        raise SourceAuthorityError(
            f"low_quality_threshold ({low_quality_threshold!r}) must not exceed "
            f"authoritative_threshold ({authoritative_threshold!r})"
        )

    cited = _cited_sources(artifact)

    assessments: list[SourceAuthorityAssessment] = []
    scored_scores: list[float] = []
    authoritative = 0
    mid = 0
    low_quality = 0
    unscored = 0

    for sid in cited:
        if sid in source_authority:
            score = source_authority[sid]
            tier = _tier(score, authoritative_threshold, low_quality_threshold)
            if tier == "authoritative":
                authoritative += 1
            elif tier == "low_quality":
                low_quality += 1
            else:
                mid += 1
            scored_scores.append(score)
            assessments.append(SourceAuthorityAssessment(source_id=sid, score=score, tier=tier))
        else:
            unscored += 1
            assessments.append(
                SourceAuthorityAssessment(source_id=sid, score=None, tier="unscored")
            )

    scored_count = len(scored_scores)
    mean_authority = sum(scored_scores) / scored_count if scored_count else None
    authority_rate = authoritative / scored_count if scored_count else None

    if authority_rate is None:
        verdict = "unknown"
    elif authority_rate >= _AUTHORITATIVE_RATE_RICH:
        verdict = "authoritative"
    elif authority_rate >= _AUTHORITATIVE_RATE_MID:
        verdict = "mixed"
    else:
        verdict = "unverified"

    notes: list[str] = [
        "source authority measures whether the cited evidence base draws from "
        "authoritative venues (top journals/arxiv) or unverified sources (blogs) — "
        "the operator's 'highest quality deep research' rests on authoritative ground; "
        "this is the third source-quality axis (diversity #1921, recency #1951, authority)",
        "each unique cited source counts once (authority of the evidence base, not citation "
        "frequency — mirrors source_diversity); sources absent from the authority map are "
        "unscored (unknown reputation — tracked via unscored_count, never fabricated as high "
        "or low, and excluded from the mean and rate)",
        "mean_authority and authority_rate are None when zero sources are scored (empty base "
        "or empty authority map — defer, never fabricate); the verdict is unknown then",
    ]
    if authority_rate is None:
        notes.append(
            f"no scored sources: {unscored} unscored of {len(cited)} cited — authority "
            "is not measurable (defer — never fabricated)"
        )
    else:
        notes.append(
            f"authority rate {authority_rate:.0%}: {authoritative} authoritative, {mid} mid, "
            f"{low_quality} low-quality of {scored_count} scored ({unscored} unscored, "
            f"{len(cited)} cited) -> verdict {verdict}"
        )

    return SourceAuthorityReport(
        artifact_id=artifact.investigation_id,
        cited_count=len(cited),
        scored_count=scored_count,
        unscored_count=unscored,
        authoritative_count=authoritative,
        mid_count=mid,
        low_quality_count=low_quality,
        mean_authority=mean_authority,
        authority_rate=authority_rate,
        assessments=tuple(assessments),
        authoritative_threshold=authoritative_threshold,
        low_quality_threshold=low_quality_threshold,
        verdict=verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "SourceAuthorityAssessment",
    "SourceAuthorityError",
    "SourceAuthorityReport",
    "measure_source_authority",
]
