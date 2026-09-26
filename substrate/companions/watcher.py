"""The companions event wiring (SPR-03): TOTAL rebuilds on project events.

The knowledge_event_projector precedent (substrate/graph/
knowledge_event_projector.py:1) — a durable event-log consumer — followed
in SUBSTANCE, at companion scale:

  TRIGGER EVENTS (the spec's closed set):
    · thread terminal — investigation.completed | .failed | .chase_halted
      (the cascade terminal set), on any linked thread;
    · island resolve — unit 1's anchor lifecycle events
      (anchor.migrated | .drifted | .orphaned | .restored, emitted on the
      read-<doc> thread by the re-resolution ladder);
    · diligence land — unit 7's transitions are DB ROWS on this stack (the
      daemon writes receipts, not events), so the trigger reads a
      (flag_id → status) WATERMARK — honest, documented, bounded;
    · fork merge commits — unit 5 has NO implementation on this stack:
      honestly UNWIRED (noted, never faked).

  THE THREE DISCIPLINES (the spec's):
    (1) COALESCING — one scan call is ONE window: every unseen trigger in
        the window coalesces into ONE rebuild PER DOCUMENT SCOPE, with ALL
        trigger ids on the receipt (never N rebuilds for N events);
    (2) BOUNDED WRITES — the read pass holds no write lock; the rebuild's
        writes are one short atomic scope (the transaction in
        rebuild_scope) + one short bookkeeping scope; never a lock across
        the read pass, never across an event wait;
    (3) RECEIPTS — every rebuild records {scope, trigger_event_ids,
        rows_written, duration_ms, status, error} (evidence_index.py's
        companion_rebuild_receipts).

  FAILURE HONESTY (last-good): a failed rebuild NEVER serves a
  half-written companion — the index write is atomic and the export file
  is only written after a successful rebuild+render, so the previous
  generation is always lawful to show (the API serves it with the failure
  header). A poisoned SOURCE poisons only itself: the corrupt trajectory's
  process row tombstones honestly and the rebuild completes for everything
  else.

  THE RUNNER: a separate-process cadence loop (``python -m
  substrate.companions.watcher``) following the daemon precedent
  (orchestration/continuous/daemon.py:279-297) — deliberately NOT an
  in-process app worker: the knowledge-event recovery worker's production
  incident (in-process mixed-config connections wedging the API,
  app.py:7785-7790) is the standing lesson; a host-local cadence process
  wedges nothing.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from runtime.db_lock import connect_read, connect_write
from substrate.diligence.schema import diligence_table_exists
from substrate.event_log import default_events_dir, log_event, trajectory
from substrate.graph.knowledge_event_projector import discover_investigations

from .evidence_index import (
    RebuildReceipt,
    mark_triggers_seen,
    read_scope,
    record_receipt,
    seen_trigger_ids,
    watcher_state_get,
    watcher_state_set,
)
from .projector import export_document_companion

#: The trigger vocabulary (the spec's closed set).
TRIGGER_ACTIONS = frozenset(
    {
        "investigation.completed",
        "investigation.failed",
        "investigation.chase_halted",
        "anchor.migrated",
        "anchor.drifted",
        "anchor.orphaned",
        "anchor.restored",
    }
)

_DILIGENCE_WATERMARK_KEY = "diligence_flag_statuses"


@dataclass(frozen=True, slots=True)
class Trigger:
    """One consumed trigger: the event id (or the honest synthetic diligence
    id — unit-7 writes receipts, not events, on this stack), the action,
    and the document scopes it touches."""

    trigger_id: str
    action_type: str
    document_ids: tuple[str, ...]


def _safe_event_id(row: dict[str, Any]) -> str | None:
    eid = row.get("event_id")
    return eid if isinstance(eid, str) and eid else None


def scan_for_triggers(
    con: Any, events_dir: str, *, owner_user_id: str
) -> tuple[list[Trigger], dict[str, str], bool]:
    """READ-ONLY scan: unseen trigger events (dedupe by event id) + the
    diligence status watermark. Returns (triggers, new_diligence_map,
    watermark_changed) — the caller writes the watermark ONLY when it
    changed (idle scans write nothing — the constant-checkpoint
    fragmentation lesson, app.py:7785-7790)."""
    seen = seen_trigger_ids(con)
    triggers: list[Trigger] = []
    for iid in discover_investigations(events_dir):
        try:
            rows = trajectory(iid, events_dir=events_dir)
        except Exception:
            # A corrupt trajectory is a poisoned SOURCE — the rebuild it
            # would trigger marks its row honestly; the scan itself must not
            # die on it (the watcher keeps going).
            continue
        for row in rows:
            at = row.get("action_type")
            if at not in TRIGGER_ACTIONS:
                continue
            eid = _safe_event_id(row)
            if eid is None or eid in seen:
                continue
            triggers.append(
                Trigger(
                    trigger_id=eid,
                    action_type=str(at),
                    document_ids=tuple(sorted(_documents_for(con, iid, str(at)))),
                )
            )

    # The diligence watermark: a flag's STATUS transition lands a trigger
    # (updated_at churn from skip receipts does NOT — only status changes).
    # FIRST SIGHTING primes the watermark WITHOUT triggering — a transition
    # needs a prior state, and a fresh watcher must not rebuild the world.
    new_diligence: dict[str, str] = {}
    prior_raw = watcher_state_get(con, _DILIGENCE_WATERMARK_KEY)
    prior: dict[str, str] = {}
    if prior_raw:
        try:
            parsed = json.loads(prior_raw)
            if isinstance(parsed, dict):
                prior = {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            prior = {}
    if diligence_table_exists(con):
        for fid, status, doc_id in con.execute(
            "SELECT flag_id, status, source_document_id FROM diligence_queue "
            "WHERE owner_user_id = ? AND source_document_id IS NOT NULL",
            [owner_user_id],
        ).fetchall():
            new_diligence[str(fid)] = str(status)
            # Only a SEEN-BEFORE flag whose status CHANGED triggers — first
            # sighting is priming, never a rebuild storm on a fresh cursor.
            if (
                doc_id is not None
                and str(fid) in prior
                and prior[str(fid)] != str(status)
            ):
                triggers.append(
                    Trigger(
                        trigger_id=f"diligence:{fid}:{status}",
                        action_type="diligence.status_changed",
                        document_ids=(str(doc_id),),
                    )
                )
    return triggers, new_diligence, prior != new_diligence


def _documents_for(con: Any, source_id: str, action_type: str) -> set[str]:
    """The document scopes a trigger touches: an anchor lifecycle event
    rides the read-<doc> thread (the document is in the name); a terminal
    investigation event reaches documents through the anchors that link it
    and the diligence flags it was sourced from."""
    if action_type.startswith("anchor."):
        # The anchor audit events ride the read-<documentId> thread.
        if source_id.startswith("read-"):
            return {source_id[len("read-"):]}
        return set()
    docs: set[str] = set()
    # A thread touches a document through the anchors that link it, the
    # diligence flags it was sourced from, AND the edges that ground its
    # nodes in the document (a research thread ABOUT the document).
    if _table(con, "edges"):
        for (doc_id,) in con.execute(
            "SELECT DISTINCT source_document_id FROM edges "
            "WHERE investigation_id = ? AND source_document_id IS NOT NULL",
            [source_id],
        ).fetchall():
            docs.add(str(doc_id))
    for (doc_id,) in con.execute(
        "SELECT DISTINCT document_id FROM anchored_highlights "
        "WHERE investigation_id = ? AND owner_user_id IS NOT NULL",
        [source_id],
    ).fetchall() if _table(con, "anchored_highlights") else []:
        docs.add(str(doc_id))
    if diligence_table_exists(con):
        for (doc_id,) in con.execute(
            "SELECT DISTINCT source_document_id FROM diligence_queue "
            "WHERE source_investigation_id = ? AND source_document_id IS NOT NULL",
            [source_id],
        ).fetchall():
            docs.add(str(doc_id))
    return docs


def _table(con: Any, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1", [name]
    ).fetchone()
    return row is not None


def _mint_rebuild_id() -> str:
    return f"crb-{secrets.token_hex(8)}"


def run_trigger_scan(
    db_path: str,
    *,
    owner_user_id: str,
    events_dir: str | None = None,
) -> list[RebuildReceipt]:
    """ONE window (the daemon-cadence precedent): consume every unseen
    trigger, ONE total rebuild per touched document scope, receipts for all
    of it. Never raises on one bad scope — a failed rebuild records its
    receipt and the last-good generation keeps serving."""
    resolved_events = events_dir or default_events_dir()
    rcon = connect_read(db_path)
    try:
        triggers, diligence_map, watermark_changed = scan_for_triggers(
            rcon, resolved_events, owner_user_id=owner_user_id
        )
    finally:
        rcon.close()
    if not triggers:
        # Nothing to rebuild — but a CHANGED watermark still persists (the
        # priming write, once), in its own short scope. Unchanged: nothing
        # is written at all (idle scans never churn the DB file).
        if watermark_changed:
            with connect_write(db_path, purpose="companions/watcher-watermark") as con:
                watcher_state_set(con, _DILIGENCE_WATERMARK_KEY, json.dumps(diligence_map))
        return []

    # Coalesce: one rebuild per document scope, ALL its trigger ids.
    by_document: dict[str, list[Trigger]] = {}
    consumed_ids: list[str] = []
    for trigger in triggers:
        consumed_ids.append(trigger.trigger_id)
        for doc_id in trigger.document_ids:
            by_document.setdefault(doc_id, []).append(trigger)

    receipts: list[RebuildReceipt] = []
    for doc_id in sorted(by_document):
        scope_triggers = by_document[doc_id]
        started = time.monotonic()
        stamp = datetime.now(UTC).isoformat()
        try:
            _html, _path, _stamp = export_document_companion(
                db_path,
                owner_user_id=owner_user_id,
                document_id=doc_id,
                events_dir=resolved_events,
            )
            rcon = connect_read(db_path)
            try:
                rows_written = len(
                    read_scope(
                        rcon, owner_user_id=owner_user_id, scope="document", scope_id=doc_id
                    )
                )
            finally:
                rcon.close()
            receipts.append(
                RebuildReceipt(
                    rebuild_id=_mint_rebuild_id(),
                    owner_user_id=owner_user_id,
                    scope="document",
                    scope_id=doc_id,
                    trigger_event_ids=tuple(sorted(t.trigger_id for t in scope_triggers)),
                    rows_written=rows_written,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    status="completed",
                    error=None,
                    rebuilt_at=stamp,
                )
            )
            # The rebuild's own audit event (the SPR-02-deferred
            # artifact-class emission, landed here): metadata-only, on the
            # document's reading thread — the anchors' audit precedent
            # (resolve.py's _audit shape), NOT artifact.generated's
            # investigation-keyed payload.
            log_event(
                f"read-{doc_id}",
                "companion.rebuilt",
                payload={
                    "document_id": doc_id,
                    "rebuild_id": receipts[-1].rebuild_id,
                    "trigger_event_ids": list(receipts[-1].trigger_event_ids),
                    "rows_written": rows_written,
                },
                document_id=doc_id,
                events_dir=resolved_events,
            )
        except Exception as e:  # noqa: BLE001 — one bad scope never kills the scan
            receipts.append(
                RebuildReceipt(
                    rebuild_id=_mint_rebuild_id(),
                    owner_user_id=owner_user_id,
                    scope="document",
                    scope_id=doc_id,
                    trigger_event_ids=tuple(sorted(t.trigger_id for t in scope_triggers)),
                    rows_written=0,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    status="failed",
                    error=f"{type(e).__name__}: {e}",
                    rebuilt_at=stamp,
                )
            )

    # The bookkeeping, ONE short write scope: receipts + the seen marks +
    # the diligence watermark. Consumed triggers stay consumed even on a
    # failed rebuild — the failure receipt IS the record (retry/backoff
    # redesign is the spec's named non-goal).
    with connect_write(db_path, purpose="companions/watcher-bookkeeping") as con:
        for receipt in receipts:
            record_receipt(con, receipt)
        mark_triggers_seen(con, consumed_ids, datetime.now(UTC).isoformat())
        watcher_state_set(con, _DILIGENCE_WATERMARK_KEY, json.dumps(diligence_map))
    return receipts


# ── The cadence loop (the daemon precedent — a host-local process) ──────


def run_forever(
    *,
    db_path: str | None = None,
    owner_user_id: str = "__operator__",
    events_dir: str | None = None,
    cadence_seconds: float = 60.0,
    iterations: int | None = None,
) -> None:
    """The cadence loop: one coalesced scan per tick, never crashing on one
    bad event (the daemon's own posture)."""
    from substrate.graph import default_db_path

    resolved_db = db_path or default_db_path()
    count = 0
    while True:
        if iterations is not None and count >= iterations:
            break
        try:
            receipts = run_trigger_scan(
                resolved_db, owner_user_id=owner_user_id, events_dir=events_dir
            )
            sys.stderr.write(
                json.dumps(
                    {
                        "scan": count + 1,
                        "rebuilds": [
                            {
                                "scope": r.scope_id,
                                "status": r.status,
                                "triggers": len(r.trigger_event_ids),
                                "rows": r.rows_written,
                                "ms": r.duration_ms,
                            }
                            for r in receipts
                        ],
                    }
                )
                + "\n"
            )
            sys.stderr.flush()
        except Exception as e:  # noqa: BLE001 — the watcher never dies on one scan
            sys.stderr.write(json.dumps({"scan": count + 1, "error": str(e)}) + "\n")
            sys.stderr.flush()
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(cadence_seconds)


def main() -> None:
    """Module CLI: ``python -m substrate.companions.watcher``."""
    run_forever(
        cadence_seconds=float(os.environ.get("ANTIEK_COMPANION_SCAN_SECONDS", "60"))
    )


if __name__ == "__main__":
    main()
