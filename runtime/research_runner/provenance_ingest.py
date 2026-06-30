"""RDR SPR-07 — provenance-complete ingestion for the research promotion funnel.

Persists each cited source as a readable ``Document`` (via ``ingest_url`` for
web refs, direct resolution for in-corpus chunks), dedups by normalized URL +
content hash (``substrate/graph/ops``), writes ``supported_by`` edges from
promoted insights to source anchors, and collects resolved refs for the cascade
synthesis artifact (M3/M4).

Single-writer: every graph mutation runs on the ``LockedConnection`` the
``PromotionFunnel`` already holds — no parallel writer is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from acquisition.urls.adapter import ingest_url, url_doc_id
from substrate.constants import CITES_RELATION
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import (
    document_body_hash,
    ensure_artifact_anchor_node,
    ensure_source_anchor_node,
    find_existing_source_document,
    insert_provenance_edge,
    normalize_source_url,
)
from .protocol import StepEvent

# Minimum word count for injected test HTML (``ingest_url`` gate).
_TEST_HTML_MIN_WORDS = (
    "Evidence snippet from a real web source about the topic. " * 12
)


@dataclass(frozen=True)
class ResolvedSource:
    """A source ref after ingestion / dedup — ready for edges + citations."""

    document_id: str
    chunk_id: str | None
    source_kind: str  # "local_chunk" | "web_url"
    url: str | None = None
    ingest_skipped: str | None = None  # honest skip reason (failed fetch, etc.)


@dataclass
class PromotionProvenanceState:
    """Per-funnel accumulator: promoted findings + resolved sources for M3."""

    findings: list[dict[str, Any]] = field(default_factory=list)
    resolved_by_investigation: dict[str, list[ResolvedSource]] = field(
        default_factory=dict,
    )


def _default_test_html(url: str) -> str:
    return (
        f"<html><head><title>Web Source</title></head><body>"
        f"<article><h1>Source</h1><p>{_TEST_HTML_MIN_WORDS}</p>"
        f"<p>Canonical: {url}</p></article></body></html>"
    )


def _resolve_local_source(
    con: Any,
    *,
    document_id: str,
    chunk_id: str | None,
) -> ResolvedSource | None:
    row = con.execute(
        "SELECT 1 FROM documents WHERE document_id = ?", [document_id],
    ).fetchone()
    if row is None:
        return None
    resolved_chunk = chunk_id
    if not resolved_chunk:
        crow = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ? "
            "ORDER BY chunk_index ASC LIMIT 1",
            [document_id],
        ).fetchone()
        resolved_chunk = str(crow[0]) if crow else None
    if not resolved_chunk:
        return None
    return ResolvedSource(
        document_id=document_id,
        chunk_id=resolved_chunk,
        source_kind="local_chunk",
    )


def _resolve_web_source(
    con: Any | None,
    *,
    url: str,
    investigation_id: str,
    embedding_provider: Any | None,
    url_fetcher: Callable[[str], Any] | None,
    db_path: str | None = None,
) -> ResolvedSource:
    """Ingest or dedup a web URL. Never raises — returns skip reason on failure.

    DuckDB rejects concurrent read+write handles on the same file — the dedup
    probe may use ``con`` (read), but ``ingest_url`` runs with NO other handle
    open."""
    normalized = normalize_source_url(url)
    fetched = None
    if url_fetcher is not None:
        try:
            fetched = url_fetcher(url)
        except Exception as exc:
            return ResolvedSource(
                document_id=url_doc_id(normalized),
                chunk_id=None,
                source_kind="web_url",
                url=url,
                ingest_skipped=f"fetch_failed:{type(exc).__name__}",
            )
    body_hash: str | None = None
    if fetched is not None:
        from acquisition.urls.extract import html_to_markdown

        md = html_to_markdown(fetched.body, base_url=fetched.final_url)
        body_hash = document_body_hash(md.markdown)
    existing: str | None = None
    if con is not None:
        existing = find_existing_source_document(
            con, normalized_url=normalized, body_hash=body_hash,
        )
    elif db_path:
        from runtime.db_lock import connect_read

        probe = connect_read(db_path)
        try:
            existing = find_existing_source_document(
                probe, normalized_url=normalized, body_hash=body_hash,
            )
        finally:
            probe.close()
    if existing is not None:
        chunk_id: str | None = None
        if con is not None:
            chunk_row = con.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = ? "
                "ORDER BY chunk_index ASC LIMIT 1",
                [existing],
            ).fetchone()
            chunk_id = str(chunk_row[0]) if chunk_row else None
        elif db_path:
            from runtime.db_lock import connect_read

            probe = connect_read(db_path)
            try:
                chunk_row = probe.execute(
                    "SELECT chunk_id FROM chunks WHERE document_id = ? "
                    "ORDER BY chunk_index ASC LIMIT 1",
                    [existing],
                ).fetchone()
                chunk_id = str(chunk_row[0]) if chunk_row else None
            finally:
                probe.close()
        return ResolvedSource(
            document_id=existing,
            chunk_id=chunk_id,
            source_kind="web_url",
            url=url,
        )
    try:
        result = ingest_url(
            url,
            investigation_id=investigation_id,
            db_path=db_path,
            embedder=embedding_provider,
            fetched=fetched,
            min_word_count=10 if url_fetcher is not None else 50,
        )
    except Exception as exc:
        return ResolvedSource(
            document_id=url_doc_id(normalized),
            chunk_id=None,
            source_kind="web_url",
            url=url,
            ingest_skipped=f"ingest_failed:{type(exc).__name__}",
        )
    if result.skipped_reason:
        return ResolvedSource(
            document_id=result.document_id,
            chunk_id=result.chunk_ids[0] if result.chunk_ids else None,
            source_kind="web_url",
            url=url,
            ingest_skipped=result.skipped_reason,
        )
    return ResolvedSource(
        document_id=result.document_id,
        chunk_id=result.chunk_ids[0] if result.chunk_ids else None,
        source_kind="web_url",
        url=url,
    )


def resolve_source_ref(
    con: Any,
    *,
    source_document_id: str,
    source_kind: str | None,
    chunk_id: str | None,
    source_url: str | None,
    investigation_id: str,
    embedding_provider: Any | None,
    url_fetcher: Callable[[str], Any] | None,
    db_path: str | None = None,
) -> ResolvedSource | None:
    """Turn a loop-emitted source ref into a persisted, readable Document ref."""
    kind = source_kind or ""
    if kind == "local_chunk" or (
        kind != "web_url" and source_document_id and not str(source_document_id).startswith("http")
    ):
        return _resolve_local_source(
            con, document_id=source_document_id, chunk_id=chunk_id,
        )
    url = source_url or (
        source_document_id if str(source_document_id).startswith("http") else None
    )
    if not url:
        return None
    return _resolve_web_source(
        con,
        url=url,
        investigation_id=investigation_id,
        embedding_provider=embedding_provider,
        url_fetcher=url_fetcher,
        db_path=db_path,
    )


def _write_supported_by_edge(
    con: Any,
    *,
    insight_node_id: str,
    resolved: ResolvedSource,
    investigation_id: str,
    extraction_confidence: float,
    embedding_provider: Any | None,
) -> None:
    if not resolved.chunk_id or resolved.ingest_skipped:
        return
    target = ensure_source_anchor_node(
        con,
        document_id=resolved.document_id,
        chunk_id=resolved.chunk_id,
        investigation_id=investigation_id,
        embedding_provider=embedding_provider,
    )
    insert_provenance_edge(
        con,
        source_node_id=insight_node_id,
        target_node_id=target,
        relation="supported_by",
        investigation_id=investigation_id,
        source_document_id=resolved.document_id,
        chunk_id=resolved.chunk_id,
        extraction_confidence=extraction_confidence,
    )


def resolve_sources_for_note(
    ev: StepEvent,
    *,
    db_path: str,
    embedding_provider: Any | None,
    url_fetcher: Callable[[str], Any] | None = None,
) -> list[ResolvedSource]:
    """Ingest / dedup sources on their OWN write lock (before funnel BEGIN).

    ``ingest_url`` acquires ``connect_write`` internally — calling it while the
    funnel already holds the promotion lock deadlocks the single-writer. Source
    resolution therefore runs in a short, separate lock acquisition first."""
    data = dict(ev.data or {})
    source_kind = data.get("source_kind")
    primary_doc = data.get("source_document_id")
    primary_chunk = data.get("source_chunk_id") or data.get("chunk_id")
    source_url = data.get("source_url")
    all_ids = data.get("all_source_document_ids") or (
        [primary_doc] if primary_doc else []
    )
    resolved_sources: list[ResolvedSource] = []
    seen_docs: set[str] = set()
    from runtime.db_lock import connect_read

    for ref_id in all_ids:
        if not ref_id or ref_id in seen_docs:
            continue
        seen_docs.add(str(ref_id))
        is_primary = ref_id == primary_doc
        kind = source_kind if is_primary else (
            "web_url" if str(ref_id).startswith("http") else "local_chunk"
        )
        # Web ingest calls ``ingest_url`` which acquires its OWN write lock —
        # never nest it inside another ``connect_write`` (deadlocks).
        if kind == "web_url" or str(ref_id).startswith("http"):
            # No read handle during ingest — DuckDB rejects concurrent rw.
            resolved = resolve_source_ref(
                None,
                source_document_id=str(ref_id),
                source_kind="web_url",
                chunk_id=primary_chunk if is_primary else None,
                source_url=source_url if is_primary else str(ref_id),
                investigation_id=ev.investigation_id,
                embedding_provider=embedding_provider,
                url_fetcher=url_fetcher,
                db_path=db_path,
            )
        else:
            con = connect_read(db_path)
            try:
                resolved = resolve_source_ref(
                    con,
                    source_document_id=str(ref_id),
                    source_kind="local_chunk",
                    chunk_id=primary_chunk if is_primary else None,
                    source_url=None,
                    investigation_id=ev.investigation_id,
                    embedding_provider=embedding_provider,
                    url_fetcher=url_fetcher,
                    db_path=db_path,
                )
            finally:
                con.close()
        if resolved is not None:
            resolved_sources.append(resolved)
    return resolved_sources


def promote_note_with_provenance(
    ev: StepEvent,
    *,
    con: Any,
    embedding_provider: Any | None,
    url_fetcher: Callable[[str], Any] | None = None,
    state: PromotionProvenanceState | None = None,
    db_path: str | None = None,
    resolved_sources: list[ResolvedSource] | None = None,
) -> str:
    """Promote one research note + write ``supported_by`` edges.

    Source ingestion MUST be done beforehand via :func:`resolve_sources_for_note`
    (separate lock) — see the deadlock note there."""
    if resolved_sources is None:
        if not db_path:
            raise ValueError("db_path required when resolved_sources not precomputed")
        resolved_sources = resolve_sources_for_note(
            ev, db_path=db_path,
            embedding_provider=embedding_provider, url_fetcher=url_fetcher,
        )
    data = dict(ev.data or {})
    primary_resolved = resolved_sources[0] if resolved_sources else None
    meta = {"source": "research_runner", **data}
    if primary_resolved and not primary_resolved.ingest_skipped:
        meta["source_document_id"] = primary_resolved.document_id
        meta["source_kind"] = primary_resolved.source_kind
        if primary_resolved.chunk_id:
            meta["source_chunk_id"] = primary_resolved.chunk_id
            meta["chunk_id"] = primary_resolved.chunk_id
    elif primary_resolved and primary_resolved.ingest_skipped:
        meta["source_ingest_skipped"] = primary_resolved.ingest_skipped

    confidence = str(data.get("confidence", "unknown"))
    extraction_confidence = 0.8
    nid = promote_insight(
        text=ev.text,
        investigation_id=ev.investigation_id,
        confidence=confidence,
        source_document_id=meta.get("source_document_id"),
        chunk_id=meta.get("chunk_id"),
        metadata=meta,
        embedding_provider=embedding_provider,
        con=con,
    )
    for rs in resolved_sources:
        _write_supported_by_edge(
            con,
            insight_node_id=nid,
            resolved=rs,
            investigation_id=ev.investigation_id,
            extraction_confidence=extraction_confidence,
            embedding_provider=embedding_provider,
        )
    if state is not None:
        state.findings.append({
            "insight_node_id": nid,
            "text": ev.text,
            "investigation_id": ev.investigation_id,
            "sources": [rs for rs in resolved_sources if not rs.ingest_skipped],
        })
        state.resolved_by_investigation.setdefault(
            ev.investigation_id, [],
        ).extend(resolved_sources)
    return nid


def make_cassette_url_fetcher(
    html_by_url: dict[str, str] | None = None,
) -> Callable[[str], Any]:
    """Build a test ``url_fetcher`` that returns ``FetchedHtml`` without network."""
    from acquisition.urls.client import FetchedHtml

    bodies = html_by_url or {}

    def _fetch(url: str) -> FetchedHtml:
        html = bodies.get(url, _default_test_html(url))
        return FetchedHtml(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html; charset=utf-8",
            charset="utf-8",
            body=html.encode("utf-8"),
        )

    return _fetch


def write_artifact_cites_edges(
    con: Any,
    *,
    artifact_document_id: str,
    artifact_title: str,
    cited_sources: list[ResolvedSource],
    investigation_id: str,
    embedding_provider: Any | None,
) -> None:
    """Write ``artifact —cites→ source`` edges after the artifact document exists."""
    artifact_anchor = ensure_artifact_anchor_node(
        con,
        artifact_document_id=artifact_document_id,
        title=artifact_title,
        investigation_id=investigation_id,
        embedding_provider=embedding_provider,
    )
    seen: set[tuple[str, str]] = set()
    for src in cited_sources:
        if not src.chunk_id or src.ingest_skipped:
            continue
        key = (src.document_id, src.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        target = ensure_source_anchor_node(
            con,
            document_id=src.document_id,
            chunk_id=src.chunk_id,
            investigation_id=investigation_id,
            embedding_provider=embedding_provider,
        )
        insert_provenance_edge(
            con,
            source_node_id=artifact_anchor,
            target_node_id=target,
            relation=CITES_RELATION,
            investigation_id=investigation_id,
            source_document_id=src.document_id,
            chunk_id=src.chunk_id,
            extraction_confidence=0.85,
        )


def verify_document_readable(con: Any, document_id: str) -> bool:
    """True when the document exists with NOT NULL content_class + body."""
    row = con.execute(
        "SELECT content_class, raw_text, structured_blocks FROM documents "
        "WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if row is None:
        return False
    content_class, raw_text, structured = row
    return content_class is not None and bool(raw_text or structured)