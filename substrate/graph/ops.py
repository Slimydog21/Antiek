"""Graph insert operations — typed wrappers around SQL writes.

Every graph mutation passes through this module and emits the typed
event for it. The architecture_notes §2.1 typed-event invariant
requires the event log to be the source of truth; these helpers make
that property structural rather than a discipline.

What's here:

- ``insert_document``, ``insert_chunk``, ``insert_node``, ``insert_edge``
  — each takes a LockedConnection (write-locked per §2.3), writes the
  row, emits the typed event AFTER the row commits. Returns the
  generated id when one is computed from content.
- ``content_addressed_id`` helper for deriving stable ids from content
  hashes (SHA-256 prefix), matching the Researchmaxx convention.

What's not here:

- Bulk import (one-row-per-call by design; bulk paths land in
  processing/chunking and processing/extraction once those migrate).
- Embedding generation (the caller passes the embedding vector; the
  ``processing/embedding`` module owns generation).
- Tier classification (caller passes the tier; middleware/source_tier
  produces it).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

try:
    from ...constants import (
        PERSONAL_READING_CONTENT_CLASS,
        THIRD_PARTY_DOCUMENT_TYPES,
    )
    from ...event_log import emit_typed
    from ...runtime.db_lock import LockedConnection
    from ...schemas import (
        GraphEdgeInsertedPayload,
        GraphNodeInsertedPayload,
    )
    from ...schemas.events import DocumentContentClassDefaultedPayload
    from .embedding_meta import record_chunk_embedding_meta
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.constants import (  # type: ignore[no-redef]
        PERSONAL_READING_CONTENT_CLASS,
        THIRD_PARTY_DOCUMENT_TYPES,
    )
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.graph.embedding_meta import (  # type: ignore[no-redef]
        record_chunk_embedding_meta,
    )
    from substrate.schemas import (  # type: ignore[no-redef]
        GraphEdgeInsertedPayload,
        GraphNodeInsertedPayload,
    )
    from substrate.schemas.events import (  # type: ignore[no-redef]
        DocumentContentClassDefaultedPayload,
    )


# ---------------------------------------------------------------------------
# Id generators
# ---------------------------------------------------------------------------


def content_addressed_id(prefix: str, content: str, n: int = 16) -> str:
    """Stable id derived from a SHA-256 of ``content``. Matches the
    Researchmaxx ``<prefix>-<16hex>`` convention.

    Same content → same id, deterministically. The caller decides what
    counts as "the same" content via what they pass in."""
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:n]
    return f"{prefix}-{h}"


def new_random_id(prefix: str) -> str:
    """Allocate a fresh non-content-addressed id (uuid4 prefix)."""
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _maybe_json(obj: Any) -> str | None:
    """Render an optional metadata dict to its TEXT column form. The
    schema uses TEXT (not VARIANT) so application code is the only
    JSON reader; mirror the convention from middleware/archive."""
    if obj is None:
        return None
    if isinstance(obj, str):
        json.loads(obj)  # validate
        return obj
    return json.dumps(obj, default=str)


def _assert_write_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"graph ops require a LockedConnection (got {type(con).__name__}). "
            "Acquire via runtime.db_lock.connect_write(db_path, purpose=...). "
            "Architecture_notes §2.3: the only-writer invariant."
        )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


OnConflict = str  # "error" | "ignore"


def _exists(con: Any, table: str, id_col: str, id_val: str) -> bool:
    """Check whether a row with the given id exists. Used by
    ``on_conflict='ignore'`` paths to make inserts idempotent."""
    return con.execute(
        f"SELECT 1 FROM {table} WHERE {id_col} = ? LIMIT 1", [id_val]
    ).fetchone() is not None


def insert_document(
    con: LockedConnection,
    *,
    document_id: str,
    source_tier: int,
    document_type: str,
    source_uri: str | None = None,
    title: str | None = None,
    author: str | None = None,
    published_at: datetime | None = None,
    investigation_id: str | None = None,
    raw_text: str | None = None,
    metadata: Any | None = None,
    content_class: str | None = None,
    ip_holder_id: str | None = None,
    owner_user_id: str = "__operator__",
    on_conflict: OnConflict = "error",
    events_dir: str | None = None,
) -> str:
    """Insert one document row. Returns the document_id.

    Does not emit a typed event today — ``document.loaded`` already
    captures the ingestion-side signal from the reading UI surface,
    and a graph-level ``GRAPH_DOCUMENT_INSERTED`` would be redundant.
    If we later need a graph-scoped admission signal that's distinct
    from the surface-loaded event, we add it here as a new ActionType.

    ``content_class`` and ``ip_holder_id`` are the master-spec §9.0
    retrieval-time gate columns (schema.py V2). They default to ``None``
    so existing callers are unchanged; the gate in
    ``substrate/graph/search.py`` treats NULL content_class as legacy/
    grandfathered for chunk search, while the Read full-text serve gate
    (``substrate/books/serve.py``) is deny-by-default and treats NULL as
    metadata-only. The Read ingest path (``substrate/books/ingest.py``)
    always sets both — never relying on the NULL fallthrough.

    DENY-BY-DEFAULT GUARD (Personal-Reading Lane SPR-01 M5). For the
    third-party ingest connectors (urls / youtube / twitter / Substack), a NULL
    content_class is NOT acceptable: a NULL row passes the public chunk-search
    gate (search.py treats NULL as legacy/grandfathered) and would be reachable
    on the monetized read path — the §9.0 (Hachette / Bartz) leak. So when
    ``document_type in THIRD_PARTY_DOCUMENT_TYPES`` AND ``content_class is None``,
    this function writes ``content_class='personal_reading'`` (the
    owner-readable / public-non-servable lane) instead of NULL, and emits a
    ``document.content_class_defaulted`` typed event recording the defaulting.
    Two scoping rules keep this tight and reversible:
      * EXPLICIT BEATS DEFAULT — if the caller passes any ``content_class``
        (including a positive servable basis from a future connector, e.g. a
        verified public_domain Project Gutenberg text), the guard does NOT
        override it.
      * GENUINE UPLOADS ARE UNTOUCHED — a non-third-party ``document_type``
        (book / paper / a real user_owned upload) with ``content_class=None``
        still writes NULL exactly as before; the schema default is NOT flipped
        (flipping it would mislabel real operator content as non-servable). The
        guard is scoped to the four third-party types only.
    The event fires ONLY on a genuine insert — the ``on_conflict='ignore'``
    early-return below short-circuits before the guard, so re-inserting an
    existing row never re-emits the defaulting event. The event carries
    document_id + document_type + the applied content_class, NEVER raw_text
    (§9.0: events carry no body).

    ``on_conflict``:
      - ``"error"`` (default): a duplicate ``document_id`` raises.
      - ``"ignore"``: silently skip if a row with that ``document_id``
        already exists. Used by the wrestling bridge to keep
        ``document.loaded`` handling idempotent.
    """
    _assert_write_locked(con)
    if not 1 <= source_tier <= 5:
        raise ValueError(f"source_tier must be 1..5, got {source_tier}")
    if on_conflict == "ignore" and _exists(con, "documents", "document_id", document_id):
        return document_id

    # Deny-by-default: a third-party document_type with no explicit content_class
    # lands personal_reading (never NULL-that-serves). Explicit always beats
    # default; non-third-party types are untouched (NULL stays NULL).
    defaulted_to_personal_reading = (
        content_class is None and document_type in THIRD_PARTY_DOCUMENT_TYPES
    )
    if defaulted_to_personal_reading:
        content_class = PERSONAL_READING_CONTENT_CLASS

    con.execute(
        "INSERT INTO documents "
        "(document_id, source_uri, title, author, published_at, "
        " source_tier, document_type, investigation_id, raw_text, metadata, "
        " content_class, ip_holder_id, owner_user_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            document_id, source_uri, title, author, published_at,
            int(source_tier), document_type, investigation_id, raw_text,
            _maybe_json(metadata), content_class, ip_holder_id, owner_user_id,
        ],
    )

    # Typed event AFTER the row commits (and only on a real insert) — records the
    # deny-by-default classification so it is reconstructable. The Event envelope
    # requires a non-null investigation_id; use the document's investigation_id
    # when present, else a stable ingest-scoped id so the event is still
    # discoverable on the log. NEVER carries raw_text (§9.0).
    if defaulted_to_personal_reading:
        emit_typed(
            investigation_id or f"ingest-{document_id}",
            DocumentContentClassDefaultedPayload(
                document_type=document_type,
                applied_content_class=PERSONAL_READING_CONTENT_CLASS,
            ),
            role="connector",
            document_id=document_id,
            events_dir=events_dir,
        )
    return document_id


# Secondary indexes on the documents gate columns. DuckDB 1.5.2 cannot
# UPDATE a secondary-indexed column on a row that is the target of a
# foreign key (chunks + book_assets both reference documents.document_id):
# it rejects the implied delete-half of its delete+reinsert update path
# with "key still referenced by a foreign key". Unindexed columns
# (raw_text, title) update fine. update_document_gate_columns works around
# this by dropping the affected index(es), running the UPDATE, and
# recreating them — atomic under the single write lock.
_GATE_COLUMN_INDEXES: dict[str, str] = {
    "content_class": "idx_documents_content_class",
    "ip_holder_id": "idx_documents_ip_holder",
}


def update_document_gate_columns(
    con: LockedConnection,
    document_id: str,
    *,
    content_class: str | None = None,
    ip_holder_id: str | None = None,
    set_content_class: bool = False,
    set_ip_holder_id: bool = False,
    null_raw_text: bool = False,
) -> None:
    """Mutate a document's retrieval-time gate columns post-ingest.

    Use the ``set_*`` flags to update a column to a value (including
    ``None``); a column is left untouched unless its flag is True. This is
    the ONLY sanctioned way to change ``content_class`` / ``ip_holder_id``
    on a document that already has chunks or a book_assets row — a raw
    ``UPDATE documents SET content_class=…`` fails on DuckDB 1.5.2 (see the
    comment above ``_GATE_COLUMN_INDEXES``).

    ``null_raw_text=True`` additionally nulls ``raw_text`` (the takedown
    purge). raw_text is unindexed, so it doesn't need the index dance, but
    it rides the same single UPDATE for atomicity.

    All of this runs on the passed ``LockedConnection`` so it inherits the
    single-writer lock; the index drop/recreate is invisible to readers
    (DuckDB DDL is transactional).
    """
    _assert_write_locked(con)
    sets: list[str] = []
    params: list[Any] = []
    touched_indexed: list[str] = []
    if set_content_class:
        sets.append("content_class = ?")
        params.append(content_class)
        touched_indexed.append("content_class")
    if set_ip_holder_id:
        sets.append("ip_holder_id = ?")
        params.append(ip_holder_id)
        touched_indexed.append("ip_holder_id")
    if null_raw_text:
        sets.append("raw_text = NULL")
    if not sets:
        return
    params.append(document_id)

    indexes = [_GATE_COLUMN_INDEXES[c] for c in touched_indexed]
    for idx in indexes:
        con.execute(f"DROP INDEX IF EXISTS {idx}")
    try:
        con.execute(
            f"UPDATE documents SET {', '.join(sets)} WHERE document_id = ?",
            params,
        )
    finally:
        # Recreate even if the UPDATE raised, so a failed mutation never
        # leaves the table without its gate indexes.
        for col, idx in zip(touched_indexed, indexes, strict=True):
            con.execute(
                f"CREATE INDEX IF NOT EXISTS {idx} ON documents({col})"
            )


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------


def insert_chunk(
    con: LockedConnection,
    *,
    document_id: str,
    chunk_index: int,
    text: str,
    section_path: str | None = None,
    embedding: Sequence[float] | None = None,
    embedding_provider: Any | None = None,
    token_count: int = 0,
    chunk_id: str | None = None,
) -> str:
    """Insert one chunk row. If ``chunk_id`` is not provided, a
    content-addressed id is derived from the chunk text (matches the
    Researchmaxx SHA-256 convention). Returns the chunk_id.

    No typed event today — chunk insertion is a processing-layer
    artifact; if RL trajectory analytics needs per-chunk events later
    we can add ``GRAPH_CHUNK_INSERTED`` then.
    """
    _assert_write_locked(con)
    cid = chunk_id or content_addressed_id("chunk", text)
    if _exists(con, "chunks", "chunk_id", cid):
        # Idempotent — content-addressed ids make duplicate inserts a
        # no-op rather than a CHECK violation.
        return cid
    con.execute(
        "INSERT INTO chunks "
        "(chunk_id, document_id, chunk_index, section_path, text, embedding, token_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            cid, document_id, int(chunk_index), section_path, text,
            list(embedding) if embedding is not None else None,
            int(token_count),
        ],
    )
    if embedding is not None and embedding_provider is not None:
        record_chunk_embedding_meta(con, chunk_id=cid, provider=embedding_provider)
    return cid


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def insert_node(
    con: LockedConnection,
    *,
    canonical_label: str,
    node_type: str,  # NodeType Literal — validated at payload time
    graph_scope: str,  # GraphScope Literal — validated at payload time
    investigation_id: str,
    embedding: Sequence[float] | None = None,
    metadata: Any | None = None,
    node_id: str | None = None,
    parent_event_id: str | None = None,
    on_conflict: OnConflict = "error",
    events_dir: str | None = None,
    owner_user_id: str | None = None,
    emit_event: bool = True,
) -> str:
    """Insert one node row AND emit GRAPH_NODE_INSERTED. Returns the
    node_id.

    Id allocation: if ``node_id`` is not provided, a content-addressed
    id is derived from ``canonical_label|node_type|graph_scope``. Same
    triple → same id, so callers using ``on_conflict='ignore'`` get
    full idempotency (no duplicate event either)."""
    _assert_write_locked(con)
    nid = node_id or content_addressed_id("node", f"{canonical_label}|{node_type}|{graph_scope}")
    if on_conflict == "ignore" and _exists(con, "nodes", "node_id", nid):
        return nid  # row exists; no INSERT, no event — fully idempotent
    con.execute(
        "INSERT INTO nodes "
        "(node_id, canonical_label, node_type, embedding, graph_scope, metadata, owner_user_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            nid, canonical_label, node_type,
            list(embedding) if embedding is not None else None,
            graph_scope, _maybe_json(metadata), owner_user_id,
        ],
    )
    # Typed event AFTER the row commits — the Pydantic Literal validators
    # on node_type and graph_scope raise here if the caller passed
    # something the DB CHECK would also reject. We get both layers.
    if emit_event:
        emit_typed(
            investigation_id,
            GraphNodeInsertedPayload(
                node_id=nid,
                canonical_label=canonical_label,
                node_type=node_type,  # type: ignore[arg-type]
                graph_scope=graph_scope,  # type: ignore[arg-type]
                has_embedding=embedding is not None,
            ),
            parent_event_id=parent_event_id,
            role="connector",
            events_dir=events_dir,
        )
    return nid


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def insert_edge(
    con: LockedConnection,
    *,
    source_node_id: str,
    target_node_id: str,
    relation: str,
    source_tier: int,
    extraction_confidence: float,
    graph_scope: str,
    investigation_id: str,
    chunk_id: str | None = None,
    source_document_id: str | None = None,
    valid_from: datetime | None = None,
    metadata: Any | None = None,
    edge_id: str | None = None,
    parent_event_id: str | None = None,
    on_conflict: OnConflict = "error",
    emit_event: bool = True,
) -> str:
    """Insert one edge row AND emit GRAPH_EDGE_INSERTED. Returns the
    edge_id.

    Id allocation: if ``edge_id`` is not provided, a content-addressed
    id is derived from ``(source_node_id, relation, target_node_id,
    chunk_id)``. Tying chunk_id into the hash means the same triple
    from different chunks gets distinct ids — that's the desired
    behavior for evidence-attributed graphs."""
    _assert_write_locked(con)
    eid = edge_id or content_addressed_id(
        "edge",
        f"{source_node_id}|{relation}|{target_node_id}|{chunk_id or '-'}",
    )
    if on_conflict == "ignore" and _exists(con, "edges", "edge_id", eid):
        return eid
    con.execute(
        "INSERT INTO edges "
        "(edge_id, source_node_id, target_node_id, relation, chunk_id, "
        " source_document_id, source_tier, extraction_confidence, valid_from, "
        " graph_scope, investigation_id, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            eid, source_node_id, target_node_id, relation, chunk_id,
            source_document_id, int(source_tier), float(extraction_confidence),
            valid_from or datetime(1970, 1, 1),
            graph_scope, investigation_id, _maybe_json(metadata),
        ],
    )
    if emit_event:
        emit_typed(
            investigation_id,
            GraphEdgeInsertedPayload(
            edge_id=eid,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation=relation,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            source_tier=int(source_tier),
            extraction_confidence=float(extraction_confidence),
            graph_scope=graph_scope,  # type: ignore[arg-type]
            ),
            parent_event_id=parent_event_id,
            role="connector",
        )
    return eid


# ---------------------------------------------------------------------------
# Deliverables (Sprint 13 — creation surface)
# ---------------------------------------------------------------------------


_DELIVERABLE_KINDS = (
    "research_memo", "book_chapter", "biography_section",
    "investor_brief", "general_essay",
)


def insert_deliverable(
    con: LockedConnection,
    *,
    title: str,
    deliverable_kind: str,
    investigation_root_id: str | None = None,
    owner_user_id: str = "__operator__",
    metadata: Any | None = None,
    deliverable_id: str | None = None,
) -> str:
    """Create a new deliverable (operator-facing document being
    assembled). Returns its ``deliverable_id``."""
    _assert_write_locked(con)
    if deliverable_kind not in _DELIVERABLE_KINDS:
        raise ValueError(
            f"deliverable_kind must be one of {_DELIVERABLE_KINDS}, "
            f"got {deliverable_kind!r}"
        )
    did = deliverable_id or new_random_id("dlv")
    con.execute(
        "INSERT INTO deliverables "
        "(deliverable_id, title, deliverable_kind, investigation_root_id, "
        " owner_user_id, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [did, title, deliverable_kind, investigation_root_id,
         owner_user_id, _maybe_json(metadata)],
    )
    return did


def insert_section(
    con: LockedConnection,
    *,
    deliverable_id: str,
    section_index: int,
    title: str | None = None,
    parent_section_id: str | None = None,
    prose_text: str | None = None,
    prose_provenance: Any | None = None,
    section_id: str | None = None,
) -> str:
    """Insert one section under a deliverable. Returns ``section_id``."""
    _assert_write_locked(con)
    sid = section_id or new_random_id("sec")
    con.execute(
        "INSERT INTO deliverable_sections "
        "(section_id, deliverable_id, parent_section_id, section_index, "
        " title, prose_text, prose_provenance) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [sid, deliverable_id, parent_section_id, int(section_index),
         title, prose_text, _maybe_json(prose_provenance)],
    )
    return sid


def attach_block_to_section(
    con: LockedConnection,
    *,
    section_id: str,
    block_kind: str,
    block_id: str,
    block_index: int,
) -> None:
    """Attach an insight/claim/note block to a section in a specific
    order. Idempotent: PRIMARY KEY collision raises, caller should
    handle reordering via update_section_block_index."""
    _assert_write_locked(con)
    if block_kind not in ("insight", "open_question", "operator_note", "claim"):
        raise ValueError(f"unknown block_kind: {block_kind!r}")
    con.execute(
        "INSERT INTO section_blocks "
        "(section_id, block_kind, block_id, block_index) "
        "VALUES (?, ?, ?, ?)",
        [section_id, block_kind, block_id, int(block_index)],
    )


# Sentinel distinguishing a prose edit from generation with a fresh map.
_PRESERVE_PROVENANCE: Any = object()
_NO_EXPECTED_PROSE: Any = object()


class ProseConflictError(ValueError):
    """The caller edited a prose version that is no longer current."""


def update_section_prose(
    con: LockedConnection,
    *,
    section_id: str,
    prose_text: str,
    prose_provenance: Any = _PRESERVE_PROVENANCE,
    unsupported_paragraphs: set[int] | None = None,
    expected_prose: Any = _NO_EXPECTED_PROSE,
    mutation_origin: str = "manual",
) -> dict[str, Any]:
    """Persist generated/edited prose for a section.

    Fresh generation supplies provenance and an exact validity document.
    Prose-only edits preserve only unambiguous, byte-identical paragraphs and
    invalidate every changed paragraph. ``expected_prose`` is an optional
    compare-and-swap precondition; the HTTP edit path always supplies it."""
    _assert_write_locked(con)
    from substrate.write.provenance_validity import (
        edited_provenance,
        generated_validity,
        outline_fingerprint,
        read_validity,
    )

    row = con.execute(
        "SELECT s.prose_text, s.prose_provenance, v.validity_json "
        "FROM deliverable_sections s LEFT JOIN "
        "deliverable_section_provenance_validity v ON v.section_id = s.section_id "
        "WHERE s.section_id = ?",
        [section_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"section not found: {section_id}")
    old_prose = row[0] or ""
    if expected_prose is not _NO_EXPECTED_PROSE and old_prose != (expected_prose or ""):
        raise ProseConflictError("section prose changed since the caller loaded it")
    if prose_text == old_prose and prose_provenance is _PRESERVE_PROVENANCE:
        validity = read_validity(old_prose, _decode_json_map(row[1]), row[2])
        return {"changed": False, "prose_provenance": _decode_json_map(row[1]), "validity": validity}

    if prose_provenance is _PRESERVE_PROVENANCE:
        old_provenance = _decode_json_map(row[1])
        old_validity = read_validity(old_prose, old_provenance, row[2])
        next_provenance, validity = edited_provenance(
            old_prose=old_prose,
            new_prose=prose_text,
            old_provenance=old_provenance,
            old_validity=old_validity,
            origin="ai_assisted" if mutation_origin == "ai_assisted" else "manual",
        )
    else:
        next_provenance = _decode_json_map(prose_provenance)
        validity = generated_validity(
            prose_text,
            next_provenance or {},
            unsupported_paragraphs=unsupported_paragraphs,
            outline_sha256=outline_fingerprint(con, section_id),
        )
    con.execute(
        "UPDATE deliverable_sections SET prose_text = ?, prose_provenance = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE section_id = ?",
        [prose_text, _maybe_json(next_provenance), section_id],
    )
    con.execute(
        "INSERT INTO deliverable_section_provenance_validity "
        "(section_id, validity_json, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (section_id) DO UPDATE SET validity_json = EXCLUDED.validity_json, "
        "updated_at = EXCLUDED.updated_at",
        [section_id, _maybe_json(validity), datetime.now(UTC)],
    )
    return {"changed": True, "prose_provenance": next_provenance, "validity": validity}


def _decode_json_map(raw: Any) -> dict[str, list[str]] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    return {
        str(key): list(blocks)
        for key, blocks in value.items()
        if isinstance(blocks, list) and all(isinstance(block, str) for block in blocks)
    }


# ---------------------------------------------------------------------------
# Interviews (Sprint 16 — DeepBlu Mode 2)
# ---------------------------------------------------------------------------


def insert_interview_project(
    con: LockedConnection,
    *,
    title: str,
    topic_description: str | None = None,
    deliverable_id: str | None = None,
    interview_guide: Any | None = None,
    owner_user_id: str = "__operator__",
    project_id: str | None = None,
) -> str:
    """Create a new interview project. Returns the ``project_id``."""
    _assert_write_locked(con)
    pid = project_id or new_random_id("ivp")
    con.execute(
        "INSERT INTO interview_projects "
        "(project_id, title, topic_description, deliverable_id, "
        " interview_guide, owner_user_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [pid, title, topic_description, deliverable_id,
         _maybe_json(interview_guide), owner_user_id],
    )
    return pid


def insert_interview(
    con: LockedConnection,
    *,
    project_id: str,
    informant_handle: str | None = None,
    informant_email: str | None = None,
    interview_id: str | None = None,
) -> str:
    """Invite an informant; creates an ``invited``-status row."""
    _assert_write_locked(con)
    iid = interview_id or new_random_id("intv")
    con.execute(
        "INSERT INTO interviews "
        "(interview_id, project_id, informant_handle, informant_email, "
        " status) VALUES (?, ?, ?, ?, 'invited')",
        [iid, project_id, informant_handle, informant_email],
    )
    return iid


def append_interview_turn(
    con: LockedConnection,
    *,
    interview_id: str,
    role: str,  # "interviewer" | "informant"
    text: str,
) -> int:
    """Append one turn to the interview transcript. Returns the new
    turn count. Promotes the status from ``invited`` to
    ``in_progress`` on the first turn."""
    _assert_write_locked(con)
    if role not in ("interviewer", "informant"):
        raise ValueError(f"unknown turn role: {role!r}")
    row = con.execute(
        "SELECT transcript_turns, status FROM interviews "
        "WHERE interview_id = ?", [interview_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"interview {interview_id!r} not found")
    existing_json, status = row
    turns = []
    if existing_json:
        try:
            turns = json.loads(existing_json)
        except (TypeError, ValueError):
            turns = []
    turns.append({
        "role": role,
        "text": text,
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    })
    new_status = "in_progress" if status == "invited" else status
    started_at_sql = "CURRENT_TIMESTAMP" if status == "invited" else "started_at"
    con.execute(
        f"UPDATE interviews SET transcript_turns = ?, status = ?, "
        f"started_at = {started_at_sql} WHERE interview_id = ?",
        [_maybe_json(turns), new_status, interview_id],
    )
    return len(turns)


def complete_interview(
    con: LockedConnection,
    *,
    interview_id: str,
    transcript_document_id: str | None = None,
) -> None:
    """Mark interview complete and link to its transcript document."""
    _assert_write_locked(con)
    con.execute(
        "UPDATE interviews SET status = 'completed', "
        "completed_at = CURRENT_TIMESTAMP, transcript_document_id = ? "
        "WHERE interview_id = ?",
        [transcript_document_id, interview_id],
    )
