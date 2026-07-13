"""Insight novelty — does a finding add anything the conclusion doesn't already say?

Operator vision: *"the highest quality deep research product in the world"* and
the research-workstation ask (*"record the valuable data, insights, and questions
recursively"*). A deep-research artifact's synthesis excerpt is its CONCLUSION —
the distilled summary. Its insights are the detailed findings. An insight that
merely restates the conclusion's vocabulary adds NO value: the operator already
has that content in the synthesis. The insights exist to ADD detail, evidence, or
framing beyond the summary. A research artifact whose every insight paraphrases
its own synthesis is hollow — long-looking but empty.

No current axis measures this. ``synthesis_grounding`` (#1942) checks the INVERSE
direction: does the conclusion rest on its evidence (synthesis terms supported by
insight terms)? ``redundancy`` (#1939) checks insight-vs-insight duplication
within the artifact. NEITHER checks insight-vs-synthesis: does THIS insight add
vocabulary the synthesis excerpt does not contain? That is the novelty axis.

**The measurement (hard to vary).** For each insight:

* Extract its distinctive terms (content words, glue stripped — the shared lexical
  floor).
* ``novelty_ratio = |insight_terms − synthesis_terms| / |insight_terms|`` — the
  fraction of the insight's distinctive vocabulary ABSENT from the synthesis
  excerpt. In ``[0.0, 1.0]``.
* An insight with ``novelty_ratio >= novelty_threshold`` (default 0.50) is
  ``novel`` (adds new content); below is ``derivative`` (restates the conclusion).
* An insight with no distinctive terms is ``unmeasurable`` (excluded from the
  novelty rate, never fabricated).

The module reports:

* ``novel_count`` / ``derivative_count`` / ``unmeasurable_count``.
* ``novelty_rate = novel / measurable`` — the overall added-value density (``None``
  when zero measurable).
* per-insight ``InsightNovelty`` (``node_id``, ``novelty_ratio``, ``verdict``,
  ``novel_terms`` — the auditable evidence: exactly which terms the insight
  contributes beyond the synthesis).
* ``mean_novelty_ratio`` over measurable insights (``None`` when zero measurable).

**Honesty rules (load-bearing):**

* When ``synthesis_withheld`` is ``True`` OR ``synthesis_excerpt`` is ``None``, the
  novelty axis is ``unmeasurable`` for EVERY insight — there is no synthesis to
  compare against (defer — never fabricated; the operator deliberately withheld or
  there is no excerpt). ``novelty_rate`` and ``mean_novelty_ratio`` are ``None``;
  ``unmeasurable_count`` = insight count; verdict ``unknown``.
* An insight with no distinctive terms is ``unmeasurable`` (excluded from the rate).
* ``novelty_rate`` is ``None`` when zero measurable insights (defer).
* ``novelty_ratio`` is in ``[0.0, 1.0]``; ``novel_terms`` is the set difference
  (auditable — exactly the added vocabulary).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock,
  no mutation.
* ``authority`` is always ``"advisory"``.

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content words
(glue stripped), NO stemming, NO synonymy. An insight that PARAPHRASES the synthesis
(same meaning, different words) scores HIGH novelty — it uses new vocabulary even
though it conveys no new idea. That is the precision/recall tradeoff, INVERTED from
twin_fidelity (#1954): here a lexical floor that flags paraphrases as "novel" is the
conservative error (the operator can confirm with a semantic check). This detector
prefers certifying a paraphrase as novel (false positive) over burying a genuinely
new finding behind a phony overlap (false negative). The synthesis is the SUMMARY —
insights should add to it, and the vocabulary test is the honest floor.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_NOVELTY_THRESHOLD: float = 0.50

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
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my",
        "do", "does", "did", "doing", "have", "has", "had", "having",
        "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "other", "such", "own", "same", "too", "s",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (grammatical glue stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


class InsightNoveltyError(ValueError):
    """An insight-novelty input violates a load-bearing invariant."""


@dataclass(frozen=True)
class InsightNovelty:
    """One insight's novelty (added value beyond the synthesis)."""

    node_id: str
    novelty_ratio: float | None  # None if unmeasurable (no terms or no synthesis)
    verdict: str  # novel | derivative | unmeasurable
    novel_terms: tuple[str, ...]  # insight terms absent from synthesis (auditable)


@dataclass(frozen=True)
class InsightNoveltyReport:
    """The artifact's insight-novelty profile. Advisory, pure."""

    artifact_id: str
    novel_count: int
    derivative_count: int
    unmeasurable_count: int
    novelty_rate: float | None  # novel/measurable; None if zero measurable
    mean_novelty_ratio: float | None  # over measurable; None if zero measurable
    insight_novelties: tuple[InsightNovelty, ...]
    novelty_threshold: float
    verdict: str  # high_novelty | mixed | derivative | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_insight_novelty(
    artifact: ResearchArtifactBody,
    *,
    novelty_threshold: float = _DEFAULT_NOVELTY_THRESHOLD,
) -> InsightNoveltyReport:
    """Measure whether the artifact's insights add value beyond their synthesis.

    ``artifact`` is a completed deep-research artifact. Returns an
    :class:`InsightNoveltyReport` with per-insight novelty + the overall
    added-value density. When the synthesis is withheld or absent, every insight is
    unmeasurable (defer — never fabricated).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= novelty_threshold <= 1.0:
        raise InsightNoveltyError(
            f"novelty_threshold must be in [0,1], got {novelty_threshold!r}"
        )

    excerpt = artifact.synthesis_excerpt
    has_synthesis = not artifact.synthesis_withheld and excerpt is not None
    if has_synthesis:
        assert excerpt is not None  # narrows for the type checker
        synthesis_terms = _distinctive_terms(excerpt)
    else:
        synthesis_terms = frozenset()

    per_insight: list[InsightNovelty] = []
    novel = 0
    derivative = 0
    unmeasurable = 0
    measurable_ratios: list[float] = []

    for ins in artifact.insights:
        ins_terms = _distinctive_terms(ins.text)
        # Unmeasurable when no insight terms OR no synthesis to compare against.
        if not ins_terms or not has_synthesis:
            per_insight.append(
                InsightNovelty(
                    node_id=ins.node_id,
                    novelty_ratio=None,
                    verdict="unmeasurable",
                    novel_terms=(),
                )
            )
            unmeasurable += 1
            continue

        novel_set = ins_terms - synthesis_terms
        ratio = len(novel_set) / len(ins_terms)
        novel_terms = tuple(sorted(novel_set))

        if ratio >= novelty_threshold:
            verdict = "novel"
            novel += 1
        else:
            verdict = "derivative"
            derivative += 1
        measurable_ratios.append(ratio)

        per_insight.append(
            InsightNovelty(
                node_id=ins.node_id,
                novelty_ratio=ratio,
                verdict=verdict,
                novel_terms=novel_terms,
            )
        )

    measurable = novel + derivative
    novelty_rate = novel / measurable if measurable else None
    mean_ratio = (
        sum(measurable_ratios) / len(measurable_ratios) if measurable_ratios else None
    )

    if novelty_rate is None:
        artifact_verdict = "unknown"
    elif novelty_rate >= 0.60:
        artifact_verdict = "high_novelty"
    elif novelty_rate >= 0.30:
        artifact_verdict = "mixed"
    else:
        artifact_verdict = "derivative"

    notes: list[str] = [
        "insight novelty measures whether each finding adds vocabulary BEYOND the "
        "synthesis excerpt (the conclusion) — an insight that merely restates the "
        "synthesis adds no value; the operator's 'highest quality deep research' bar "
        "demands insights that contribute detail/evidence/framing the summary lacks",
        "the INVERSE of synthesis_grounding #1942 (does the conclusion rest on evidence) "
        "and DISTINCT from redundancy #1939 (insight-vs-insight duplication): here an "
        "insight is judged against the synthesis (insights->synthesis direction)",
        "novelty_ratio = |insight_terms - synthesis_terms| / |insight_terms|: the "
        "fraction of distinctive vocabulary ABSENT from the synthesis; novel_terms is "
        "the auditable evidence (exactly which terms the insight contributes)",
        "lexical floor (no stemming/synonymy): a paraphrase (same meaning, different "
        "words) scores HIGH novelty — this detector prefers certifying a paraphrase as "
        "novel (false positive) over burying a genuine finding (false negative); a "
        "semantic check can confirm downstream",
    ]
    if not has_synthesis:
        notes.append(
            "synthesis is withheld or absent — novelty is not measurable for any "
            "insight (defer — never fabricated; there is no conclusion to compare "
            "against)"
        )
    elif novelty_rate is None:
        notes.append(
            "no measurable insights (empty artifact or all-empty text); novelty is "
            "not measurable (defer — never fabricated)"
        )
    else:
        notes.append(
            f"novelty rate {novelty_rate:.0%}: {novel} novel, {derivative} derivative, "
            f"{unmeasurable} unmeasurable of {len(artifact.insights)} insight(s) at "
            f"threshold {novelty_threshold:.0%} -> verdict {artifact_verdict}"
        )

    return InsightNoveltyReport(
        artifact_id=artifact.investigation_id,
        novel_count=novel,
        derivative_count=derivative,
        unmeasurable_count=unmeasurable,
        novelty_rate=novelty_rate,
        mean_novelty_ratio=mean_ratio,
        insight_novelties=tuple(per_insight),
        novelty_threshold=novelty_threshold,
        verdict=artifact_verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "InsightNovelty",
    "InsightNoveltyError",
    "InsightNoveltyReport",
    "measure_insight_novelty",
]
