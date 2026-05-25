"""DRW SPR-01 — promotion of insights and questions to graph nodes.

``promote_insight`` / ``promote_question`` are the **only** sanctioned
writers of ``node_type='insight'`` / ``'question'`` rows. They turn a
distilled note (``note.emerged``) or an identified question
(``question.identified``) into a first-class graph node — with an
embedding and provenance edges drawn from the controlled
``INSIGHT_QUESTION_RELATIONS`` vocabulary — so the rest of the Deep
Research Workspace can traverse, join, and similarity-search them.

Design choices (see also docs/decisions if promoted to canon):

* **Single writer.** Every node + its edges are written through
  ``runtime/db_lock.connect_write``. When the caller passes its own
  ``LockedConnection`` (the backfill, the SPR-02 promotion funnel) it
  owns the transaction boundary; when it does not, this module acquires
  a fresh write-locked connection and commits node+edges **atomically**
  so there is never a node-without-its-edges intermediate state.

* **Dedup identity = content hash of normalized text.** The node id is
  ``content_addressed_id(node_type, canonical_text)`` where
  ``canonical_text`` is the insight/question text lower-cased with
  whitespace collapsed and stripped. Re-emitting the same note (same
  text, modulo case/whitespace) resolves to the same node id; with
  ``on_conflict='ignore'`` that is a no-op — no duplicate row, no
  duplicate ``GRAPH_NODE_INSERTED`` event. The hash is SHA-256 truncated
  to 16 hex chars (64 bits). At the corpus scale this product targets
  (≤ 10^6 notes), the birthday-bound collision probability is
  ~N²/2^65 ≈ 3×10⁻⁸ — negligible, and a collision degrades to "two
  distinct insights share a node", caught downstream by text inequality,
  never silent corruption.

* **Provenance the schema can actually hold.** Edges are node→node, so
  the investigation an insight came from rides on the
  ``GRAPH_NODE_INSERTED`` event envelope's ``investigation_id`` and in
  node ``metadata``; the grounding document/chunk rides on the
  ``supported_by`` edge's own ``source_document_id`` / ``chunk_id``
  columns. A cited node that no longer exists (deleted claim) is a
  **dangling edge** — we skip it and record the skip in metadata rather
  than fail the whole promotion (tombstone-not-cascade policy).

Promotion from events is **opt-in** via the ``enabled`` flag on
``promote_from_note_event`` / ``promote_from_question_event``. SPR-03
owns the always-on trigger; this sprint only builds the path.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional, Sequence, Tuple

try:
    from ...runtime.db_lock import LockedConnection, connect_write
    from ...constants import (
        DUCKDB_PATH,
        validate_insight_question_edge,
    )
    from .ops import content_addressed_id, insert_edge, insert_node
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]
    from substrate.constants import (  # type: ignore[no-redef]
        DUCKDB_PATH,
        validate_insight_question_edge,
    )
    from substrate.graph.ops import (  # type: ignore[no-redef]
        content_addressed_id,
        insert_edge,
        insert_node,
    )


# insight/question live in the primary in-domain ("depth") graph — not
# the cross_domain connector layer nor the constraint layer.
_PROMOTION_GRAPH_SCOPE = "depth"

# Map the note-taker's ConfidenceLevel string onto an edge
# extraction_confidence float (the edges table needs a 0..1 number).
_CONFIDENCE_TO_FLOAT = {
    "high": 0.9,
    "moderate": 0.7,
    "low": 0.5,
    "unknown": 0.5,
}


def graph_db_path() -> str:
    """Resolve the canonical graph DB path (``constants.DUCKDB_PATH`` with
    ``~`` expanded). The connect-our-own-connection fallback uses this."""
    return os.path.expanduser(DUCKDB_PATH)


def canonical_text(text: str) -> str:
    """Normalization for dedup identity: lower-case, collapse internal
    whitespace, strip. Documented so a future maintainer can reproduce
    the identity decision rather than guess it. ``str.split()`` collapses
    every run of whitespace (incl. newlines/tabs) to single spaces."""
    return " ".join(text.lower().split())


def insight_node_id(text: str) -> str:
    """Deterministic node id for an insight with this (normalized) text."""
    return content_addressed_id("insight", canonical_text(text))


def question_node_id(text: str) -> str:
    """Deterministic node id for a question with this (normalized) text."""
    return content_addressed_id("question", canonical_text(text))


def _node_type_of(con: LockedConnection, node_id: str) -> Optional[str]:
    row = con.execute(
        "SELECT node_type FROM nodes WHERE node_id = ? LIMIT 1", [node_id]
    ).fetchone()
    return row[0] if row else None


def _coerce_confidence_float(confidence: str) -> float:
    return _CONFIDENCE_TO_FLOAT.get(confidence, 0.5)


def _add_provenance_edges(
    con: LockedConnection,
    *,
    source_node_id: str,
    relation: str,
    targets: Sequence[str],
    investigation_id: str,
    source_tier: int,
    extraction_confidence: float,
    source_document_id: Optional[str],
    chunk_id: Optional[str],
) -> Tuple[list, list]:
    """Create ``relation`` edges from ``source_node_id`` to each target
    node, validating against the controlled vocabulary. Returns
    ``(written_edge_ids, skipped_dangling_targets)``. A target that does
    not exist is skipped (tombstone policy), not an error."""
    written: list = []
    dangling: list = []
    for target_id in targets:
        ttype = _node_type_of(con, target_id)
        if ttype is None:
            dangling.append(target_id)
            continue
        # Loud failure if the caller wires an out-of-vocabulary edge.
        validate_insight_question_edge(relation, _node_type_of_source(relation), ttype)
        eid = insert_edge(
            con,
            source_node_id=source_node_id,
            target_node_id=target_id,
            relation=relation,
            source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            graph_scope=_PROMOTION_GRAPH_SCOPE,
            investigation_id=investigation_id,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            on_conflict="ignore",
        )
        written.append(eid)
    return written, dangling


def _node_type_of_source(relation: str) -> str:
    """The source node_type a relation originates from (insight or
    question), per the vocabulary."""
    from ..constants import _INSIGHT_QUESTION_RELATION_BY_NAME  # type: ignore
    spec = _INSIGHT_QUESTION_RELATION_BY_NAME.get(relation)
    if spec is None:
        raise ValueError(f"unknown insight/question relation {relation!r}")
    return spec.source_type


def _with_connection(con: Optional[LockedConnection], purpose: str, fn):
    """Run ``fn(con)`` either on the caller's connection (caller owns the
    transaction) or on a fresh write-locked connection wrapped in an
    atomic BEGIN/COMMIT."""
    if con is not None:
        return fn(con)
    owned = connect_write(graph_db_path(), purpose=purpose)
    try:
        owned.execute("BEGIN")
        try:
            result = fn(owned)
            owned.execute("COMMIT")
            return result
        except Exception:
            try:
                owned.execute("ROLLBACK")
            except Exception:  # pragma: no cover
                pass
            raise
    finally:
        owned.close()


def promote_insight(
    *,
    text: str,
    investigation_id: str,
    confidence: str = "unknown",
    supported_by: Sequence[str] = (),
    source_document_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
    source_tier: int = 3,
    extraction_confidence: Optional[float] = None,
    embedding_provider: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    con: Optional[LockedConnection] = None,
) -> str:
    """Promote an insight to a first-class ``insight`` node. Returns the
    node id (stable, content-addressed — idempotent on re-promotion).

    ``supported_by`` is a sequence of *node ids* (claims/entities) the
    insight rests on; each becomes a ``supported_by`` edge carrying
    ``source_document_id`` + ``chunk_id`` for the originating source.
    """
    nid = insight_node_id(text)
    edge_conf = (
        extraction_confidence
        if extraction_confidence is not None
        else _coerce_confidence_float(confidence)
    )

    def _do(c: LockedConnection) -> str:
        node_meta: Dict[str, Any] = dict(metadata or {})
        node_meta.update(
            {
                "promoted_kind": "insight",
                "confidence": confidence,
                "canonical_text": canonical_text(text),
            }
        )
        emb = (embedding_provider or _default_provider()).encode(text)
        insert_node(
            c,
            canonical_label=text,
            node_type="insight",
            graph_scope=_PROMOTION_GRAPH_SCOPE,
            investigation_id=investigation_id,
            embedding=emb,
            metadata=node_meta,
            node_id=nid,
            on_conflict="ignore",
        )
        _written, dangling = _add_provenance_edges(
            c,
            source_node_id=nid,
            relation="supported_by",
            targets=supported_by,
            investigation_id=investigation_id,
            source_tier=source_tier,
            extraction_confidence=edge_conf,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )
        if dangling:
            _record_dangling(c, nid, "supported_by", dangling)
        return nid

    return _with_connection(con, "promote_insight", _do)


def promote_question(
    *,
    text: str,
    investigation_id: str,
    asks_about: Sequence[str] = (),
    resolved_by: Sequence[str] = (),
    anchor_region_id: Optional[str] = None,
    source_document_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
    source_tier: int = 3,
    extraction_confidence: float = 0.5,
    embedding_provider: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    con: Optional[LockedConnection] = None,
) -> str:
    """Promote a question to a first-class ``question`` node. Returns the
    node id (stable, content-addressed — idempotent on re-promotion).

    ``asks_about`` are node ids the question concerns; ``resolved_by`` are
    insight node ids that answer it.
    """
    nid = question_node_id(text)

    def _do(c: LockedConnection) -> str:
        node_meta: Dict[str, Any] = dict(metadata or {})
        node_meta.update({"promoted_kind": "question", "canonical_text": canonical_text(text)})
        if anchor_region_id:
            node_meta["anchor_region_id"] = anchor_region_id
        emb = (embedding_provider or _default_provider()).encode(text)
        insert_node(
            c,
            canonical_label=text,
            node_type="question",
            graph_scope=_PROMOTION_GRAPH_SCOPE,
            investigation_id=investigation_id,
            embedding=emb,
            metadata=node_meta,
            node_id=nid,
            on_conflict="ignore",
        )
        _w1, d1 = _add_provenance_edges(
            c, source_node_id=nid, relation="asks_about", targets=asks_about,
            investigation_id=investigation_id, source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            source_document_id=source_document_id, chunk_id=chunk_id,
        )
        _w2, d2 = _add_provenance_edges(
            c, source_node_id=nid, relation="resolved_by", targets=resolved_by,
            investigation_id=investigation_id, source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            source_document_id=source_document_id, chunk_id=chunk_id,
        )
        if d1:
            _record_dangling(c, nid, "asks_about", d1)
        if d2:
            _record_dangling(c, nid, "resolved_by", d2)
        return nid

    return _with_connection(con, "promote_question", _do)


def _record_dangling(con: LockedConnection, node_id: str, relation: str, targets: list) -> None:
    """Append skipped dangling targets into the node's metadata so the
    skip is auditable. Best-effort; failure here never fails promotion."""
    try:
        row = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ?", [node_id]
        ).fetchone()
        import json
        meta = {}
        if row and row[0]:
            try:
                meta = json.loads(row[0])
            except (TypeError, ValueError):
                meta = {}
        skipped = meta.get("skipped_dangling", {})
        skipped.setdefault(relation, [])
        for t in targets:
            if t not in skipped[relation]:
                skipped[relation].append(t)
        meta["skipped_dangling"] = skipped
        con.execute(
            "UPDATE nodes SET metadata = ? WHERE node_id = ?",
            [json.dumps(meta, default=str), node_id],
        )
    except Exception:  # pragma: no cover — metadata audit is best-effort
        pass


# ---------------------------------------------------------------------------
# Event → node wiring (opt-in; SPR-03 owns the always-on trigger)
# ---------------------------------------------------------------------------


def _event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """A trajectory row's payload is a dict (``trajectory`` already
    json.loads-es it). Tolerate a still-stringified payload defensively."""
    payload = event.get("payload")
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    return payload if isinstance(payload, dict) else {}


def promote_from_note_event(
    event: Dict[str, Any],
    *,
    con: Optional[LockedConnection] = None,
    enabled: bool = False,
    embedding_provider: Any = None,
) -> Optional[str]:
    """Promote a single ``note.emerged`` event into an insight node.

    Opt-in: returns ``None`` unless ``enabled=True`` (SPR-03 flips the
    always-on switch). The note's ``source_event_ids`` are recorded in
    node metadata (they reference events, not nodes, so they cannot be
    ``supported_by`` edges); document/claim-node grounding is the job of
    richer callers that pass ``supported_by`` explicitly.
    """
    if not enabled:
        return None
    payload = _event_payload(event)
    text = payload.get("note_text")
    if not isinstance(text, str) or not text.strip():
        return None
    investigation_id = event.get("investigation_id") or payload.get("investigation_id") or ""
    return promote_insight(
        text=text.strip(),
        investigation_id=investigation_id,
        confidence=payload.get("confidence", "unknown"),
        metadata={
            "source_event_ids": payload.get("source_event_ids", []),
            "origin_event_id": event.get("event_id"),
            "origin_note_id": payload.get("note_id"),
        },
        embedding_provider=embedding_provider,
        con=con,
    )


def promote_from_question_event(
    event: Dict[str, Any],
    *,
    con: Optional[LockedConnection] = None,
    enabled: bool = False,
    embedding_provider: Any = None,
) -> Optional[str]:
    """Promote a single ``question.identified`` event into a question
    node. Opt-in (see :func:`promote_from_note_event`)."""
    if not enabled:
        return None
    payload = _event_payload(event)
    text = payload.get("question_text")
    if not isinstance(text, str) or not text.strip():
        return None
    investigation_id = event.get("investigation_id") or payload.get("investigation_id") or ""
    return promote_question(
        text=text.strip(),
        investigation_id=investigation_id,
        anchor_region_id=payload.get("anchor_region_id"),
        metadata={
            "origin_event_id": event.get("event_id"),
            "origin_question_id": payload.get("question_id"),
        },
        embedding_provider=embedding_provider,
        con=con,
    )


# ---------------------------------------------------------------------------
# Embedding provider — reuse the claim-embedding path, no new wiring
# ---------------------------------------------------------------------------


def _default_provider():
    """The same provider claims use. Imported lazily so a test can install
    a hash provider via ANTIEK_EMBEDDING_PROVIDER=hash without paying the
    sentence-transformers import at module load."""
    from processing.embedding import default_embedding_provider
    return default_embedding_provider()
