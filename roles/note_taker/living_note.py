"""DRW SPR-03 M3 + M6 — living notes.

A note is not frozen at emission: when a user challenges it or new evidence
arrives, the note *updates in place* rather than spawning a duplicate. That
is the "living note". The hazard is concurrency — a user challenge and a
background re-distillation can target the same note at once — so updates
need a deterministic resolution rule.

The rule: **single logical writer per note, ordered by event sequence;
last-writer-by-event-seq wins; the full history is preserved in the event
log.** Each refinement carries a monotonic ``seq`` (in production, the
emission order of the driving event). The note node records the highest
``seq`` it has applied in ``metadata.last_update_seq``. An incoming
refinement is applied to the node iff its ``seq`` is strictly greater;
otherwise it is the *loser* — the node is left untouched, but a
``note.refined`` event is still written so the log records the attempt and
the prior text. Determinism is therefore independent of arrival order.

Worked example (the docstring the maintainer should not have to guess):
a background pass refines a note at ``seq=11`` and a user challenge refines
it at ``seq=12``. Whichever lands first, the node's final text is the
``seq=12`` text; the ``seq=11`` refinement is preserved in the event log
(``previous_text`` + ``new_text``) but not reflected on the node.

Escalation seam (M6): a challenge the existing graph cannot resolve emits
``question.escalated_to_research`` on the relevant question node, carrying a
*reserved* (not launched) child ``investigation_id``. SPR-06 / SPR-10 launch
into that reserved id later. **Nothing is launched here.**
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from ...event_log import emit_typed
    from ...graph.insight_question import graph_db_path, promote_question
    from ...runtime.db_lock import connect_write
    from ...schemas.events import NoteRefinedPayload, QuestionEscalatedToResearchPayload
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.graph.insight_question import (  # type: ignore[no-redef]
        graph_db_path,
        promote_question,
    )
    from substrate.schemas.events import (  # type: ignore[no-redef]
        NoteRefinedPayload,
        QuestionEscalatedToResearchPayload,
    )


# A resolver decides whether a challenge can be answered from what's known.
# It returns the refined note text (resolved) or None (escalate). Production
# wires an LLM; tests inject a deterministic function.
Resolver = Callable[[str, str], str | None]


@dataclass
class ChallengeResult:
    note_node_id: str
    applied: bool                       # did the node text change?
    superseded: bool = False            # lost the seq race (older seq)?
    new_text: str | None = None
    escalated: bool = False
    escalated_question_id: str | None = None
    reserved_child_investigation_id: str | None = None


def _open(con):
    return con if con is not None else connect_write(graph_db_path(), purpose="living_note")


def _read_node(con, node_id: str) -> tuple[str | None, dict]:
    row = con.execute(
        "SELECT canonical_label, metadata FROM nodes WHERE node_id = ?", [node_id]
    ).fetchone()
    if row is None:
        return None, {}
    meta = {}
    if row[1]:
        try:
            meta = json.loads(row[1])
        except (TypeError, ValueError):
            meta = {}
    return row[0], meta


def apply_refinement(
    note_node_id: str,
    new_text: str,
    *,
    seq: int,
    investigation_id: str,
    reason: str = "challenge",
    document_id: str | None = None,
    events_dir: str | None = None,
    con: Any = None,
) -> ChallengeResult:
    """Apply a refinement to a note node under the seq rule. Always writes a
    ``note.refined`` event (history); updates the node only if ``seq`` beats
    the last applied seq."""
    owned = con is None
    c = _open(con)
    try:
        prev_text, meta = _read_node(c, note_node_id)
        if prev_text is None:
            return ChallengeResult(note_node_id, applied=False)
        # note.refined is a wrestling-loop event and requires document_id on
        # the envelope (architecture_notes §9.1). A living note inherits the
        # document it was distilled from — resolve it from node metadata when
        # the caller did not pass one.
        document_id = document_id or meta.get("source_document_id")
        last_seq = int(meta.get("last_update_seq", -1))
        wins = seq > last_seq
        # History is preserved regardless of who wins.
        emit_typed(
            investigation_id,
            NoteRefinedPayload(note_id=note_node_id, previous_text=prev_text,
                               new_text=new_text, refinement_reason=reason),
            role="note_taker", document_id=document_id, events_dir=events_dir,
        )
        if wins:
            meta["last_update_seq"] = seq
            meta.setdefault("refinement_count", 0)
            meta["refinement_count"] += 1
            c.execute(
                "UPDATE nodes SET canonical_label = ?, metadata = ? WHERE node_id = ?",
                [new_text, json.dumps(meta, default=str), note_node_id],
            )
        return ChallengeResult(note_node_id, applied=wins, superseded=not wins,
                               new_text=new_text if wins else None)
    finally:
        if owned:
            c.close()


def challenge_note(
    note_node_id: str,
    challenge_text: str,
    *,
    resolver: Resolver,
    seq: int,
    investigation_id: str,
    document_id: str | None = None,
    embedding_provider: Any = None,
    events_dir: str | None = None,
    con: Any = None,
) -> ChallengeResult:
    """Resolve a challenge against a note. If the resolver produces refined
    text, update the note in place (seq rule). If not, escalate: ensure a
    question node exists for the challenge and emit
    ``question.escalated_to_research`` with a reserved (un-launched) child
    investigation id."""
    owned = con is None
    c = _open(con)
    try:
        prev_text, _meta = _read_node(c, note_node_id)
        if prev_text is None:
            return ChallengeResult(note_node_id, applied=False)
        document_id = document_id or _meta.get("source_document_id")
        resolved_text = resolver(prev_text, challenge_text)
        if resolved_text is not None and resolved_text.strip():
            return apply_refinement(
                note_node_id, resolved_text.strip(), seq=seq,
                investigation_id=investigation_id, reason="challenge_resolved",
                document_id=document_id, events_dir=events_dir, con=c,
            )
        # Unresolvable → escalate. Promote the challenge as a question node,
        # reserve a child investigation id, emit the escalation. No launch.
        qid = promote_question(
            text=challenge_text, investigation_id=investigation_id,
            asks_about=[note_node_id] if _is_node_target(note_node_id) else [],
            metadata={"raised_by_challenge_of": note_node_id},
            embedding_provider=embedding_provider, con=c,
        )
        reserved_child = "inv-" + uuid.uuid4().hex[:16]
        emit_typed(
            investigation_id,
            QuestionEscalatedToResearchPayload(
                question_id=qid, child_investigation_id=reserved_child),
            role="note_taker", document_id=document_id, events_dir=events_dir,
        )
        return ChallengeResult(
            note_node_id, applied=False, escalated=True,
            escalated_question_id=qid, reserved_child_investigation_id=reserved_child,
        )
    finally:
        if owned:
            c.close()


def _is_node_target(node_id: str) -> bool:
    # asks_about may point at an insight node; the vocabulary allows
    # question --asks_about--> insight. Always true for our promoted notes.
    return bool(node_id)
