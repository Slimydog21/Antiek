"""Source-diversity axis — is the evidence base broad, or a monoculture?

Operator vision: *"call arxiv, substack, and other knowledge-dense publications
to be referenced when I do my deep researches"* (ask #7) and *"the highest quality
deep research product in the world."* A deep-research artifact that grounds every
insight in a SINGLE source passes ``citation_density`` yet is a monoculture --
its evidence base is narrow and a single source's framing dominates the whole
synthesis. This module measures the BREADTH and EVENNESS of the source base
AMONG grounded insights, which ``citation_density`` cannot see.

**Orthogonality (load-bearing).** ``citation_density`` answers "are insights
grounded at all?" (binary per insight: has a ``source_document_id`` or not).
This axis answers "among the grounded insights, is the evidence broad or a
monoculture?" The two compose: a high-density / low-diversity artifact is
grounded but monocultural; a low-density artifact has nothing to measure, so
this axis reports ``measured=False`` (it defers to citation_density, never
duplicates it).

**The score (hard to vary).** The primary score is the **Gini-Simpson index**,
``1 - sum(p_i**2)`` over source shares ``p_i`` -- the probability that two
insights drawn at random (with replacement) cite DIFFERENT sources. It is a
standard, interpretation-clear diversity measure in [0, 1] that rewards both
breadth (more distinct sources) and evenness (balanced citation). It is NOT a
vibes score: it is the literal chance of drawing two differently-sourced
insights, and it is maximized exactly when the evidence base is broad and
balanced. (Honest ceiling: even with every insight citing a unique source the
index is ``(n-1)/n``, never quite 1.0 -- documented in ``notes`` so a consumer
does not expect a spurious 1.0.)

**Evenness is reported separately (Pielou's J = H / log2(distinct)).** Breadth
and evenness are both diversity but they are different signals: 2 sources cited
50/50 and 10 sources cited 50/50.../50 have the same evenness (1.0) but very
different breadth. ``evenness`` lets the operator see the balance independently
of the count; ``distinct_source_count`` carries the breadth; the score carries
the combined picture.

**Honesty rules (load-bearing):**
* ``measured=False`` when zero insights carry a source -- diversity of nothing is
  unknown, never fabricated. Only insights WITH a ``source_document_id`` count.
* Deterministic and pure: same artifact in -> same report out. No LLM, no
  network, no clock, no mutation. ``authority`` is always ``"advisory"``.
* ``monoculture`` is a crisp flag, not a judgment: the single most-cited source
  accounts for >= ``monoculture_dominance`` (default 0.80) of cited insights.
* ``None`` source ids are excluded (they are ungrounded, not a "source"). An
  empty / whitespace-only source id is treated the same -- it is not a source.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_MONOCULTURE_DOMINANCE: float = 0.80


class SourceDiversityError(ValueError):
    """A source-diversity input violates a load-bearing invariant."""


@dataclass(frozen=True)
class SourceDiversityReport:
    """The source-diversity verdict for one artifact. Advisory, pure."""

    investigation_id: str
    score: float  # Gini-Simpson index in [0, 1]; 0.0 when not measurable
    measured: bool  # False when zero insights carry a source
    distinct_source_count: int  # number of distinct non-null sources cited
    total_cited_insights: int  # insights carrying a non-null source id
    total_insights: int  # all insights in the artifact
    top_source_share: float  # share of the single most-cited source; 0.0 if none
    evenness: float | None  # Pielou's J in [0,1]; None when only one source
    monoculture: bool  # top source >= monoculture_dominance of cited insights
    notes: tuple[str, ...]
    authority: str = "advisory"


def _clamp01(value: float) -> float:
    if value != value:  # NaN
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _real_source_id(raw: str | None) -> str | None:
    """A source id counts only if it is a non-empty, non-whitespace string.

    ``None`` and blank ids are ungrounded, not sources -- they are excluded from
    the diversity distribution (they belong to citation_density, not here).
    """
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def score_source_diversity(
    body: ResearchArtifactBody,
    *,
    monoculture_dominance: float = _DEFAULT_MONOCULTURE_DOMINANCE,
) -> SourceDiversityReport:
    """Score the source diversity of a completed artifact. Pure, advisory.

    Returns a :class:`SourceDiversityReport`. ``measured=False`` when no insight
    carries a source (diversity of nothing is unknown). The ``score`` is the
    Gini-Simpson index -- the probability two randomly-drawn cited insights cite
    different sources.
    """
    if not monoculture_dominance or not 0.0 < monoculture_dominance <= 1.0:
        raise SourceDiversityError(
            "monoculture_dominance must be in (0.0, 1.0], got "
            f"{monoculture_dominance!r}"
        )

    total_insights = len(body.insights)
    cited_ids = [
        sid
        for insight in body.insights
        if (sid := _real_source_id(insight.source_document_id)) is not None
    ]
    total_cited = len(cited_ids)

    notes: list[str] = [
        "score is the Gini-Simpson index: the probability two randomly-drawn "
        "cited insights cite different sources; rewards breadth + evenness",
        "even with every insight citing a unique source the index is (n-1)/n, "
        "never a spurious 1.0",
    ]

    if total_cited == 0:
        return SourceDiversityReport(
            investigation_id=body.investigation_id,
            score=0.0,
            measured=False,
            distinct_source_count=0,
            total_cited_insights=0,
            total_insights=total_insights,
            top_source_share=0.0,
            evenness=None,
            monoculture=False,
            notes=tuple(
                notes
                + [
                    "no insight carries a source_document_id; diversity is "
                    "unmeasurable (defer to citation_density, not duplicated here)"
                ]
            ),
        )

    counts = Counter(cited_ids)
    distinct = len(counts)
    shares = [count / total_cited for count in counts.values()]
    top_share = max(shares)

    # Gini-Simpson index: 1 - sum(p_i^2).
    gini_simpson = _clamp01(1.0 - sum(p * p for p in shares))

    # Pielou's evenness J = H / H_max, H = -sum(p log2 p), H_max = log2(distinct).
    # Undefined when distinct == 1 (a single source has no distribution to balance).
    if distinct > 1:
        entropy = -sum(p * math.log2(p) for p in shares if p > 0.0)
        evenness = _clamp01(entropy / math.log2(distinct))
    else:
        evenness = None

    monoculture = top_share >= monoculture_dominance

    if monoculture:
        notes.append(
            f"MONOCULTURE: a single source accounts for {top_share:.0%} of cited "
            f"insights (>= {monoculture_dominance:.0%} threshold); broaden the "
            "evidence base (ask #7: call arxiv, substack, and other dense sources)"
        )

    return SourceDiversityReport(
        investigation_id=body.investigation_id,
        score=gini_simpson,
        measured=True,
        distinct_source_count=distinct,
        total_cited_insights=total_cited,
        total_insights=total_insights,
        top_source_share=top_share,
        evenness=evenness,
        monoculture=monoculture,
        notes=tuple(notes),
    )


__all__ = [
    "SourceDiversityError",
    "SourceDiversityReport",
    "score_source_diversity",
]
