"""URL → Antiek substrate adapter.

Fetch HTML, extract main content as markdown, emit ``document.loaded``,
write to ``substrate.graph``. Mirrors the ``acquisition.arxiv.adapter``
contract — same return shape, same idempotency guarantees.

Stable doc id: ``doc-url-<sha256-of-final-url[:16]>`` so the same URL
resurfacing in a new session dedups against prior ingestion. Using a
hash (not the URL itself) keeps the id length bounded and
DuckDB-string-safe regardless of how nasty the URL is.

Default source tier: 4 (general web — operator can override for
known-good outlets via ``ingest_url(..., source_tier=2)``).

What this does NOT do (the parameter_extractor's job): mint typed
nodes + edges from the article body. Loop 1 will pick that up when
it walks the trajectory.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Repo root on path for direct invocation.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import (  # noqa: E402
    Chunk,
    chunk_markdown,
    content_hash,
)
from processing.embedding.embed import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from substrate.books.servability import servability_of  # noqa: E402
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
)
from substrate.graph.ops import (  # noqa: E402
    insert_chunk,
    insert_document,
    insert_node,
)
from substrate.rights.register import (  # noqa: E402
    SourceKind,
    register_source_document,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    FetchFallbackEscalatedPayload,
)

from .client import FetchedHtml, fetch  # noqa: E402  # sys.path bootstrap
from .extract import (  # noqa: E402  # sys.path bootstrap
    MarkdownDoc,
    html_to_markdown,
)

DEFAULT_URL_SOURCE_TIER = 4
_NODE_LABEL_MAX = 160

# Minimum markdown word count below which we skip graph writes.
# Pages where the extractor returns near-empty body usually mean it
# missed the article (paywall, JS-rendered). Emitting events but
# skipping graph writes lets the operator see the failure in the
# trajectory without polluting the graph.
MIN_INGEST_WORD_COUNT = 50


# ---------------------------------------------------------------------------
# Stable document id
# ---------------------------------------------------------------------------


def url_doc_id(url: str) -> str:
    """Stable Antiek doc id for a URL. Hashes the URL so the id length
    is bounded and DuckDB-string-safe regardless of URL shape."""
    if not url:
        raise ValueError("empty url")
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"doc-url-{h}"


def lookup_url_alias(
    requested_url: str,
    *,
    db_path: str | None = None,
) -> str | None:
    """Consult the `url_alias` table for a prior ingestion of this
    URL. Returns the canonical `document_id` if found, None
    otherwise.

    Spec §14.2 mitigation — guards against doc-id collision via
    final-url drift: when the same `requested_url` resolves to two
    different `final_url` values across fetches (because the site
    changed its canonical slug), we'd otherwise mint two doc_ids
    for the same logical content. The alias table records every
    URL we've ever ingested under so the next encounter can
    short-circuit to the canonical doc.

    Safe to call against a missing DB file (returns None — the
    cache fails open per the discovery_cache convention).
    """
    import duckdb

    resolved = db_path or default_db_path()
    try:
        con = duckdb.connect(resolved, read_only=True)
    except Exception:
        return None
    try:
        rows = con.execute(
            "SELECT document_id FROM url_alias WHERE requested_url = ?",
            [requested_url],
        ).fetchall()
    except Exception:
        # url_alias table not yet created (schema older than v3-with-aliases).
        return None
    finally:
        con.close()
    if not rows:
        return None
    # DuckDB fetchall() returns Any-typed cells; document_id is a TEXT column.
    return str(rows[0][0])


def _resolve_alias_projection(
    document_id: str, *, requested_url: str, db_path: str | None
) -> str | None:
    """Return the canonical projection, repairing legacy pre-HTML rows once."""
    import duckdb

    from acquisition.snapshot.reader_html import (
        build_reader_snapshot,
        markdown_to_safe_html,
        reader_snapshot_path_for,
        write_reader_snapshot,
    )

    path = reader_snapshot_path_for(document_id)
    resolved = db_path or default_db_path()
    try:
        con = duckdb.connect(resolved, read_only=True)
        row = con.execute(
            """SELECT source_uri, title, author, raw_text, metadata,
                      content_class, ip_holder_id, owner_user_id
               FROM documents WHERE document_id = ?""",
            [document_id],
        ).fetchone()
    except Exception:
        return None
    finally:
        if "con" in locals():
            con.close()
    if row is None:
        return None
    source_uri, title, author, raw_text, raw_metadata, content_class, ip_holder, owner = row
    metadata = json.loads(raw_metadata) if raw_metadata else {}
    text = str(raw_text or "")
    status = servability_of(content_class).value
    viewable = status == "personal_readable"
    rendered = build_reader_snapshot(
        source_url=str(source_uri or requested_url),
        document_id=document_id,
        ip_holder_id=str(ip_holder) if ip_holder else None,
        main_html=markdown_to_safe_html(text),
        ingested_at=datetime.now(UTC).isoformat(),
        title=str(title) if title else None,
        author=str(author) if author else None,
        canonical_content_hash=str(
            metadata.get("canonical_content_hash") or "sha256:" + content_hash(text)
        ),
        source_event_id=str(metadata.get("source_event_id") or "legacy:alias-projection-repair"),
        content_class=str(content_class) if content_class else None,
        servability=status,
        owner_scope=str(owner),
        viewable=viewable,
        non_viewable_reason=None if viewable else f"servability:{status}",
    )
    write_reader_snapshot(path, rendered)
    _mark_url_projection_ready(
        db_path=resolved,
        document_id=document_id,
        snapshot_path=str(path),
    )
    return str(path)


def _mark_url_projection_ready(*, db_path: str, document_id: str, snapshot_path: str) -> None:
    """Acknowledge a successfully published derived projection durably."""
    from runtime.db_lock import connect_write

    projection_hash = "sha256:" + hashlib.sha256(Path(snapshot_path).read_bytes()).hexdigest()
    with connect_write(db_path, purpose="acquisition/urls/projection-ready") as con:
        row = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
        if row is None:
            return
        metadata = json.loads(row[0]) if row[0] else {}
        metadata["reader_projection_state"] = "ready"
        metadata["reader_projection_hash"] = projection_hash
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            [json.dumps(metadata), document_id],
        )


def _existing_url_document(
    document_id: str, *, db_path: str
) -> tuple[str, str | None, str | None, list[str]] | None:
    """Read current canonical hash/title/author/chunks for ignore admission."""
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            "SELECT raw_text, metadata, title, author FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
        if row is None:
            return None
        raw_text, raw_metadata, title, author = row
        metadata = json.loads(raw_metadata) if raw_metadata else {}
        canonical_hash = str(
            metadata.get("canonical_content_hash") or "sha256:" + content_hash(str(raw_text or ""))
        )
        chunk_ids = [
            str(item[0])
            for item in con.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                [document_id],
            ).fetchall()
        ]
        return (
            canonical_hash,
            str(title) if title else None,
            str(author) if author else None,
            chunk_ids,
        )
    finally:
        con.close()


def _archive_url_chunks_for_replace(con: Any, document_id: str) -> None:
    """Preserve an addressable historical revision before refreshing chunks.

    Downstream edges and tier overrides keep pointing at immutable cloned chunks;
    the canonical document can then own only its current chunk set.
    """
    row = con.execute(
        "SELECT metadata FROM documents WHERE document_id = ?", [document_id]
    ).fetchone()
    metadata = json.loads(row[0]) if row and row[0] else {}
    old_hash = str(metadata.get("canonical_content_hash") or "unknown")
    revision_id = f"{document_id}::rev::{old_hash.removeprefix('sha256:')[:16]}"
    chunks = con.execute(
        """SELECT chunk_id, chunk_index, section_path, text, embedding, token_count
           FROM chunks WHERE document_id = ? ORDER BY chunk_index""",
        [document_id],
    ).fetchall()
    referenced = {
        str(item[0])
        for item in con.execute(
            """SELECT chunk_id FROM edges
               WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id = ?)
               UNION
               SELECT chunk_id FROM chunk_tier_overrides
               WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id = ?)""",
            [document_id, document_id],
        ).fetchall()
    }
    if not referenced:
        con.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
        return

    revision_metadata = dict(metadata)
    revision_metadata.update(
        {
            "revision_of": document_id,
            "revision_content_hash": old_hash,
            "archived_at": datetime.now(UTC).isoformat(),
            "reader_projection_state": "historical",
        }
    )
    con.execute(
        """INSERT INTO documents (
               document_id, source_uri, title, author, published_at, acquired_at,
               source_tier, document_type, investigation_id, raw_text, metadata,
               owner_user_id, content_class, ip_holder_id
           )
           SELECT ?, source_uri, title, author, published_at, acquired_at,
                  source_tier, 'web_article_revision', investigation_id, raw_text, ?,
                  owner_user_id, content_class, ip_holder_id
           FROM documents WHERE document_id = ?
           ON CONFLICT (document_id) DO NOTHING""",
        [revision_id, json.dumps(revision_metadata), document_id],
    )
    clone_ids: dict[str, str] = {}
    for old_id, index, section, chunk_text, embedding, token_count in chunks:
        clone_id = f"{revision_id}::chunk::{int(index)}"
        clone_ids[str(old_id)] = clone_id
        con.execute(
            """INSERT INTO chunks (
                   chunk_id, document_id, chunk_index, section_path,
                   text, embedding, token_count
               ) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (chunk_id) DO NOTHING""",
            [
                clone_id,
                revision_id,
                int(index),
                section,
                chunk_text,
                embedding,
                int(token_count),
            ],
        )
    for old_id in referenced:
        clone_id = clone_ids[old_id]
        con.execute(
            "UPDATE edges SET chunk_id = ?, source_document_id = ? WHERE chunk_id = ?",
            [clone_id, revision_id, old_id],
        )
        con.execute(
            "UPDATE chunk_tier_overrides SET chunk_id = ? WHERE chunk_id = ?",
            [clone_id, old_id],
        )
    con.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestUrlResult:
    """What ``ingest_url`` returns. ``skipped_reason`` is non-None when
    extraction succeeded but graph writes were skipped (e.g.
    ``"low_word_count"``)."""

    document_id: str
    final_url: str
    chunk_ids: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    skipped_reason: str | None = None
    title: str | None = None
    author: str | None = None
    reader_snapshot_path: str | None = None


def _write_url_projection(
    *,
    page: FetchedHtml,
    document_id: str,
    canonical_content_hash: str,
    source_event_id: str,
    viewable: bool,
    non_viewable_reason: str | None = None,
) -> str:
    """Materialize the canonical owner-scoped HTML projection or receipt."""
    from acquisition.snapshot.reader_html import (
        build_reader_snapshot,
        reader_snapshot_path_for,
        write_reader_snapshot,
    )

    raw_html: str | bytes = page.body
    if isinstance(raw_html, bytes):
        raw_html = raw_html.decode(page.charset or "utf-8", errors="replace")
    path = reader_snapshot_path_for(document_id)
    rendered = build_reader_snapshot(
        source_url=page.final_url,
        document_id=document_id,
        ip_holder_id=None,
        main_html=raw_html,
        ingested_at=datetime.now(UTC).isoformat(),
        canonical_content_hash=canonical_content_hash,
        source_event_id=source_event_id,
        content_class=PERSONAL_READING_CONTENT_CLASS,
        servability=servability_of(PERSONAL_READING_CONTENT_CLASS).value,
        owner_scope="__operator__",
        viewable=viewable,
        non_viewable_reason=non_viewable_reason,
    )
    write_reader_snapshot(path, rendered)
    return str(path)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _try_browserbase_escalation(
    *,
    url: str,
    primary_word_count: int,
    investigation_id: str,
    wait_for: str | None,
) -> FetchedHtml | None:
    """Drive a Browserbase session and emit
    ``FetchFallbackEscalatedPayload`` regardless of outcome. Returns
    the new ``FetchedHtml`` on success, ``None`` on any failure so
    the caller can fall back to the original skip path."""
    from .budget_browserbase import BrowserbaseBudgetExceeded
    from .client_browserbase import (
        DEFAULT_SESSION_COST_USD,
        BrowserbaseFetchError,
        BrowserbaseRobotsDisallowed,
        BrowserbaseUnavailable,
        fetch_via_browserbase,
    )

    fallback_word_count = 0
    fetched: FetchedHtml | None = None
    estimated_cost = DEFAULT_SESSION_COST_USD
    try:
        fetched = fetch_via_browserbase(url, wait_for=wait_for)
        md = html_to_markdown(fetched.body, base_url=fetched.final_url)
        fallback_word_count = md.word_count
    except (
        BrowserbaseUnavailable,
        BrowserbaseRobotsDisallowed,
        BrowserbaseBudgetExceeded,
        BrowserbaseFetchError,
        Exception,
    ):
        fetched = None
        fallback_word_count = 0

    emit_typed(
        investigation_id,
        FetchFallbackEscalatedPayload(
            url=url,
            primary_word_count=primary_word_count,
            fallback_fetcher="browserbase",
            fallback_word_count=fallback_word_count,
            escalation_reason="low_word_count",
            estimated_cost_usd=estimated_cost,
        ),
        role="acquisition",
        policy_id="acquisition/urls/browserbase",
    )
    return fetched


def ingest_url(
    url: str,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_URL_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
    http_client: object | None = None,
    fetched: FetchedHtml | None = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
    on_conflict: str = "ignore",
    # Wedge 2 (Browserbase escalation) — opt-in per call (default off).
    fallback_to_browserbase: bool = False,
    browserbase_wait_for: str | None = None,
) -> IngestUrlResult:
    """Fetch ``url``, extract markdown, ingest into substrate.

    ``fetched`` lets callers reuse an already-fetched body (e.g. a
    crawler that batches requests) — when set, no HTTP is performed
    and ``http_client`` is ignored.

    ``on_conflict`` defaults to ``"ignore"``. An unchanged re-ingest emits its
    acquisition event but does not rewrite canonical state. A changed body is
    rejected with ``changed_content_requires_replace`` so versions cannot mix.
    Explicit ``"replace"`` updates the canonical row in place and archives any
    chunks carrying downstream references under a hash-addressed historical
    document before admitting the new chunk set.

    ``fallback_to_browserbase`` opts in to Wedge 2 escalation when
    the httpx primary fetch returns low_word_count. Per spec §7.4
    Browserbase is 1000-5000× more expensive than httpx; default off.
    """
    # Spec §14.2 — alias short-circuit. When the caller passes a
    # bare URL (no pre-fetched bytes), consult url_alias first; if
    # we've ingested this requested_url before, return the canonical
    # doc_id without paying the fetch cost OR forking a new doc_id.
    # Skipped when `fetched=` is passed (caller has bytes and is
    # intentionally re-ingesting).
    if fetched is None:
        canonical = lookup_url_alias(url, db_path=db_path)
        if canonical is not None:
            return IngestUrlResult(
                document_id=canonical,
                final_url=url,
                document_loaded_event_id=None,
                skipped_reason="alias_resolved_to_existing_document",
                title=None,
                author=None,
                reader_snapshot_path=_resolve_alias_projection(
                    canonical, requested_url=url, db_path=db_path
                ),
            )

    page: FetchedHtml = fetched or fetch(url, client=http_client)  # type: ignore[arg-type]
    md_doc: MarkdownDoc = html_to_markdown(page.body, base_url=page.final_url)

    document_id = url_doc_id(page.final_url)
    text = md_doc.markdown
    chash = "sha256:" + content_hash(text)

    payload = DocumentLoadedPayload(
        media_type="url_extracted",
        content_hash=chash,
        size_bytes=len(text.encode("utf-8")),
        title=md_doc.title,
        page_count=None,
        source_uri=page.final_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/urls",
    )
    assert event_id is not None

    # Word-count gate. Emit the event so the operator can see the
    # fetch happened, but skip graph writes for plausibly-misextracted
    # pages — keeps the graph cleaner during dev.
    if md_doc.word_count < min_word_count:
        escalation_ran = False
        if fallback_to_browserbase and fetched is None:
            escalation_ran = True
            escalated = _try_browserbase_escalation(
                url=url,
                primary_word_count=md_doc.word_count,
                investigation_id=investigation_id,
                wait_for=browserbase_wait_for,
            )
            if escalated is not None:
                page = escalated
                md_doc = html_to_markdown(page.body, base_url=page.final_url)
                text = md_doc.markdown
                chash = "sha256:" + content_hash(text)
                event_id = emit_typed(
                    investigation_id,
                    DocumentLoadedPayload(
                        media_type="url_extracted",
                        content_hash=chash,
                        size_bytes=len(text.encode("utf-8")),
                        title=md_doc.title,
                        page_count=None,
                        source_uri=page.final_url,
                    ),
                    document_id=document_id,
                    role="acquisition",
                    policy_id="acquisition/urls/browserbase",
                )
                assert event_id is not None

        if md_doc.word_count < min_word_count:
            skipped_reason = "low_word_count_after_fallback" if escalation_ran else "low_word_count"
            reader_snapshot_path = _write_url_projection(
                page=page,
                document_id=document_id,
                canonical_content_hash=chash,
                source_event_id=event_id,
                viewable=False,
                non_viewable_reason=skipped_reason,
            )
            return IngestUrlResult(
                document_id=document_id,
                final_url=page.final_url,
                document_loaded_event_id=event_id,
                skipped_reason=skipped_reason,
                title=md_doc.title,
                author=md_doc.author,
                reader_snapshot_path=reader_snapshot_path,
            )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    if on_conflict == "ignore":
        existing = _existing_url_document(document_id, db_path=resolved_db_path)
        if existing is not None:
            stored_hash, stored_title, stored_author, stored_chunk_ids = existing
            admission_reason = None if stored_hash == chash else "changed_content_requires_replace"
            return IngestUrlResult(
                document_id=document_id,
                final_url=page.final_url,
                chunk_ids=stored_chunk_ids,
                document_loaded_event_id=event_id,
                chunks_written=0,
                skipped_reason=admission_reason,
                title=stored_title,
                author=stored_author,
                reader_snapshot_path=_resolve_alias_projection(
                    document_id,
                    requested_url=page.requested_url,
                    db_path=resolved_db_path,
                ),
            )

    chunks: list[Chunk] = chunk_markdown(text)
    chunk_ids: list[str] = []
    node_ids: list[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()
    document_metadata = {
        "requested_url": page.requested_url,
        "final_url": page.final_url,
        "content_type": page.content_type,
        "status_code": page.status_code,
        "fetched_at": datetime.now(UTC).isoformat(),
        "canonical_content_hash": chash,
        "source_event_id": event_id,
        "projection_version": "reader-html-allowlist-v1",
        "reader_projection_state": "pending",
        "reader_projection_hash": None,
    }

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/urls") as con:
        # ``replace`` is adapter-level admission; insert_document itself only
        # accepts error/ignore. The canonical row remains in place so foreign
        # keys and URL aliases preserve stable identity.
        insert_on_conflict = on_conflict
        if on_conflict == "replace":
            # A CHANGED re-ingest must overwrite the body under the SAME id
            # without forking. We do NOT delete the documents row (other tables
            # FK-reference it, so a DELETE trips a foreign-key constraint);
            # instead we UPDATE in place. Referenced chunks are cloned to a
            # historical revision before the canonical chunk set is refreshed;
            # unreferenced chunks can be removed directly.
            # DuckDB 1.5 rejects a multi-column UPDATE of an FK target as an
            # implied row replacement. Independent unindexed-column updates
            # remain within this one transaction and preserve the referenced
            # document identity.
            for column, value in (
                ("source_uri", page.final_url),
                ("title", md_doc.title),
                ("author", md_doc.author),
                ("raw_text", text),
                ("metadata", json.dumps(document_metadata)),
            ):
                con.execute(
                    f"UPDATE documents SET {column} = ? WHERE document_id = ?",
                    [value, document_id],
                )
            _archive_url_chunks_for_replace(con, document_id)
            insert_on_conflict = "ignore"
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="web_article",
            # Personal-Reading Lane (SPR-02): a third-party web article the
            # owner fetched for their own reading lands personal_reading —
            # full body readable by the owner, NEVER served publicly / ad-
            # attributed / trained on (§9.0 Hachette/Bartz discipline). The
            # IMPORTED CONSTANT is passed, never the string literal
            # "personal_reading": corpus_audit's bypass-scanner flags any
            # content_class string literal to keep classify() the single
            # content_class chokepoint (an ast.Name is safe, an ast.Constant
            # str is the retired anti-pattern). This is belt-and-suspenders
            # with the insert_document deny-by-default fallback (SPR-01).
            content_class=PERSONAL_READING_CONTENT_CLASS,
            source_uri=page.final_url,
            title=md_doc.title,
            author=md_doc.author,
            published_at=None,
            investigation_id=investigation_id,
            raw_text=text,
            metadata=document_metadata,
            on_conflict=insert_on_conflict,
        )
        register_source_document(
            con,
            document_id=document_id,
            source_kind=SourceKind.WEB,
            content_class=PERSONAL_READING_CONTENT_CLASS,
        )
        # Spec §14.2 — record the requested_url→document_id alias so
        # future fetches that resolve to a different final_url for
        # the same logical content can find their canonical doc_id
        # via the alias table. Two aliases written: requested_url
        # (the input) and final_url (the redirect target). Both row
        # writes are upserts that increment seen_count when present.
        #
        # `now_ts` is passed as a parameter (rather than using the
        # SQL CURRENT_TIMESTAMP keyword) because DuckDB's ON CONFLICT
        # parser interprets CURRENT_TIMESTAMP in the UPDATE SET clause
        # as a column reference, which fails binding.
        now_ts = datetime.now(UTC).replace(tzinfo=None)
        for alias in {page.requested_url, page.final_url}:
            if not alias:
                continue
            con.execute(
                """
                INSERT INTO url_alias (
                    requested_url, document_id, first_seen_at,
                    last_seen_at, seen_count
                ) VALUES (?, ?, ?, ?, 1)
                ON CONFLICT (requested_url) DO UPDATE SET
                    last_seen_at = EXCLUDED.last_seen_at,
                    seen_count = url_alias.seen_count + 1
                """,
                [alias, document_id, now_ts, now_ts],
            )
        for i, chunk in enumerate(chunks):
            # ``insert_chunk`` has deterministic ids (``<doc>::c<index>``) and a
            # plain INSERT. It needs no ``on_conflict`` here: on the default
            # path the driver only reaches this block for a brand-new doc (an
            # unchanged re-run short-circuits in the PG driver before calling
            # ingest_url), and on the replace path the prior chunks were just
            # DELETEd above — so every insert in this loop is a fresh row.
            chunk_id = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
            )
            chunk_ids.append(chunk_id)
            chunks_written += 1

            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"{document_id}#{i}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "url",
                    "final_url": page.final_url,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    # Publish only after the substrate transaction has committed. Atomic file
    # replacement ensures readers see either the prior complete version or this
    # complete version, never a partially written projection.
    reader_snapshot_path = _write_url_projection(
        page=page,
        document_id=document_id,
        canonical_content_hash=chash,
        source_event_id=event_id,
        viewable=True,
    )
    _mark_url_projection_ready(
        db_path=resolved_db_path,
        document_id=document_id,
        snapshot_path=reader_snapshot_path,
    )

    return IngestUrlResult(
        document_id=document_id,
        final_url=page.final_url,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=md_doc.title,
        author=md_doc.author,
        reader_snapshot_path=reader_snapshot_path,
    )
