"""Link Monster — graph stew (storage into the Antiek substrate).

Writes one digest into the single-writer DuckDB graph exactly the way
every other acquisition adapter does: ``connect_write`` flock → typed
ops → rights registration → typed event. No new tables, no schema
migration: the digest packet lives in ``documents.metadata`` (JSON)
with the body in ``documents.raw_text`` and chunks in the standard
chunks table, so the existing search/traverse/read surfaces work
unchanged.

Document type mapping (platform → substrate vocabulary) is in
``platforms.PLATFORM_DOCUMENT_TYPE``; every value is a member of
``THIRD_PARTY_DOCUMENT_TYPES``, so the deny-by-default content_class
guard in ``insert_document`` stamps ``personal_reading`` (owner-
readable, never servable) with the documented event. We pass
``content_class=None`` on purpose: the guard's job is exactly this
classification, and an explicit override here would be the kind of
silent rights promotion the substrate forbids.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import (  # noqa: E402
    Chunk,
    chunk_markdown,
)
from processing.embedding.embed import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
)
from substrate.graph.ops import (  # noqa: E402
    insert_chunk,
    insert_document,
    insert_edge,
    insert_node,
)
from substrate.rights.register import (  # noqa: E402
    SourceKind,
    register_source_document,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    LinkMonsterDigestedPayload,
)

from .digest import LinkDigest  # noqa: E402
from .platforms import PLATFORM_DOCUMENT_TYPE  # noqa: E402

DEFAULT_SOURCE_TIER = 4  # third-party web / social tier (master spec)
_NODE_LABEL_MAX = 160
_MIN_CHUNK_WORDS = 5  # a single tweet / short note is still a chunk

# Transcript segments → ~250-word chunks with timestamp sections
# (mirrors acquisition/youtube/adapter.py grouping so cross-surface
# deep-links behave identically).
DEFAULT_CHUNK_TARGET_WORDS = 250


def link_monster_doc_id(final_url: str) -> str:
    """Stable doc id for a canonical final URL. Same final URL → same
    id → re-ingest is idempotent at the document row."""
    if not final_url:
        raise ValueError("empty final_url")
    h = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:16]
    return f"doc-lm-{h}"


def _format_timestamp(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _chunks_from_transcript(
    segments: list[dict[str, Any]], full_text: str,
) -> list[Chunk]:
    """Group transcript segments into ~250-word timestamped chunks
    (same contract as the YouTube adapter: section_path carries the
    timestamp range so the reader can deep-link to the moment)."""
    chunks: list[Chunk] = []
    cur_words: list[str] = []
    cur_end: float = 0.0
    cur_text: list[str] = []
    _group_start: float | None = None

    def flush() -> None:
        nonlocal _group_start
        if not cur_words:
            return
        text = "\n".join(cur_text).strip()
        start_secs = _group_start if _group_start is not None else 0.0
        section = (
            f"Timestamp: {_format_timestamp(start_secs)} - "
            f"{_format_timestamp(cur_end)}"
        )
        chunks.append(Chunk(text=text, section=section, token_count=len(cur_words)))
        cur_words.clear()
        cur_text.clear()
        _group_start = None

    for seg in segments:
        start = float(seg.get("start", 0.0))
        duration = float(seg.get("duration", 0.0))
        text = str(seg.get("text", ""))
        if _group_start is None:
            _group_start = start
        cur_end = start + duration
        cur_words.extend(text.split())
        cur_text.append(text)
        if len(cur_words) >= DEFAULT_CHUNK_TARGET_WORDS:
            flush()
    flush()
    return chunks


def _chunks_from_markdown(markdown: str) -> list[Chunk]:
    return chunk_markdown(markdown)


def _digest_metadata(digest: LinkDigest) -> dict[str, Any]:
    """The digest packet minus the raw body (body lives in raw_text /
    chunks; metadata stays lean)."""
    data = digest.to_jsonable()
    if digest.text:
        data["text"] = {
            "chars": digest.text.chars,
            "word_count": digest.text.word_count,
            "source": digest.text.source,
        }
    return data


def _store_nodes_and_edges(
    con: Any,
    *,
    digest: LinkDigest,
    document_id: str,
    investigation_id: str,
    emb: EmbeddingProvider,
) -> tuple[list[str], list[str]]:
    """Author + publisher nodes with edges to the document. Light-touch
    v1 (no LLM extraction): the parameter-extractor / loop-one machinery
    owns deep entity extraction; the Monster records who wrote it and
    who published it, with honest confidence from the extraction
    source (oEmbed author = 0.9, OG author = 0.6)."""
    node_ids: list[str] = []
    edge_ids: list[str] = []

    def add_node(label: str, node_type: str) -> str:
        label = (label or "").strip()
        if not label:
            return ""
        if len(label) > _NODE_LABEL_MAX:
            label = label[:_NODE_LABEL_MAX - 1] + "…"
        nid = insert_node(
            con,
            canonical_label=label,
            node_type=node_type,
            graph_scope="depth",
            investigation_id=investigation_id,
            embedding=emb.encode(label),
            metadata={"source": "link_monster", "document_id": document_id},
            on_conflict="ignore",
        )
        if nid not in node_ids:
            node_ids.append(nid)
        return nid

    # The edges table connects NODES to NODES (documents are attributed
    # via edges.source_document_id, never as an edge endpoint). So the
    # Monster's graph shape is: author --authored_on--> publisher, with
    # the digest's document id riding on source_document_id so the
    # document's neighbors stay queryable.
    author_nid = add_node(digest.author, "person") if digest.author else ""
    publisher_nid = add_node(
        digest.site_name or digest.platform_label, "organization"
    )
    confidence = 0.9 if digest.provenance.get("author_name") == "oembed" else 0.6
    if author_nid and publisher_nid:
        eid = insert_edge(
            con,
            source_node_id=author_nid,
            target_node_id=publisher_nid,
            relation="authored_on",
            source_tier=DEFAULT_SOURCE_TIER,
            extraction_confidence=confidence,
            graph_scope="depth",
            investigation_id=investigation_id,
            source_document_id=document_id,
            metadata={"source": "link_monster"},
            on_conflict="ignore",
        )
        edge_ids.append(eid)
    elif publisher_nid and digest.title:
        # Authorless page (Wikipedia, most news homepages): still give
        # the graph a traversable statement — the publisher published
        # this title. Low confidence, honest, queryable.
        title_nid = add_node(digest.title, "entity")
        if title_nid:
            eid = insert_edge(
                con,
                source_node_id=publisher_nid,
                target_node_id=title_nid,
                relation="published",
                source_tier=DEFAULT_SOURCE_TIER,
                extraction_confidence=0.5,
                graph_scope="depth",
                investigation_id=investigation_id,
                source_document_id=document_id,
                metadata={"source": "link_monster"},
                on_conflict="ignore",
            )
            edge_ids.append(eid)
    return node_ids, edge_ids


@dataclass(frozen=True)
class StoreResult:
    document_id: str
    chunk_ids: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    edge_ids: list[str] = field(default_factory=list)
    chunks_written: int = 0
    already_digested: bool = False
    content_class: str | None = None


def store_digest(
    digest: LinkDigest,
    *,
    db_path: str | None = None,
    investigation_id: str | None = None,
    emb: EmbeddingProvider | None = None,
    duration_ms: int = 0,
) -> StoreResult:
    """Stew one digest into the graph. Idempotent: re-storing the same
    final_url returns the existing document id with
    ``already_digested=True`` (no duplicate rows, no duplicate events —
    the ops layer's on_conflict='ignore' short-circuits before emitting)."""
    resolved_db = db_path or default_db_path()
    ensure_initialized(resolved_db)
    provider = emb or default_embedding_provider()
    document_id = link_monster_doc_id(digest.final_url)
    inv_id = investigation_id or f"link-monster-{document_id}"

    from runtime.db_lock import connect_write

    with connect_write(resolved_db, purpose="link-monster") as con:
        # Dedup: the document row already exists → already eaten.
        exists = con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1",
            [document_id],
        ).fetchone()
        if exists is not None:
            return StoreResult(
                document_id=document_id,
                already_digested=True,
            )

        # Full text for raw_text + chunks.
        if digest.transcript and digest.transcript.chars:
            full_text = "\n".join(
                str(seg["text"]) for seg in digest.transcript.segments
            )
            chunks = _chunks_from_transcript(digest.transcript.segments, full_text)
        elif digest.text:
            full_text = digest.text.markdown
            chunks = _chunks_from_markdown(digest.text.markdown)
        else:
            full_text = None
            chunks = []

        insert_document(
            con,
            document_id=document_id,
            source_tier=DEFAULT_SOURCE_TIER,
            document_type=PLATFORM_DOCUMENT_TYPE[digest.platform],
            source_uri=digest.url,
            title=digest.title,
            author=digest.author,
            published_at=digest.published_at,
            investigation_id=inv_id,
            raw_text=full_text,
            metadata=_digest_metadata(digest),
            content_class=None,  # deny-by-default guard stamps personal_reading
        )
        # Rights: deny-by-default → personal_reading (owner-readable,
        # never servable on the monetized read path).
        content_class = register_source_document(
            con,
            document_id=document_id,
            source_kind=SourceKind.WEB,
            # Explicit personal_reading — the same explicit stamp the
            # urls adapter passes. The insert_document guard defaulted
            # the row to personal_reading already; registering the same
            # class explicitly keeps the rights row reconstructable
            # without relying on the default.
            content_class=PERSONAL_READING_CONTENT_CLASS,
        )

        chunk_ids: list[str] = []
        for i, chunk in enumerate(chunks):
            if chunk.token_count < _MIN_CHUNK_WORDS and len(chunks) > 1:
                continue
            cid = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=provider.encode(chunk.text),
                token_count=chunk.token_count,
            )
            chunk_ids.append(cid)

        node_ids, edge_ids = _store_nodes_and_edges(
            con,
            digest=digest,
            document_id=document_id,
            investigation_id=inv_id,
            emb=provider,
        )

        # document.loaded — the canonical ingestion signal the reading
        # surface consumes (same contract as the other adapters).
        emit_typed(
            inv_id,
            DocumentLoadedPayload(
                media_type="url_extracted",
                content_hash=hashlib.sha256(
                    (full_text or "").encode("utf-8")
                ).hexdigest(),
                size_bytes=len((full_text or "").encode("utf-8")),
                title=digest.title,
                source_uri=digest.url,
            ),
            document_id=document_id,
            role="connector",
        )

        # link.monster.digested — the Monster's own ledger event.
        emit_typed(
            inv_id,
            LinkMonsterDigestedPayload(
                url=digest.url,
                final_url=digest.final_url,
                platform=digest.platform,
                document_id=document_id,
                outcome=digest.outcome,
                artifacts=dict(digest.artifacts),
                title=digest.title,
                author=digest.author,
                duration_ms=duration_ms,
            ),
            document_id=document_id,
            role="connector",
        )

    return StoreResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        edge_ids=edge_ids,
        chunks_written=len(chunk_ids),
        content_class=content_class,
    )


def list_digests(
    *,
    db_path: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Monster Menu: recent digests (documents with Link Monster
    metadata), newest first. Read-only; fails open to [] on a missing
    DB."""
    import duckdb

    resolved = db_path or default_db_path()
    try:
        con = duckdb.connect(resolved, read_only=True)
    except Exception:
        return []
    try:
        rows = con.execute(
            "SELECT document_id, title, author, source_uri, acquired_at, "
            " metadata FROM documents "
            " WHERE metadata IS NOT NULL "
            "   AND json_extract_string(metadata, '$.digested_at') IS NOT NULL "
            " ORDER BY acquired_at DESC LIMIT ?",
            [int(limit)],
        ).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    out = []
    for row in rows:
        try:
            meta = json.loads(row[5])
        except Exception:
            continue
        out.append(
            {
                "document_id": row[0],
                "title": row[1],
                "author": row[2],
                "source_uri": row[3],
                "acquired_at": (
                    row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4])
                ),
                "digest": meta,
            }
        )
    return out


def get_digest(
    document_id: str,
    *,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """One digest + chunk summary + graph neighbors. Read-only."""
    import duckdb

    resolved = db_path or default_db_path()
    try:
        con = duckdb.connect(resolved, read_only=True)
    except Exception:
        return None
    try:
        row = con.execute(
            "SELECT document_id, title, author, source_uri, "
            "       acquired_at, metadata, document_type "
            " FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
        if row is None:
            return None
        meta = json.loads(row[5]) if row[5] else {}
        chunk_rows = con.execute(
            "SELECT chunk_id, chunk_index, section_path, token_count, "
            "       length(text) FROM chunks WHERE document_id = ? "
            " ORDER BY chunk_index",
            [document_id],
        ).fetchall()
        node_rows = con.execute(
            "SELECT n.node_id, n.canonical_label, n.node_type "
            " FROM nodes n JOIN edges e "
            "   ON e.source_node_id = n.node_id OR e.target_node_id = n.node_id "
            " WHERE e.source_document_id = ? OR ? IN ("
            "   SELECT source_document_id FROM edges WHERE target_node_id = n.node_id"
            ") LIMIT 50",
            [document_id, document_id],
        ).fetchall()
        return {
            "document_id": row[0],
            "title": row[1],
            "author": row[2],
            "source_uri": row[3],
            # NOTE: raw_text is deliberately NOT returned here — the
            # compliance invariant (tests/test_compliance_invariants.py)
            # forbids reading documents.raw_text outside the sanctioned
            # serve gate. The digest packet (metadata) + chunk index
            # carry the read surface.
            "acquired_at": (
                row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4])
            ),
            "metadata": meta,
            "document_type": row[6],
            "chunks": [
                {
                    "chunk_id": c[0],
                    "chunk_index": c[1],
                    "section_path": c[2],
                    "token_count": c[3],
                    "chars": c[4],
                }
                for c in chunk_rows
            ],
            "neighbors": [
                {"node_id": n[0], "label": n[1], "node_type": n[2]}
                for n in node_rows
            ],
        }
    finally:
        con.close()


def digest_stats(*, db_path: str | None = None) -> dict[str, Any]:
    """Monster stats: counts by outcome/platform + graph contribution.
    Read-only; fails open on a missing DB."""
    import duckdb

    resolved = db_path or default_db_path()
    try:
        con = duckdb.connect(resolved, read_only=True)
    except Exception:
        return {
            "meals": 0, "snacks": 0, "total": 0, "chunks": 0,
            "nodes": 0, "edges": 0, "by_platform": {}, "last_digested_at": None,
        }
    try:
        rows = con.execute(
            "SELECT document_id, "
            "       json_extract_string(metadata, '$.outcome'), "
            "       json_extract_string(metadata, '$.platform') "
            " FROM documents "
            " WHERE json_extract_string(metadata, '$.digested_at') IS NOT NULL"
        ).fetchall()
    except Exception:
        rows = []
    meals = snacks = 0
    by_platform: dict[str, int] = {}
    for _doc_id, outcome, platform in rows:
        if outcome == "meal":
            meals += 1
        else:
            snacks += 1
        by_platform[platform or "unknown"] = by_platform.get(platform or "unknown", 0) + 1
    ids = [r[0] for r in rows] if rows else []
    chunks = nodes = edges = 0
    last_at = None
    if ids:
        try:
            _chunk_row = con.execute(
                "SELECT count(*) FROM chunks WHERE document_id IN ("
                + ",".join("?" for _ in ids) + ")",
                ids,
            ).fetchone()
            chunks = int(_chunk_row[0]) if _chunk_row else 0
            _node_row = con.execute(
                "SELECT count(DISTINCT n.node_id) FROM nodes n "
                " JOIN edges e ON e.source_node_id = n.node_id "
                " WHERE e.source_document_id IN ("
                + ",".join("?" for _ in ids) + ")",
                ids,
            ).fetchone()
            nodes = int(_node_row[0]) if _node_row else 0
            _edge_row = con.execute(
                "SELECT count(*) FROM edges WHERE source_document_id IN ("
                + ",".join("?" for _ in ids) + ")",
                ids,
            ).fetchone()
            edges = int(_edge_row[0]) if _edge_row else 0
        except Exception:
            chunks = nodes = edges = 0
    try:
        _last_row = con.execute(
            "SELECT max(acquired_at) FROM documents WHERE json_extract_string("
            "metadata, '$.digested_at') IS NOT NULL"
        ).fetchone()
        last = _last_row[0] if _last_row else None
        last_at = last.isoformat() if last is not None and hasattr(last, "isoformat") else (str(last) if last is not None else None)
    except Exception:
        last_at = None
    con.close()
    return {
        "meals": meals,
        "snacks": snacks,
        "total": meals + snacks,
        "chunks": chunks,
        "nodes": nodes,
        "edges": edges,
        "by_platform": by_platform,
        "last_digested_at": last_at,
    }
