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
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import (
        best_supporting_chunk,
        graph_db_path,
        promote_insight,
        promote_question,
    )

    from .protocol import StepEvent
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write
    from runtime.research_runner.protocol import StepEvent
    from substrate.graph.insight_question import (
        best_supporting_chunk,
        graph_db_path,
        promote_insight,
        promote_question,
    )


_FUNNEL_DONE = object()


# The ``StepEvent.data`` keys the funnel carries into node metadata. An
# allowlist, because the producer controls ``data`` entirely (a remote
# sandbox's event data is forwarded verbatim), and spreading the whole dict let
# it assert the provenance and trust the substrate reads back:
# ``groundedness_score`` (preferred over scoring by ``knowledge_unit_of`` and
# the SPR-08 reuse gate), ``source_kind`` (the §9 user/model discriminator),
# ``source``, ``identity_scope``, ``source_document_id`` and ``chunk_id``. The
# set is the in-tree host loops' note keys plus the Prime mapper's host-built
# telemetry, all descriptive; ``document_id`` is the one grounding input.
_CARRIED_NOTE_KEYS = frozenset({
    "document_id",
    "gather_mode", "backend", "workspace_id", "contained_passes", "ran_as_uid",
    "artifact_records", "discovery_id", "promotion_decision",
    "prime_event_type", "input_tokens", "output_tokens", "inference_provider",
    "finish_reason",
})


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

    Only ``_CARRIED_NOTE_KEYS`` (e.g. ``gather_mode``) are preserved; any
    other key is dropped, so the producer can never set ``source``,
    ``source_kind``, ``groundedness_score`` or the grounding chunk (``_promote``
    resolves that host-side from ``document_id``). For an honest note the
    result is unchanged, so ``content_hash`` for already-doc-url paths is too.
    """
    meta: dict[str, Any] = {"source": "research_runner"}
    meta.update((k, v) for k, v in ev.data.items() if k in _CARRIED_NOTE_KEYS)
    doc_id = meta.get("document_id")
    if isinstance(doc_id, str) and doc_id:
        meta["source_document_id"] = doc_id
    else:
        meta.pop("document_id", None)
    return meta



def _resolve_chunk_id(
    con: Any, document_id: str | None, note: str = "",
) -> str | None:
    """Resolve the non-boilerplate ``chunk_id`` of a document that best
    supports ``note`` (ties go to the longest chunk).

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

    Among those substantive chunks the note cites the one that supports it
    best on its own (``best_supporting_chunk``, the same choice the note-event
    and document-pass deposits make), not simply the longest: the longest
    chunk may say something else entirely, and the evidence pack only presents
    a note its cited chunk supports. Candidates are ordered longest first, so
    a note no chunk supports (an Exa source pointer) keeps the old choice.

    Read-only (a SELECT on the write connection, before the INSERT); it never
    creates a row on read (§16). Returns ``None`` when the document has no
    qualifying chunk (e.g. a placeholder gather doc) — promotion still
    proceeds, just without chunk-level grounding, preserving prior behaviour
    for un-groundable notes."""
    if not document_id:
        return None
    rows = con.execute(
        """SELECT chunk_id, text FROM chunks
           WHERE document_id = ?
             AND length(text) BETWEEN 400 AND 4000
             AND text NOT ILIKE '%bibliography%'
             AND text NOT ILIKE '%references%'
             AND text NOT ILIKE '%index%'
             AND text NOT ILIKE '## Page%'
             AND text NOT ILIKE 'chapter %'
             AND text NOT ILIKE 'contents%'
           ORDER BY length(text) DESC, chunk_id""",
        [document_id],
    ).fetchall()
    candidates = {str(cid): str(text) for cid, text in rows if cid is not None}
    if not candidates:
        return None
    chunk_id, _score = best_supporting_chunk(note, candidates)
    return chunk_id


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
                # The chunk is the substantive chunk of the source document
                # that best supports the note, resolved host-side (read-only
                # SELECT, §16-safe) and never taken from the producer, which
                # could name a chunk of another document. Stays None for
                # un-groundable notes, preserving prior behaviour.
                chunk_id = _resolve_chunk_id(con, source_document_id, ev.text)
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
