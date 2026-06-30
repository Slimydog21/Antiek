"""DRW SPR-02 + RDR SPR-07 — the serialized graph-promotion funnel.

The single point at which parallel research output reaches the graph. N
browse loops emit ``note`` / ``question`` ``StepEvent``s concurrently; this
funnel drains them through **one** worker and promotes each via SPR-01's
``promote_insight`` / ``promote_question`` under ``runtime/db_lock``.
Because exactly one promotion is ever in flight, the single-writer lock is
never contended — 20 researches completing near-simultaneously produce
zero ``WriteLockTimeout``s, which is the whole point of funnelling rather
than letting each loop write the graph itself.

RDR SPR-07 extends the note path: each source-bearing insight triggers
``ingest_url`` (web) or corpus resolution (local), URL+hash dedup via
``substrate/graph/ops``, and ``supported_by`` provenance edges. Findings
accumulate in ``provenance_state`` for the cascade synthesis artifact (M3).

The blocking ``db_lock`` acquisition runs in a worker thread
(``asyncio.to_thread``) so a promotion never blocks the event loop the
browse loops run on; the funnel still serializes (it awaits each promotion
before taking the next), so only one thread ever holds the lock.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Callable

try:
    from ...graph.insight_question import (
        graph_db_path,
        promote_question,
    )
    from ...runtime.db_lock import connect_write
    from .provenance_ingest import (
        PromotionProvenanceState,
        promote_note_with_provenance,
        resolve_sources_for_note,
    )
    from .protocol import StepEvent
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from runtime.research_runner.provenance_ingest import (  # type: ignore[no-redef]
        PromotionProvenanceState,
        promote_note_with_provenance,
        resolve_sources_for_note,
    )
    from runtime.research_runner.protocol import StepEvent  # type: ignore[no-redef]
    from substrate.graph.insight_question import (  # type: ignore[no-redef]
        graph_db_path,
        promote_question,
    )


_FUNNEL_DONE = object()


class PromotionFunnel:
    """Serialized drain of research notes/questions into graph nodes."""

    def __init__(
        self,
        *,
        db_path: str | None = None,
        embedding_provider: Any = None,
        url_fetcher: Callable[[str], Any] | None = None,
    ):
        self._db_path = db_path or graph_db_path()
        self._embedding_provider = embedding_provider
        self._url_fetcher = url_fetcher
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self.promoted_insights = 0
        self.promoted_questions = 0
        self.errors: list[str] = []
        self.promoted_node_ids: list[str] = []
        self.provenance_state = PromotionProvenanceState()
        self.artifact_document_id: str | None = None

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
        pre_resolved = None
        if ev.kind == "note":
            pre_resolved = resolve_sources_for_note(
                ev,
                db_path=self._db_path,
                embedding_provider=self._embedding_provider,
                url_fetcher=self._url_fetcher,
            )
        con = connect_write(self._db_path, purpose="promotion_funnel")
        try:
            con.execute("BEGIN")
            try:
                if ev.kind == "note":
                    nid = promote_note_with_provenance(
                        ev,
                        con=con,
                        embedding_provider=self._embedding_provider,
                        url_fetcher=self._url_fetcher,
                        state=self.provenance_state,
                        db_path=self._db_path,
                        resolved_sources=pre_resolved,
                    )
                    self.promoted_insights += 1
                    self.promoted_node_ids.append(nid)
                elif ev.kind == "question":
                    nid = promote_question(
                        text=ev.text, investigation_id=ev.investigation_id,
                        metadata={"source": "research_runner", **ev.data},
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