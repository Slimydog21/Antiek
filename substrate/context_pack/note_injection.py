"""DRW SPR-04 M3 + M4 — inject project notes into the context pack.

The assembler (``assembler.assemble_context_pack``) already accepts an
arbitrary list of ``LayerSource``s and renders them in canonical order, so
injecting the project's insights/questions needs **no change to the
assembler core** — it is one more layer. This module builds that layer
(retrieve → budget → render) and offers a flagged wrapper so the feature
can be measured on vs. off, returning coverage metadata alongside the pack.

The notes ride as a ``graph_evidence`` layer (an existing layer kind, so no
schema change) sourced ``project_notes``, with a priority just below
``session`` so the project's distilled state is preserved before generic
evidence/skills but never above the current task itself.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

try:
    from .assembler import (
        ContextPack, DefaultTokenCounter, LayerSource, TokenCounter,
        TruncationStrategy, assemble_context_pack, default_budget_for,
    )
    from .note_retrieval import RetrievedNote, retrieve_project_notes
    from .note_budget import NoteCoverage, render_note, select_within_budget
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))
    from context_pack.assembler import (  # type: ignore[no-redef]
        ContextPack, DefaultTokenCounter, LayerSource, TokenCounter,
        TruncationStrategy, assemble_context_pack, default_budget_for,
    )
    from context_pack.note_retrieval import RetrievedNote, retrieve_project_notes  # type: ignore[no-redef]
    from context_pack.note_budget import NoteCoverage, render_note, select_within_budget  # type: ignore[no-redef]


# The notes layer rides as graph_evidence (valid ContextLayer.kind, no schema
# change) but with this source tag so observers can identify it.
NOTES_LAYER_SOURCE = "project_notes"
# Priority sits between session (80) and generic graph_evidence (60): the
# project's distilled state is preserved before generic retrieved facts, but
# never above the role's current task.
NOTES_LAYER_PRIORITY = 70
# Fraction of the role's pack budget the notes section may claim, capped so a
# huge note set can never crowd out the task/evidence. Origin: notes are a
# supporting context, not the payload — a quarter of the window, ≤ 8k tokens.
NOTES_BUDGET_FRACTION = 0.25
NOTES_BUDGET_CAP_TOKENS = 8000

_NOTES_HEADER = (
    "The project's accumulated insights and open questions, most relevant first. "
    "Treat these as known context you do not need to re-derive.\n"
)


def notes_token_budget(role: str, pack_budget: Optional[int] = None) -> int:
    base = pack_budget if pack_budget is not None else default_budget_for(role)
    return min(NOTES_BUDGET_CAP_TOKENS, int(base * NOTES_BUDGET_FRACTION))


def build_project_notes_layer(
    con: Any,
    *,
    task_text: str,
    embedding_provider: Any,
    token_budget: int,
    counter: Optional[TokenCounter] = None,
    restrict_node_ids: Optional[Sequence[str]] = None,
) -> tuple[Optional[LayerSource], NoteCoverage]:
    """Retrieve + budget the project notes and render them as a LayerSource.
    Returns ``(layer_or_None, coverage)``; layer is None when there are no
    notes to inject (so the pack is unchanged)."""
    counter = counter or DefaultTokenCounter()
    notes = retrieve_project_notes(
        con, task_text=task_text, embedding_provider=embedding_provider,
        restrict_node_ids=restrict_node_ids,
    )
    if not notes:
        return None, NoteCoverage(relevant=0, included=0, truncated=0)
    selected, coverage = select_within_budget(
        notes, token_budget=token_budget, counter=counter, header_text=_NOTES_HEADER,
    )
    if not selected:
        return None, coverage
    body = _NOTES_HEADER + "\n".join(render_note(n) for n in selected)
    layer = LayerSource(
        kind="graph_evidence", source=NOTES_LAYER_SOURCE,
        content=body, priority=NOTES_LAYER_PRIORITY,
    )
    return layer, coverage


@dataclass(frozen=True)
class PackWithNotes:
    pack: ContextPack
    coverage: NoteCoverage
    notes_injected: bool


def assemble_context_pack_with_notes(
    *,
    role: str,
    investigation_id: str,
    layers: Iterable[LayerSource],
    con: Any,
    task_text: str,
    embedding_provider: Any,
    include_project_notes: bool = True,
    target_tokens: Optional[int] = None,
    truncation: TruncationStrategy = "smart",
    counter: Optional[TokenCounter] = None,
    parent_event_id: Optional[str] = None,
    restrict_node_ids: Optional[Sequence[str]] = None,
) -> PackWithNotes:
    """Assemble a context pack with the project's insights/questions injected.

    ``include_project_notes`` is the measurement flag: when False this is a
    plain ``assemble_context_pack`` (no notes layer), so the on/off effect is
    directly testable. Returns the pack plus coverage metadata for the UI."""
    layer_list = list(layers)
    coverage = NoteCoverage(relevant=0, included=0, truncated=0)
    injected = False
    if include_project_notes:
        budget = notes_token_budget(role, target_tokens)
        notes_layer, coverage = build_project_notes_layer(
            con, task_text=task_text, embedding_provider=embedding_provider,
            token_budget=budget, counter=counter, restrict_node_ids=restrict_node_ids,
        )
        if notes_layer is not None:
            layer_list.append(notes_layer)
            injected = True
    pack = assemble_context_pack(
        role=role, investigation_id=investigation_id, layers=layer_list,
        target_tokens=target_tokens, truncation=truncation, counter=counter,
        parent_event_id=parent_event_id,
    )
    return PackWithNotes(pack=pack, coverage=coverage, notes_injected=injected)
