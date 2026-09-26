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

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from runtime.db_lock import ReadConnection

__all__ = ["maybe_reuse_prior_knowledge_at_start"]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return (dot / (na * nb)) if na and nb else 0.0


def _supplement_units_from_index(
    con: Any,
    model: Any,
    units: list[Any],
    node_ids: list[str],
    question_text: str,
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
    query_vec = [float(x) for x in model.encode(question_text)]
    out = list(units)
    for nid in node_ids:
        if nid in have:
            continue
        try:
            emb_row = con.execute(
                "SELECT embedding FROM nodes WHERE node_id = ? LIMIT 1", [nid]
            ).fetchone()
            if emb_row is None or emb_row[0] is None:
                continue
            unit = knowledge_unit_of(con, nid, score_groundedness=True)
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
                    similarity=_cosine(query_vec, [float(x) for x in emb_row[0]]),
                    content_class=None if cc_row is None else cc_row[0],
                    taken_down=False if cc_row is None else bool(cc_row[1]),
                )
            )
        except Exception:
            # A node the index refs but the graph can't project is skipped
            # honestly — the reuse path never crashes a start.
            continue
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
    registered = False
    resolved_db = ""
    try:
        import duckdb

        from processing.embedding import default_embedding_provider
        from runtime.db_lock import _register_local_writer, _unregister_local_writer
        from substrate.context_pack.knowledge_reuse import (
            assemble_context_pack_with_reuse,
            retrieve_prior_units,
        )
        from substrate.event_log import default_events_dir
        from substrate.graph import default_db_path
        from substrate.graph.retrieval_substrate import (
            make_substrate_from_con,
            resolve_reuse_substrate_kind,
        )

        resolved_db = db_path or default_db_path()
        resolved_events = events_dir or default_events_dir()
        model = embedding_provider or default_embedding_provider()

        # Prefer same-process RW (no flock) so we coexist with note-taker /
        # LazyRW writers. Cross-process (ops smoke while uvicorn holds the
        # file) falls back to connect_read — retrieve is read-only; emit only
        # touches the event log.
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
        # Companions SPR-01 — the evidence base's FIRST agent consumer: the
        # additive index query BEFORE the trajectory/graph re-walk. An absent
        # or empty index returns [] and changes NOTHING (the re-walk runs
        # exactly as today); live claim refs join the SAME gated pipeline as
        # supplemental candidates (the trust gate still decides downstream).
        from substrate.companions.evidence_index import query_claim_node_ids

        index_node_ids = query_claim_node_ids(
            parent,
            # The reuse hook runs substrate-side in the single-operator
            # deployment — the owner constant the graph schema defaults to.
            owner_user_id="__operator__",
            source_document_id=source_document_id,
        )
        units = retrieve_prior_units(
            substrate,
            question_text=question_text.strip(),
            source_document_id=source_document_id,
        )
        if index_node_ids:
            units = _supplement_units_from_index(
                parent, model, units, index_node_ids, question_text.strip()
            )
        result = assemble_context_pack_with_reuse(
            role=role,
            investigation_id=investigation_id,
            layers=[],
            units=units,
            events_dir=resolved_events,
            owner=True,
        )
        return getattr(result, "reuse_event_id", None)
    except Exception:
        return None
    finally:
        if parent is not None:
            with contextlib.suppress(Exception):
                parent.close()
        if registered and resolved_db:
            with contextlib.suppress(Exception):
                from runtime.db_lock import _unregister_local_writer

                _unregister_local_writer(resolved_db)
