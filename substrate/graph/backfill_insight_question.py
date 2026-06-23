"""DRW SPR-01 — one-shot backfill of historical insight/question events.

Walks the event log, finds every ``note.emerged`` and
``question.identified`` event already on disk, and promotes each into an
``insight`` / ``question`` graph node via the SPR-01 promotion path.

Idempotent by construction: node ids are the content hash of the
normalized text (see ``insight_question.canonical_text``), promoted with
``on_conflict='ignore'``. So a second run promotes zero new nodes, and
re-emitting a note that was already backfilled is a no-op.

Operational shape:

* ``--dry-run`` reports counts (events scanned, unique candidates,
  already-present, would-promote) **without** opening a write
  connection or emitting a single event.
* a real run holds **one** write lock for the whole backfill and commits
  in a single transaction, so 20 investigations' worth of history does
  not thrash the single-writer lock (acquired once, not once-per-note).
  Lock timeouts are an *acquire*-time risk only; holding the lock for the
  duration of an offline operator backfill is intended.

Back up ``~/.antiek/research_graph.duckdb`` before a real run.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

try:
    from ...event_log import default_events_dir, trajectory
    from ...runtime.db_lock import LockedConnection, connect_read, connect_write
    from ...schemas.events import ActionType
    from .insight_question import (
        graph_db_path,
        insight_node_id,
        promote_from_marginalia_event,
        promote_from_note_event,
        promote_from_question_event,
        question_node_id,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import (  # type: ignore[no-redef]
        LockedConnection,
        connect_read,
        connect_write,
    )
    from substrate.event_log import default_events_dir, trajectory  # type: ignore[no-redef]
    from substrate.graph.insight_question import (  # type: ignore[no-redef]
        graph_db_path,
        insight_node_id,
        promote_from_marginalia_event,
        promote_from_note_event,
        promote_from_question_event,
        question_node_id,
    )
    from substrate.schemas.events import ActionType  # type: ignore[no-redef]

_NOTE_ACTION = ActionType.NOTE_EMERGED.value
_QUESTION_ACTION = ActionType.QUESTION_IDENTIFIED.value
# An in-book FloatMenu NOTE (Read SPR-07 M3). It promotes to a user-authored
# insight node, so it is backfilled like a note — its candidate id is the
# insight id of its note_text, so it dedups against the same content-addressed
# node a re-emit would resolve to.
_MARGINALIA_ACTION = ActionType.MARGINALIA_NOTED.value


@dataclass
class BackfillReport:
    notes_scanned: int = 0
    questions_scanned: int = 0
    marginalia_scanned: int = 0
    notes_promoted: int = 0
    questions_promoted: int = 0
    marginalia_promoted: int = 0
    notes_already_present: int = 0
    questions_already_present: int = 0
    marginalia_already_present: int = 0
    dry_run: bool = False
    investigations: int = 0
    errors: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "investigations": self.investigations,
            "notes_scanned": self.notes_scanned,
            "notes_promoted": self.notes_promoted,
            "notes_already_present": self.notes_already_present,
            "questions_scanned": self.questions_scanned,
            "questions_promoted": self.questions_promoted,
            "questions_already_present": self.questions_already_present,
            "marginalia_scanned": self.marginalia_scanned,
            "marginalia_promoted": self.marginalia_promoted,
            "marginalia_already_present": self.marginalia_already_present,
            "errors": self.errors,
        }


def _investigation_ids(events_dir: str) -> list[str]:
    if not os.path.isdir(events_dir):
        return []
    out: list[str] = []
    for fn in sorted(os.listdir(events_dir)):
        if fn.endswith(".parquet"):
            out.append(fn[: -len(".parquet")])
        elif fn.endswith(".jsonl"):
            out.append(fn[: -len(".jsonl")])
    # An investigation may appear as both live JSONL and sealed Parquet;
    # trajectory() prefers Parquet, so dedup the ids.
    return sorted(set(out))


def _iter_candidates(events_dir: str) -> Iterator[tuple[str, dict]]:
    """Yield ``(kind, event)`` for every note.emerged / question.identified
    event across all investigations. ``kind`` is ``"note"`` or
    ``"question"``."""
    for iid in _investigation_ids(events_dir):
        for event in trajectory(iid, events_dir=events_dir):
            at = event.get("action_type")
            if at == _NOTE_ACTION:
                yield "note", event
            elif at == _QUESTION_ACTION:
                yield "question", event
            elif at == _MARGINALIA_ACTION:
                yield "marginalia", event


def _candidate_node_id(kind: str, event: dict) -> str | None:
    payload = event.get("payload")
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return None
    if not isinstance(payload, dict):
        return None
    if kind in ("note", "marginalia"):
        # A marginalia note promotes to a user-authored insight node whose id
        # is the content hash of its note_text — same id space as a distilled
        # insight, so the dedup/idempotency story is identical.
        text = payload.get("note_text")
        return insight_node_id(text) if isinstance(text, str) and text.strip() else None
    text = payload.get("question_text")
    return question_node_id(text) if isinstance(text, str) and text.strip() else None


def _existing_node_ids(read_con, node_ids: set[str]) -> set[str]:
    if not node_ids:
        return set()
    ids = list(node_ids)
    placeholders = ", ".join("?" for _ in ids)
    rows = read_con.execute(
        f"SELECT node_id FROM nodes WHERE node_id IN ({placeholders})", ids
    ).fetchall()
    return {r[0] for r in rows}


def backfill(
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    dry_run: bool = False,
    embedding_provider: Any = None,
) -> BackfillReport:
    """Promote all historical note/question events to nodes. Returns a
    :class:`BackfillReport`. Idempotent; ``dry_run`` writes nothing."""
    db_path = db_path or graph_db_path()
    events_dir = events_dir or default_events_dir()
    report = BackfillReport(dry_run=dry_run)

    candidates = list(_iter_candidates(events_dir))
    report.investigations = len(_investigation_ids(events_dir))
    for kind, _ in candidates:
        if kind == "note":
            report.notes_scanned += 1
        elif kind == "marginalia":
            report.marginalia_scanned += 1
        else:
            report.questions_scanned += 1

    if dry_run:
        # Count would-promote without any write. Read-only connection.
        note_ids = {nid for k, e in candidates if k == "note"
                    and (nid := _candidate_node_id(k, e))}
        q_ids = {nid for k, e in candidates if k == "question"
                 and (nid := _candidate_node_id(k, e))}
        m_ids = {nid for k, e in candidates if k == "marginalia"
                 and (nid := _candidate_node_id(k, e))}
        con = connect_read(db_path)
        try:
            present = _existing_node_ids(con, note_ids | q_ids | m_ids)
        finally:
            con.close()
        report.notes_already_present = len(note_ids & present)
        report.questions_already_present = len(q_ids & present)
        report.marginalia_already_present = len(m_ids & present)
        report.notes_promoted = len(note_ids - present)      # would-promote
        report.questions_promoted = len(q_ids - present)
        report.marginalia_promoted = len(m_ids - present)
        return report

    # Real run: one lock, one transaction.
    con: LockedConnection = connect_write(db_path, purpose="backfill_insight_question")
    try:
        # Pre-count what's already present so we can report new vs. existing.
        all_ids = {nid for k, e in candidates if (nid := _candidate_node_id(k, e))}
        present_before = _existing_node_ids(con, all_ids)
        con.execute("BEGIN")
        try:
            for kind, event in candidates:
                try:
                    if kind == "note":
                        nid = promote_from_note_event(
                            event, con=con, enabled=True,
                            embedding_provider=embedding_provider,
                        )
                        if nid and nid not in present_before:
                            report.notes_promoted += 1
                            present_before.add(nid)
                        elif nid:
                            report.notes_already_present += 1
                    elif kind == "marginalia":
                        nid = promote_from_marginalia_event(
                            event, con=con, enabled=True,
                            embedding_provider=embedding_provider,
                        )
                        if nid and nid not in present_before:
                            report.marginalia_promoted += 1
                            present_before.add(nid)
                        elif nid:
                            report.marginalia_already_present += 1
                    else:
                        nid = promote_from_question_event(
                            event, con=con, enabled=True,
                            embedding_provider=embedding_provider,
                        )
                        if nid and nid not in present_before:
                            report.questions_promoted += 1
                            present_before.add(nid)
                        elif nid:
                            report.questions_already_present += 1
                except Exception as exc:  # one bad event must not abort the batch
                    report.errors.append(
                        f"{event.get('event_id', '?')}: {type(exc).__name__}: {exc}"
                    )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()
    return report


def main(argv: list | None = None) -> int:  # pragma: no cover — CLI
    import argparse
    import json

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db-path", default=None, help="Graph DuckDB path (default: constants.DUCKDB_PATH)")
    p.add_argument("--events-dir", default=None, help="Event-log dir (default: ANTIEK_RESEARCH_EVENTS_DIR)")
    p.add_argument("--dry-run", action="store_true", help="Report counts; write nothing")
    args = p.parse_args(argv)
    report = backfill(db_path=args.db_path, events_dir=args.events_dir, dry_run=args.dry_run)
    print(json.dumps(report.as_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
