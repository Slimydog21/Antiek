"""Merge integrity — did the merge preserve its parents without dropping content?

Operator vision (asks #2/#3): *"create floating windows where I spin up deep
research instances ... I can choose to merge it into the asset I am reading ...
maybe I want to merge various sub-agent deep researches after they come to
completion to create a written analysis, or maybe I want to click on multiple of
these sub agents to engage in a collective deep research where I merge those
instances and prompt them as a cohesive unit."* The merge is the workstation's
COMBINATION operation: N parent artifacts (highlights, floating instances,
collective researches) fold into one merged artifact. But NOTHING measures whether
that fold PRESERVED its inputs. A merge that silently drops a parent's key insight
— or every question a parent raised — is an information failure masquerading as a
combination: the operator believes the merged asset carries everything its parents
did, when it does not. No engine grades its own homework; the merge *operation*
(#1833 draft-analysis writer, #1835 synthesis mode, #1837 research→parent merge,
#1846 promotion state machine, #1852 twin-substrate merge) cannot certify its own
fidelity.

No current axis measures this. ``provenance_coverage`` (#1940) traces insights to
external SOURCES (arxiv, substack, URLs) — it never checks whether the merged
artifact carried forward the PARENT ARTIFACTS' content.
``twin_fidelity`` (#1954) is 1:1 (one twin vs its single original, measuring
hallucination) — the merge is N:1 (many parents into one merged, measuring
preservation across the combination boundary). ``redundancy`` (#1939) measures
within-document repetition; ``insight_novelty`` (#1958) measures a finding's value
beyond its OWN synthesis; ``recursion_closure`` (#1961) measures whether a child
resolved a parent QUESTION. THIS is the missing check: across the merge boundary,
did each parent's insights AND questions lexically survive into the merged result?

**The measurement (hard to vary).** For each parent artifact P and the merged
artifact M:

* Tokenise every insight/question into distinctive content terms (glue +
  interrogatives stripped). All-glue items are NOT measurable and are excluded
  from both numerator and denominator (carried as a count for honesty — never
  fabricated as a lost item).
* An insight "survives" if it lexically matches ANY insight in M with an
  overlap-coefficient ``|P_terms ∩ M_terms| / min(|P_terms|, |M_terms|) >=
  survival_threshold`` (default 0.50). Overlap-coefficient (not Jaccard) so a
  short parent insight that is a SUBSET of a richer merged insight scores 1.0
  (it clearly survived) rather than being penalised for the merge's added
  context.
* ``insight_survival = survived_insights / measurable_insights`` per parent
  (``None`` when the parent has zero measurable insights). ``question_survival``
  is the symmetric measure over questions.

The per-parent verdict:

* both ``insight_survival`` and ``question_survival`` ``None`` → ``unknown`` (no
  measurable content — defer, never fabricated).
* ``insight_survival < survival_threshold`` → ``insight_loss`` (the parent's
  findings were dropped).
* ``question_survival < survival_threshold`` → ``question_loss`` (the parent's
  recursive questions were dropped).
* else → ``preserved`` (the parent's content made it through the fold).

The overall verdict: ``parent_loss`` if ANY measurable parent lost content
(insight or question survival below threshold), else ``preserved``; ``unknown``
when no parent carries measurable content.

The module ALSO reports ``orphan_insight_ratio`` — the fraction of M's
measurable insights that match NO parent — as INFORMATIONAL, never a verdict
input. A merge that COMBINES parents then SYNTHESISES a written analysis will
legitimately produce insights traced to no single parent; flagging that as
"injection" would falsely accuse legitimate synthesis of fabrication. The ratio
characterises the merge (faithful combination = low orphan; active synthesis =
high orphan) without judging it. ``provenance_coverage`` (#1940) and
``contradiction`` (#1943) carry the source-tracing and conflict lanes.

**Lexical floor, not semantic (load-bearing).** No stemming, no synonymy. A
parent insight rephrased in the merge (same meaning, different words) may score
low — that is the conservative direction shared with twin_fidelity (#1954) and
recursion_closure (#1961): this detector prefers flagging a rephrased insight
(false positive — the operator confirms downstream) over certifying a preserved
merge that silently dropped a parent (false negative — that hides real
information loss behind a phony all-clear).

**Honesty rules (load-bearing):**

* ``insight_survival`` / ``question_survival`` are ``None`` when a parent has
  zero measurable items (defer — never ``0.0`` or ``1.0``).
* All-glue items are excluded from survival ratios and orphan counts (carried as
  ``unmeasurable_*`` counts) — fabricating a lost item from glue would conflate
  "unmeasurable" with "dropped".
* ``orphan_insight_ratio`` is carried through (auditable) but is NOT a verdict
  input — novel merged content is legitimate synthesis, not fabrication.
* Survival ratios are in ``[0.0, 1.0]``; matched-term evidence is recorded per
  parent (auditable — exactly which parent items found a home in the merge).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The
parents and merged artifact are ordinary ``ResearchArtifactBody`` instances (the
route layer reads them from the graph DB by following the merge edge).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_SURVIVAL_THRESHOLD: float = 0.50

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


def _survival_rate(
    parent_items: list[str],
    merged_item_sets: list[frozenset[str]],
    *,
    threshold: float,
) -> tuple[float | None, int, int, int]:
    """Return (survival_ratio, survived, measurable, unmeasurable) for one parent.

    ``survival_ratio`` is ``None`` when the parent has zero measurable items.
    """
    measurable_sets: list[frozenset[str]] = []
    unmeasurable = 0
    for text in parent_items:
        terms = _distinctive_terms(text)
        if terms:
            measurable_sets.append(terms)
        else:
            unmeasurable += 1

    if not measurable_sets:
        return None, 0, 0, unmeasurable

    survived = 0
    for pterms in measurable_sets:
        best = 0.0
        for mterms in merged_item_sets:
            score = _overlap_coefficient(pterms, mterms)
            if score > best:
                best = score
                if best >= 1.0:
                    break
        if best >= threshold:
            survived += 1

    return survived / len(measurable_sets), survived, len(measurable_sets), unmeasurable


class MergeIntegrityError(ValueError):
    """A merge-integrity input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ParentCoverage:
    """One parent's preservation profile across the merge. Advisory, pure."""

    parent_id: str
    insight_survival: float | None  # None if zero measurable insights
    question_survival: float | None  # None if zero measurable questions
    survived_insights: int
    measurable_insights: int
    unmeasurable_insights: int  # all-glue (excluded from the ratio)
    survived_questions: int
    measurable_questions: int
    unmeasurable_questions: int
    verdict: str  # preserved | insight_loss | question_loss | loss | unknown


@dataclass(frozen=True)
class MergeIntegrityReport:
    """The merged artifact's preservation profile. Advisory, pure."""

    merged_id: str
    parent_coverages: tuple[ParentCoverage, ...]
    mean_insight_survival: float | None  # None if no parent measurable on insights
    mean_question_survival: float | None
    weakest_parent_id: str | None  # the parent with the lowest binding survival
    weakest_survival: float | None  # the binding (min of insight/question) survival
    orphan_insight_ratio: float | None  # informational: merged insights matching no parent
    orphan_insight_count: int
    measurable_merge_insights: int
    survival_threshold: float
    verdict: str  # preserved | parent_loss | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_merge_integrity(
    parents: list[ResearchArtifactBody],
    merged: ResearchArtifactBody,
    *,
    survival_threshold: float = _DEFAULT_SURVIVAL_THRESHOLD,
) -> MergeIntegrityReport:
    """Measure whether the merged artifact preserved its parents' content.

    ``parents`` are the N artifacts folded into ``merged``. Each parent and the
    merged artifact are ordinary :class:`ResearchArtifactBody` instances (the
    route layer reads them from the graph DB by following the merge edge).
    Returns a :class:`MergeIntegrityReport` with per-parent preservation + the
    overall verdict + the informational orphan ratio.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not parents:
        raise MergeIntegrityError("at least one parent is required to measure a merge")
    if not 0.0 <= survival_threshold <= 1.0:
        raise MergeIntegrityError(
            f"survival_threshold must be in [0,1], got {survival_threshold!r}"
        )

    merged_insight_sets = [
        t for t in (_distinctive_terms(i.text) for i in merged.insights) if t
    ]
    merged_question_sets = [
        t for t in (_distinctive_terms(q.text) for q in merged.open_questions) if t
    ]

    coverages: list[ParentCoverage] = []
    insight_survivals: list[float] = []
    question_survivals: list[float] = []
    weakest_parent_id: str | None = None
    weakest_survival: float | None = None

    for parent in parents:
        i_ratio, i_surv, i_meas, i_unmeas = _survival_rate(
            [ins.text for ins in parent.insights],
            merged_insight_sets,
            threshold=survival_threshold,
        )
        q_ratio, q_surv, q_meas, q_unmeas = _survival_rate(
            [q.text for q in parent.open_questions],
            merged_question_sets,
            threshold=survival_threshold,
        )

        if i_ratio is not None:
            insight_survivals.append(i_ratio)
        if q_ratio is not None:
            question_survivals.append(q_ratio)

        # Per-parent verdict: a parent is "loss" if EITHER insight or question
        # survival fell below threshold (dropping findings OR questions both
        # lose information the parent contributed).
        if i_ratio is None and q_ratio is None:
            p_verdict = "unknown"
        elif i_ratio is not None and i_ratio < survival_threshold and (
            q_ratio is None or q_ratio >= survival_threshold
        ):
            p_verdict = "insight_loss"
        elif q_ratio is not None and q_ratio < survival_threshold and (
            i_ratio is None or i_ratio >= survival_threshold
        ):
            p_verdict = "question_loss"
        elif (
            i_ratio is not None
            and i_ratio < survival_threshold
            and q_ratio is not None
            and q_ratio < survival_threshold
        ):
            p_verdict = "loss"
        else:
            p_verdict = "preserved"

        # Binding survival = the worse of the two measurable ratios (None treated
        # as "not constraining"). Used to find the weakest parent overall.
        binding_candidates: list[float] = [
            r for r in (i_ratio, q_ratio) if r is not None
        ]
        binding = min(binding_candidates) if binding_candidates else None
        if binding is not None and (
            weakest_survival is None or binding < weakest_survival
        ):
            weakest_survival = binding
            weakest_parent_id = parent.investigation_id

        coverages.append(
            ParentCoverage(
                parent_id=parent.investigation_id,
                insight_survival=i_ratio,
                question_survival=q_ratio,
                survived_insights=i_surv,
                measurable_insights=i_meas,
                unmeasurable_insights=i_unmeas,
                survived_questions=q_surv,
                measurable_questions=q_meas,
                unmeasurable_questions=q_unmeas,
                verdict=p_verdict,
            )
        )

    mean_insight = (
        sum(insight_survivals) / len(insight_survivals) if insight_survivals else None
    )
    mean_question = (
        sum(question_survivals) / len(question_survivals) if question_survivals else None
    )

    # Informational orphan ratio: fraction of M's measurable insights matching no
    # parent (NOT a verdict input — novel merged content may be legitimate
    # synthesis, not fabrication).
    parent_insight_term_sets: list[frozenset[str]] = []
    for parent in parents:
        for ins in parent.insights:
            terms = _distinctive_terms(ins.text)
            if terms:
                parent_insight_term_sets.append(terms)

    orphan_count = 0
    if merged_insight_sets:
        for mterms in merged_insight_sets:
            best = 0.0
            for pterms in parent_insight_term_sets:
                score = _overlap_coefficient(mterms, pterms)
                if score > best:
                    best = score
                    if best >= 1.0:
                        break
            if best < survival_threshold:
                orphan_count += 1
        orphan_ratio: float | None = orphan_count / len(merged_insight_sets)
    else:
        orphan_ratio = None

    any_loss = any(
        c.verdict in {"insight_loss", "question_loss", "loss"} for c in coverages
    )
    all_unknown = all(c.verdict == "unknown" for c in coverages)

    if all_unknown:
        verdict = "unknown"
    elif any_loss:
        verdict = "parent_loss"
    else:
        verdict = "preserved"

    notes: list[str] = [
        "merge integrity measures whether a merged artifact PRESERVED its parents' "
        "content across the combination boundary — the N:1 fold's fidelity check; "
        "the merge operation (#1833/#1835/#1837/#1846/#1852) cannot grade its own "
        "preservation, and provenance_coverage #1940 traces to external sources, not "
        "parent artifacts",
        "survival uses overlap-coefficient |P ∩ M| / min(|P|, |M|) >= threshold so a "
        "short parent insight that is a subset of a richer merged insight scores 1.0 "
        "(survived) rather than being penalised for the merge's added context",
        "parent_loss if ANY parent's insight OR question survival fell below threshold "
        "(dropping findings or recursive questions both lose information); all-glue "
        "items are excluded from the ratios and carried as unmeasurable counts (never "
        "fabricated as lost)",
        "orphan_insight_ratio is INFORMATIONAL only (fraction of merged insights "
        "matching no parent) — novel merged content may be legitimate synthesis, not "
        "fabrication; provenance_coverage #1940 and contradiction #1943 carry the "
        "source-tracing and conflict lanes",
        "lexical floor (no stemming/synonymy): a parent insight rephrased in the merge "
        "may score low — prefers flagging a rephrased insight (false positive) over "
        "certifying a preserved merge that silently dropped a parent (false negative); "
        "a semantic check confirms downstream",
    ]
    loss_count = sum(
        1 for c in coverages if c.verdict in {"insight_loss", "question_loss", "loss"}
    )
    notes.append(
        f"verdict {verdict}: {len(coverages)} parent(s), {loss_count} with content loss "
        f"(threshold {survival_threshold:.0%}); "
        f"mean insight survival "
        f"{(f'{mean_insight:.0%}' if mean_insight is not None else 'n/a')}, "
        f"mean question survival "
        f"{(f'{mean_question:.0%}' if mean_question is not None else 'n/a')}, "
        f"orphan insight ratio "
        f"{(f'{orphan_ratio:.0%}' if orphan_ratio is not None else 'n/a')}"
    )

    return MergeIntegrityReport(
        merged_id=merged.investigation_id,
        parent_coverages=tuple(coverages),
        mean_insight_survival=mean_insight,
        mean_question_survival=mean_question,
        weakest_parent_id=weakest_parent_id,
        weakest_survival=weakest_survival,
        orphan_insight_ratio=orphan_ratio,
        orphan_insight_count=orphan_count,
        measurable_merge_insights=len(merged_insight_sets),
        survival_threshold=survival_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
