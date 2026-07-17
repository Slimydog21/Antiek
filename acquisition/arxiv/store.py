"""Tier-gated PDF storage + promotion for an EXISTING arXiv row (SPR-04 M2).

THE LOAD-BEARING INVARIANT (hard-to-vary): a body is stored, and a row promoted
to a servable ``content_class``, for **T1 papers only**. A T3 paper's body is
NEVER written; a T2 paper is DEFERRED (counsel-gated, see below). The test suite
asserts the negative directly: after a store attempt on a T3 row, ``raw_text``
is still NULL and ``content_class`` is still the gated floor.

Operate on the row SPR-01 already harvested — do not mint a new id
-----------------------------------------------------------------
SPR-01's ``oai_persist`` inserted ONE ``documents`` row per paper, keyed by
``arxiv_doc_id(arxiv_id)``, at the gated floor (``restricted_pending_opt_in``),
with ``license_uri`` / ``rights_tier`` / ``license_content_class`` stamped into
``documents.metadata``. SPR-04 UPDATES THAT ROW: it sets ``raw_text`` to the
extracted body and promotes ``content_class`` to the license-derived servable
class. It must NOT create a ``book_doc_id`` row (``ingest_servable_book`` would) —
that would duplicate the paper and orphan its rights metadata. A row that does
not exist is an error: SPR-01 must have harvested the paper first.

The tier gate — why T1 only, and why T2 is deferred not stored
--------------------------------------------------------------
``substrate.rights.resolve_tier(license_uri)`` is the authoritative tier. Only
``RightsTier.T1_REDISTRIBUTABLE`` proceeds to fetch-store-promote.

  * **T3** (arXiv-default / unknown / absent license — the corpus majority) →
    REFUSED. Storing it would rehost a paper Antiek holds no redistribution right
    to (the *Hachette* / *Bartz* liability the §9.0 gate exists to avoid). This is
    an ``assert``-class refusal: the function returns a ``refused`` outcome and
    writes NOTHING.
  * **T2** (CC-BY-NC) → DEFERRED. Not stored, not promoted. The shipped canonical
    resolver ``acquisition.licenses_core`` gates CC-BY-NC (``redistributable=
    False`` — "Antiek's ad-funded serving is commercial"), and SPR-02's serve
    guard's ``_BODY_SERVABLE_TIERS = {T1}`` would RAISE if a T2 body were ever
    promoted+served. So T2 storage-for-serving is MECHANICALLY PRECLUDED today —
    deny-by-default on the unresolved "is a commercial platform's NC use
    commercial" question. The T2-in-app-reading world is the same §9.0/counsel-
    gated future as SPR-02's ``{T1}``→``{T1,T2}`` flip. See
    docs/decisions/arxiv-t1-only-storage.md (which cites SPR-02's
    arxiv-t2-noncommercial-serving.md).

The promotion class is RE-DERIVED, not re-stored
------------------------------------------------
The servable ``content_class`` comes from the canonical mapping
``acquisition.arxiv.licenses.resolve_license(license_uri).content_class`` (CC0 →
public_domain; CC-BY / CC-BY-SA → source_declared_open) — the SAME table the
serve gate enforces against. We re-derive from the immutable ``license_uri``
rather than trusting the ``license_content_class`` cached in metadata, so a
corrupt cache cannot launder a body to servable. ``license_uri`` /
``license_basis`` / ``rights_tier`` are IMMUTABLE here — never touched.

The backstop assertion
----------------------
After a T1 store, ``substrate.books.serve_guard.serve_full_text_guarded`` MUST
serve the body without raising (tier=T1). The store path itself runs that guard
as a self-check so a promotion that the SPR-02 guard would reject fails loudly at
write time, not silently at read time.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from runtime.db_lock import LockedConnection, connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import update_document_gate_columns
from substrate.rights import RightsTier, resolve_tier

from .adapter import arxiv_doc_id
from .index import index_body
from .licenses import resolve_license
from .pdf_fetch import FetchedPdf

logger = logging.getLogger("acquisition.arxiv.store")

# Below this word count the extracted body is treated as a husk (a scanned /
# image-only PDF, or an extraction failure) and is NOT stored. Mirrors the book
# adapter's MIN_INGEST_WORD_COUNT so the two ingest paths apply the same
# don't-store-a-husk floor.
MIN_BODY_WORD_COUNT = 100


# The PDF→text extractor signature: pdf bytes -> an object exposing .markdown /
# .word_count / .page_count / .title. The default is the book adapter's reader
# (``acquisition.books.reader.read_pdf``) — REUSED, not re-implemented. It is a
# parameter so tests can inject a deterministic fake extractor without building a
# byte-perfect PDF, while production parses the real bytes.
PdfTextExtractor = Callable[[bytes], object]


@dataclass(frozen=True)
class StoreOutcome:
    """The result of a store attempt on one arXiv row.

    ``status`` is one of:
      - ``"stored"``   — T1: body written, content_class promoted, body indexed.
      - ``"refused"``  — T3 (or unknown tier): nothing written; the row is left
                          at the gated floor with raw_text NULL.
      - ``"deferred"`` — T2 (CC-BY-NC): nothing written; counsel-gated future.
      - ``"skipped_low_words"`` — T1 but the extracted body is a husk; not stored.
      - ``"skipped_extraction_failure"`` — T1 with a ``%PDF``-headed body the
                          reader cannot parse (a corrupt / encrypted / truncated
                          PDF that raised during extraction): logged + left
                          metadata-only, never stored, never faked (honesty
                          bar 1).

    ``content_class`` echoes the row's class AFTER the attempt (the promoted
    servable class on ``stored``; the unchanged gated floor otherwise), so a
    caller can assert the gate held without re-querying.
    """

    document_id: str
    arxiv_id: str
    status: str
    tier: RightsTier
    content_class: str
    chunks_written: int = 0
    sha256: str | None = None
    page_count: int | None = None
    word_count: int | None = None


def _record_fetch_audit(
    con: LockedConnection, *, arxiv_id: str, document_id: str, fetched: FetchedPdf
) -> None:
    """SPR-09 M4 — record the ``arxiv.fetch`` leg for ``store_pdf_for_arxiv_row``.

    HONESTY NOTE (round-3): ``store_pdf_for_arxiv_row`` is TEST-ONLY today — it has
    ZERO production callers (verified: the operator CLIs run
    ``ingest_paper_with_rights`` → ``ingest_servable_book``, never this store
    path). The round-2 claim that THIS was "the REAL production fetch→store
    boundary" was wrong; the genuine production fetch leg is emitted in
    ``acquisition.arxiv.adapter.ingest_paper_with_rights`` (the live on-demand T1
    path). This emission is retained because the store path is a real (if
    currently test-exercised) T1 fetch→store boundary and SHOULD carry a fetch
    leg if it is ever wired into production — but the production trace's fetch leg
    does NOT come from here.

    §9.0: provenance refs ONLY (source_url / sha256 / byte_size) — never the body.
    Defensively isolated: an audit-layer failure must NEVER break the store (wrap
    + log), exactly like the serve/accrue legs (books.py / book_escrow.py)."""
    try:
        from substrate.audit.arxiv_audit import ARXIV_FETCH, record_event

        record_event(
            con,
            arxiv_id=arxiv_id,
            document_id=document_id,
            kind=ARXIV_FETCH,
            detail={
                "source_url": fetched.source_url,
                "sha256": fetched.sha256,
                "byte_size": fetched.byte_size,
            },
        )
    except Exception:
        logger.exception(
            "arxiv_audit fetch-leg failed for arxiv_id=%s; store unaffected",
            arxiv_id,
        )


def _read_doc_row(con: LockedConnection, document_id: str) -> dict | None:
    """Return ``{license_uri, content_class, metadata}`` for the row, or None
    when the row is absent. Raises ``ValueError`` on malformed metadata JSON —
    we never blind-overwrite a row whose rights metadata we cannot safely read."""
    row = con.execute(
        "SELECT content_class, metadata FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None:
        return None
    content_class, raw_meta = row
    if raw_meta is None:
        metadata: dict = {}
    elif isinstance(raw_meta, dict):
        metadata = raw_meta
    else:
        try:
            metadata = json.loads(raw_meta)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(
                f"malformed metadata JSON for {document_id} — refusing to store "
                "against a row whose rights anchor cannot be read"
            ) from exc
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "content_class": content_class,
        "license_uri": metadata.get("license_uri"),
        "metadata": metadata,
    }


def store_pdf_for_arxiv_row(
    fetched: FetchedPdf,
    *,
    db_path: str | None = None,
    embedder=None,
    extract_text: PdfTextExtractor | None = None,
    min_word_count: int = MIN_BODY_WORD_COUNT,
    now: Callable[[], datetime] | None = None,
) -> StoreOutcome:
    """Store + promote + index a fetched PDF for its EXISTING arXiv row, T1 only.

    ``fetched`` is the verified result from ``acquisition.arxiv.pdf_fetch`` (it
    carries the arxiv_id, source_url, bytes, sha256, byte_size). The flow:

      1. Resolve the row by ``arxiv_doc_id(fetched.arxiv_id)``; read its
         immutable ``license_uri`` from metadata. A missing row is an error.
      2. ``resolve_tier(license_uri)`` → gate:
         T2 → ``deferred`` (no write); non-T1/non-T2 → ``refused`` (no write);
         T1 → proceed.
      3. Extract text (default: the book reader). A husk (< ``min_word_count``
         words) → ``skipped_low_words`` (no write — never store a husk).
      4. Under ONE ``connect_write`` lock: UPDATE raw_text (plain UPDATE — it is
         unindexed), promote content_class via ``update_document_gate_columns``
         to ``resolve_license(license_uri).content_class``, merge a
         ``pdf_acquisition`` provenance block into metadata (additive — rights
         keys untouched), and index the body (M3) on the same connection.
      5. Self-check: ``serve_full_text_guarded`` must now serve the body without
         raising. A failure here means the promotion disagrees with the SPR-02
         guard — we raise rather than leave a mis-promoted row.

    ``extract_text`` / ``embedder`` are injectable for CI (a fake extractor + a
    deterministic fake embedder), so a test needs neither a byte-perfect PDF nor
    a sentence-transformers model.
    """
    arxiv_id = fetched.arxiv_id
    document_id = arxiv_doc_id(arxiv_id)
    resolved_db_path = ensure_initialized(db_path or default_db_path())

    if extract_text is None:
        from acquisition.books.reader import read_pdf

        extract_text = read_pdf  # type: ignore[assignment]
    if embedder is None:
        from processing.embedding.embed import default_embedding_provider

        embedder = default_embedding_provider()
    clock = now or (lambda: datetime.now(UTC))

    with connect_write(resolved_db_path, purpose="acquisition/arxiv_pdf_store") as con:
        row = _read_doc_row(con, document_id)
        if row is None:
            raise ValueError(
                f"no documents row for arxiv_id={arxiv_id!r} (document_id="
                f"{document_id!r}); SPR-01's OAI harvest must persist the paper "
                "before SPR-04 can store its PDF body."
            )

        license_uri = row["license_uri"]
        current_class = row["content_class"]
        tier = resolve_tier(license_uri)

        # --- the tier gate (fail-closed) ----------------------------------
        if tier is RightsTier.T2_NON_COMMERCIAL:
            # Deferred — counsel-gated. No fetch-to-store, no promote. The body
            # is mechanically un-servable today (SPR-02 guard {T1}); storing it
            # would be a no-op at best and a latent rights leak at worst.
            return StoreOutcome(
                document_id=document_id,
                arxiv_id=arxiv_id,
                status="deferred",
                tier=tier,
                content_class=current_class,
            )
        if tier is not RightsTier.T1_REDISTRIBUTABLE:
            # T3 / unknown — REFUSED. Storing rehosts a paper Antiek may not host.
            return StoreOutcome(
                document_id=document_id,
                arxiv_id=arxiv_id,
                status="refused",
                tier=tier,
                content_class=current_class,
            )

        # --- T1: extract, gate the husk, then write+promote+index ---------
        # The untrusted-PDF-parsing boundary: the body cleared the %PDF
        # precheck, but a corrupt / encrypted / truncated PDF can still make the
        # reader RAISE mid-parse. Catch ONLY that call (real bugs elsewhere must
        # still propagate) and skip gracefully — mirroring the husk path — so a
        # future batch caller is not aborted by one bad PDF. Nothing is written:
        # raw_text stays NULL, the class stays the gated floor (honesty bar 1:
        # never store or fake a body we could not read).
        try:
            read = extract_text(fetched.content)
        except Exception as exc:
            logger.warning(
                "arxiv pdf extraction failed for %s: %s — skipping (metadata-only, "
                "not stored)",
                arxiv_id,
                exc,
            )
            return StoreOutcome(
                document_id=document_id,
                arxiv_id=arxiv_id,
                status="skipped_extraction_failure",
                tier=tier,
                content_class=current_class,
            )
        body = getattr(read, "markdown", "") or ""
        word_count = int(getattr(read, "word_count", 0) or 0)
        page_count = getattr(read, "page_count", None)

        if word_count < min_word_count:
            # A scanned / image-only PDF or a failed extraction. Do NOT store a
            # husk and do NOT promote — leave the row metadata-only (honesty
            # bar 1: never fabricate or store an empty body that looks servable).
            return StoreOutcome(
                document_id=document_id,
                arxiv_id=arxiv_id,
                status="skipped_low_words",
                tier=tier,
                content_class=current_class,
                page_count=page_count,
                word_count=word_count,
            )

        promoted_class = resolve_license(license_uri).content_class

        # Every mutation below is one DuckDB transaction. Any exception exits
        # the connection context with an open transaction, and DuckDB rolls it
        # back on close; the explicit COMMIT occurs only after indexing,
        # guarded serve verification, and audit persistence all succeed.
        con.execute("BEGIN")
        # raw_text is UNINDEXED → a plain UPDATE is safe (the indexed-column
        # dance in update_document_gate_columns is only needed for content_class).
        con.execute(
            "UPDATE documents SET raw_text = ? WHERE document_id = ?",
            [body, document_id],
        )

        # Promote the gate column via the ONLY sanctioned primitive (a raw
        # UPDATE of content_class fails on DuckDB 1.5.2 once chunks reference the
        # row). The class is RE-DERIVED from the immutable license_uri.
        if current_class != promoted_class:
            update_document_gate_columns(
                con,
                document_id,
                content_class=promoted_class,
                set_content_class=True,
            )
        else:
            # Re-store keeps the indexed gate column untouched (DuckDB cannot
            # rewrite a referenced indexed row) but the body may have changed,
            # so refresh its unindexed dependent declaration in this txn.
            from substrate.twin_recursion import stamp_existing_document

            stamp_existing_document(con, document_id, refresh=True)

        # Additive provenance merge — mirrors SPR-03's enrichment merge. The
        # rights anchors (license_uri / license_basis / rights_tier) are left
        # verbatim; only the pdf_acquisition block is added.
        metadata = dict(row["metadata"])
        metadata["pdf_acquisition"] = {
            "source_url": fetched.source_url,
            "fetched_at": clock().isoformat(),
            "sha256": fetched.sha256,
            "byte_size": fetched.byte_size,
            "page_count": page_count,
        }
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            [json.dumps(metadata), document_id],
        )

        # Index the body for search (M3) on the SAME locked connection, so the
        # body write and its index are one atomic critical section.
        chunk_ids = index_body(
            con, document_id=document_id, body=body, embedder=embedder
        )

        # --- the backstop self-check (rigor bar 3) ------------------------
        # The promoted row MUST serve cleanly through the SPR-02 guard. If the
        # promotion disagrees with the guard's {T1} ceiling, this raises
        # T3BodyServeError here at WRITE time rather than leaking a mis-promoted
        # body at read time. For a correctly-resolved T1 row this is a no-op.
        from substrate.books.serve_guard import serve_full_text_guarded

        result = serve_full_text_guarded(con, document_id)
        if result.full_text is None:
            raise RuntimeError(
                f"post-store self-check: serve gate did not emit a body for "
                f"{document_id!r} after a T1 promotion to {promoted_class!r} "
                f"(servable={result.servable}, reason={result.reason!r}). A "
                "promoted T1 row must be servable; refusing to leave it in this "
                "inconsistent state."
            )

        # SPR-09 M4 — emit the FETCH leg for this store path. The body is now
        # genuinely stored + servable on this locked connection, so a fetch leg is
        # consistent with the lifecycle. NOTE (round-3): this store path is
        # TEST-ONLY today; the PRODUCTION fetch leg is emitted in
        # ``adapter.ingest_paper_with_rights`` (the live CLI path). Same locked
        # connection; defensively isolated so it can never break the store.
        _record_fetch_audit(
            con, arxiv_id=arxiv_id, document_id=document_id, fetched=fetched
        )
        con.execute("COMMIT")

    return StoreOutcome(
        document_id=document_id,
        arxiv_id=arxiv_id,
        status="stored",
        tier=tier,
        content_class=promoted_class,
        chunks_written=len(chunk_ids),
        sha256=fetched.sha256,
        page_count=page_count,
        word_count=word_count,
    )


__all__ = [
    "StoreOutcome",
    "store_pdf_for_arxiv_row",
    "MIN_BODY_WORD_COUNT",
    "PdfTextExtractor",
]
