"""Speak SPR-04 — the compounding interviewer (context-conditioned).

The operator's vision: as a project aggregates information, the
interviewer gets sharper — "a better Walter Isaacson available to
everyone" — asking the next person exactly the question that fills a
gap, deepens an insight, or corroborates a story.

Honest framing (rigor #1): v1 asks better questions because it has more
CONTEXT, not because it LEARNED anything. It is context-conditioned at
the prompt level, not trained, not superhuman. The RL-tuned interviewer
that learns to ask better questions is captured-and-deferred to
Loop-3/G8 (``interviewer_capture.py``).

The load-bearing privacy rule (rigor #3): conditioning interviewee B's
questions on interviewee A's statements must respect A's consent scope.
A statement from a record-ONLY source must NEVER surface in another
interview — not as an insight, not as a corroboration probe. The filter
here is: a source's claim may inform ANOTHER interviewee only if that
source granted ``attribute`` consent.

And don't lead the witness: corroboration prompts ask OPENLY about the
topic — they never restate the claim's assertion, which would put words
in the next person's mouth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import corroboration
from .consent import ConsentScope, has_consent
from .contracts import GapSource, OpenQuestion
from .project import project_claims
from .third_party import get_claim

# ---------------------------------------------------------------------------
# Default GapSource — until DRW SPR-07 (substrate/gap_detection/) lands
# ---------------------------------------------------------------------------


class SpeakGraphGapSource:
    """The default ``GapSource``: surfaces gaps from the Speak project
    graph itself — single-sourced third-party claims to corroborate,
    under-explored subjects to deepen, and unanswered must-cover
    questions. DRW SPR-07 will replace this with graph-wide centrality;
    both satisfy ``contracts.GapSource``."""

    def __init__(self, con: Any):
        self.con = con

    def open_questions(self, project_id: str, *, limit: int = 20) -> list[OpenQuestion]:
        gaps: list[OpenQuestion] = []

        # corroborate: single-sourced third-party claims.
        for c in corroboration.claims_needing_corroboration(self.con, project_id):
            subject = c.subject_ref or "them"
            gaps.append(OpenQuestion(
                question_id=f"corr-{c.claim_id}",
                # Non-leading: anchor to the subject, never restate the claim.
                text=f"I'd like your own account — what can you tell me about {subject}?",
                kind="corroborate",
                salience=c.confidence,
                anchor_id=c.claim_id,
            ))

        # deepen: subjects appearing in only one claim (under-explored).
        rows = self.con.execute(
            "SELECT subject_ref, count(*) FROM speak_claims "
            "WHERE project_id = ? AND subject_ref IS NOT NULL "
            "GROUP BY subject_ref HAVING count(*) = 1",
            [project_id],
        ).fetchall()
        for subject_ref, _ in rows:
            gaps.append(OpenQuestion(
                question_id=f"deepen-{subject_ref}",
                text=f"There's more to explore about {subject_ref} — what stands out to you?",
                kind="deepen",
                salience=0.5,
                anchor_id=subject_ref,
            ))

        # open_question: unanswered must-cover across the project.
        guide_row = self.con.execute(
            "SELECT interview_guide FROM interview_projects WHERE project_id = ?",
            [project_id],
        ).fetchone()
        if guide_row and guide_row[0]:
            import json
            try:
                guide = json.loads(guide_row[0])
            except (TypeError, ValueError):
                guide = {}
            for index, q in enumerate(guide.get("must_cover", [])):
                if isinstance(q, str):
                    q = {"id": f"legacy-{index}", "text": q}
                if not isinstance(q, dict):
                    continue
                question_node_id = q.get("question_node_id")
                if question_node_id:
                    resolved = self.con.execute(
                        "SELECT canonical_label FROM nodes "
                        "WHERE node_id = ? AND node_type = 'question'",
                        [question_node_id],
                    ).fetchone()
                    if resolved is None:
                        continue
                    q = {**q, "id": question_node_id, "text": resolved[0]}
                gaps.append(OpenQuestion(
                    question_id=f"mc-{q.get('id', '')}",
                    text=q.get("text", ""),
                    kind="open_question",
                    salience=0.6,
                    anchor_id=q.get("id"),
                ))

        gaps.sort(key=lambda g: g.salience, reverse=True)
        return gaps[:limit]


# ---------------------------------------------------------------------------
# The conditioning context (M1–M4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConditioningContext:
    """What the project already knows, distilled for the NEXT
    interviewee's questions — consent-filtered and budgeted."""

    accumulated_insights: list[str] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    corroboration_targets: list[OpenQuestion] = field(default_factory=list)
    deepening_targets: list[OpenQuestion] = field(default_factory=list)
    # How many other-interviewee claims were withheld to respect a
    # record-only source's consent scope. A maintainer can confirm the
    # privacy filter is doing work.
    withheld_for_privacy: int = 0


def _source_may_inform_others(con: Any, source_interview_id: str | None) -> bool:
    """A source's claim may inform ANOTHER interviewee only if the source
    granted ``attribute`` consent. Operator-authored claims (no source
    interview) are always shareable."""
    if source_interview_id is None:
        return True
    return has_consent(con, source_interview_id, ConsentScope.ATTRIBUTE)


def build_conditioning_context(
    con: Any,
    *,
    project_id: str,
    for_interview_id: str,
    gap_source: GapSource | None = None,
    max_items: int = 12,
) -> ConditioningContext:
    """Assemble the accumulated context to condition ``for_interview_id``'s
    questions on — what OTHER interviewees have contributed (M1), the
    open questions to chase (M2), single-sourced claims to probe (M3),
    and under-explored subjects to deepen (M4) — with the consent-scope
    privacy filter applied and the whole thing budgeted to ``max_items``.
    """
    if gap_source is not None:
        gaps_src = gap_source
    else:
        # DRW SPR-07 has landed: default to the composite source (DRW's
        # centrality-ranked shared-graph gaps for this project + Speak's
        # consent-aware project-local source). Lazy import avoids the
        # drw_gap_source ↔ interviewer_context cycle. With no Speak content
        # promoted to the shared graph yet, DRW contributes [] and this is
        # exactly SpeakGraphGapSource — unchanged behavior.
        from .drw_gap_source import default_gap_source
        gaps_src = default_gap_source(con)
    gaps = gaps_src.open_questions(project_id, limit=max_items * 3)

    # M1 — accumulated insights from OTHER interviewees, consent-filtered.
    insights: list[str] = []
    withheld = 0
    for c in project_claims(con, project_id):
        if c.interview_id == for_interview_id:
            continue  # cross-interviewee value is in OTHERS' contributions
        if not _source_may_inform_others(con, c.interview_id):
            withheld += 1  # PRIVACY: record-only source never leaks into B
            continue
        insights.append(c.text)
    insights = insights[:max_items]

    # M3 — corroboration targets, consent-filtered (don't leak the
    # record-only source whose claim we'd be probing) and not anchored to
    # the current interviewee's own claims.
    corroboration_targets: list[OpenQuestion] = []
    for g in (x for x in gaps if x.kind == "corroborate"):
        src = get_claim(con, g.anchor_id) if g.anchor_id else None
        if src is None:
            continue
        if src.interview_id == for_interview_id:
            continue
        if not _source_may_inform_others(con, src.interview_id):
            withheld += 1
            continue
        corroboration_targets.append(g)

    open_questions = [g for g in gaps if g.kind == "open_question"][:max_items]
    deepening_targets = [g for g in gaps if g.kind == "deepen"][:max_items]

    return ConditioningContext(
        accumulated_insights=insights,
        open_questions=open_questions,
        corroboration_targets=corroboration_targets[:max_items],
        deepening_targets=deepening_targets,
        withheld_for_privacy=withheld,
    )
