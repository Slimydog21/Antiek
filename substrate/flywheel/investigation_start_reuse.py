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
from typing import Any

__all__ = ["maybe_reuse_prior_knowledge_at_start"]


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
    parent = None
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

        # Read-write, no flock — shares process DuckDB config with writers.
        # Register so concurrent connect_read sees a local writer (LazyRW).
        parent = duckdb.connect(resolved_db)
        _register_local_writer(resolved_db)
        registered = True
        kind = resolve_reuse_substrate_kind()
        substrate = make_substrate_from_con(
            kind, parent, model=model, db_path=resolved_db,
        )
        units = retrieve_prior_units(
            substrate,
            question_text=question_text.strip(),
            source_document_id=source_document_id,
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
