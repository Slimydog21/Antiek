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


def _authorized_membership(con, authority, node_id: str) -> tuple[str, dict] | None:
    from substrate.graph.tenancy import assert_graph_authority

    assert_graph_authority(con, authority)
    row = con.execute(
        "SELECT role, membership_metadata FROM investigation_node_memberships "
        "WHERE account_digest = ? AND investigation_digest = ? AND node_id = ? "
        "AND role IN ('insight', 'note') ORDER BY role LIMIT 1",
        [authority.account_digest, authority.investigation_digest, node_id],
    ).fetchone()
    if row is None:
        return None
    try:
        metadata = json.loads(row[1])
    except (TypeError, ValueError) as exc:
        from substrate.graph.tenancy import GraphAuthorityConflict

        raise GraphAuthorityConflict("graph membership metadata is invalid") from exc
    if not isinstance(metadata, dict):
        from substrate.graph.tenancy import GraphAuthorityConflict

        raise GraphAuthorityConflict("graph membership metadata is invalid")
    return str(row[0]), metadata


def apply_refinement_authorized(
    authority,
    note_node_id: str,
    new_text: str,
    *,
    seq: int,
    reason: str = "challenge",
    document_id: str | None = None,
    con: Any = None,
) -> ChallengeResult:
    """Refine only one exact membership; shared node storage stays immutable."""
    from substrate.event_log import emit_typed_authorized_strict
    from substrate.investigation_streams import resolve_investigation_stream
    from substrate.investigation_tenancy import InvestigationAuthority

    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("authorized refinement requires InvestigationAuthority")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise ValueError("authorized refinement seq must be a non-negative integer")
    refined = new_text.strip()
    if not refined:
        raise ValueError("authorized refinement text must not be blank")
    resolve_investigation_stream(authority)
    owned = con is None
    c = _open(con)
    if owned:
        c.execute("BEGIN")
    try:
        membership = _authorized_membership(c, authority, note_node_id)
        if membership is None:
            return ChallengeResult(note_node_id, applied=False)
        role, metadata = membership
        previous = metadata.get("canonical_text")
        if not isinstance(previous, str) or not previous:
            from substrate.graph.tenancy import GraphAuthorityConflict

            raise GraphAuthorityConflict("graph membership lacks canonical text")
        document_id = document_id or metadata.get("source_document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("authorized refinement requires a grounded document")
        last_seq = int(metadata.get("last_update_seq", -1))
        wins = seq > last_seq
        emit_typed_authorized_strict(
            authority,
            NoteRefinedPayload(
                note_id=note_node_id,
                previous_text=previous,
                new_text=refined,
                refinement_reason=reason,
            ),
            role="note_taker",
            document_id=document_id,
        )
        if wins:
            metadata["canonical_text"] = refined
            metadata["last_update_seq"] = seq
            metadata["refinement_count"] = int(
                metadata.get("refinement_count", 0) or 0
            ) + 1
            c.execute(
                "UPDATE investigation_node_memberships "
                "SET membership_metadata = ? WHERE account_digest = ? "
                "AND investigation_digest = ? AND node_id = ? AND role = ?",
                [
                    json.dumps(
                        metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ),
                    authority.account_digest,
                    authority.investigation_digest,
                    note_node_id,
                    role,
                ],
            )
        result = ChallengeResult(
            note_node_id,
            applied=wins,
            superseded=not wins,
            new_text=refined if wins else None,
        )
        if owned:
            c.execute("COMMIT")
        return result
    except Exception:
        if owned:
            c.execute("ROLLBACK")
        raise
    finally:
        if owned:
            c.close()


def challenge_note_authorized(
    authority,
    note_node_id: str,
    challenge_text: str,
    *,
    resolver: Resolver,
    seq: int,
    document_id: str | None = None,
    embedding_provider: Any = None,
    con: Any = None,
) -> ChallengeResult:
    """Resolve or escalate a challenge inside one exact graph authority."""
    from substrate.event_log import emit_typed_authorized_strict
    from substrate.graph.insight_question import promote_question_authorized
    from substrate.investigation_streams import resolve_investigation_stream

    resolve_investigation_stream(authority)
    owned = con is None
    c = _open(con)
    if owned:
        c.execute("BEGIN")
    try:
        membership = _authorized_membership(c, authority, note_node_id)
        if membership is None:
            return ChallengeResult(note_node_id, applied=False)
        _role, metadata = membership
        previous = metadata.get("canonical_text")
        if not isinstance(previous, str) or not previous:
            from substrate.graph.tenancy import GraphAuthorityConflict

            raise GraphAuthorityConflict("graph membership lacks canonical text")
        document_id = document_id or metadata.get("source_document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("authorized challenge requires a grounded document")
        resolved_text = resolver(previous, challenge_text)
        if resolved_text is not None and resolved_text.strip():
            result = apply_refinement_authorized(
                authority,
                note_node_id,
                resolved_text,
                seq=seq,
                reason="challenge_resolved",
                document_id=document_id,
                con=c,
            )
        else:
            question_id = promote_question_authorized(
                authority,
                text=challenge_text,
                asks_about=[note_node_id],
                metadata={"raised_by_challenge_of": note_node_id},
                embedding_provider=embedding_provider,
                con=c,
            )
            reserved_child = "inv-" + uuid.uuid4().hex[:16]
            emit_typed_authorized_strict(
                authority,
                QuestionEscalatedToResearchPayload(
                    question_id=question_id,
                    child_investigation_id=reserved_child,
                ),
                role="note_taker",
                document_id=document_id,
            )
            result = ChallengeResult(
                note_node_id,
                applied=False,
                escalated=True,
                escalated_question_id=question_id,
                reserved_child_investigation_id=reserved_child,
            )
        if owned:
            c.execute("COMMIT")
        return result
    except Exception:
        if owned:
            c.execute("ROLLBACK")
        raise
    finally:
        if owned:
            c.close()


def _is_node_target(node_id: str) -> bool:
    # asks_about may point at an insight node; the vocabulary allows
    # question --asks_about--> insight. Always true for our promoted notes.
    return bool(node_id)
