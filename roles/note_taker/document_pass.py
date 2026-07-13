"""DRW SPR-03 M1 — the always-on document note pass.

Given a document, asynchronously distil insights + questions and promote
them to graph nodes (SPR-01), off the document's critical path. Every
promoted insight carries provenance — the source document and (when known)
its chunks — so there are no provenance-free notes in the graph. Idempotent
by SPR-01's content-hash dedup: re-running on an unchanged document
promotes zero new nodes.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

try:
    from ...event_log import emit_typed
    from ...graph.insight_question import promote_insight, promote_question
    from ...schemas.events import NoteEmergedPayload, QuestionIdentifiedPayload
    from .distill import Distillation, Distiller
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles.note_taker.distill import Distillation, Distiller  # type: ignore[no-redef]
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.graph.insight_question import (  # type: ignore[no-redef]
        promote_insight,
        promote_question,
    )
    from substrate.schemas.events import (  # type: ignore[no-redef]
        NoteEmergedPayload,
        QuestionIdentifiedPayload,
    )


@dataclass
class PassResult:
    insight_node_ids: list[str] = field(default_factory=list)
    question_node_ids: list[str] = field(default_factory=list)
    dropped_provenance_free: int = 0

    @property
    def promoted(self) -> int:
        return len(self.insight_node_ids) + len(self.question_node_ids)


async def run_document_pass(
    document_id: str,
    text: str,
    *,
    investigation_id: str,
    distiller: Distiller,
    chunk_ids: Sequence[str] = (),
    supported_by: Sequence[str] = (),
    source_event_ids: Sequence[str] = (),
    identity_scope: str | None = None,
    owner_user_id: str | None = None,
    emit_graph_events: bool = True,
    embedding_provider: Any = None,
    emit_events: bool = True,
    events_dir: str | None = None,
    con: Any = None,
) -> PassResult:
    """Distil + promote a document's insights/questions. A coroutine so the
    caller can schedule it off the ingest critical path (document
    availability never waits on note extraction). The blocking distillation
    runs in a worker thread."""
    distillation: Distillation = await asyncio.to_thread(
        distiller.distill, text, source_event_ids=source_event_ids
    )
    result = PassResult()
    primary_chunk = chunk_ids[0] if chunk_ids else None

    for note in distillation.insights:
        # Provenance guard (rigor #1): the parser already drops notes with no
        # source_event_ids; we additionally anchor document-level provenance.
        # A note that somehow reaches here with neither attribution nor a
        # document is dropped, never promoted.
        if source_event_ids and set(note.source_event_ids) != set(source_event_ids):
            result.dropped_provenance_free += 1
            continue
        if not note.source_event_ids and not document_id:
            result.dropped_provenance_free += 1
            continue
        if emit_events:
            emit_typed(
                investigation_id,
                NoteEmergedPayload(
                    note_id=note.note_id, note_text=note.text,
                    source_event_ids=list(note.source_event_ids),
                    confidence=note.confidence,
                ),
                role="note_taker", document_id=document_id, events_dir=events_dir,
            )
        nid = promote_insight(
            text=note.text, investigation_id=investigation_id,
            confidence=note.confidence, supported_by=supported_by,
            source_document_id=document_id, chunk_id=primary_chunk,
            metadata={"source_chunk_ids": list(chunk_ids),
                      "source_event_ids": list(note.source_event_ids),
                      "origin_note_id": note.note_id},
            embedding_provider=embedding_provider, con=con,
            identity_scope=identity_scope,
            owner_user_id=owner_user_id,
            emit_graph_events=emit_graph_events,
        )
        result.insight_node_ids.append(nid)

    for q in distillation.questions:
        if emit_events:
            emit_typed(
                investigation_id,
                QuestionIdentifiedPayload(
                    question_id="q-" + uuid.uuid4().hex[:12],
                    question_text=q.text, anchor_region_id=q.anchor_region_id,
                ),
                role="note_taker", document_id=document_id, events_dir=events_dir,
            )
        qid = promote_question(
            text=q.text, investigation_id=investigation_id,
            asks_about=q.asks_about, anchor_region_id=q.anchor_region_id,
            source_document_id=document_id, chunk_id=primary_chunk,
            metadata={
                "source_document_id": document_id,
                "source_event_ids": list(source_event_ids),
            },
            embedding_provider=embedding_provider, con=con,
            identity_scope=identity_scope,
            owner_user_id=owner_user_id,
            emit_graph_events=emit_graph_events,
        )
        result.question_node_ids.append(qid)

    return result
