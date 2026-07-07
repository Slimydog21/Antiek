"""DRW SPR-02 — the serialized graph-promotion funnel.

The single point at which parallel research output reaches the graph. N
browse loops emit ``note`` / ``question`` ``StepEvent``s concurrently; this
funnel drains them through **one** worker and promotes each via SPR-01's
``promote_insight`` / ``promote_question`` under ``runtime/db_lock``.
Because exactly one promotion is ever in flight, the single-writer lock is
never contended — 20 researches completing near-simultaneously produce
zero ``WriteLockTimeout``s, which is the whole point of funnelling rather
than letting each loop write the graph itself.

The blocking ``db_lock`` acquisition runs in a worker thread
(``asyncio.to_thread``) so a promotion never blocks the event loop the
browse loops run on; the funnel still serializes (it awaits each promotion
before taking the next), so only one thread ever holds the lock.

Wiring: SPR-01's promotion functions exist, so this funnel calls them
directly. If they had not landed, the ``_promote_*`` hooks would be the
single place to stub.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

try:
    from ...graph.insight_question import (
        graph_db_path,
        promote_insight,
        promote_question,
    )
    from ...runtime.db_lock import connect_write
    from .protocol import StepEvent
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from runtime.research_runner.protocol import StepEvent  # type: ignore[no-redef]
    from substrate.graph.insight_question import (  # type: ignore[no-redef]
        graph_db_path,
        promote_insight,
        promote_question,
    )


_FUNNEL_DONE = object()


def _promotion_metadata(ev: StepEvent) -> dict[str, Any]:
    """Map a StepEvent's ``data`` to the node metadata the graph stores.

    The single load-bearing transform: when a gather loop's note carries a
    real ``document_id`` (a ``doc-url-*`` id from ``promote_discovery`` →
    ``ingest_url``), surface it under the key the substrate + the evidence
    pack read for grounding — ``source_document_id``. Without this map the
    id would land under ``document_id`` in metadata, which
    ``session_evidence_pack`` does not consult, so the pack would fall back
    to the ``doc-gather-*`` placeholder and the chunk→document→ip_holder
    attribution chain would be broken for Exa-sourced evidence.

    Everything else in ``ev.data`` (e.g. ``gather_mode``) is preserved.
    The base ``source`` tag matches the funnel's prior behavior so
    ``content_hash`` for already-doc-url paths is unchanged.
    """
    meta: dict[str, Any] = {"source": "research_runner", **ev.data}
    doc_id = meta.get("document_id")
    if doc_id:
        meta["source_document_id"] = doc_id
    return meta



def _resolve_chunk_id(con: Any, document_id: str | None) -> str | None:
    """Resolve the most substantive non-boilerplate ``chunk_id`` for a document.

    The funnel's promote path grounds each promoted insight/question on a real
    chunk so ``knowledge_unit_of`` (the flywheel's reuse half) can recover its
    claim→chunk→doc grounding and the deposited unit becomes reusable. Without
    this, every funnel-promoted node lands with ``chunk_id=None`` (and no
    ``supported_by`` edge) — reuse finds candidates by similarity but
    ``knowledge_unit_of`` rejects them all, so the flywheel's reuse half is
    structurally starved (``knowledge_reuse_count`` stays 0 even though the
    event emits). This mirrors the proven
    ``tools.run_investigation._pick_substantive_chunk`` heuristic so the two
    deposit paths agree on what "grounded" means.

    Read-only (a SELECT on the write connection, before the INSERT); it never
    creates a row on read (§16). Returns ``None`` when the document has no
    qualifying chunk (e.g. a placeholder gather doc) — promotion still
    proceeds, just without chunk-level grounding, preserving prior behaviour
    for un-groundable notes."""
    if not document_id:
        return None
    row = con.execute(
        """SELECT chunk_id FROM chunks
           WHERE document_id = ?
             AND length(text) BETWEEN 400 AND 4000
             AND text NOT ILIKE '%bibliography%'
             AND text NOT ILIKE '%references%'
             AND text NOT ILIKE '%index%'
             AND text NOT ILIKE '## Page%'
             AND text NOT ILIKE 'chapter %'
             AND text NOT ILIKE 'contents%'
           ORDER BY length(text) DESC
           LIMIT 1""",
        [document_id],
    ).fetchone()
    if not row or row[0] is None:
        return None
    return str(row[0])


class PromotionFunnel:
    """Serialized drain of research notes/questions into graph nodes."""

    def __init__(self, *, db_path: str | None = None, embedding_provider: Any = None):
        self._db_path = db_path or graph_db_path()
        self._embedding_provider = embedding_provider
        # Items are StepEvents plus the _FUNNEL_DONE sentinel object.
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self.promoted_insights = 0
        self.promoted_questions = 0
        self.errors: list[str] = []
        self.promoted_node_ids: list[str] = []

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def submit(self, ev: StepEvent) -> None:
        """Hook the runner calls (``on_emit``) for each note/question."""
        await self._queue.put(ev)

    async def drain_and_stop(self) -> None:
        """Wait for every queued promotion to finish, then stop the worker.
        Call after the fan-out's researches have all completed."""
        await self._queue.join()
        await self._queue.put(_FUNNEL_DONE)
        if self._worker is not None:
            await self._worker
            self._worker = None

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is _FUNNEL_DONE:
                self._queue.task_done()
                return
            try:
                await asyncio.to_thread(self._promote, item)
            except Exception as exc:  # one bad promotion must not wedge the funnel
                self.errors.append(f"{item.investigation_id}: {type(exc).__name__}: {exc}")
            finally:
                self._queue.task_done()

    def _promote(self, ev: StepEvent) -> None:
        """Runs in a worker thread. One promotion = one lock acquisition;
        the single worker guarantees only one is ever in flight."""
        if not ev.text.strip():
            return
        meta = _promotion_metadata(ev)
        # Thread the real grounding document onto the node so the evidence
        # pack emits a doc-url-* chunk. ``promote_insight``/``promote_question``
        # stamp ``source_document_id`` into node metadata via setdefault — and
        # the key is already present in ``meta`` from the map above, so the two
        # paths agree (no double-write, content_hash stable).
        source_document_id = meta.get("source_document_id")
        con = connect_write(self._db_path, purpose="promotion_funnel")
        try:
            con.execute("BEGIN")
            try:
                # Ground the promoted node on a real chunk so the flywheel's
                # reuse half (knowledge_unit_of) can recover its
                # claim→chunk→doc grounding and the unit becomes reusable.
                # Prefer a chunk_id the producer already carried; otherwise
                # resolve the most substantive chunk of the source document
                # (read-only SELECT, §16-safe). Stays None for un-groundable
                # notes, preserving prior behaviour.
                chunk_id = meta.get("chunk_id")
                if chunk_id is None and source_document_id:
                    chunk_id = _resolve_chunk_id(con, source_document_id)
                if ev.kind == "note":
                    nid = promote_insight(
                        text=ev.text, investigation_id=ev.investigation_id,
                        source_document_id=source_document_id,
                        chunk_id=chunk_id,
                        metadata=meta,
                        embedding_provider=self._embedding_provider, con=con,
                    )
                    self.promoted_insights += 1
                    self.promoted_node_ids.append(nid)
                elif ev.kind == "question":
                    nid = promote_question(
                        text=ev.text, investigation_id=ev.investigation_id,
                        source_document_id=source_document_id,
                        chunk_id=chunk_id,
                        metadata=meta,
                        embedding_provider=self._embedding_provider, con=con,
                    )
                    self.promoted_questions += 1
                    self.promoted_node_ids.append(nid)
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        finally:
            con.close()
