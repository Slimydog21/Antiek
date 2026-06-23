"""DRW SPR-03 M5 + M7 — async scheduling, idempotency, backpressure.

The always-on pass makes LLM calls, so it cannot run inline on ingest and
cannot ignore the dispatch budget. This scheduler:

* **debounces + coalesces** re-submissions of the same document (latest
  job wins) so a document edited three times in a second is distilled
  once, not three times. The debounce interval defaults to 2.0s — long
  enough to coalesce a burst of edits, short enough that a reader does not
  wait noticeably for notes to appear;
* **is idempotent** by leaning on SPR-01's content-hash dedup: even if the
  same document is processed twice, re-promotion produces zero new nodes;
* **applies backpressure, never silent loss** — when ``budget_ok()`` is
  False the job stays queued and ``backlog()`` reflects it, rather than
  being dropped. Document availability and research progress never block on
  this pass; it degrades by queuing.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

try:
    from .distill import Distiller
    from .document_pass import PassResult, run_document_pass
except ImportError:  # pragma: no cover
    from roles.note_taker.distill import Distiller  # type: ignore[no-redef]
    from roles.note_taker.document_pass import (  # type: ignore[no-redef]
        run_document_pass,
    )


DEFAULT_DEBOUNCE_S = 2.0


@dataclass
class _Job:
    document_id: str
    text: str
    investigation_id: str
    chunk_ids: tuple
    submitted_at: float
    enqueued_seq: int


@dataclass
class SchedulerStats:
    submitted: int = 0
    processed: int = 0
    coalesced: int = 0
    held_for_budget: int = 0


class AsyncNoteScheduler:
    """Debounced, budget-aware scheduler for the document note pass."""

    def __init__(
        self,
        *,
        distiller: Distiller,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        budget_ok: Callable[[], bool] = lambda: True,
        embedding_provider: Any = None,
        events_dir: str | None = None,
    ):
        self._distiller = distiller
        self._debounce_s = debounce_s
        self._budget_ok = budget_ok
        self._embedding_provider = embedding_provider
        self._events_dir = events_dir
        self._pending: dict[str, _Job] = {}     # doc_id -> latest job (coalesces)
        self._cond = asyncio.Condition()
        self._worker: asyncio.Task | None = None
        self._stop = False
        self._seq = 0
        self.stats = SchedulerStats()

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop = True
        async with self._cond:
            self._cond.notify_all()
        if self._worker is not None:
            await self._worker
            self._worker = None

    def backlog(self) -> int:
        """Observable backlog — pending (incl. budget-held) documents."""
        return len(self._pending)

    async def submit(self, document_id: str, text: str, *, investigation_id: str,
                     chunk_ids: Sequence[str] = ()) -> None:
        async with self._cond:
            self._seq += 1
            if document_id in self._pending:
                self.stats.coalesced += 1
            self._pending[document_id] = _Job(
                document_id, text, investigation_id, tuple(chunk_ids),
                time.monotonic(), self._seq,
            )
            self.stats.submitted += 1
            self._cond.notify_all()

    async def drain(self) -> None:
        """Process all currently-ready jobs once (test/flush convenience)."""
        await self._process_ready(ignore_debounce=True)

    async def _run(self) -> None:
        while not self._stop:
            async with self._cond:
                if not self._pending:
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=self._debounce_s)
                    except TimeoutError:
                        pass
                if self._stop:
                    return
            await asyncio.sleep(0)  # let debounce window accrue coalescing
            await self._process_ready(ignore_debounce=False)

    async def _process_ready(self, *, ignore_debounce: bool) -> None:
        now = time.monotonic()
        ready: list[_Job] = []
        async with self._cond:
            for doc_id, job in list(self._pending.items()):
                if ignore_debounce or (now - job.submitted_at) >= self._debounce_s:
                    if not self._budget_ok():
                        self.stats.held_for_budget += 1
                        continue  # leave in _pending — backpressure, not loss
                    ready.append(job)
                    del self._pending[doc_id]
        for job in ready:
            try:
                await run_document_pass(
                    job.document_id, job.text, investigation_id=job.investigation_id,
                    distiller=self._distiller, chunk_ids=job.chunk_ids,
                    embedding_provider=self._embedding_provider, events_dir=self._events_dir,
                )
                self.stats.processed += 1
            except Exception:  # one bad doc must not wedge the scheduler
                self.stats.processed += 1  # counted as attempted
