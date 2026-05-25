"""Speak — typed seams for cross-spec dependencies.

Speak reuses three sibling workflows (per the master spec's "reuse,
don't fork" invariant). Their build status, verified against the live
codebase 2026-05-25:

  • Read   — servable corpus / ``platform_authored`` → **EXISTS** as
             ``substrate.books.servability`` (``ServabilityStatus``,
             ``servability_of``, ``is_servable_full_text``). SPR-09
             builds against it directly; no seam needed here.
  • Write  — ``OutlineBlock`` composition → the EVENT vocabulary
             exists (``outline_block.*``) and the SUBSTRATE exists
             (``deliverables`` / ``deliverable_sections`` /
             ``section_blocks`` tables + the ``creative_writer`` role),
             but ``substrate/write/`` is not yet a module. We define an
             ``OutlineComposer`` Protocol so SPR-08 builds against a
             contract; the default adapter writes ``section_blocks``
             directly until Write ships its composer.
  • DRW    — structural gap detection (``substrate/gap_detection/``,
             "DRW SPR-07") → **ABSENT**. We define a ``GapSource``
             Protocol so SPR-04's open-question chasing builds against
             a contract; the default reads open questions + single-
             sourced claims from the Speak graph itself.

Defining these as Protocols (not imports of not-yet-existing modules)
is the honest move: Speak does not pretend a dependency is built, and
when the real Write/DRW modules land they satisfy the Protocol with no
change to Speak's call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# DRW SPR-07 — structural gap detection (ABSENT; Protocol + default)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenQuestion:
    """One structural gap in a project's knowledge: an unanswered
    question, an under-explored high-value node, or a single-sourced
    claim that wants corroboration. Drives the compounding interviewer
    (SPR-04)."""

    question_id: str
    text: str
    kind: str  # "open_question" | "deepen" | "corroborate"
    # Centrality / importance in [0, 1]; higher = chase sooner.
    salience: float = 0.5
    # The node/claim this gap hangs off, for provenance.
    anchor_id: Optional[str] = None


@runtime_checkable
class GapSource(Protocol):
    """Surfaces the open questions / gaps a project should chase next.

    DRW SPR-07 (``substrate/gap_detection/``) will be the real
    implementation, ranking gaps over the whole shared graph. Until it
    lands, SPR-04 uses ``SpeakGraphGapSource`` (reads the Speak project
    graph). Either satisfies this contract."""

    def open_questions(self, project_id: str, *, limit: int = 20) -> list[OpenQuestion]:
        ...


# ---------------------------------------------------------------------------
# Write SPR-01/06 — outline composition (substrate exists, module doesn't)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlineBlock:
    """One block in a biography outline — the unit Write's OutlineBlock
    model composes and ``creative_writer`` consumes. Mirrors the
    existing ``section_blocks`` row shape (block_kind ∈ insight /
    open_question / operator_note / claim) plus the contributor
    provenance Speak needs for the SPR-06 split."""

    block_id: str
    block_kind: str  # 'insight' | 'open_question' | 'operator_note' | 'claim'
    label: str
    body: str
    # Interviewees whose contributions this block draws on — consumed by
    # SPR-06 to attribute the contribution split. Empty for operator notes.
    contributor_interview_ids: tuple[str, ...] = ()
    source_tier: Optional[int] = None


@runtime_checkable
class OutlineComposer(Protocol):
    """Assembles + persists an ordered outline of blocks under a
    deliverable section. Write's composer is the eventual owner; the
    SPR-08 default writes ``section_blocks`` directly."""

    def compose(
        self,
        *,
        deliverable_id: str,
        section_title: str,
        blocks: list[OutlineBlock],
    ) -> str:  # returns section_id
        ...
