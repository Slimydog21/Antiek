"""Cross-document question→answer linking (Sprint 4 day 2-3).

The differentiator from the operator's Sprint 1 vision: "a question
in one document can get the answer that gets delivered after
wrestling with another document". This module is the watcher that
makes that property structural.

How it works:

- Subscribes to ``question.identified`` events. Each one is added to a
  per-investigation open-questions index keyed by question_id with
  the home document_id + question text.
- Subscribes to ``note.emerged`` events (the note-taker's output). For
  each emerging note, scores cosine similarity between the note text
  and each OPEN question on a DIFFERENT document. If the score
  exceeds ``ANTIEK_CROSS_DOC_THRESHOLD`` (default 0.5), emits
  ``cross_doc.question_answered`` with both document_ids + the
  bridging note_id, then removes the question from the open index.
- Subscribes to ``question.resolved_by_doc`` events (in-document
  resolution by other paths). On fire: drops the question from the
  open index so we don't emit a redundant cross_doc link later.

Discipline:

- Per-investigation isolation — questions raised in one investigation
  never link to notes from another. Open-questions state is keyed on
  ``investigation_id``.
- Deduplication — a question is linked at most once. After the first
  cross-doc match it leaves the open index and is also added to a
  per-investigation ``answered`` set as belt-and-suspenders.
- Same-doc skip — a note that emerges on the same document as a
  question's home document is NOT a cross-doc match (it's a regular
  in-doc resolution, which would emit ``question.resolved_by_doc``
  through a different path when that surfaces).
- Embedding agnostic — uses the injected EmbeddingProvider. With the
  hash fallback, threshold ~0.3 produces useful matches on
  word-overlapping text; with sentence-transformers, 0.5+ is the
  right default. Operator sets ``ANTIEK_CROSS_DOC_THRESHOLD`` to taste.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Optional, Sequence

# Direct import — interfaces/research/api/ depends on substrate + processing.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.embedding import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    CrossDocQuestionAnsweredPayload,
    Event,
    NoteEmergedPayload,
    QuestionIdentifiedPayload,
    QuestionResolvedByDocPayload,
)

from .broadcast import EventBroadcaster


# Default similarity threshold. Tuned for the sentence-transformers
# production embedder. For the HashEmbedding fallback used in dev/tests,
# operator should lower to ~0.3 via the env var. Anything below that
# starts producing false positives even on weak word overlap.
DEFAULT_THRESHOLD = 0.5


def _resolve_threshold() -> float:
    raw = os.environ.get("ANTIEK_CROSS_DOC_THRESHOLD")
    if not raw:
        return DEFAULT_THRESHOLD
    try:
        v = float(raw)
        if v < 0.0 or v > 1.0:
            return DEFAULT_THRESHOLD
        return v
    except ValueError:
        return DEFAULT_THRESHOLD


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity. Returns 0.0 when either vector is zero — the
    degenerate case shouldn't fire a cross-doc link anyway."""
    if not a or not b:
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return num / (na * nb)


# ---------------------------------------------------------------------------
# Per-investigation state
# ---------------------------------------------------------------------------


# Shape: {investigation_id: {question_id: {"document_id": str, "text": str}}}
OpenQuestions = dict[str, dict[str, dict[str, str]]]
# Shape: {investigation_id: set[question_id]} — claimed questions
Answered = dict[str, set[str]]


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_cross_doc_handler(
    broadcaster: EventBroadcaster,
    *,
    embedder: Optional[EmbeddingProvider] = None,
    threshold: Optional[float] = None,
):
    """Build the async handler closed over the broadcaster + embedder
    + threshold. Same handler is registered for question.identified,
    note.emerged, and question.resolved_by_doc — it dispatches on
    ``event.action_type`` internally."""

    resolved_threshold = threshold if threshold is not None else _resolve_threshold()
    open_questions: OpenQuestions = {}
    answered: Answered = {}

    async def handle(event: Event) -> None:
        # Lazy-resolve the embedder so env var + test injection both
        # take effect.
        emb = embedder if embedder is not None else default_embedding_provider()
        action_type = (
            event.action_type.value
            if hasattr(event.action_type, "value")
            else str(event.action_type)
        )

        if action_type == ActionType.QUESTION_IDENTIFIED.value:
            await _on_question_identified(event, open_questions)
            return

        if action_type == ActionType.QUESTION_RESOLVED_BY_DOC.value:
            _on_question_resolved(event, open_questions)
            return

        if action_type == ActionType.NOTE_EMERGED.value:
            await _on_note_emerged(
                event, open_questions, answered, emb, resolved_threshold,
                broadcaster,
            )
            return

    return handle


async def _on_question_identified(
    event: Event,
    open_questions: OpenQuestions,
) -> None:
    """Record the question + its home document in the per-investigation
    open-questions index."""
    if not isinstance(event.payload, QuestionIdentifiedPayload):
        return
    if not event.document_id:
        return  # wrestling validator requires document_id; defensive
    inv_qs = open_questions.setdefault(event.investigation_id, {})
    inv_qs[event.payload.question_id] = {
        "document_id": event.document_id,
        "text": event.payload.question_text,
    }


def _on_question_resolved(
    event: Event,
    open_questions: OpenQuestions,
) -> None:
    """Some other path resolved the question (in-doc note or
    something else). Drop it from the open index so we don't
    duplicate-emit a cross-doc link for it later."""
    if not isinstance(event.payload, QuestionResolvedByDocPayload):
        return
    inv_qs = open_questions.get(event.investigation_id, {})
    inv_qs.pop(event.payload.question_id, None)


async def _on_note_emerged(
    event: Event,
    open_questions: OpenQuestions,
    answered: Answered,
    embedder: EmbeddingProvider,
    threshold: float,
    broadcaster: EventBroadcaster,
) -> None:
    """For each open question on a DIFFERENT document, score similarity
    between the note text and the question text. If above threshold,
    emit a cross_doc.question_answered event and remove the question
    from the open index."""
    if not isinstance(event.payload, NoteEmergedPayload):
        return
    if not event.document_id:
        return  # note's home document is required; defensive

    inv_qs = open_questions.get(event.investigation_id, {})
    if not inv_qs:
        return

    inv_answered = answered.setdefault(event.investigation_id, set())
    note_text = event.payload.note_text
    note_doc = event.document_id

    try:
        note_vec = embedder.encode(note_text)
    except Exception:  # pragma: no cover — diagnostic
        return

    # Iterate over a snapshot so we can mutate inv_qs during the loop.
    for q_id, q_info in list(inv_qs.items()):
        if q_info["document_id"] == note_doc:
            continue  # same-doc; not a cross-doc match
        if q_id in inv_answered:
            continue
        try:
            q_vec = embedder.encode(q_info["text"])
        except Exception:  # pragma: no cover
            continue
        sim = _cosine(note_vec, q_vec)
        if sim < threshold:
            continue
        # Match. Emit + dedupe.
        emitted_id = emit_typed(
            event.investigation_id,
            CrossDocQuestionAnsweredPayload(
                question_id=q_id,
                question_document_id=q_info["document_id"],
                answer_document_id=note_doc,
                answer_note_id=event.payload.note_id,
            ),
            parent_event_id=event.event_id,
            role="connector",
            # NOTE: no document_id on the envelope — CROSS_DOC events
            # span two docs by definition (per architecture_notes §13.3
            # carve-out: not in WRESTLING_ACTION_TYPES).
        )
        inv_answered.add(q_id)
        inv_qs.pop(q_id, None)

        if emitted_id is None:
            continue
        # Broadcast so subscribed WS clients see the link live.
        for row in reversed(trajectory(event.investigation_id)):
            if row.get("event_id") == emitted_id:
                try:
                    cross_event = Event.model_validate(row)
                    await broadcaster.broadcast(cross_event)
                except Exception:  # pragma: no cover — best-effort
                    pass
                break


def register_handlers(
    broadcaster: EventBroadcaster,
    *,
    embedder: Optional[EmbeddingProvider] = None,
    threshold: Optional[float] = None,
) -> None:
    """Wire the cross-doc watcher. Single handler registered for all
    three subscribed action types so the per-investigation state is
    shared across event kinds."""
    handler = make_cross_doc_handler(
        broadcaster, embedder=embedder, threshold=threshold,
    )
    for at in (
        ActionType.QUESTION_IDENTIFIED.value,
        ActionType.NOTE_EMERGED.value,
        ActionType.QUESTION_RESOLVED_BY_DOC.value,
    ):
        broadcaster.register_handler(at, handler)
