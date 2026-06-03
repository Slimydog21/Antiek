"""Speak SPR-11 — the Biography TEMPLATE composition (NOT a fifth graph).

A biography is a **template** that composes the three EXISTING surfaces —
Research, Write, Speak — over the ONE substrate and the ONE insight/
question graph. It is deliberately **not a fifth product and not a fifth
graph** (master-spec §16). "Start a biography" provisions, over the same
substrate:

  • a RESEARCH folder — an ``investigation_id`` (the frontend's
    ``startInvestigation`` → ``POST /investigations`` → ``emit_typed``;
    an investigation is identified by its id in the shared event log, it
    is NOT a dedicated store row). This module takes that id as input;
  • a WRITE deliverable scaffold — ``insert_deliverable`` with
    ``investigation_root_id = investigation_id`` (the SPR-09 piece↔research
    link). The Write deliverable resolves to the SAME identity as the
    Research folder by construction;
  • a SPEAK interview project — the shipped ``project.create_project``
    (the ``interview_projects`` + ``speak_projects`` sidecar). UNCHANGED
    and reused as-is (SPR-03/10).

THE ONE REAL GAP (parent context): ``create_project`` takes no
investigation link. We close it WITHOUT a new store or a new column by
recording ONE ``speak.biography.composed`` event through the shared
funnel (``record_speak_event`` → ``log_event``), keyed on the
``investigation_id``, whose payload carries ``{investigation_id,
deliverable_id, project_id}``. That event — not a ``biography_*`` table —
IS the Speak↔investigation link. It lives in the same trajectory log as
the Research start event, so the whole biography (research + composition)
is one queryable stream under one identity.

Why a template over a fifth graph (the rejected alternative, rigor #2):
A dedicated biography graph — tuned for timelines, life-chapters, and
relationship structure, marketable on its own — is genuinely appealing,
and it would let biography-specific structure (a chronological spine, a
who-knew-whom graph) be a first-class schema rather than an emergent view.
It loses because a separate graph kills the cross-corpus value §16
protects: an interview captured for a biography would become a dead silo
instead of a reusable source for any research, and the shared insight/
question graph — the thing that compounds across all four surfaces — is
the moat. The one-graph guard test (``test_biography_creates_no_new_store``)
is the executable form of this decision; if the operator decides
biographies need a tuned standalone graph, that test is exactly where the
reversal surfaces.

Honesty (rigor #1): this provisions the three surfaces FOR REAL — a real
investigation id (created upstream), a real deliverable row linked to it,
and a real Speak project — plus the shared composition event. It does NOT
run the research, write the draft, or capture an interview; those are the
surfaces' own jobs (Research/Write/Speak), reused, not rebuilt here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.graph.ops import insert_deliverable

from .events import SPEAK_BIOGRAPHY_COMPOSED, record_speak_event
from .project import SpeakProject, create_project
from .schema import ensure_speak_schema

# The Write deliverable kind a biography scaffold uses. Reuses the kind the
# shipped Speak authoring orchestration (biography.py:120) already emits, so a
# composed biography's Write piece and an authored biography section are the
# same deliverable_kind — one Write notion of "a biography", not two.
BIOGRAPHY_DELIVERABLE_KIND = "biography_section"


@dataclass(frozen=True)
class BiographyComposition:
    """The three surface ids a biography template wires together, over the
    ONE graph. There is no ``biography_id`` — a biography is not its own
    entity; it is the COMPOSITION of these three, recorded as a shared
    event. The ``investigation_id`` is the shared identity the Write
    deliverable (via ``investigation_root_id``) and the composition event
    both point at."""

    investigation_id: str        # the Research folder (shared graph identity)
    deliverable_id: str          # the Write scaffold (investigation_root_id == investigation_id)
    project_id: str              # the Speak interview project
    composition_event_id: str | None  # the shared-funnel link event; None if events disabled


def create_biography(
    con: Any,
    *,
    investigation_id: str,
    subject_name: str,
    title: str | None = None,
    subject_status: str = "unknown",
    publish_intent: str = "private_never_published",
) -> BiographyComposition:
    """Compose a biography template over the three EXISTING surfaces.

    ``investigation_id`` is the Research folder — created upstream by
    ``startInvestigation`` (the one-graph identity everything threads on).
    This wires the Write deliverable and the Speak project to it and
    records the shared composition link event. It creates NO new store.

    The three surfaces resolve to one identity:
      • Write: ``deliverable.investigation_root_id == investigation_id``;
      • Speak: the ``speak.biography.composed`` event (keyed on
        ``investigation_id``) carries ``project_id``;
    so a reader of the shared trajectory + the deliverables table can
    follow Research → Write → Speak without a biography-specific table.
    """
    ensure_speak_schema(con)
    if not investigation_id:
        raise ValueError("create_biography requires an investigation_id (the Research folder)")

    bio_title = title or f"{subject_name}'s story"

    # SPEAK — the shipped project (SPR-03/10), reused as-is. This is the
    # interview project the invite-to-talk flow (M3) lands voices into.
    project: SpeakProject = create_project(
        con,
        title=bio_title,
        subject_ref=subject_name,
        subject_status=subject_status,
        publish_intent=publish_intent,
        topic_description=f"Biography of {subject_name}.",
    )

    # WRITE — the SPR-09 deliverable scaffold, linked to the SAME Research
    # folder via investigation_root_id. This is the link that makes the
    # Write piece resolve to the biography's one graph identity.
    deliverable_id = insert_deliverable(
        con,
        title=bio_title,
        deliverable_kind=BIOGRAPHY_DELIVERABLE_KIND,
        investigation_root_id=investigation_id,
    )

    # THE LINK — one shared-funnel event (NOT a store) recording the three
    # ids. Keyed on the investigation_id so it lands in the SAME trajectory
    # stream as the Research start event: one biography == one identity.
    event_id = record_speak_event(
        SPEAK_BIOGRAPHY_COMPOSED,
        {
            "investigation_id": investigation_id,
            "deliverable_id": deliverable_id,
            "project_id": project.project_id,
            "subject_ref": subject_name,
        },
        project_id=investigation_id,
    )

    return BiographyComposition(
        investigation_id=investigation_id,
        deliverable_id=deliverable_id,
        project_id=project.project_id,
        composition_event_id=event_id,
    )
