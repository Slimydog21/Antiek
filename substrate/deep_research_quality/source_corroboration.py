"""Source corroboration — do independent sources converge on the same claim?

Operator vision (ask #1): *"I want to live in my research workstation and send
subagents to chase questions as I interrogate, assess, and wrestle with the
information in front of me."* When the operator wrestles with a claim, the FIRST
question is: is this independently confirmed, or is it a single-source claim?
A claim backed by three independent sources (arxiv paper + substack analysis +
industry report) is far more trustworthy than one cited to a single source —
that is the bedrock triangulation principle of professional research. Nothing
measures it.

**Orthogonality (load-bearing — each measures a different source-axis):**

* ``source_diversity`` (#1921) measures BREADTH + EVENNESS of the source base
  (how many distinct sources, how evenly are insights spread across them — the
  SHAPE of the distribution). It never asks whether two sources say the SAME
  thing.
* ``source_authority`` (#1956) measures source REPUTATION (is the evidence base
  reputable?). It never asks whether sources AGREE.
* ``contradiction`` (#1943) measures whether two insights CONFLICT (asymmetric
  negation within one artifact). It never asks whether sources CONVERGE.
* THIS axis measures CONVERGENCE: do insights from DIFFERENT
  ``source_document_id`` values lexically support the same claim?

A source-diverse artifact can have zero corroboration (each source makes a unique
claim — broad but uncorroborated). A corroborated artifact can be low-diversity
(three sources all confirm one claim — narrow but strongly triangulated). The two
are orthogonal: diversity is the breadth of the evidence base; corroboration is
the independent confirmation of its claims.

**The measurement (hard to vary).** Among the artifact's GROUNDED insights
(those carrying a ``source_document_id``):

* Tokenise each insight into distinctive content terms (glue + interrogatives
  stripped — the lexical floor shared across all quality modules).
* Two insights from DIFFERENT sources ``corroborate`` each other if their
  overlap-coefficient ``|a_terms ∩ b_terms| / min(|a_terms|, |b_terms|) >=
  match_threshold`` (default 0.50). Overlap-coefficient (not Jaccard) so a short
  claim that is a SUBSET of a richer one scores 1.0 (they clearly agree) rather
  than being penalised for the richer insight's extra context.
* A claim is ``independently_confirmed`` if it is corroborated by at least one
  insight from a DIFFERENT source (``confirmation_count >= 2`` sources). A claim
  cited to a single source is ``single_source``.

The module reports:

* ``confirmed_claims`` / ``single_source_claims`` / ``ungrounded_claims`` (the
  claim categories — ungrounded = no source_document_id, carried as a count,
  never fabricated as single-source).
* ``corroboration_rate = confirmed / (confirmed + single_source)`` — the fraction
  of GROUNDED claims that are independently confirmed (``None`` when zero
  grounded claims — defer, never ``0.0``/``1.0``).
* ``max_source_agreement`` — the highest number of independent sources supporting
  any single claim (the strongest triangulation in the artifact).
* per-claim ``ClaimCorroboration`` (the claim's representative node_id,
  ``source_ids``, ``confirmation_count``, ``verdict``, ``corroborating_node_ids``
  — auditable).

**Unconfirmed is NOT disproven (load-bearing).** A single-source claim is not
wrong — it may be novel, unique, or ahead of other sources. This axis reports
corroboration as a CREDIBILITY-CONTEXT signal (how independently confirmed is the
evidence), never as a truth verdict. The operator, wrestling with the
information, decides whether a single-source claim needs more chase (escalate it)
or stands on its authority (check source_authority). ``contradiction`` (#1943)
carries the conflict lane; this carries the convergence lane.

**Lexical floor, not semantic (load-bearing).** No stemming, no synonymy. Two
sources that make the SAME POINT in DIFFERENT WORDS may not be flagged as
corroborating — that is the SAME conservative direction as twin_coverage (#1964)
and merge_integrity (#1962): this detector prefers flagging an uncorroborated
claim (false positive — the operator checks and finds the sources do agree) over
certifying corroboration where sources merely share vocabulary (false negative —
that would inflate the triangulation signal behind phony convergence). A
semantic similarity check confirms downstream.

**Honesty rules (load-bearing):**

* ``corroboration_rate`` is ``None`` when zero grounded claims (no confirmed +
  no single-source — defer, never ``0.0`` or ``1.0``).
* Ungrounded insights (no ``source_document_id``) are EXCLUDED from the rate
  (carried as ``ungrounded_claims`` count) — fabricating a single-source verdict
  on an ungrounded insight would conflate "no source" with "one source."
* ``confirmation_count`` counts DISTINCT source ids (two insights from the same
  source corroborating each other is NOT independent confirmation — it is one
  source saying the same thing twice, which ``redundancy`` #1939 measures).
* All-glue insights (zero distinctive terms) are excluded from matching (carried
  as ``unmeasurable_claims`` count) — never fabricated as single-source.
* Corroboration is a CREDIBILITY-CONTEXT signal, never a truth verdict (a
  single-source claim may be novel and correct).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The
artifact is an ordinary ``ResearchArtifactBody`` (the route layer reads it from
the graph DB).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_MATCH_THRESHOLD: float = 0.50

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "been", "being", "am",
        "of", "to", "in", "on", "at", "by", "for", "with", "from",
        "into", "onto", "upon", "over", "under", "between", "through",
        "during", "before", "after", "above", "below", "up", "down",
        "out", "off", "about", "against", "as", "than", "then",
        "and", "or", "but", "nor", "so", "yet", "if", "because",
        "while", "where", "when", "how", "what", "which", "who", "whom",
        "why", "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "other", "such", "own", "same", "too", "do", "does", "did",
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my", "s",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (glue + interrogatives stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


def _overlap_coefficient(a: frozenset[str], b: frozenset[str]) -> float:
    """|a ∩ b| / min(|a|, |b|); 0.0 when either set is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


class SourceCorroborationError(ValueError):
    """A source-corroboration input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ClaimCorroboration:
    """One grounded claim's independent-confirmation profile. Advisory, pure."""

    node_id: str
    source_ids: tuple[str, ...]  # distinct sources supporting this claim
    confirmation_count: int  # len(source_ids) — distinct source count
    corroborating_node_ids: tuple[str, ...]  # other insights that corroborate
    verdict: str  # independently_confirmed | single_source
    match_overlap: float  # best overlap with a corroborating insight (1.0 if exact)


@dataclass(frozen=True)
class SourceCorroborationReport:
    """The artifact's source-corroboration profile. Advisory, pure."""

    artifact_id: str
    confirmed_claims: int
    single_source_claims: int
    ungrounded_claims: int
    unmeasurable_claims: int
    corroboration_rate: float | None  # confirmed/(confirmed+single_source); None if 0 grounded
    max_source_agreement: int  # highest confirmation_count across claims
    distinct_sources: int  # total distinct source_document_ids among grounded insights
    claim_corroborations: tuple[ClaimCorroboration, ...]
    match_threshold: float
    verdict: str  # strongly_corroborated | corroborated | mostly_single_source | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_source_corroboration(
    artifact: ResearchArtifactBody,
    *,
    match_threshold: float = _DEFAULT_MATCH_THRESHOLD,
) -> SourceCorroborationReport:
    """Measure whether the artifact's grounded claims are independently confirmed.

    ``artifact`` is the research artifact whose evidence convergence is being
    measured. Returns a :class:`SourceCorroborationReport` with per-claim
    corroboration + the overall rate + max source agreement.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= match_threshold <= 1.0:
        raise SourceCorroborationError(
            f"match_threshold must be in [0,1], got {match_threshold!r}"
        )

    # Partition insights: grounded (has source_document_id) vs ungrounded.
    grounded: list[tuple[str, str, frozenset[str]]] = []  # (node_id, source_id, terms)
    ungrounded = 0
    unmeasurable = 0
    for ins in artifact.insights:
        terms = _distinctive_terms(ins.text)
        if ins.source_document_id is None:
            ungrounded += 1
            continue
        if not terms:
            unmeasurable += 1
            continue
        grounded.append((ins.node_id, ins.source_document_id, terms))

    confirmed = 0
    single_source = 0
    per_claim: list[ClaimCorroboration] = []
    max_agreement = 0

    for i, (node_id, source_id, terms_i) in enumerate(grounded):
        corrob_sources: set[str] = {source_id}
        corrob_nodes: list[str] = []
        best_overlap = 0.0
        for j, (other_node, other_source, terms_j) in enumerate(grounded):
            if i == j:
                continue
            if other_source == source_id:
                continue  # same source = not independent confirmation (redundancy's lane)
            overlap = _overlap_coefficient(terms_i, terms_j)
            if overlap >= match_threshold:
                corrob_sources.add(other_source)
                corrob_nodes.append(other_node)
                if overlap > best_overlap:
                    best_overlap = overlap

        confirmation_count = len(corrob_sources)
        if confirmation_count >= 2:
            verdict = "independently_confirmed"
            confirmed += 1
        else:
            verdict = "single_source"
            single_source += 1

        if confirmation_count > max_agreement:
            max_agreement = confirmation_count

        per_claim.append(
            ClaimCorroboration(
                node_id=node_id,
                source_ids=tuple(sorted(corrob_sources)),
                confirmation_count=confirmation_count,
                corroborating_node_ids=tuple(corrob_nodes),
                verdict=verdict,
                match_overlap=best_overlap if corrob_nodes else 1.0,
            )
        )

    measurable_grounded = confirmed + single_source
    corroboration_rate = (
        confirmed / measurable_grounded if measurable_grounded else None
    )
    distinct_sources = len({src for _, src, _ in grounded})

    if corroboration_rate is None:
        verdict = "unknown"
    elif corroboration_rate >= 0.60:
        verdict = "strongly_corroborated"
    elif corroboration_rate >= 0.30:
        verdict = "corroborated"
    else:
        verdict = "mostly_single_source"

    notes: list[str] = [
        "source corroboration measures CONVERGENCE — do insights from DIFFERENT "
        "sources lexically support the same claim? The triangulation signal: a claim "
        "backed by 3 independent sources (arxiv + substack + report) is more "
        "trustworthy than a single-source claim. Orthogonal to source_diversity "
        "#1921 (breadth of source base), source_authority #1956 (reputation), and "
        "contradiction #1943 (conflict)",
        "two insights from DIFFERENT sources corroborate if overlap-coefficient "
        "(intersection over the smaller set) >= threshold; a claim with >= 2 "
        "distinct supporting sources is independently_confirmed, else single_source",
        "unconfirmed is NOT disproven — a single-source claim may be novel, unique, "
        "or ahead of other sources; corroboration is a CREDIBILITY-CONTEXT signal, "
        "never a truth verdict (the operator decides whether to chase more sources "
        "or accept the claim on its authority)",
        "confirmation_count counts DISTINCT source_document_ids — two insights from "
        "the SAME source matching is not independent confirmation (that is redundancy "
        "#1939's lane); ungrounded insights (no source) and all-glue insights are "
        "excluded from the rate (carried as counts, never fabricated as single-source)",
        "lexical floor (no stemming/synonymy): two sources making the same point in "
        "different words may not be flagged — prefers flagging an uncorroborated "
        "claim (false positive) over certifying phony convergence (false negative); "
        "a semantic similarity check confirms downstream",
    ]
    rate_str = (
        f"{corroboration_rate:.0%}" if corroboration_rate is not None else "n/a"
    )
    notes.append(
        f"verdict {verdict}: corroboration_rate {rate_str} "
        f"({confirmed} confirmed, {single_source} single-source of "
        f"{measurable_grounded} grounded), max_source_agreement {max_agreement}, "
        f"{distinct_sources} distinct source(s), {ungrounded} ungrounded, "
        f"{unmeasurable} unmeasurable; threshold {match_threshold:.0%}"
    )

    return SourceCorroborationReport(
        artifact_id=artifact.investigation_id,
        confirmed_claims=confirmed,
        single_source_claims=single_source,
        ungrounded_claims=ungrounded,
        unmeasurable_claims=unmeasurable,
        corroboration_rate=corroboration_rate,
        max_source_agreement=max_agreement,
        distinct_sources=distinct_sources,
        claim_corroborations=tuple(per_claim),
        match_threshold=match_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
