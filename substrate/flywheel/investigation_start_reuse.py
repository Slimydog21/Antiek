"""Investigation-start knowledge reuse (AFF SPR-06) for Loop One / spin-research.

HostLocalRunner (cascade) already calls ``assemble_context_pack_with_reuse``
when a RetrievalSubstrate is injected. Mini dogfood's daily path is
spin-research → Loop One, which never touched the reuse half — so
``/health`` stayed at ``flywheel_ready=false`` / ``knowledge_reuse_count=0``
despite a populated insight graph.

This module is the single-writer-safe reuse burst for that path:

* Opens one plain read-write DuckDB handle (NO ``connect_write`` flock) so it
  coexists with the note-taker / funnel writers in the same process — same
  config as ``interfaces.research.api.cascade_routes._LazyReuseSubstrate``.
* Retrieves prior units, assembles a reuse pack, emits ``knowledge.reused``
  (including empty inject — reuse-of-nothing is recorded).
* Closes the handle before returning so subsequent ``connect_read`` callers
  are not starved.

Best-effort: any failure returns None and never raises into the orchestrator.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from runtime.db_lock import ReadConnection

__all__ = ["maybe_reuse_prior_knowledge_at_start"]


@dataclass
class _PendingReuseCleanup:
    parent: Any
    child: Any | None
    registered: bool
    child_closed: bool = False
    parent_closed: bool = False
    terminal: bool = False


# Serialize one database's whole read/cleanup attempt. A failed close retains
# the actual handles, not merely the writer-registration count.
_REUSE_LOCKS_GUARD = threading.Lock()
_REUSE_LOCKS: dict[str, threading.Lock] = {}
_PENDING_REUSE_CLEANUP: dict[str, _PendingReuseCleanup] = {}


def _reuse_lock(db_identity: str) -> threading.Lock:
    with _REUSE_LOCKS_GUARD:
        return _REUSE_LOCKS.setdefault(db_identity, threading.Lock())


def _finish_reuse_cleanup(db_identity: str, state: _PendingReuseCleanup) -> Exception | None:
    """Called only under this database's lock; busy may be retried next start."""
    from runtime.db_lock import _unregister_local_writer
    from substrate.graph.retrieval_substrate import SnapshotBusyError

    if state.terminal:
        return RuntimeError("previous reuse cleanup is terminal and uncertain")
    if not state.child_closed:
        try:
            if state.child is not None:
                state.child.close()
        except Exception as exc:
            if not isinstance(exc, SnapshotBusyError):
                state.terminal = True
            return exc
        state.child_closed = True
        state.child = None
    if not state.parent_closed:
        try:
            state.parent.close()
        except Exception as exc:
            state.terminal = True
            return exc
        state.parent_closed = True
    if state.registered:
        try:
            _unregister_local_writer(db_identity)
        except Exception as exc:
            state.terminal = True
            return exc
        state.registered = False
    _PENDING_REUSE_CLEANUP.pop(db_identity, None)
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return (dot / (na * nb)) if na and nb else 0.0


def _supplement_units_from_index(
    con: Any,
    query_vec: tuple[float, ...],
    units: list[Any],
    node_ids: list[str],
) -> list[Any]:
    """Companions SPR-01's additive supplement: the evidence index's claim
    refs join the reuse pipeline as RetrievedUnits (the SAME
    ``knowledge_unit_of`` projection + the REAL cosine vs the question, the
    content-class join mirroring retrieve_prior_units). A vanished or
    ungrounded node skips honestly; the trust gate decides downstream —
    the index never forces an injection."""
    from substrate.context_pack.knowledge_reuse import RetrievedUnit
    from substrate.graph.insight_question import knowledge_unit_of

    have = {u.unit_id for u in units}
    out = list(units)
    for nid in node_ids:
        if nid in have:
            continue
        emb_row = con.execute(
            "SELECT embedding FROM nodes WHERE node_id = ? LIMIT 1", [nid]
        ).fetchone()
        if emb_row is None or emb_row[0] is None:
            continue
        try:
            unit = knowledge_unit_of(con, nid, score_groundedness=True)
        except ValueError:
            continue
        cc_row = con.execute(
            "SELECT d.content_class, COALESCE(b.taken_down, FALSE) "
            "FROM edges e JOIN documents d ON e.source_document_id = d.document_id "
            "LEFT JOIN book_assets b ON d.document_id = b.document_id "
            "WHERE e.source_node_id = ? AND e.relation = 'supported_by' "
            "AND e.source_document_id IS NOT NULL LIMIT 1",
            [nid],
        ).fetchone()
        out.append(
            RetrievedUnit(
                unit=unit,
                similarity=_cosine(list(query_vec), [float(x) for x in emb_row[0]]),
                content_class=None if cc_row is None else cc_row[0],
                taken_down=False if cc_row is None else bool(cc_row[1]),
            )
        )
    return out


def maybe_reuse_prior_knowledge_at_start(
    *,
    investigation_id: str,
    question_text: str,
    db_path: str | None = None,
    events_dir: str | None = None,
    role: str = "decomposer",
    embedding_provider: Any | None = None,
    source_document_id: str | None = None,
) -> str | None:
    """Run AFF SPR-06 reuse once for an investigation start.

    Returns the ``knowledge.reused`` event id when emitted, else None.
    """
    if not investigation_id or not (question_text or "").strip():
        return None
    parent: ReadConnection | None = None
    substrate: Any | None = None
    registered = False
    resolved_db = ""
    units: list[Any] = []
    work_error: Exception | None = None
    cleanup_error: Exception | None = None
    db_identity = ""
    path_lock: threading.Lock | None = None
    try:
        import duckdb

        from processing.embedding import default_embedding_provider
        from runtime.db_lock import _db_identity, _register_local_writer
        from substrate.context_pack.knowledge_reuse import (
            DEFAULT_RETRIEVE_LIMIT,
            _materialize_prior_units_from_snapshot,
            _usable_reuse_snapshot,
        )
        from substrate.event_log import default_events_dir
        from substrate.graph import default_db_path
        from substrate.graph.retrieval_substrate import (
            make_substrate_from_con,
            resolve_reuse_substrate_kind,
        )

        resolved_db = db_path or default_db_path()
        db_identity = _db_identity(resolved_db)
        path_lock = _reuse_lock(db_identity)
        path_lock.acquire()
        prior = _PENDING_REUSE_CLEANUP.get(db_identity)
        if prior is not None:
            prior_error = _finish_reuse_cleanup(db_identity, prior)
            if prior_error is not None:
                raise RuntimeError("previous reuse cleanup remains unresolved") from prior_error
        resolved_events = events_dir or default_events_dir()
        model = embedding_provider or default_embedding_provider()
        try:
            parent = duckdb.connect(resolved_db)
            _register_local_writer(resolved_db)
            registered = True
        except Exception:
            from runtime.db_lock import connect_read

            parent = connect_read(resolved_db)
            registered = False
        kind = resolve_reuse_substrate_kind()
        substrate = make_substrate_from_con(
            kind, parent, model=model, db_path=resolved_db,
        )
        query_snapshot = getattr(substrate, "query_snapshot", None)
        if callable(query_snapshot):
            from substrate.companions.evidence_index import query_claim_node_ids

            with query_snapshot(
                question_text.strip(), top_k=DEFAULT_RETRIEVE_LIMIT,
                policy_tag="attribution_eligible",
            ) as snapshot:
                query_vec = snapshot.query_vector
                if query_vec is not None and _usable_reuse_snapshot(snapshot):
                    index_node_ids = query_claim_node_ids(
                        snapshot.con,
                        owner_user_id="__operator__",
                        source_document_id=source_document_id,
                    )
                    units = _materialize_prior_units_from_snapshot(
                        snapshot, limit=DEFAULT_RETRIEVE_LIMIT,
                        source_document_id=source_document_id,
                    )
                    if index_node_ids:
                        units = _supplement_units_from_index(
                            snapshot.con, query_vec, units, index_node_ids,
                        )
    except Exception as exc:
        work_error = exc
    finally:
        try:
            if parent is not None:
                state = _PendingReuseCleanup(parent, substrate, registered)
                _PENDING_REUSE_CLEANUP[db_identity] = state
                cleanup_error = _finish_reuse_cleanup(db_identity, state)
        finally:
            if path_lock is not None:
                path_lock.release()
    if work_error is not None or cleanup_error is not None:
        if work_error is not None and cleanup_error is not None:
            work_error.add_note(f"reuse cleanup also failed: {cleanup_error!r}")
        logging.getLogger(__name__).warning(
            "knowledge reuse read or cleanup failed: work=%r cleanup=%r",
            work_error, cleanup_error,
        )
        return None
    try:
        from substrate.context_pack.knowledge_reuse import assemble_context_pack_with_reuse

        result = assemble_context_pack_with_reuse(
            role=role, investigation_id=investigation_id, layers=[], units=units,
            events_dir=resolved_events, owner=True,
        )
        return getattr(result, "reuse_event_id", None)
    except Exception:
        logging.getLogger(__name__).exception("knowledge reuse event assembly failed")
        return None
