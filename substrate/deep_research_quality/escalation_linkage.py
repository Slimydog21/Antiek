"""Escalation linkage — did the recursive chase actually get scheduled?

Operator vision (ask #1): *"send subagents to chase questions as I interrogate,
assess, and wrestle with the information ... record the valuable data, insights,
and questions recursively that informs all prompts."* The canonical
``ResearchArtifactBody`` schema makes this first-class: each
``ArtifactQuestion`` carries ``escalated: bool`` (flagged for deeper chase) and
``reserved_child_investigation_id: str | None`` (the child investigation reserved
to chase it). Together they encode the RECURSION: a question is escalated → a
child investigation is reserved → it runs → its findings inform the parent.

But escalation without reservation is a LEAK: the question was flagged *"this
needs a deeper chase"* yet no child investigation was ever reserved to deliver
it. The recursion stalled at the flag. Nothing in the quality engine surfaces
this — ``plan_resolution`` (#1937) measures whether a PLAN's sub-questions were
answered (content resolution via graph edges); it does not measure whether
ESCALATED questions in an artifact were even assigned a chase (structural linkage
via reservation ids).

THIS module is that measurement — the recursive-chase accountability surface.

**Distinct from ``plan_resolution`` (#1937).** That module takes a PLAN
(``PlanQuestion`` graph node ids) + a resolved-set and asks *"were the plan's
questions answered?"* (CONTENT resolution). This module takes the artifact's
``open_questions`` (with ``escalated`` + ``reserved_child_investigation_id``) and
asks *"were the ESCALATED questions assigned a chase?"* (STRUCTURAL linkage).
Different input (open questions vs plan), different failure mode (unscheduled
chase vs unresolved question). Complementary: linkage finds the chases that never
started; resolution finds the chases that started but didn't finish.

**The two accountability surfaces.**
  * ``orphaned_escalation_ids`` — escalated questions with NO reservation (the
    leak: flagged but never scheduled). This is the primary surface: every entry
    is a question the operator/system wanted chased deeper that never was.
  * ``unescalated_reservation_ids`` — questions carrying a reservation but NOT
    escalated (an integrity oddity: a chase was reserved for a question never
    flagged as needing one). Surfaced for the operator, not penalized into the
    linkage ratio — it is a different kind of anomaly.

**Honesty rules (load-bearing):**
* An artifact with no ESCALATED questions has ``escalation_linkage = None``
  (never fabricated 0 or 1) — linkage of nothing is unknown, not measured. A
  question that was never escalated correctly has no reservation; that is the
  expected state, not a leak.
* ``escalation_linkage`` is ``linked_escalated / total_escalated`` — a ratio in
  ``[0.0, 1.0]``. An orphaned escalation is a leak regardless of whether the
  question was otherwise answered; this module never claims a chase succeeded
  (that is reservation resolution, out of pure scope — the reserved child's
  findings live in the graph/DB, not the artifact).
* ``reserved_child_investigation_id`` is carried through verbatim (never
  coerced); a whitespace-only reservation is treated as absent (an honest
  unknown, never a placeholder chase).
* Deterministic and pure: same artifact -> same report. No LLM, no network, no
  clock, no mutation, no DB reads. ``authority`` is always ``"advisory"``.
* Every escalated question is carried through (auditable): it is in
  ``linked_escalation_ids`` or ``orphaned_escalation_ids``, never lost.
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody


@dataclass(frozen=True)
class EscalationLinkageReport:
    """The artifact's recursive-chase accountability surface. Advisory, pure."""

    artifact_id: str  # the artifact's investigation_id (traceability)
    question_count: int
    escalated_count: int  # questions with escalated=True
    linked_count: int  # escalated AND reservation present
    orphaned_count: int  # escalated AND reservation absent (the leak)
    escalation_linkage: float | None  # linked/escalated in [0,1]; None if no escalated
    linked_escalation_ids: tuple[str, ...]  # sorted node_ids
    orphaned_escalation_ids: tuple[str, ...]  # the primary accountability surface, sorted
    unescalated_reservation_ids: tuple[str, ...]  # reservation-but-not-escalated, sorted
    notes: tuple[str, ...]
    authority: str = "advisory"


def _has_reservation(value: object) -> bool:
    """A question has a reservation iff reserved_child_investigation_id is a
    non-empty string (whitespace-only is an honest absent, never a placeholder)."""
    if not isinstance(value, str):
        return False
    return bool(value.strip())


def measure_escalation_linkage(
    artifact: ResearchArtifactBody,
) -> EscalationLinkageReport:
    """Measure whether an artifact's escalated questions carry chase reservations.

    ``artifact`` is the canonical knowledge-asset body. Returns an
    :class:`EscalationLinkageReport` with the linkage ratio, the orphaned-
    escalation surface, and the unescalated-reservation oddities.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    questions = artifact.open_questions

    linked_ids: list[str] = []
    orphaned_ids: list[str] = []
    unescalated_reservation_ids: list[str] = []
    escalated = 0

    for q in questions:
        reserved = _has_reservation(q.reserved_child_investigation_id)
        if q.escalated:
            escalated += 1
            if reserved:
                linked_ids.append(q.node_id)
            else:
                orphaned_ids.append(q.node_id)
        elif reserved:
            # reservation present but the question was NOT escalated — oddity.
            unescalated_reservation_ids.append(q.node_id)

    linked_ids.sort()
    orphaned_ids.sort()
    unescalated_reservation_ids.sort()

    linkage: float | None = (len(linked_ids) / escalated) if escalated else None

    notes: list[str] = [
        "escalation linkage is a STRUCTURAL check (did an escalated question get "
        "a reserved child investigation); it composes with plan_resolution (#1937, "
        "which measures whether a plan's questions were answered) — linkage finds "
        "chases that never started, resolution finds chases that didn't finish",
        "a reserved child investigation's actual findings live in the graph/DB, "
        "not the artifact, so this module never claims a chase succeeded (that is "
        "reservation resolution, out of pure scope)",
    ]
    if escalated == 0:
        notes.append(
            "no escalated questions; escalation linkage is not measurable "
            "(a non-escalated question correctly has no reservation)"
        )
    else:
        notes.append(
            f"escalation linkage {linkage:.0%}: {len(linked_ids)} linked, "
            f"{len(orphaned_ids)} orphaned of {escalated} escalated question(s)"
        )
    if orphaned_ids:
        notes.append(
            f"LEAK: {len(orphaned_ids)} escalated question(s) carry no reserved "
            "child investigation (flagged for a deeper chase that was never "
            "scheduled)"
        )
    if unescalated_reservation_ids:
        notes.append(
            f"INTEGRITY ODDITY: {len(unescalated_reservation_ids)} question(s) "
            "carry a reservation but were not escalated (a chase reserved for a "
            "question never flagged as needing one)"
        )

    return EscalationLinkageReport(
        artifact_id=artifact.investigation_id,
        question_count=len(questions),
        escalated_count=escalated,
        linked_count=len(linked_ids),
        orphaned_count=len(orphaned_ids),
        escalation_linkage=linkage,
        linked_escalation_ids=tuple(linked_ids),
        orphaned_escalation_ids=tuple(orphaned_ids),
        unescalated_reservation_ids=tuple(unescalated_reservation_ids),
        notes=tuple(notes),
    )


__all__ = [
    "EscalationLinkageReport",
    "measure_escalation_linkage",
]
