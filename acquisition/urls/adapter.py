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
from runtime.db_lock import connect_write  # noqa: E402
from substrate.books.servability import servability_of  # noqa: E402
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
)
from substrate.graph.ops import (  # noqa: E402
    delete_document_chunks,
    insert_chunk,
    insert_chunk_admitted,
    insert_document,
    insert_document_admitted,
    insert_node,
    reseal_admitted_document,
)
from substrate.investigation_tenancy import InvestigationAuthority  # noqa: E402
from substrate.legal_gate.admission import admit_staged_document  # noqa: E402
from substrate.legal_gate.policy_store import (  # noqa: E402
    LegalPolicyDenied,
    account_policy_authority,
)
from substrate.legal_gate.read import (  # noqa: E402
    DocumentReplacementCapability,
    UrlReplacementArchive,
    authorize_document_replacement,
    document_custody_exists,
    read_chunks_compatibility,
    read_document,
    read_document_compatibility,
    url_legacy_replacement_archive,
    url_replacement_archive,
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
    document_id: str,
    *,
    requested_url: str,
    db_path: str | None,
    authority: InvestigationAuthority | None = None,
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
        document = read_document_compatibility(
            con,
            document_id,
            authority=authority,
            enforce=authority is not None,
        )
        row = None if document is None else (
            document["source_uri"],
            document["title"],
            document["author"],
            document["raw_text"],
            document["metadata"],
            document["content_class"],
            document["ip_holder_id"],
            document["owner_user_id"],
        )
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


def _mark_url_projection_ready(
    *,
    db_path: str,
    document_id: str,
    snapshot_path: str,
    authority: InvestigationAuthority | None = None,
) -> None:
    """Acknowledge a successfully published derived projection durably."""
    projection_hash = "sha256:" + hashlib.sha256(Path(snapshot_path).read_bytes()).hexdigest()
    with connect_write(db_path, purpose="acquisition/urls/projection-ready") as con:
        admitted_document: dict[str, Any] | None = None
        if authority is not None:
            admitted_document = read_document(con, authority, document_id)
        stored = admitted_document or read_document_compatibility(
            con, document_id, authority=None, enforce=False
        )
        if stored is None:
            return
        metadata = json.loads(stored["metadata"]) if stored["metadata"] else {}
        metadata["reader_projection_state"] = "ready"
        metadata["reader_projection_hash"] = projection_hash
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            [json.dumps(metadata), document_id],
        )
        if authority is not None and admitted_document is not None:
            reseal_admitted_document(
                con,
                authority,
                admission_receipt_id=str(
                    admitted_document["legal_admission_receipt_id"]
                ),
                admitted_content_sha256=hashlib.sha256(
                    str(admitted_document["raw_text"]).encode()
                ).hexdigest(),
                document_id=document_id,
            )


def _invalidate_url_projection(document_id: str) -> None:
    """Remove stale HTML before an authorized canonical replacement begins."""
    from acquisition.snapshot.reader_html import reader_snapshot_path_for

    reader_snapshot_path_for(document_id).unlink(missing_ok=True)


def _existing_url_document(
    document_id: str, *, db_path: str
) -> tuple[str, str | None, str | None, list[str]] | None:
    """Read current canonical hash/title/author/chunks for ignore admission."""
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        document = read_document_compatibility(
            con, document_id, authority=None, enforce=False
        )
        if document is None:
            return None
        raw_text = document["raw_text"]
        raw_metadata = document["metadata"]
        title = document["title"]
        author = document["author"]
        metadata = json.loads(raw_metadata) if raw_metadata else {}
        canonical_hash = str(
            metadata.get("canonical_content_hash") or "sha256:" + content_hash(str(raw_text or ""))
        )
        chunk_ids = [
            str(item["chunk_id"])
            for item in read_chunks_compatibility(
                con, document_id, authority=None, enforce=False
            )
        ]
        return (
            canonical_hash,
            str(title) if title else None,
            str(author) if author else None,
            chunk_ids,
        )
    finally:
        con.close()


def _archive_authorized_url_chunks_for_replace(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority,
    capability: DocumentReplacementCapability,
    state: UrlReplacementArchive,
) -> None:
    if not state.referenced_chunk_ids and not state.referenced_document_edge_ids:
        return
    old_hash = capability.prior_content_sha256
    revision_id = f"{document_id}::rev::{old_hash[:16]}"
    raw_metadata = state.document_value("metadata")
    revision_metadata = json.loads(raw_metadata) if raw_metadata else {}
    revision_metadata.update(
        {
            "revision_of": document_id,
            "revision_content_hash": f"sha256:{old_hash}",
            "archived_at": datetime.now(UTC).isoformat(),
            "reader_projection_state": "historical",
        }
    )
    historical = admit_staged_document(
        con,
        account_policy_authority(authority),
        investigation_digest=authority.investigation_digest,
        document_id=revision_id,
        provenance_class="external_network",
        canonical_url=str(state.document_value("source_uri") or ""),
        title=str(state.document_value("title") or ""),
        author=str(state.document_value("author") or ""),
        source_corpus="web",
        content_sha256=old_hash,
        at=datetime.now(UTC),
    )
    if historical.decision != "allow":
        raise LegalPolicyDenied("historical revision is unavailable")
    revision_metadata["legal_admission_receipt_id"] = historical.receipt_id
    insert_document_admitted(
        con,
        authority,
        admission_receipt_id=historical.receipt_id,
        admitted_content_sha256=old_hash,
        document_id=revision_id,
        source_uri=state.document_value("source_uri"),
        title=state.document_value("title"),
        author=state.document_value("author"),
        published_at=state.document_value("published_at"),
        source_tier=int(state.document_value("source_tier")),
        document_type="web_article_revision",
        investigation_id=authority.investigation_id,
        raw_text=str(state.document_value("raw_text")),
        metadata=revision_metadata,
        content_class=state.document_value("content_class"),
        ip_holder_id=state.document_value("ip_holder_id"),
        on_conflict="error",
    )
    clone_ids: dict[str, str] = {}
    for chunk in state.chunks:
        clone_id = f"{revision_id}::chunk::{chunk.chunk_index}"
        clone_ids[chunk.chunk_id] = insert_chunk_admitted(
            con,
            authority,
            admission_receipt_id=historical.receipt_id,
            admitted_content_sha256=old_hash,
            chunk_id=clone_id,
            document_id=revision_id,
            chunk_index=chunk.chunk_index,
            section_path=chunk.section_path,
            text=chunk.text,
            embedding=chunk.embedding,
            token_count=chunk.token_count,
        )
    for old_id in state.referenced_chunk_ids:
        con.execute(
            "UPDATE edges SET chunk_id = ?, source_document_id = ? WHERE chunk_id = ?",
            [clone_ids[old_id], revision_id, old_id],
        )
    for edge_id in state.referenced_document_edge_ids:
        con.execute(
            "UPDATE edges SET source_document_id = ? WHERE edge_id = ?",
            [revision_id, edge_id],
        )
    con.execute(
        "DELETE FROM chunk_tier_overrides WHERE chunk_id IN ("
        + ",".join("?" for _ in state.chunks)
        + ")",
        [chunk.chunk_id for chunk in state.chunks],
    )
    for override in state.overrides:
        con.execute(
            """INSERT INTO chunk_tier_overrides
                   (chunk_id, original_tier, override_tier, reason, set_at, set_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                clone_ids[override.chunk_id],
                override.original_tier,
                override.override_tier,
                override.reason,
                override.set_at,
                override.set_by,
            ],
        )
    # Superseded custody chunks remain inert because DuckDB cannot atomically
    # retarget and delete an FK parent. Receipt manifests make them unreadable.


def _archive_url_chunks_for_replace(con: Any, document_id: str) -> None:
    """Legacy replacement compatibility for authority-free callers."""
    state = url_legacy_replacement_archive(con, document_id)
    if state is None:
        return
    raw_metadata = state.document_value("metadata")
    metadata = json.loads(raw_metadata) if raw_metadata else {}
    old_hash = str(metadata.get("canonical_content_hash") or "unknown")
    revision_id = f"{document_id}::rev::{old_hash.removeprefix('sha256:')[:16]}"
    if not state.referenced_chunk_ids and not state.referenced_document_edge_ids:
        delete_document_chunks(con, document_id)
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
    insert_document(
        con,
        document_id=revision_id,
        source_uri=state.document_value("source_uri"),
        title=state.document_value("title"),
        author=state.document_value("author"),
        published_at=state.document_value("published_at"),
        source_tier=int(state.document_value("source_tier")),
        document_type="web_article_revision",
        investigation_id=state.document_value("investigation_id"),
        raw_text=str(state.document_value("raw_text")),
        metadata=revision_metadata,
        content_class=state.document_value("content_class"),
        ip_holder_id=state.document_value("ip_holder_id"),
        owner_user_id=state.document_value("owner_user_id"),
        on_conflict="ignore",
    )
    clone_ids: dict[str, str] = {}
    for chunk in state.chunks:
        clone_id = f"{revision_id}::chunk::{chunk.chunk_index}"
        clone_ids[chunk.chunk_id] = insert_chunk(
            con,
            chunk_id=clone_id,
            document_id=revision_id,
            chunk_index=chunk.chunk_index,
            section_path=chunk.section_path,
            text=chunk.text,
            embedding=chunk.embedding,
            token_count=chunk.token_count,
        )
    for old_id in state.referenced_chunk_ids:
        con.execute(
            "UPDATE edges SET chunk_id = ?, source_document_id = ? WHERE chunk_id = ?",
            [clone_ids[old_id], revision_id, old_id],
        )
    for edge_id in state.referenced_document_edge_ids:
        con.execute(
            "UPDATE edges SET source_document_id = ? WHERE edge_id = ?",
            [revision_id, edge_id],
        )
    for override in state.overrides:
        con.execute(
            "UPDATE chunk_tier_overrides SET chunk_id = ? WHERE chunk_id = ?",
            [clone_ids[override.chunk_id], override.chunk_id],
        )
    delete_document_chunks(con, document_id)


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
    admission_receipt_id: str | None = None


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
    authority: InvestigationAuthority | None = None,
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
    if fetched is None and authority is None:
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
    event_id: str | None = None
    if authority is None:
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
            if authority is not None:
                return IngestUrlResult(
                    document_id=document_id,
                    final_url=page.final_url,
                    skipped_reason=skipped_reason,
                    title=None,
                    author=None,
                )
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

    replacement_capability = None
    if authority is not None:
        if authority.investigation_id != investigation_id:
            raise ValueError("URL admission authority does not match investigation")
        with connect_write(resolved_db_path, purpose="acquisition/urls/existing") as con:
            if document_custody_exists(con, document_id):
                if on_conflict == "ignore":
                    try:
                        current = read_document(con, authority, document_id)
                    except LegalPolicyDenied:
                        current = None
                    if current is not None:
                        current_hash = "sha256:" + content_hash(current["raw_text"])
                        return IngestUrlResult(
                            document_id=document_id,
                            final_url=page.final_url,
                            skipped_reason=(
                                None
                                if current_hash == chash
                                else "changed_content_requires_replace"
                            ),
                            title=current["title"],
                            author=current["author"],
                            admission_receipt_id=current["legal_admission_receipt_id"],
                        )
                if on_conflict == "replace":
                    replacement_capability = authorize_document_replacement(
                        con,
                        authority,
                        document_id,
                        next_content_sha256=chash,
                    )
                    _invalidate_url_projection(document_id)

    if on_conflict == "ignore" and authority is None:
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

    with connect_write(resolved_db_path, purpose="acquisition/urls") as con:
        if authority is not None:
            con.execute("BEGIN TRANSACTION")
        admission_receipt_id: str | None = None
        replacement_archive: UrlReplacementArchive | None = None
        if authority is not None:
            if replacement_capability is not None:
                replacement_archive = url_replacement_archive(
                    con,
                    replacement_capability,
                    authority,
                    document_id,
                    chash,
                )
            admission = admit_staged_document(
                con,
                account_policy_authority(authority),
                investigation_digest=authority.investigation_digest,
                document_id=document_id,
                provenance_class="external_network",
                canonical_url=page.final_url,
                title=md_doc.title or "",
                author=md_doc.author or "",
                source_corpus="web",
                content_sha256=chash,
                at=datetime.now(UTC),
            )
            admission_receipt_id = admission.receipt_id
            if admission.decision != "allow":
                con.execute("COMMIT")
                return IngestUrlResult(
                    document_id=document_id,
                    final_url=page.final_url,
                    skipped_reason=f"legal_policy:{admission.reason_code or 'deny'}",
                    title=None,
                    author=None,
                    admission_receipt_id=admission.receipt_id,
                )
            document_metadata["legal_admission_receipt_id"] = admission.receipt_id
            document_metadata["source_event_id"] = None
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
            if authority is not None:
                if replacement_capability is None or replacement_archive is None:
                    raise LegalPolicyDenied("document replacement is unavailable")
                _archive_authorized_url_chunks_for_replace(
                    con,
                    document_id,
                    authority=authority,
                    capability=replacement_capability,
                    state=replacement_archive,
                )
            else:
                _archive_url_chunks_for_replace(con, document_id)
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
            insert_on_conflict = "ignore"
        document_insert = insert_document_admitted if authority is not None else insert_document
        document_insert(
            con,
            **(
                {
                    "authority": authority,
                    "admission_receipt_id": admission_receipt_id,
                    "admitted_content_sha256": chash,
                }
                if authority is not None
                else {}
            ),
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
        if replacement_capability is None:
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
            chunk_insert = insert_chunk_admitted if authority is not None else insert_chunk
            chunk_id = chunk_insert(
                con,
                **(
                    {
                        "authority": authority,
                        "admission_receipt_id": admission_receipt_id,
                        "admitted_content_sha256": chash,
                    }
                    if authority is not None
                    else {}
                ),
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
                **(
                    {"chunk_id": f"{document_id}::{admission_receipt_id}::c{i}"}
                    if authority is not None
                    else {}
                ),
            )
            chunk_ids.append(chunk_id)
            chunks_written += 1

            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"{document_id}#{i}"
            # Authorized acquisition publishes no content-derived graph event
            # from inside the database transaction. Loop 1 performs the
            # authority-bound extraction after commit.
            if authority is not None:
                continue
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

        if authority is not None:
            con.execute("COMMIT")

    if authority is not None:
        try:
            event_id = emit_typed(
                investigation_id,
                payload,
                document_id=document_id,
                role="acquisition",
                policy_id="acquisition/urls",
            )
            assert event_id is not None
        except Exception:
            return IngestUrlResult(
                document_id=document_id,
                final_url=page.final_url,
                chunk_ids=chunk_ids,
                node_ids=node_ids,
                chunks_written=chunks_written,
                skipped_reason="post_commit_publication_pending",
                title=md_doc.title,
                author=md_doc.author,
                admission_receipt_id=admission_receipt_id,
            )

    # Publish only after the substrate transaction has committed. Atomic file
    # replacement ensures readers see either the prior complete version or this
    # complete version, never a partially written projection.
    try:
        reader_snapshot_path = _write_url_projection(
            page=page,
            document_id=document_id,
            canonical_content_hash=chash,
            source_event_id=event_id,
            viewable=True,
        )
    except Exception:
        if authority is None:
            raise
        return IngestUrlResult(
            document_id=document_id,
            final_url=page.final_url,
            chunk_ids=chunk_ids,
            node_ids=node_ids,
            document_loaded_event_id=event_id,
            chunks_written=chunks_written,
            skipped_reason="post_commit_publication_pending",
            title=md_doc.title,
            author=md_doc.author,
            admission_receipt_id=admission_receipt_id,
        )
    _mark_url_projection_ready(
        db_path=resolved_db_path,
        document_id=document_id,
        snapshot_path=reader_snapshot_path,
        authority=authority,
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
        admission_receipt_id=admission_receipt_id,
    )
