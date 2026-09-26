"""The projector (companions SPR-01): ONE snapshot-scoped pass over the
lawful stores → the evidence-index rows AND the companion rendering — two
renderings of one read, so the human text and the agent index can never
disagree.

DOCUMENT scope ships; PROJECT scope is honestly UNAVAILABLE until the
unit-3 container lands (PR #3431) — ``rebuild_project`` raises
``ProjectScopeUnavailable``, never mints a synthetic project id (the same
discipline as not forking the anchor schema).

Sources read (this stack), each from its lawful store — and each ABSENT
store degrades honestly (no rows, and the rendering says so):

  graph nodes (claim rows)      — insight/question nodes grounded in the
                                  document via supported_by edges;
  unit-1 anchors (evidence rows) — the owner-scoped highlight store;
  event log (process rows)      — the anchor-linked threads + the reading
                                  thread, terminal status from the
                                  trajectory (the cascade terminal set);
  unit-7 diligence (process)    — flags sourced from the document, with
                                  their receipts;
  unit-4 reading state (process)— the owner's position row;
  unit-5 forks/merges           — NO store on this stack: zero rows, and
                                  the companion's forks section is an
                                  honest empty state.

Rebuild is TOTAL and idempotent: read once, delete-scope + batch-write in
bounded batches (the writer-lock lesson — many short scopes), render from
the same read. The snapshot stamp (``rebuilt_at``) is SOURCE-DERIVED (the
max source timestamp), never a wall clock — unchanged sources rebuild
byte-identically.

Rights flow through: a withheld (non-servable) document contributes
METADATA ONLY — the index never stores text (refs only, by construction)
and the rendering shows the claim's metadata line, never its text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from runtime.db_lock import connect_read, connect_write
from substrate.books.highlights.resolve import document_servable
from substrate.books.highlights.store import HighlightsStore
from substrate.diligence.schema import diligence_table_exists
from substrate.event_log import default_events_dir, trajectory

from .evidence_index import EvidenceRow, make_evidence_id, rebuild_scope
from .render import render_document_companion


class ProjectScopeUnavailable(RuntimeError):
    """The honest project-scope answer: no project aggregate exists before
    the unit-3 container lands."""


# ── The read model (one pass, everything the two renderings need) ──────


@dataclass(frozen=True, slots=True)
class ClaimRead:
    node_id: str
    node_kind: str  # insight | question
    text: str  # read substrate-side for the id + the servable rendering
    evidence_id: str


@dataclass(frozen=True, slots=True)
class AnchorRead:
    anchor_id: str
    status: str
    page_index_hint: int | None
    evidence_id: str


@dataclass(frozen=True, slots=True)
class ProcessRead:
    detail: str  # thread | diligence | reading — the row's sub-kind
    label: str  # human, calm — never a raw id
    status_line: str  # "working…" / "done" / "done — stopped" / honest lines
    evidence_id: str


@dataclass(frozen=True, slots=True)
class BiteRead:
    """One derived bite's calm ledger entry (unit 8, SPR-03): class,
    byte-verification, and whether it traces — never the bite's text here
    (the text lives in the derived document's own body)."""
    ordinal: int
    contribution_class: str
    byte_verified: bool
    traced: bool  # has source spans
    evidence_id: str


@dataclass(frozen=True, slots=True)
class DocumentView:
    document_id: str
    exists: bool
    title: str | None
    servable: bool
    claims: tuple[ClaimRead, ...]
    anchors: tuple[AnchorRead, ...]
    processes: tuple[ProcessRead, ...]
    """The unit-8 bite ledger — present only for a DERIVED document."""
    bites: tuple[BiteRead, ...]
    rebuilt_at: str


_EPOCH = "1970-01-01T00:00:00+00:00"

#: The cascade terminal set (orchestration/cascade_session.py:426-430),
#: mapped to the companion's honest status lines.
_TERMINAL_STATUS_LINES = {
    "investigation.completed": "done",
    "investigation.failed": "done — failed",
    "investigation.chase_halted": "done — stopped",
}


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        v = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return v.isoformat()
    return str(value)


def read_trajectory_honest(
    events_dir: str, investigation_id: str
) -> tuple[str, list[dict[str, Any]]]:
    """The corruption-honest trajectory read (knowledge_event_projector.py's
    corruption class): ("ok", rows) · ("absent", []) — nothing on disk ·
    ("corrupt", []) — a trajectory EXISTS but cannot be parsed (a corrupt
    sealed snapshot raises out of trajectory()). Poison is told apart from
    empty, never silently flattened into a benign "no events"."""
    import os as _os

    from substrate.event_log.events import _jsonl_path, _parquet_path

    try:
        return "ok", trajectory(investigation_id, events_dir=events_dir)
    except Exception:
        pass
    jl = _jsonl_path(investigation_id, events_dir=events_dir)
    pq = _parquet_path(investigation_id, events_dir=events_dir)
    if _os.path.exists(jl) or _os.path.exists(pq):
        return "corrupt", []
    return "absent", []


def trajectory_status_line(events_dir: str, investigation_id: str) -> str:
    """One thread's honest status line from its trajectory: the terminal
    set's line, else 'working…' when started, else 'no events on record'.
    A CORRUPT trajectory reads as itself — the poison is named, never
    flattened."""
    state, rows = read_trajectory_honest(events_dir, investigation_id)
    if state == "corrupt":
        return "the record is unreadable — marked honestly, nothing guessed"
    status = "no events on record"
    for row in rows:
        at = row.get("action_type")
        if at == "investigation.start_requested":
            status = "working…"
        elif at in _TERMINAL_STATUS_LINES:
            status = _TERMINAL_STATUS_LINES[at]
    return status


def _artifact_ref(events_dir: str, investigation_id: str) -> str | None:
    """The artifact's PATH hash when the thread generated one (refs only —
    the hash of the path, never the artifact's content)."""
    state, rows = read_trajectory_honest(events_dir, investigation_id)
    if state != "ok":
        return None
    for row in rows:
        if row.get("action_type") == "artifact.generated":
            path = (row.get("payload") or {}).get("artifact_path")
            if path:
                digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
                return f"artifact:{digest}"
    return None


def project_document(
    con: Any,
    *,
    owner_user_id: str,
    document_id: str,
    events_dir: str | None = None,
) -> tuple[list[EvidenceRow], DocumentView]:
    """The ONE read pass: every source read once, on one snapshot (the
    caller's connection) + the event log's files. Returns the index rows
    AND the view both renderings draw from."""
    resolved_events = events_dir or default_events_dir()

    doc = con.execute(
        "SELECT document_id, title FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    exists = doc is not None
    title = None if doc is None else (None if doc[1] is None else str(doc[1]))
    servable = exists and document_servable(con, document_id)

    rows: list[EvidenceRow] = []
    claims: list[ClaimRead] = []
    anchors: list[AnchorRead] = []
    processes: list[ProcessRead] = []
    stamps: list[str] = []

    # ── Claims: insight/question nodes grounded in the document ────────
    for nid, nkind, label, created in con.execute(
        "SELECT DISTINCT n.node_id, n.node_type, n.canonical_label, n.created_at "
        "FROM nodes n JOIN edges e ON e.source_node_id = n.node_id "
        "WHERE e.relation = 'supported_by' AND e.source_document_id = ? "
        "AND n.node_type IN ('insight', 'question') "
        "ORDER BY n.node_id ASC",
        [document_id],
    ).fetchall():
        text = str(label)
        eid = make_evidence_id(
            "claim", text, [f"node:{nid}", f"doc:{document_id}"]
        )
        rows.append(
            EvidenceRow(
                evidence_id=eid,
                owner_user_id=owner_user_id,
                scope="document",
                scope_id=document_id,
                kind="claim",
                refs=(f"node:{nid}", f"doc:{document_id}"),
                tombstone=False,
                rebuilt_at=_iso(created) or _EPOCH,
            )
        )
        claims.append(ClaimRead(node_id=str(nid), node_kind=str(nkind), text=text, evidence_id=eid))
        stamps.append(_iso(created))

    # ── Evidence: the unit-1 anchors on the document (owner-scoped) ────
    investigation_ids: set[str] = set()
    from substrate.books.highlights.schema import highlights_table_exists

    anchor_rows = (
        HighlightsStore().list_for_document(con, document_id)
        if highlights_table_exists(con)
        else []
    )
    for anchor in anchor_rows:
        if anchor.owner_user_id != owner_user_id:
            continue
        a = anchor.anchor
        identity = f"{a.node_id}:{a.start_scalar}:{a.end_scalar}"
        eid = make_evidence_id(
            "evidence", identity, [f"anchor:{anchor.anchor_id}", f"doc:{document_id}"]
        )
        rows.append(
            EvidenceRow(
                evidence_id=eid,
                owner_user_id=owner_user_id,
                scope="document",
                scope_id=document_id,
                kind="evidence",
                refs=(f"anchor:{anchor.anchor_id}", f"doc:{document_id}"),
                tombstone=False,
                rebuilt_at=_iso(anchor.updated_at) or _EPOCH,
            )
        )
        anchors.append(
            AnchorRead(
                anchor_id=anchor.anchor_id,
                status=str(anchor.status),
                page_index_hint=anchor.page_index_hint,
                evidence_id=eid,
            )
        )
        stamps.append(_iso(anchor.updated_at))
        if anchor.investigation_id:
            investigation_ids.add(anchor.investigation_id)

    # ── Process: the linked threads + the reading thread ───────────────
    thread_ids = sorted(investigation_ids | {f"read-{document_id}"})
    for iid in thread_ids:
        refs = [f"investigation:{iid}", f"doc:{document_id}"]
        artifact = _artifact_ref(resolved_events, iid)
        if artifact:
            refs.append(artifact)
        eid = make_evidence_id("process", iid, refs)
        status_line = trajectory_status_line(resolved_events, iid)
        traj_state, rows_ev = read_trajectory_honest(resolved_events, iid)
        last_event = _iso(rows_ev[-1].get("emitted_at")) if rows_ev else ""
        # Poison containment (SPR-03): a corrupt trajectory poisons ONLY its
        # own row — the process row is written TOMBstoned with the honest
        # status line, and the rebuild completes for everything else.
        poisoned = traj_state == "corrupt"
        rows.append(
            EvidenceRow(
                evidence_id=eid,
                owner_user_id=owner_user_id,
                scope="document",
                scope_id=document_id,
                kind="process",
                refs=tuple(refs),
                tombstone=poisoned,
                rebuilt_at=last_event or _EPOCH,
            )
        )
        processes.append(
            ProcessRead(
                detail="thread",
                label=(
                    "the reading thread"
                    if iid == f"read-{document_id}"
                    else "a research thread on a passage"
                ),
                status_line=status_line,
                evidence_id=eid,
            )
        )
        if last_event:
            stamps.append(last_event)

    # ── Process: the unit-7 diligence flags sourced from this document ─
    if diligence_table_exists(con):
        for fid, fstatus, updated in con.execute(
            "SELECT flag_id, status, updated_at FROM diligence_queue "
            "WHERE owner_user_id = ? AND source_document_id = ? "
            "ORDER BY flag_id ASC",
            [owner_user_id, document_id],
        ).fetchall():
            eid = make_evidence_id("process", f"flag:{fid}", [f"flag:{fid}", f"doc:{document_id}"])
            rows.append(
                EvidenceRow(
                    evidence_id=eid,
                    owner_user_id=owner_user_id,
                    scope="document",
                    scope_id=document_id,
                    kind="process",
                    refs=(f"flag:{fid}", f"doc:{document_id}"),
                    tombstone=False,
                    rebuilt_at="",
                )
            )
            processes.append(
                ProcessRead(
                    detail="diligence",
                    label="a diligence flag from this document",
                    status_line=str(fstatus),
                    evidence_id=eid,
                )
            )
            stamps.append(_iso(updated))

    # ── Process: the unit-4 reading position (refs/numbers only) ───────
    try:
        from substrate.books.reading_state import ReadingStateStore

        reading = ReadingStateStore().get(
            con, owner_user_id=owner_user_id, document_id=document_id
        )
    except Exception:
        reading = None  # an absent store degrades honestly
    if reading is not None:
        eid = make_evidence_id(
            "process", f"reading:{owner_user_id}:{document_id}", [f"doc:{document_id}"]
        )
        rows.append(
            EvidenceRow(
                evidence_id=eid,
                owner_user_id=owner_user_id,
                scope="document",
                scope_id=document_id,
                kind="process",
                refs=(f"reading:{owner_user_id}:{document_id}", f"doc:{document_id}"),
                tombstone=False,
                rebuilt_at=_iso(reading.updated_at) or _EPOCH,
            )
        )
        processes.append(
            ProcessRead(
                detail="reading",
                label="your reading position",
                status_line=f"page {reading.page_index + 1}",
                evidence_id=eid,
            )
        )
        stamps.append(_iso(reading.updated_at))

    # ── Claims (unit 8): a DERIVED document's bites project with their
    # provenance refs — CONSUMED through the provenance store, never
    # duplicated. Refs namespace the generation, the class, the
    # investigation, and the core spans. ──
    from substrate.provenance.schema import provenance_tables_exist
    from substrate.provenance.store import ProvenanceStore

    bites: list[BiteRead] = []
    if provenance_tables_exist(con):
        gen_row = con.execute(
            "SELECT generation_id, source_document_id FROM generation_records "
            "WHERE derived_document_id = ? LIMIT 1",
            [document_id],
        ).fetchone()
        if gen_row is not None:
            store = ProvenanceStore()
            record = store.get_generation(con, str(gen_row[0]))
            if record is None:  # the FK guarantees it — refuse loudly if not
                raise RuntimeError(
                    f"generation record {gen_row[0]} vanished between read "
                    "and projection"
                )
            for bite in store.bites_for_generation(con, record.generation_id):
                refs = [
                    f"bite:{bite.bite_id}",
                    f"generation:{record.generation_id}",
                    f"doc:{document_id}",
                    f"class:{bite.contribution_class}",
                ]
                if bite.investigation_id:
                    refs.append(f"investigation:{bite.investigation_id}")
                for span_json in bite.source_refs or []:
                    import json as _json

                    span = _json.loads(span_json)
                    refs.append(
                        "corespan:"
                        f"{record.source_document_id}:{span['node_id']}:"
                        f"{span['start_scalar']}:{span['end_scalar']}"
                    )
                eid = make_evidence_id(
                    "claim", f"bite:{bite.bite_id}", refs
                )
                rows.append(
                    EvidenceRow(
                        evidence_id=eid,
                        owner_user_id=owner_user_id,
                        scope="document",
                        scope_id=document_id,
                        kind="claim",
                        refs=tuple(sorted(refs)),
                        tombstone=False,
                        rebuilt_at=_iso(record.created_at) or _EPOCH,
                    )
                )
                bites.append(
                    BiteRead(
                        ordinal=bite.ordinal,
                        contribution_class=bite.contribution_class,
                        byte_verified=(
                            bite.contribution_class == "author_verbatim"
                            and bite.source_span_sha256 is not None
                            and bite.derived_text_sha256 == bite.source_span_sha256
                        ),
                        traced=bite.source_refs is not None,
                        evidence_id=eid,
                    )
                )
            stamps.append(_iso(record.created_at))

    # The snapshot stamp: SOURCE-DERIVED (the max source timestamp), never a
    # wall clock — unchanged sources rebuild byte-identically. Each ROW
    # carries its own sources' stamp, so one source event changes exactly
    # the affected rows (the delta contract).
    stamp = max((s for s in stamps if s), default=_EPOCH)
    rows.sort(key=lambda r: r.evidence_id)

    view = DocumentView(
        document_id=document_id,
        exists=exists,
        title=title,
        servable=servable,
        claims=tuple(claims),
        anchors=tuple(anchors),
        processes=tuple(processes),
        bites=tuple(bites),
        rebuilt_at=stamp,
    )
    return rows, view


def rebuild_document(
    db_path: str,
    *,
    owner_user_id: str,
    document_id: str,
    events_dir: str | None = None,
) -> str:
    """TOTAL idempotent rebuild of one document's scope: one read pass, one
    bounded write phase, the companion rendered from the SAME read. Returns
    the companion HTML."""
    html, _view = rebuild_document_full(
        db_path,
        owner_user_id=owner_user_id,
        document_id=document_id,
        events_dir=events_dir,
    )
    return html


def rebuild_document_full(
    db_path: str,
    *,
    owner_user_id: str,
    document_id: str,
    events_dir: str | None = None,
) -> tuple[str, DocumentView]:
    """The rebuild + the VIEW (SPR-02's export/API needs the stamp without a
    second read — one pass, both products)."""
    rcon = connect_read(db_path)
    try:
        rows, view = project_document(
            rcon,
            owner_user_id=owner_user_id,
            document_id=document_id,
            events_dir=events_dir,
        )
    finally:
        rcon.close()
    with connect_write(db_path, purpose="companions/rebuild-document") as wcon:
        rebuild_scope(
            wcon,
            owner_user_id=owner_user_id,
            scope="document",
            scope_id=document_id,
            rows=rows,
        )
    return render_document_companion(view), view


def rebuild_project(
    db_path: str, *, owner_user_id: str, project_id: str, events_dir: str | None = None
) -> str:
    """HONESTLY UNAVAILABLE before the unit-3 container lands — raise, never
    mint a synthetic project id."""
    raise ProjectScopeUnavailable(
        "project scope unavailable: no project aggregate exists until the "
        "workstation container lands (unit 3) — document scope ships first"
    )


# ── SPR-02: the structured payload + the export ────────────────────────────


def document_companion_payload(view: DocumentView) -> dict[str, Any]:
    """The companion as STRUCTURED data (the rail + the agent API render
    THIS, never raw generated HTML — the sanctioned-rendering discipline).
    Rights flow through identically to the HTML: a withheld document's
    claims carry text=None (metadata lines only) — the withheld text never
    leaves the projector in ANY shape."""
    return {
        "document_id": view.document_id,
        "exists": view.exists,
        "title": view.title,
        "servable": view.servable,
        "rebuilt_at": view.rebuilt_at,
        "claims": [
            {
                "evidence_id": c.evidence_id,
                "kind": c.node_kind,
                "node_ref": f"node:{c.node_id}",
                "text": c.text if view.servable else None,
            }
            for c in view.claims
        ],
        "anchors": [
            {
                "evidence_id": a.evidence_id,
                "anchor_ref": f"anchor:{a.anchor_id}",
                "status": a.status,
                "page_index_hint": a.page_index_hint,
            }
            for a in view.anchors
        ],
        "processes": [
            {
                "evidence_id": p.evidence_id,
                "detail": p.detail,
                "label": p.label,
                "status_line": p.status_line,
            }
            for p in view.processes
        ],
        "bites": [
            {
                "evidence_id": b.evidence_id,
                "ordinal": b.ordinal,
                "contribution_class": b.contribution_class,
                "byte_verified": b.byte_verified,
                "traced": b.traced,
            }
            for b in view.bites
        ],
    }


def export_document_companion(
    db_path: str,
    *,
    owner_user_id: str,
    document_id: str,
    events_dir: str | None = None,
) -> tuple[str, Any, str]:
    """Rebuild + render + EXPORT the per-document companion beside the
    research artifacts (paths.py conventions: validated ids, bounded reads).
    The honesty header rides the file's head: generated-never-authored, the
    sources, the source-derived rebuild stamp. Returns (html, path, stamp).

    NO artifact event here — rebuild triggers are SPR-03's wiring; the
    export is a manual/API rebuild only."""
    from substrate.research_artifact.paths import companion_path_for

    html, view = rebuild_document_full(
        db_path,
        owner_user_id=owner_user_id,
        document_id=document_id,
        events_dir=events_dir,
    )
    header = (
        "<!-- generated: never authored · sources: graph nodes, event log, "
        "anchors, diligence, reading state · rebuilt_at: "
        f"{view.rebuilt_at} · rebuilt on demand — edit the sources, never "
        "this file -->\n"
    )
    out = companion_path_for(document_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + html, encoding="utf-8")
    return header + html, out, view.rebuilt_at
