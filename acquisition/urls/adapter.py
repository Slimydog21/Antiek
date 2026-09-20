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
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Repo root on path for direct invocation.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
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
    replace_document_body,
)
from substrate.reader_html.store import store_reader_html  # noqa: E402
from substrate.rights.register import (  # noqa: E402
    SourceKind,
    register_source_document,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

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
    requested_url: str, *, db_path: str | None = None,
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
) -> IngestUrlResult:
    """Fetch ``url``, extract markdown, ingest into substrate.

    ``fetched`` lets callers reuse an already-fetched body (e.g. a
    crawler that batches requests) — when set, no HTTP is performed
    and ``http_client`` is ignored.

    ``on_conflict`` (default ``"ignore"``): on the default path a re-ingest of
    an unchanged ``document_id`` is a graph no-op (``insert_document`` early-
    returns; the PG driver also short-circuits before calling here when the
    content hash is unchanged). A caller that has already detected a *changed*
    body (its hash differs from the stored ``documents.content_hash``) passes
    ``"replace"``: the adapter deletes the prior ``documents`` row + its chunks
    first, then re-inserts the edited body under the SAME ``document_id`` — never
    forking a second doc and never silently keeping the stale body while
    reporting a re-ingest. (``insert_document`` itself only knows
    ``"error"``/``"ignore"``; ``"replace"`` is the adapter's delete-then-insert.)

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

    # Word-count gate. Emit the event so the operator can see the
    # fetch happened, but skip graph writes for plausibly-misextracted
    # pages — keeps the graph cleaner during dev.
    if md_doc.word_count < min_word_count:
        return IngestUrlResult(
            document_id=document_id,
            final_url=page.final_url,
            document_loaded_event_id=event_id,
            skipped_reason="low_word_count",
            title=md_doc.title,
            author=md_doc.author,
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: list[Chunk] = chunk_markdown(text)
    chunk_ids: list[str] = []
    node_ids: list[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/urls") as con:
        # On a CHANGED re-ingest (``on_conflict="replace"``), drop the prior
        # document row + its chunks FIRST so the re-insert below is a genuine
        # fresh write of the edited body under the SAME deterministic id (no
        # fork) — and so a shrinking edit leaves no orphan tail chunks. We then
        # call insert_document with ``"ignore"`` (the row is gone, so it inserts
        # cleanly and the SPR-01 deny-by-default guard still fires). Scoped to
        # the replace path; the default ignore/no-op path is untouched.
        # ``insert_document`` itself only knows "error"/"ignore"; replace is the
        # adapter's responsibility (delete-then-insert) so we never pass an
        # unsupported value down.
        insert_on_conflict = on_conflict
        if on_conflict == "replace":
            # A CHANGED re-ingest must overwrite the body under the SAME id
            # without forking. We do NOT delete the documents row (other tables
            # FK-reference it, so a DELETE trips a foreign-key constraint);
            # instead we UPDATE raw_text in place, then refresh the chunks.
            # Chunks are deleted first (deterministic content-addressed ids mean
            # a shrinking edit would otherwise orphan tail rows) and re-inserted
            # below. insert_document is then told "ignore" (the row already
            # exists) so it does not raise; the UPDATE is what persists the edit.
            replace_document_body(con, document_id, raw_text=text)
            con.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
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
            metadata={
                "requested_url": page.requested_url,
                "final_url": page.final_url,
                "content_type": page.content_type,
                "status_code": page.status_code,
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            on_conflict=insert_on_conflict,
        )
        register_source_document(
            con,
            document_id=document_id,
            source_kind=SourceKind.WEB,
            content_class=PERSONAL_READING_CONTENT_CLASS,
        )
        # Reader-HTML sidecar (doc→HTML S1): the reader snapshot is now stored
        # TRUSTED — the ISOLATED main-content HTML (never raw ``page.body``;
        # chrome was stripped in ``html_to_markdown``) passes through the book
        # allowlist sanitizer inside ``store_reader_html``, which stamps the
        # exact ``SANITIZER_VERSION`` at the same write. The sidecar is the
        # only trust carrier for the serve path; ``documents.metadata`` is not
        # touched (the §5.2 hazard). The legacy env-gated FILE snapshot above
        # stays untouched for back-compat with tests/test_reader_snapshot.py.
        store_reader_html(
            con,
            document_id=document_id,
            main_html=md_doc.main_html,
            source_kind="url",
            source_url=page.final_url,
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

    reader_snapshot_path: str | None = None
    if os.environ.get("ANTIEK_READER_SNAPSHOT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        from acquisition.snapshot.reader_html import (  # noqa: E402
            build_reader_snapshot,
            reader_snapshot_path_for,
            write_reader_snapshot,
        )

        snap_path = reader_snapshot_path_for(document_id)
        ingested_at = datetime.now(UTC).isoformat()
        # ``FetchedHtml.body`` is declared ``bytes``, but the guard below
        # tolerates duck-typed ``fetched=`` callers passing str — the union
        # keeps that existing isinstance narrowing honest for mypy.
        raw_html: str | bytes = page.body
        if isinstance(raw_html, bytes):
            raw_html = raw_html.decode(page.charset or "utf-8", errors="replace")
        snap_html = build_reader_snapshot(
            source_url=page.final_url,
            document_id=document_id,
            ip_holder_id=None,
            main_html=raw_html,
            ingested_at=ingested_at,
        )
        write_reader_snapshot(snap_path, snap_html)
        reader_snapshot_path = str(snap_path)

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
