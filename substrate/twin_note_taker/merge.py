"""Twin-substrate merge — combine N twins into one unified substrate (ask #4).

The operator's vision (ask #4): *"...that substrate of information can be
merged, referenced, and leveraged in combining contexts or doing intelligent
search over my dream of an infinite information platform."* A twin is the
LLM-proposed insights + questions of ONE asset (#1836 generation core). The
vision is recursive: twins of many assets must COMBINE into one substrate so the
operator can reference and search across everything at once. THIS module is that
combination — it merges N twin ``ResearchArtifactBody`` documents into ONE
unified, deduped, content-addressed merged twin.

**What this is NOT** (the seam boundaries, kept honest):
  * NOT synthesis. The merge mechanically DEDUPES and UNIONS; it does not write
    a new analysis. Writing a unified analysis is the collective synthesizer's
    job (#1835, an injectable LLM caller). The merged twin carries
    ``synthesis_withheld=True`` — we never fake a synthesis the pure layer did
    not perform.
  * NOT promotion. The merged twin is advisory; earning permanent graph-node
    status is the promotion planner's job (#1847). The merge feeds #1847 a
    single unified substrate instead of N scattered twins.
  * NOT search. Retrieval over the substrate is #1844. The merge produces the
    substrate that makes cross-asset search meaningful.

**The content-addressed guarantee (load-bearing, mirrors the graph writers).**
Dedup identity is ``canonical_text(text)`` — lower-case, whitespace-collapsed,
stripped — exactly as ``substrate/graph/insight_question.py`` defines it. The
merged finding's ``node_id`` is ``insight_node_id`` / ``question_node_id`` — the
SAME content-addressed id the sanctioned graph writers assign. So:

  * **Two twins surfacing the same insight collapse to ONE finding** with one
    node_id — the cross-asset "reference and leverage" the operator named is
    structural, not approximate.
  * **The merge is execution-faithful for promotion.** The node_id the merge
    computes IS the node_id ``promote_insight`` will assign — #1847 can plan the
    merged twin's promotion with zero id surprises.

**Corroboration is the signal, not a guess.** A finding that appears in K twins
carries ``corroboration_count = K`` and the tuple of contributing twin ids. The
operator asked to "leverage in combining contexts" — a corroborated insight
(surfaced independently by several assets) is the highest-value substrate
member. This is real provenance (which twins, in input order), never a fabricated
confidence score.

**Honesty rules (each is a test):**
  1. Blank/whitespace texts are FILTERED (never merged), counted in stats.
  2. Representative text is the FIRST-SEEN original casing (input-order
     deterministic); canonical normalization is used only for identity.
  3. ``source_document_id`` on the merged ``ArtifactInsight`` is the first
     contributing source's document (deterministic primary source); the FULL
     provenance tuple lives on ``MergedFinding`` (the merge's auditable copy).
  4. A merged question is ``escalated`` if ANY source question was escalated
     (escalation propagates — never silently dropped).
  5. Empty input fails closed (nothing to merge). A single twin merges (the
     idempotent within-twin dedup base case).
  6. The merged twin's ``investigation_id`` is content-addressed over the sorted
     contributing twin ids → re-merging the same twins is stable (idempotent).
  7. Pure: no I/O, no clock, no dispatch, no DB. Only on-main schema + graph
     pure helpers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from substrate.graph.insight_question import (
    canonical_text,
    insight_node_id,
    question_node_id,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


class TwinMergeError(ValueError):
    """Fail-closed: merge input that cannot produce an honest unified substrate."""


@dataclass(frozen=True)
class MergedFinding:
    """One deduped insight/question across twins, with corroboration provenance.

    The canonical ``ResearchArtifactBody`` carries the deduped finding; THIS
    object is the merge's auditable copy with the FULL cross-twin provenance the
    pydantic model cannot natively hold (which twins contributed, in input order).
    """

    node_id: str  # content-addressed — matches the sanctioned graph writers / #1847
    text: str  # first-seen original casing; canonical normalization is identity-only
    source_twin_ids: tuple[str, ...]  # investigation_ids of contributing twins (input order, deduped)
    source_document_ids: tuple[str | None, ...]  # per-twin source asset (None preserved)
    corroboration_count: int  # == len(source_twin_ids); the cross-twin reuse signal
    escalated: bool = False  # questions only: True if ANY source escalated


@dataclass(frozen=True)
class MergeStats:
    """Auditable counts for one merge (the dedup signal made explicit)."""

    input_twin_count: int
    input_insight_count: int  # raw, pre-dedup
    input_question_count: int  # raw, pre-dedup
    merged_insight_count: int  # post-dedup
    merged_question_count: int  # post-dedup
    insight_dedup_collapses: int  # input_insight_count - merged_insight_count
    question_dedup_collapses: int
    corroborated_insight_count: int  # insights with corroboration_count > 1
    corroborated_question_count: int
    filtered_blank_insights: int
    filtered_blank_questions: int
    synthesis_withheld: bool  # always True — the pure merge does not synthesize


@dataclass(frozen=True)
class TwinMergeResult:
    """The unified substrate: a merged twin + the merge's auditable provenance."""

    merged: ResearchArtifactBody  # a twin-of-twins (recursion); canonical transport
    merged_insights: tuple[MergedFinding, ...]  # full cross-twin provenance
    merged_questions: tuple[MergedFinding, ...]
    source_twin_ids: tuple[str, ...]  # all contributing twins, input order (deduped)
    stats: MergeStats


def _merged_investigation_id(source_twin_ids: tuple[str, ...]) -> str:
    """Content-addressed merge id over sorted contributing twin ids.

    Sorting makes the id independent of input order → re-merging the same set of
    twins (in any order) yields the same merged twin investigation_id (idempotent).
    """
    blob = "|".join(sorted(source_twin_ids))
    return "twin-merge-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _first_nonblank(values: tuple[str, ...], default: str) -> str:
    for value in values:
        if value.strip():
            return value
    return default


def merge_twins(
    twins: list[ResearchArtifactBody],
    *,
    problem_question_override: str | None = None,
) -> TwinMergeResult:
    """Merge N twin documents into one unified, deduped, content-addressed substrate.

    Inputs are twin ``ResearchArtifactBody`` objects (each the proposed
    insights+questions of one source asset, per #1836). The output is a single
    merged twin carrying the deduped findings, plus ``MergedFinding`` objects with
    the full cross-twin corroboration provenance.

    ``problem_question_override`` lets a caller name the merged problem statement
    (e.g. from a synthesis step). Without it, the merged twin carries the first
    non-blank source problem_question (deterministic); a real unified problem
    statement requires synthesis (#1835), which is withheld here.
    """
    if not twins:
        raise TwinMergeError("cannot merge zero twins — at least one twin is required")

    # Stable, deduped contributing-twin roster in input order.
    seen_twin_ids: list[str] = []
    for twin in twins:
        if twin.investigation_id not in seen_twin_ids:
            seen_twin_ids.append(twin.investigation_id)
    source_twin_ids = tuple(seen_twin_ids)

    # ---- insight dedup by canonical text ---------------------------------- #
    insight_groups: dict[str, MergedFinding] = {}
    insight_order: list[str] = []  # canonical key in first-seen order
    input_insight_count = 0
    filtered_blank_insights = 0

    for twin in twins:
        for insight in twin.insights:
            input_insight_count += 1
            canonical = canonical_text(insight.text)
            if not canonical:
                filtered_blank_insights += 1
                continue
            source_doc = insight.source_document_id
            if canonical in insight_groups:
                existing = insight_groups[canonical]
                # accumulate provenance (dedup twin ids within one canonical group)
                twin_ids = (
                    existing.source_twin_ids
                    if twin.investigation_id in existing.source_twin_ids
                    else (*existing.source_twin_ids, twin.investigation_id)
                )
                doc_ids = (
                    existing.source_document_ids
                    if source_doc in existing.source_document_ids
                    else (*existing.source_document_ids, source_doc)
                )
                insight_groups[canonical] = MergedFinding(
                    node_id=existing.node_id,
                    text=existing.text,  # first-seen casing preserved
                    source_twin_ids=twin_ids,
                    source_document_ids=doc_ids,
                    corroboration_count=len(twin_ids),
                    escalated=existing.escalated,
                )
            else:
                insight_order.append(canonical)
                insight_groups[canonical] = MergedFinding(
                    node_id=insight_node_id(insight.text),
                    text=insight.text,
                    source_twin_ids=(twin.investigation_id,),
                    source_document_ids=(source_doc,),
                    corroboration_count=1,
                )

    # ---- question dedup by canonical text --------------------------------- #
    question_groups: dict[str, MergedFinding] = {}
    question_order: list[str] = []
    input_question_count = 0
    filtered_blank_questions = 0

    for twin in twins:
        for question in twin.open_questions:
            input_question_count += 1
            canonical = canonical_text(question.text)
            if not canonical:
                filtered_blank_questions += 1
                continue
            if canonical in question_groups:
                existing = question_groups[canonical]
                twin_ids = (
                    existing.source_twin_ids
                    if twin.investigation_id in existing.source_twin_ids
                    else (*existing.source_twin_ids, twin.investigation_id)
                )
                question_groups[canonical] = MergedFinding(
                    node_id=existing.node_id,
                    text=existing.text,
                    source_twin_ids=twin_ids,
                    source_document_ids=existing.source_document_ids,  # questions carry no doc id
                    corroboration_count=len(twin_ids),
                    escalated=existing.escalated or question.escalated,
                )
            else:
                question_order.append(canonical)
                question_groups[canonical] = MergedFinding(
                    node_id=question_node_id(question.text),
                    text=question.text,
                    source_twin_ids=(twin.investigation_id,),
                    source_document_ids=(),
                    corroboration_count=1,
                    escalated=question.escalated,
                )

    merged_insights = tuple(insight_groups[key] for key in insight_order)
    merged_questions = tuple(question_groups[key] for key in question_order)

    # ---- build the canonical merged twin (a twin-of-twins) ---------------- #
    merged_problem_question = (
        problem_question_override.strip()
        if problem_question_override is not None and problem_question_override.strip()
        else _first_nonblank(
            tuple(twin.problem_question for twin in twins),
            default="(merged twin substrate)",
        )
    )

    merged_body_insights: list[ArtifactInsight] = [
        ArtifactInsight(
            node_id=finding.node_id,
            text=finding.text,
            source_document_id=finding.source_document_ids[0]
            if finding.source_document_ids
            else None,  # deterministic primary source; full tuple on the finding
            confidence=f"corroborated:{finding.corroboration_count}"
            if finding.corroboration_count > 1
            else None,
        )
        for finding in merged_insights
    ]
    merged_body_questions: list[ArtifactQuestion] = [
        ArtifactQuestion(
            node_id=finding.node_id,
            text=finding.text,
            escalated=finding.escalated,
        )
        for finding in merged_questions
    ]

    merged = ResearchArtifactBody(
        investigation_id=_merged_investigation_id(source_twin_ids),
        problem_question=merged_problem_question,
        insights=merged_body_insights,
        open_questions=merged_body_questions,
        synthesis_excerpt=None,  # honest: the pure merge does not synthesize
        synthesis_withheld=True,
        source_event_ids=list(source_twin_ids),  # provenance: contributing twins
        agent_notes=[
            f"merged {len(twins)} twins "
            f"({input_insight_count} insights -> {len(merged_insights)}, "
            f"{input_question_count} questions -> {len(merged_questions)}); "
            f"synthesis withheld (pure merge)"
        ],
    )

    corroborated_insight_count = sum(
        1 for finding in merged_insights if finding.corroboration_count > 1
    )
    corroborated_question_count = sum(
        1 for finding in merged_questions if finding.corroboration_count > 1
    )

    stats = MergeStats(
        input_twin_count=len(twins),
        input_insight_count=input_insight_count,
        input_question_count=input_question_count,
        merged_insight_count=len(merged_insights),
        merged_question_count=len(merged_questions),
        insight_dedup_collapses=input_insight_count
        - filtered_blank_insights
        - len(merged_insights),
        question_dedup_collapses=input_question_count
        - filtered_blank_questions
        - len(merged_questions),
        corroborated_insight_count=corroborated_insight_count,
        corroborated_question_count=corroborated_question_count,
        filtered_blank_insights=filtered_blank_insights,
        filtered_blank_questions=filtered_blank_questions,
        synthesis_withheld=True,
    )

    return TwinMergeResult(
        merged=merged,
        merged_insights=merged_insights,
        merged_questions=merged_questions,
        source_twin_ids=source_twin_ids,
        stats=stats,
    )


__all__ = [
    "TwinMergeError",
    "MergedFinding",
    "MergeStats",
    "TwinMergeResult",
    "merge_twins",
]
