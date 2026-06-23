"""DRW SPR-03 M2 — per-step research note-taking.

A deep research is not just its final report; the *steps* (a retrieval, a
read, an intermediate synthesis) each carry distillable truth. This module
turns a meaningful browse-loop step's content into ``note`` / ``question``
``StepEvent``s (SPR-02's stream shape) that the SPR-02 ``PromotionFunnel``
then promotes to graph nodes. So the division of labour is: **step_pass
distils, the funnel promotes** — no second promotion path.

Within-run dedup (M2 acceptance): an insight whose normalized text was
already emitted earlier in the same run is suppressed, so a fact restated
at every step does not echo into N identical nodes. (Cross-run identity is
SPR-01's content hash; this is the cheaper in-run guard so we don't even
enqueue the dupes.)
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any

try:
    from ...graph.insight_question import canonical_text
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.graph.insight_question import canonical_text  # type: ignore[no-redef]

# StepEvent is defined by SPR-02; import lazily so this module does not hard-
# depend on the runner package being importable in every context.
try:
    from runtime.research_runner.protocol import StepEvent
except Exception:  # pragma: no cover
    StepEvent = None  # type: ignore


class RunNoteDeduper:
    """Tracks the normalized insight/question text already emitted in one
    research run, so a restated fact is not promoted N times. One instance
    per investigation/run."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_new(self, text: str) -> bool:
        key = canonical_text(text)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


def notes_for_step(
    investigation_id: str,
    step_text: str,
    *,
    distiller: Any,
    deduper: RunNoteDeduper,
    seq_start: int = 0,
    source_event_ids: Sequence[str] = (),
) -> list[Any]:
    """Distil one step's content into ``note`` / ``question`` StepEvents,
    suppressing within-run duplicates. Returns the list of StepEvents for
    the runner to yield (and the funnel to promote). Synchronous — the
    caller decides whether to run it in a thread."""
    if StepEvent is None:  # pragma: no cover — runner not importable
        raise RuntimeError("runtime.research_runner.protocol.StepEvent unavailable")
    distillation = distiller.distill(step_text, source_event_ids=source_event_ids)
    out: list[Any] = []
    seq = seq_start
    for note in distillation.insights:
        if not deduper.is_new(note.text):
            continue
        seq += 1
        out.append(StepEvent(
            investigation_id, seq, "note", text=note.text,
            data={"confidence": note.confidence,
                  "source_event_ids": list(note.source_event_ids)},
        ))
    for q in distillation.questions:
        if not deduper.is_new(q.text):
            continue
        seq += 1
        out.append(StepEvent(
            investigation_id, seq, "question", text=q.text,
            data={"asks_about": list(q.asks_about)},
        ))
    return out
