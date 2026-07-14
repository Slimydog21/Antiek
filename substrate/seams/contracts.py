"""Typed cross-workflow seam handoffs (antiek-unified SPR-03).

A *seam* is the place where two of the four workflows — Research (DRW), Read,
Write, Speak — touch. The flywheel is a cycle of these touches: research a
question, read the corpus, write the book, speak it into being, serve it back.
For that to be one product rather than four apps, every touch has to be an
explicit, typed, one-direction handoff that carries **the same graph entity**
(by id + a provenance reference) — never a denormalized copy of its content.
A copied entity is a provenance bug: it forks the moat the instant it is made,
because the two halves of the flywheel then drift independently.

So each contract here carries:

* an **entity reference** — a stable node / claim / document id, the thing
  that already lives in the substrate. The receiving workflow resolves the id
  against the one graph; it does not receive (or store) a second copy of the
  entity's content. The SPR-07 no-copy guard exercises exactly this.
* a **provenance reference** — the originating event / region / source id, so
  the handoff itself is reconstructable from the trajectory.
* the **direction** — pinned, one-way. A seam fires from one workflow to one
  workflow; it does not define the reverse. (read↔research is two distinct
  seams: read→research to launch, research→read to surface results.)
* a **terminating-handoff marker** — ``terminates: Literal[True]``. There is
  no field on any seam that names or schedules a successor handoff. The
  flywheel advances only when a human or an explicit trigger fires the next
  seam; a seam that auto-chained its successor would be a runaway-cost bug
  (the "no auto-loop" rule — research→read→research must never auto-recurse).

These build *on* the SPR-01 substrate contracts; they do not redefine them. A
read→write seam carries the *id* of an :class:`InsightNodeContract` node and
hands it to a :class:`OutlineBlockContract` (``provenance_kind='graph_node'``,
same ``node_id``). The seam owns the handoff shape; each product spec
implements its own side against the SPR-01 contract the seam names.

Seven committed seams:

* ``ResearchToReadSeam``  research → read   (surface a researched insight)
* ``ReadToResearchSeam``  read → research   (research a highlighted passage)
* ``ReadToWriteSeam``     read → write      (drag an insight into an outline)
* ``WriteToReadSeam``     write → read      (trace a block to its source)
* ``SpeakToWriteSeam``    speak → write     (author a bio from interview claims)
* ``SpeakToReadSeam``     speak → read      (serve a published bio)
* ``WriteToSpeakSeam``    write → speak     (commission interviews from a
  node-backed outline question)

The seam *events* are typed in ``substrate/schemas/events.py`` (the
``seam.*`` action types) and emitted through ``substrate/event_log`` →
``runtime/db_lock`` like every other substrate write; no seam writes the graph
directly off the critical path.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# The four workflow identifiers. Stated inline (not imported) so the seam
# package has zero dependency on any product's internals — a seam names a
# workflow, it does not import it.
Workflow = Literal["research", "read", "write", "speak"]

# The kinds of entity a seam can carry by reference. Each resolves to a row
# the substrate already owns; the seam never inlines the entity's content.
#
# * ``insight_node`` / ``question_node`` — a DRW graph node (content-addressed
#   id, stable across re-emission; ``InsightNodeContract`` / ``QuestionNodeContract``).
# * ``outline_block``                    — a Write composition unit
#   (``OutlineBlockContract``).
# * ``document_region``                  — a (document_id, region_id) anchor in
#   the reading surface (``DocumentRegionSelected``).
# * ``servable_entry``                   — a Read servable-corpus document
#   (``ServableEntryContract``).
# * ``speak_claim``                      — an interview-attested claim in
#   ``speak_claims`` (NOT a graph node — promoting it to one is operator-gated
#   G2/G3, so the speak→write seam carries the claim_id, not a node_id).
EntityKind = Literal[
    "insight_node",
    "question_node",
    "outline_block",
    "document_region",
    "servable_entry",
    "speak_claim",
]

# A seam is COMMITTED (both sides have a real implementing sprint and the
# handoff shape is pinned) or PROVISIONAL (the handoff is the weakest / least
# specced; defined but flagged, and off the SPR-08 critical path).
SeamStatus = Literal["committed", "provisional"]


class _SeamBase(BaseModel):
    """The shared shape of every cross-workflow handoff.

    The four load-bearing fields are the same for every seam: who hands to
    whom, *which* entity (by id + kind), and the provenance reference that
    makes the handoff auditable. The ``terminates`` marker is fixed ``True``
    on every seam — it is the structural proof that no handoff carries a
    successor (the no-auto-loop invariant lives in the *absence* of a
    next-handoff field, and this marker documents that absence is deliberate)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Pinned, one-way direction. A subclass fixes both ends with Literals.
    from_workflow: Workflow
    to_workflow: Workflow

    # The entity the seam carries — BY REFERENCE. ``entity_id`` is the id of a
    # row the substrate already owns; ``entity_kind`` says how to resolve it.
    # The receiving side reads the same row; it does not get a copy.
    entity_id: str
    entity_kind: EntityKind

    # The originating provenance reference (an event_id, region_id, or source
    # id) so the handoff is reconstructable from the trajectory. Never the
    # entity's content — the content lives on the referenced entity.
    provenance_ref: str

    # Terminating-handoff marker. Fixed True: a seam is a single, terminating
    # event. There is deliberately NO ``next_seam`` / ``successor`` /
    # ``auto_fire`` field — the flywheel advances only on an explicit trigger.
    terminates: Literal[True] = True


# ---------------------------------------------------------------------------
# The seven committed seams
# ---------------------------------------------------------------------------


class ResearchToReadSeam(_SeamBase):
    """research → read. A researched insight surfaces in the reading corpus.

    The Research workflow promotes an insight (``InsightNodeContract``); Read
    surfaces *that node* in its living-note / corpus view. Read resolves
    ``entity_id`` (the insight ``node_id``) against the one graph — the insight
    a reader sees is the same node Research created, not a copy. Implemented
    by: DRW SPR-01 (the node) + Read's corpus/living-note surface."""

    from_workflow: Literal["research"] = "research"
    to_workflow: Literal["read"] = "read"
    entity_kind: Literal["insight_node"] = "insight_node"


class ReadToResearchSeam(_SeamBase):
    """read → research. A highlighted passage spins a focused investigation.

    Implemented by **Read SPR-08** (research-from-passage): a selected document
    region pre-seeds DRW SPR-05's cascade planner; the completed research links
    back to the originating passage (two-way provenance). The seam carries the
    ``document_region`` reference (a ``DocumentRegionSelected`` anchor), NOT the
    region's full text — and for a gated book the seed downstream is restricted
    to metadata/snippet (Read SPR-08 acceptance criterion). ``investigation_id``
    is the launched session, set by the receiving (research) side."""

    from_workflow: Literal["read"] = "read"
    to_workflow: Literal["research"] = "research"
    entity_kind: Literal["document_region"] = "document_region"
    # The document the region belongs to (the region anchor needs its doc).
    document_id: str
    # Set by the RECEIVING side once a research session is launched. None at
    # hand-off time. This is a result pointer, NOT a successor-handoff field —
    # it names the investigation this seam launched, it does not auto-fire a
    # follow-on seam.
    launched_investigation_id: str | None = None


class ReadToWriteSeam(_SeamBase):
    """read → write. An insight is dragged from research/reading into an outline.

    The cleanest no-copy case: the insight (``InsightNodeContract``,
    ``entity_kind='insight_node'``) becomes a node-backed
    :class:`OutlineBlockContract` (``provenance_kind='graph_node'``) whose
    ``node_id`` is *the same id* the seam carried. The block references the
    node; it does not inline the insight's text (an inlined copy would be the
    fabricated-citation bug ``OutlineBlockContract`` already forbids).
    Implemented by: Write SPR-03 (block repository — dragging nodes into
    folders/outlines). ``target_section_id`` is where the block lands."""

    from_workflow: Literal["read"] = "read"
    to_workflow: Literal["write"] = "write"
    entity_kind: Literal["insight_node"] = "insight_node"
    # Which outline section the node-backed block is placed into.
    target_section_id: str


class WriteToReadSeam(_SeamBase):
    """write → read. Trace a block (or generated sentence) to its source.

    Implemented by **Write SPR-07** (trace-to-source): from a block whose
    provenance is ``graph_node``, resolve node → document → chunks and open the
    source in the **shared reading surface** (DRW SPR-10) at the cited span,
    with highlights + rabbit holes. The seam carries the ``outline_block``
    reference; Write SPR-07 resolves it and MUST respect Read's servability gate
    (a gated-book span shows metadata/snippet only — Write SPR-07 acceptance
    criterion). ``source_document_id`` / ``source_region_id`` are the resolved
    destination in document space (resolved by the receiving side)."""

    from_workflow: Literal["write"] = "write"
    to_workflow: Literal["read"] = "read"
    entity_kind: Literal["outline_block"] = "outline_block"
    # The resolved source the trace lands on (None until provenance resolves).
    source_document_id: str | None = None
    source_region_id: str | None = None


class SpeakToWriteSeam(_SeamBase):
    """speak → write. Author a biography from interview-attested claims.

    Implemented by **Speak SPR-08** (biography authoring, reusing Write). An
    important honesty nuance, verified against ``substrate/speak/write_composer.py``:
    a Speak biography unit is an interview-attested *claim* in ``speak_claims``,
    NOT a graph node. Promoting it to a shared graph node carries G2/G3-class
    consent weight Speak keeps operator-gated, so the seam carries the
    ``speak_claim`` id (``entity_kind='speak_claim'``) and the receiving Write
    side maps it to a ``synthesized`` :class:`OutlineBlockContract` (node_id
    null; the claim_id rides as the block's ``source_block_id`` provenance
    link). The handoff still moves one entity of record (the claim) by
    reference; it does not copy the claim into a new node. ``contributor_interview_ids``
    rides for the SPR-06 split provenance."""

    from_workflow: Literal["speak"] = "speak"
    to_workflow: Literal["write"] = "write"
    entity_kind: Literal["speak_claim"] = "speak_claim"
    # The interviews whose contributors earn a share when this claim is
    # published (SPR-06 split provenance). Ids only — references, not copies.
    contributor_interview_ids: tuple[str, ...] = ()


class SpeakToReadSeam(_SeamBase):
    """speak → read. A published biography is served back in the corpus.

    Implemented by **Speak SPR-09** (publishing, reusing Read's servable
    corpus). A public biography registers as a ``platform_authored``
    :class:`ServableEntryContract` with ``provenance_class='speak_derived'`` —
    which is exactly the condition that routes it through the seam-#4 publish
    gate before Read serves full text. The seam carries the ``servable_entry``
    (document) reference. ``publish_gate_passed`` records the gate outcome that
    the producing (Speak) side computed; Read consults it (it does not recompute
    Speak's gate, keeping Read uncoupled from Speak internals — seam #4)."""

    from_workflow: Literal["speak"] = "speak"
    to_workflow: Literal["read"] = "read"
    entity_kind: Literal["servable_entry"] = "servable_entry"
    # The Speak publish gate's outcome for this document, computed by the
    # producing side. Read serves full text only when this is True (and the
    # entry is speak_derived). See ``substrate/seams/servability_gate.py``.
    publish_gate_passed: bool = False


class WriteToSpeakSeam(_SeamBase):
    """write → speak. Commission interviews from a node-backed outline gap.

    The Write side accepts only an ``open_question`` block backed by an existing
    question node. The Speak side stores that node id in its interview guide and
    resolves the question when an interview is resumed. No question text is
    copied into the commission record."""

    from_workflow: Literal["write"] = "write"
    to_workflow: Literal["speak"] = "speak"
    entity_kind: Literal["question_node"] = "question_node"
    outline_section_id: str | None = None


COMMITTED_SEAMS: tuple[type[_SeamBase], ...] = (
    ResearchToReadSeam,
    ReadToResearchSeam,
    ReadToWriteSeam,
    WriteToReadSeam,
    SpeakToWriteSeam,
    SpeakToReadSeam,
    WriteToSpeakSeam,
)

PROVISIONAL_SEAMS: tuple[type[_SeamBase], ...] = ()

ALL_SEAMS: tuple[type[_SeamBase], ...] = COMMITTED_SEAMS + PROVISIONAL_SEAMS


def seam_status(seam: type[_SeamBase]) -> SeamStatus:
    """Whether a seam type is committed or provisional. The single source of
    truth a consumer (and the SPR-08 conformance harness) reads to decide
    whether a seam is load-bearing."""
    return "provisional" if seam in PROVISIONAL_SEAMS else "committed"
