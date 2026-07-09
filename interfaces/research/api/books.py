"""Servable-corpus query API (Read SPR-01 M6).

The thin HTTP surface the Library (SPR-02) and Reader (SPR-03) consume.
The legal gate lives in the substrate (``substrate/books/``); this router
only adapts it to HTTP. Two guarantees it inherits, not re-implements:

- A gated book is returned in listings/detail FLAGGED (its servability
  status is always present) but its full text is never inline.
- The ``/full-text`` endpoint routes through ``substrate.books.serve``,
  so the deny-by-default gate is enforced at the data layer regardless of
  what the caller asks for.

Endpoints:

  GET /books                         list servable books (default)
  GET /books?status=gated            list gated metadata-only books
  GET /books?status=all              list both, each flagged
  GET /books/{document_id}           book detail + TOC (never full text)
  GET /books/{document_id}/full-text serve full text (gated by serve.py)

All endpoints are reads; they use ``connect_read`` and run concurrently
with the single writer.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Literal, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from substrate.books.model import BookAsset, get_book_asset, list_book_assets
from substrate.books.serve import ServeResult

from .operator_allowlist import operator_allowlist_from_env
from .serve_guard import serve_full_text_guarded

logger = logging.getLogger("antiek.interfaces.books")

# §9.0 owner-read policy tags. The owner's OWN-corpus read path (talk-to-book +
# corpus search) passes the PRIVILEGED ``operator_only`` tag so the retrieval
# gate admits the owner's gated/personal content; everything else stays on the
# non-privileged default. The string is the canonical privileged tag from
# ``substrate.graph.retrieval_gate.PRIVILEGED_POLICY_TAGS`` — kept here as a
# named local so the owner-read intent is legible at the call site (the gate
# module remains the single source of which tags are privileged).
_OWNER_READ_POLICY_TAG = "operator_only"
_PUBLIC_READ_POLICY_TAG = "attribution_eligible"

# Auth methods the middleware (``app.py::_operator_auth_middleware``) stamps on
# ``request.state.auth_method`` once a caller has PROVEN owner identity with a
# real credential. These four are the ONLY paths past the middleware when
# enforcement is ON (an unauthenticated caller is 401'd and never reaches the
# endpoint), so each one is a positive proof that THIS request is the owner.
#
# ``unauthenticated_local`` is deliberately EXCLUDED: it means enforcement is
# OFF (no ANTIEK_OPERATOR_EMAIL / _TOKEN / _SECRET set). The §9.0 gated-content
# bypass must bind to a real credential, never to "auth happened to be disabled"
# — otherwise a box accidentally deployed without auth would serve the owner's
# gated/personal corpus to any caller. Fail-closed by construction: the bypass
# is granted only on an explicit authenticated method, never by default. (The
# rest of the app gives ``unauthenticated_local`` full operator SCOPES for
# local dev convenience; the §9.0 retrieval bypass is held to the stricter
# bar deliberately — see the handoff steelman.)
#
# ── SINGLE-OPERATOR ENFORCEMENT (CLAUDE.md invariant #5) ─────────────────────
# ``authenticated ⇒ owner`` holds ONLY under the single-operator invariant.
# ``ANTIEK_OPERATOR_EMAIL`` is parsed as a COMMA-SEPARATED allowlist
# (app.py:1215), and this helper keys on ``auth_method`` — it never consults
# ``request.state``'s ``user_id`` / ``user_email``, and ``search()`` applies no
# ``owner_user_id`` filter (the column exists, schema.py:81). So with TWO+
# operator emails, two distinct tenants would both authenticate and a shared
# ``operator_only`` could read each other's ``personal_reading`` corpus.
# ``_owner_read_policy_tag`` therefore grants the privilege ONLY when the
# deployment is provably single-operator (``operator_allowlist_from_env``
# resolves ≤ 1 operator); a multi-operator config FAILS CLOSED to the
# non-privileged tag, so the cross-tenant path is STRUCTURALLY IMPOSSIBLE, not
# merely documented. When Sprint-22 multi-user lands, restoring multi-operator
# owner-read requires scoping retrieval by ``request.state.user_id`` against
# ``owner_user_id``; ``operator_only`` alone is not sufficient.
_OWNER_AUTH_METHODS: frozenset[str] = frozenset({
    "antiek_session_cookie",
    "cloudflare_access_email",
    "cloudflare_service_token",
    "bearer_token",
})


def _owner_read_policy_tag(request: Request) -> str:
    """Resolve the §9.0 retrieval policy_tag for an OWNER read endpoint.

    Returns the PRIVILEGED ``operator_only`` tag ONLY when the auth middleware
    has stamped ``request.state.auth_method`` with one of the four AUTHENTICATED
    methods (a real credential proven: session cookie, Cloudflare Access email,
    Cloudflare service token, or operator bearer). For ANY other value — see the
    ``_OWNER_AUTH_METHODS`` comment above for why ``unauthenticated_local`` and
    absent state are EXCLUDED (the fail-closed, bind-to-a-real-credential rule) —
    it returns the non-privileged default, so the §9.0 gate keeps excluding
    gated/personal content. The privileged bypass requires a positive,
    middleware-set authenticated signal; it is NEVER the default.

    The signal is SERVER-DERIVED: ``auth_method`` is written only by the auth
    middleware on the request object; a caller cannot set ``request.state`` or
    spoof it via a header/param. When enforcement is on, a non-owner caller is
    rejected with 401 BEFORE this runs, so it can only ever see owner requests.

    PRIVILEGE == OWNER is ENFORCED, not merely assumed: the bypass is granted
    only when the deployment is single-operator (``operator_allowlist_from_env``
    resolves ≤ 1 operator); a multi-operator config FAILS CLOSED to the
    non-privileged tag. See the SINGLE-OPERATOR ENFORCEMENT note above
    ``_OWNER_AUTH_METHODS``.
    """
    auth_method = getattr(getattr(request, "state", None), "auth_method", None)
    # SINGLE-OPERATOR ENFORCEMENT: the privilege is owner-scoped only when the
    # deployment has ≤ 1 operator. With 2+ operator emails the bypass would be
    # cross-tenant (this helper keys on auth_method, not user_id), so it FAILS
    # CLOSED to the non-privileged tag.
    if auth_method in _OWNER_AUTH_METHODS and len(operator_allowlist_from_env()) <= 1:
        return _OWNER_READ_POLICY_TAG
    return _PUBLIC_READ_POLICY_TAG

# arXiv canonical-link prefix; the serve guard stamps result.canonical_url as
# ``https://arxiv.org/abs/<arxiv_id>`` for an arXiv doc (None otherwise), so the
# arxiv_id is recoverable from it for the M4 serve-audit without re-reading the DB.
_ARXIV_ABS_PREFIX = "https://arxiv.org/abs/"


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _record_arxiv_serve_audit(db_path: str, document_id: str, result: ServeResult) -> None:
    """SPR-09 M4 — record an ``arxiv.serve`` leg for an arXiv full-text serve.

    Defensively isolated: a failure here must NEVER break the serve, so the whole
    body is wrapped. Only an arXiv doc carries a ``canonical_url`` (the
    ``https://arxiv.org/abs/<id>`` link the guard stamps) — we derive the arxiv_id
    from it and skip non-arXiv books. §9.0: we record only the served/gated REASON
    + tier + servable flag, never the body. The audit takes its OWN write lock
    (the serve itself ran on a read connection)."""
    try:
        canonical = getattr(result, "canonical_url", None)
        if not canonical or not canonical.startswith(_ARXIV_ABS_PREFIX):
            return  # non-arXiv book — no arXiv audit leg
        arxiv_id = canonical[len(_ARXIV_ABS_PREFIX):]
        if not arxiv_id:
            return
        from runtime.db_lock import connect_write
        from substrate.audit.arxiv_audit import ARXIV_SERVE, record_event

        con = connect_write(db_path, purpose="arxiv_serve_audit")
        try:
            record_event(
                con,
                arxiv_id=arxiv_id,
                document_id=document_id,
                kind=ARXIV_SERVE,
                reason=result.reason,
                tier=result.tier,
                detail={
                    "servable": bool(result.servable),
                    "ad_eligible": bool(result.ad_eligible),
                    "served_body": result.full_text is not None,
                },
            )
        finally:
            con.close()
    except Exception:
        logger.exception(
            "arxiv_audit serve-leg failed for document_id=%s; serve unaffected",
            document_id,
        )


# ── Response shapes ─────────────────────────────────────────────────


class TocItemResponse(BaseModel):
    title: str
    page_index: int | None
    level: int


class BookSummary(BaseModel):
    document_id: str
    title: str | None
    author: str | None
    servability: str
    servable_full_text: bool
    page_count: int
    cover_uri: str | None
    ip_holder_id: str | None
    taken_down: bool

    @classmethod
    def from_asset(cls, a: BookAsset) -> BookSummary:
        return cls(
            document_id=a.document_id,
            title=a.title,
            author=a.author,
            servability=a.servability.value,
            servable_full_text=a.servable_full_text,
            page_count=a.page_count,
            cover_uri=a.cover_uri,
            ip_holder_id=a.ip_holder_id,
            taken_down=a.taken_down,
        )


class BookDetail(BookSummary):
    pagination_scheme: str
    provenance: str | None
    license_basis: str | None
    toc: list[TocItemResponse]

    @classmethod
    def from_asset(cls, a: BookAsset) -> BookDetail:
        return cls(
            **BookSummary.from_asset(a).model_dump(),
            pagination_scheme=a.pagination_scheme,
            provenance=a.provenance,
            license_basis=a.license_basis,
            toc=[
                TocItemResponse(title=t.title, page_index=t.page_index, level=t.level)
                for t in a.toc
            ],
        )


class BookListResponse(BaseModel):
    books: list[BookSummary]
    count: int


class CuratedBookResponse(BaseModel):
    document_id: str
    title: str | None
    author: str | None
    score: float


class CurateResponse(BaseModel):
    prompt: str
    books: list[CuratedBookResponse]


class BookPurchaseRequestIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1000)
    store: Literal["publisher", "amazon", "bookshop", "google_books", "apple_books", "other"] = (
        "other"
    )
    max_price_usd_cents: int = Field(ge=0, le=50_000)
    desired_format: Literal["epub", "html", "pdf", "kindle", "unknown"] = "unknown"
    import_target: Literal["antiek_html"] = "antiek_html"
    acknowledge_manual_purchase_only: bool = False


class BookPurchaseRequestOut(BaseModel):
    request_id: str
    status: Literal["needs_operator_purchase"]
    title: str
    author: str | None
    store: str
    source_url: str | None
    max_price_usd_cents: int
    desired_format: str
    import_target: Literal["antiek_html"]
    purchase_allowed: bool
    external_call_performed: bool
    spend_reserved_usd_cents: int
    charge_attempted: bool
    ingest_attempted: bool
    html_hosting_required: bool
    required_operator_steps: list[str]
    policy_notes: list[str]


class BookHtmlImportPreflightIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str | None = Field(default=None, max_length=200)
    source_request_id: str | None = Field(default=None, max_length=80)
    file_name: str | None = Field(default=None, max_length=300)
    file_format: Literal["epub", "html", "pdf", "kindle", "unknown"] = "unknown"
    has_legal_access: bool = False
    acknowledge_no_upload_or_ingest: bool = False


class BookHtmlImportPreflightOut(BaseModel):
    import_preflight_id: str
    status: Literal["ready_for_operator_file", "blocked"]
    title: str
    author: str | None
    source_request_id: str | None
    file_name: str | None
    file_format: str
    import_target: Literal["antiek_html"]
    external_call_performed: bool
    file_uploaded: bool
    file_read_attempted: bool
    ingest_attempted: bool
    graph_mutation_performed: bool
    html_conversion_required: bool
    html_hosting_required: bool
    required_operator_steps: list[str]
    policy_notes: list[str]


class BookHtmlFileHandoffIn(BaseModel):
    import_preflight_id: str = Field(min_length=1, max_length=80)
    file_name: str = Field(min_length=1, max_length=300)
    file_format: Literal["epub", "html", "pdf", "kindle", "unknown"] = "unknown"
    storage_ref: str = Field(min_length=1, max_length=500)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    acknowledge_manual_storage_only: bool = False
    acknowledge_no_file_read_or_conversion: bool = False


class BookHtmlFileHandoffOut(BaseModel):
    handoff_id: str
    status: Literal["ready_for_conversion_review"]
    import_preflight_id: str
    file_name: str
    file_format: str
    storage_ref: str
    checksum_sha256: str | None
    import_target: Literal["antiek_html"]
    storage_ref_recorded: bool
    upload_accepted: bool
    external_call_performed: bool
    file_read_attempted: bool
    conversion_attempted: bool
    ingest_attempted: bool
    graph_mutation_performed: bool
    html_conversion_required: bool
    html_hosting_required: bool
    required_operator_steps: list[str]
    policy_notes: list[str]


class BookHtmlConversionReviewIn(BaseModel):
    handoff_id: str = Field(min_length=1, max_length=80)
    import_preflight_id: str = Field(min_length=1, max_length=80)
    converter: Literal["pandoc", "calibre", "native_html", "manual_review", "unknown"] = "unknown"
    sandbox_profile: Literal["locked_down", "network_disabled", "manual_only"] = "locked_down"
    output_format: Literal["antiek_html"] = "antiek_html"
    acknowledge_sandbox_required: bool = False
    acknowledge_no_conversion_run: bool = False


class BookHtmlConversionReviewOut(BaseModel):
    conversion_review_id: str
    status: Literal["ready_for_explicit_conversion_job"]
    handoff_id: str
    import_preflight_id: str
    converter: str
    sandbox_profile: str
    output_format: Literal["antiek_html"]
    storage_ref_read: bool
    file_read_attempted: bool
    conversion_attempted: bool
    output_written: bool
    ingest_attempted: bool
    graph_mutation_performed: bool
    html_hosting_required: bool
    serve_gate_required: bool
    required_operator_steps: list[str]
    policy_notes: list[str]


class BookHtmlConversionResultIn(BaseModel):
    conversion_review_id: str = Field(min_length=1, max_length=80)
    handoff_id: str = Field(min_length=1, max_length=80)
    html_output_ref: str = Field(min_length=1, max_length=500)
    html_checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    page_count_estimate: int | None = Field(default=None, ge=0, le=100_000)
    acknowledge_output_metadata_only: bool = False
    acknowledge_no_publish_or_serve: bool = False


class BookHtmlConversionResultOut(BaseModel):
    conversion_result_id: str
    status: Literal["ready_for_serve_gate_review"]
    conversion_review_id: str
    handoff_id: str
    html_output_ref: str
    html_checksum_sha256: str | None
    page_count_estimate: int | None
    import_target: Literal["antiek_html"]
    output_metadata_recorded: bool
    output_ref_fetched: bool
    html_output_read: bool
    ingest_attempted: bool
    graph_mutation_performed: bool
    shelf_publication_attempted: bool
    full_text_served: bool
    serve_gate_required: bool
    required_operator_steps: list[str]
    policy_notes: list[str]


class BookHtmlServeGateReviewIn(BaseModel):
    conversion_result_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    author: str | None = Field(default=None, max_length=200)
    rights_basis: Literal[
        "public_domain",
        "publisher_opt_in",
        "platform_authored",
        "personal_license",
        "unknown",
    ] = "unknown"
    servability_decision: Literal["servable_full_text", "gated_metadata_only", "blocked"] = (
        "gated_metadata_only"
    )
    acknowledge_rights_reviewed: bool = False
    acknowledge_no_publication: bool = False


class BookHtmlServeGateReviewOut(BaseModel):
    serve_gate_review_id: str
    status: Literal["ready_for_publication_request", "blocked"]
    conversion_result_id: str
    title: str
    author: str | None
    rights_basis: str
    servability_decision: str
    import_target: Literal["antiek_html"]
    rights_review_recorded: bool
    html_output_read: bool
    ingest_attempted: bool
    graph_mutation_performed: bool
    shelf_publication_attempted: bool
    full_text_served: bool
    publication_allowed_next: bool
    required_operator_steps: list[str]
    policy_notes: list[str]


class BookHtmlPublicationRequestIn(BaseModel):
    serve_gate_review_id: str = Field(min_length=1, max_length=80)
    conversion_result_id: str = Field(min_length=1, max_length=80)
    document_id_hint: str | None = Field(default=None, max_length=160)
    shelf_visibility: Literal["private_library", "workspace_only"] = "private_library"
    acknowledge_publication_intent: bool = False
    acknowledge_no_ingest_or_serve: bool = False


class BookHtmlPublicationRequestOut(BaseModel):
    publication_request_id: str
    status: Literal["ready_for_explicit_publish_job"]
    serve_gate_review_id: str
    conversion_result_id: str
    document_id_hint: str | None
    shelf_visibility: str
    import_target: Literal["antiek_html"]
    publication_intent_recorded: bool
    ingest_attempted: bool
    graph_mutation_performed: bool
    shelf_publication_attempted: bool
    full_text_served: bool
    reader_route_created: bool
    required_operator_steps: list[str]
    policy_notes: list[str]


class BookHtmlPublishJobIn(BaseModel):
    publication_request_id: str = Field(min_length=1, max_length=80)
    serve_gate_review_id: str = Field(min_length=1, max_length=80)
    document_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    author: str | None = Field(default=None, max_length=200)
    html_body: str = Field(min_length=1, max_length=2_000_000)
    rights_basis: Literal[
        "public_domain",
        "publisher_opt_in",
        "platform_authored",
        "personal_license",
    ]
    page_count: int = Field(default=0, ge=0, le=100_000)
    license_basis: str = Field(min_length=1, max_length=1000)
    acknowledge_write_to_library: bool = False
    acknowledge_full_text_servable: bool = False


class BookHtmlPublishJobOut(BaseModel):
    publish_job_id: str
    status: Literal["published_to_private_library"]
    publication_request_id: str
    serve_gate_review_id: str
    document_id: str
    title: str
    author: str | None
    import_target: Literal["antiek_html"]
    content_class: str
    servability: str
    servable_full_text: bool
    document_inserted: bool
    book_asset_registered: bool
    graph_mutation_performed: bool
    shelf_publication_attempted: bool
    reader_route_created: bool
    full_text_served: bool
    open_route: str
    policy_notes: list[str]


_PUBLISH_CONTENT_CLASS_BY_RIGHTS: dict[str, str] = {
    "public_domain": "public_domain",
    "publisher_opt_in": "opt_in_licensed",
    "platform_authored": "user_owned",
    "personal_license": "user_owned",
}


def _book_purchase_request_id(req: BookPurchaseRequestIn) -> str:
    normalized = "|".join(
        [
            req.title.strip().casefold(),
            (req.author or "").strip().casefold(),
            (req.source_url or "").strip(),
            req.store,
            str(req.max_price_usd_cents),
            req.desired_format,
            req.import_target,
        ]
    )
    return f"bookreq-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _book_html_import_preflight_id(req: BookHtmlImportPreflightIn) -> str:
    normalized = "|".join(
        [
            req.title.strip().casefold(),
            (req.author or "").strip().casefold(),
            (req.source_request_id or "").strip(),
            (req.file_name or "").strip(),
            req.file_format,
            str(req.has_legal_access),
        ]
    )
    return f"bookimp-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _book_html_file_handoff_id(req: BookHtmlFileHandoffIn) -> str:
    normalized = "|".join(
        [
            req.import_preflight_id.strip(),
            req.file_name.strip(),
            req.file_format,
            req.storage_ref.strip(),
            (req.checksum_sha256 or "").strip().casefold(),
        ]
    )
    return f"bookhand-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _book_html_conversion_review_id(req: BookHtmlConversionReviewIn) -> str:
    normalized = "|".join(
        [
            req.handoff_id.strip(),
            req.import_preflight_id.strip(),
            req.converter,
            req.sandbox_profile,
            req.output_format,
        ]
    )
    return f"bookconv-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _book_html_conversion_result_id(req: BookHtmlConversionResultIn) -> str:
    normalized = "|".join(
        [
            req.conversion_review_id.strip(),
            req.handoff_id.strip(),
            req.html_output_ref.strip(),
            (req.html_checksum_sha256 or "").strip().casefold(),
            str(req.page_count_estimate),
        ]
    )
    return f"bookout-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _book_html_serve_gate_review_id(req: BookHtmlServeGateReviewIn) -> str:
    normalized = "|".join(
        [
            req.conversion_result_id.strip(),
            req.title.strip().casefold(),
            (req.author or "").strip().casefold(),
            req.rights_basis,
            req.servability_decision,
        ]
    )
    return f"bookserve-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _book_html_publication_request_id(req: BookHtmlPublicationRequestIn) -> str:
    normalized = "|".join(
        [
            req.serve_gate_review_id.strip(),
            req.conversion_result_id.strip(),
            (req.document_id_hint or "").strip(),
            req.shelf_visibility,
        ]
    )
    return f"bookpub-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _book_html_publish_job_id(req: BookHtmlPublishJobIn) -> str:
    normalized = "|".join(
        [
            req.publication_request_id.strip(),
            req.serve_gate_review_id.strip(),
            req.document_id.strip(),
            req.title.strip().casefold(),
            req.rights_basis,
        ]
    )
    return f"bookjob-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


class SpinResearchRequest(BaseModel):
    page_index: int = Field(ge=0)
    # The reader's selected text. For a gated book it is IGNORED server-
    # side and replaced by the bounded snippet — the seed can never carry
    # gated full text, even if the client sends it (defense in depth).
    passage_text: str | None = None
    # Optional HTML-first bridge: immediately export the spawned research shell
    # and twin notes so the reader/workstation can open it without waiting for
    # any provider-backed research work.
    export_artifact: bool = False


class SpinResearchResponse(BaseModel):
    investigation_id: str
    document_id: str
    page_index: int
    gated: bool
    servability: str
    seed_preview: str
    artifact_path: str | None = None
    twin_notes_path: str | None = None


class ImpressionItem(BaseModel):
    slot_id: str = Field(min_length=1, max_length=128)
    page_index: int = Field(ge=0)
    fill_kind: Literal["ad", "house"]
    revenue_usd_cents: int = Field(ge=0, default=0)
    focused_dwell_ms: int = Field(ge=0, default=0)
    tab_focused: bool = True


class RecordImpressionsRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    impressions: list[ImpressionItem] = Field(default_factory=list)


class RecordImpressionsResponse(BaseModel):
    document_id: str
    recorded: int
    attention_impressions: int
    accrued_to_escrow_cents: int


class FullTextResponse(BaseModel):
    document_id: str
    servable: bool
    servability: str | None
    full_text: str | None
    snippet: str | None
    title: str | None
    author: str | None
    reason: str
    # Rights context (Read SPR-05) — the data the reader renders off the
    # backend response instead of a local flag. ``tier`` is the arXiv
    # RightsTier value ('T1'|'T2'|'T3') or None for a non-arXiv document;
    # ``ad_eligible`` is the ad-rail gate (T1-only for arXiv; == servable for
    # non-arXiv, preserving today's behaviour); ``canonical_url`` is the
    # arxiv.org/abs link or None; ``license`` is the license_uri or None.
    tier: str | None = None
    ad_eligible: bool = False
    canonical_url: str | None = None
    license: str | None = None


# ── SPR-08 M2 — talk-to-book (multi-turn, page-cited) ───────────────


class TalkTurn(BaseModel):
    """One prior conversation turn the client carries forward (the multi-turn
    thread lives in the reader's session state — the floating bookmark — NOT in
    substrate truth). ``question`` is user-sourced; ``answer`` the model's prior
    reply, kept distinct."""

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class AskBookRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # The recent tail of the running conversation (server bounds it again).
    history: list[TalkTurn] = Field(default_factory=list)
    research_tier: Literal["fast", "deep"] = "deep"


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    # The 0-based reader page the cited chunk anchors to, or null when the
    # chunk's section_path did not resolve to a page marker (then
    # ``page_resolved`` is False and the surface shows an honest "page not
    # pinpointed" — never a fabricated page).
    page_index: int | None = None
    page_resolved: bool = False
    snippet: str


class AskBookResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    # False when the book had no extractable text to ground on (scanned-image
    # PDF / fully-withheld) — the honest no-context state, never a hallucination.
    grounded: bool
    context_chunk_count: int


# ── SPR-08 M1 — corpus search (NET-NEW) ─────────────────────────────


class CorpusSearchHit(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str | None
    page_index: int | None = None
    page_resolved: bool = False
    snippet: str
    similarity: float


class CorpusSearchResponse(BaseModel):
    query: str
    hits: list[CorpusSearchHit]
    count: int


# ── SPR-08 M4 — meta-reading deliverable (PROPOSED boundary) ────────


class MetaReadingRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    length_unit: Literal["pages", "minutes"]
    length_amount: int = Field(ge=1)
    research_tier: Literal["fast", "deep"] = "deep"
    # The owned-corpus scope. "hard" is the PROPOSED Research↔Read boundary
    # (owned servable docs, optionally an explicit pick); "soft" is the rollback
    # when operator sign-off is withheld (the whole owned readable corpus).
    # NEITHER reaches the open internet — meta-reading is internet-agnostic.
    corpus_scope: Literal["hard", "soft"] = "hard"
    # An explicit pick of owned document ids (intersected with the owned set
    # under "hard" scope). Omit to scope to the whole owned servable corpus.
    document_ids: list[str] | None = None


class MetaReadingResponse(BaseModel):
    asset_id: str
    report: str
    citations: list[CitationResponse]
    length_unit: Literal["pages", "minutes"]
    length_amount: int
    word_budget: int
    truncated: bool
    corpus_scope: Literal["hard", "soft"]
    corpus_document_ids: list[str]
    # True when the owned corpus had nothing to synthesize from (honest empty,
    # never a fabricated report).
    empty: bool
    context_chunk_count: int


# ── SPR-13 — personal document space (collect / categorize / file) ──


class PersonalAssetResponse(BaseModel):
    """One item in the personal space (a created deliverable or a saved read).
    Substrate-backed — reconstructed from the event log, NOT a new store."""

    asset_id: str
    kind: Literal["meta_reading", "saved_read"]
    title: str
    prompt: str | None
    document_ids: list[str]
    emitted_at: str | None
    # The in-app route that re-opens the item (the meta-doc view / the reader).
    open_route: str


class PersonalSpaceResponse(BaseModel):
    assets: list[PersonalAssetResponse]
    count: int


class AssetCategoryResponse(BaseModel):
    # Stable, unique key the surface renders on — two clusters can share a
    # human label, so the id (not the label) is the safe list key.
    category_id: str
    label: str
    asset_ids: list[str]
    # "theme" when the label emerged from clustering; "recency" when the corpus
    # was below the stability bound and we fell back honestly (never a fake label).
    ordering: Literal["theme", "recency"]


class CategorizedSpaceResponse(BaseModel):
    categories: list[AssetCategoryResponse]
    ordering: Literal["theme", "recency"]
    # The asset-count below which categories don't stabilize → recency fallback.
    stability_bound: int


class ProjectMatchResponse(BaseModel):
    investigation_id: str
    question: str
    score: float


class FileSuggestionResponse(BaseModel):
    document_id: str
    # The candidate projects above the suggestion threshold (top match first;
    # >1 when the doc matches several — the surface names them, never auto-files).
    matches: list[ProjectMatchResponse]


class SavedMetaReadingResponse(BaseModel):
    """A previously-saved meta-reading asset, re-opened by id from the event log
    (Read SPR-13 M1 — the item opens back into the meta-doc view). The same
    shape MetaReadingResponse carries, minus the generation-only word_budget."""

    asset_id: str
    prompt: str
    report: str
    citations: list[CitationResponse]
    length_unit: Literal["pages", "minutes"]
    length_amount: int
    truncated: bool
    corpus_scope: Literal["hard", "soft"]
    corpus_document_ids: list[str]


# ── Routes ──────────────────────────────────────────────────────────


def register_book_routes(app: FastAPI) -> None:
    """Mount the servable-corpus query routes. Mirrors
    ``register_advertiser_routes`` — one call from ``create_app``."""

    @app.get("/books", response_model=BookListResponse, tags=["books"])
    async def list_books(
        status: Literal["servable", "gated", "all"] = "servable",
    ) -> BookListResponse:
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            if status == "servable":
                assets = list_book_assets(con, servable_only=True)
            else:
                # "gated" and "all" both list non-taken-down books; the
                # servability flag on each lets the caller filter. We never
                # widen to taken-down books on a public listing.
                assets = list_book_assets(con, servable_only=False)
                if status == "gated":
                    assets = [a for a in assets if not a.servable_full_text]
        finally:
            con.close()
        summaries = [BookSummary.from_asset(a) for a in assets]
        return BookListResponse(books=summaries, count=len(summaries))

    # Registered BEFORE /books/{document_id} so "curate" is not matched as
    # a document id.
    @app.get("/books/curate", response_model=CurateResponse, tags=["books"])
    async def curate(prompt: str, limit: int = 20) -> CurateResponse:
        from runtime.db_lock import connect_read
        from substrate.books.curate import curate_reading_list
        from substrate.graph.search import SentenceTransformerEmbedding

        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:  # sentence-transformers not installed
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            curated = curate_reading_list(con, prompt, model=model, limit=limit)
        finally:
            con.close()
        return CurateResponse(
            prompt=prompt,
            books=[
                CuratedBookResponse(
                    document_id=c.document_id, title=c.title, author=c.author, score=c.score
                )
                for c in curated
            ],
        )

    @app.post(
        "/books/marketplace/purchase-request",
        response_model=BookPurchaseRequestOut,
        status_code=202,
        tags=["books"],
    )
    async def request_book_purchase(req: BookPurchaseRequestIn) -> BookPurchaseRequestOut:
        """Prepare a no-spend book acquisition/import request.

        This endpoint is deliberately a PRE-CHECKOUT contract: it records the
        operator's desired title, budget ceiling, and target HTML import posture
        without fetching the source URL, calling a store, reserving budget,
        charging a card, or ingesting the work. A later, explicit operator
        purchase/import action can consume this envelope once rights and file
        access are clear.
        """
        if not req.acknowledge_manual_purchase_only:
            raise HTTPException(
                status_code=400,
                detail="manual_purchase_ack_required",
            )

        return BookPurchaseRequestOut(
            request_id=_book_purchase_request_id(req),
            status="needs_operator_purchase",
            title=req.title.strip(),
            author=req.author.strip() if req.author else None,
            store=req.store,
            source_url=req.source_url.strip() if req.source_url else None,
            max_price_usd_cents=req.max_price_usd_cents,
            desired_format=req.desired_format,
            import_target=req.import_target,
            purchase_allowed=False,
            external_call_performed=False,
            spend_reserved_usd_cents=0,
            charge_attempted=False,
            ingest_attempted=False,
            html_hosting_required=True,
            required_operator_steps=[
                "Buy or obtain the book outside Antiek using the approved price ceiling.",
                "Provide the legally obtained file or receipt-backed access in a later import step.",
                "Convert and host the readable copy as an Antiek HTML asset after the import gate approves it.",
            ],
            policy_notes=[
                "No checkout, store lookup, provider call, URL fetch, budget reservation, charge, or ingest was performed.",
                "The future reader surface must continue to render HTML-first and keep gated/source material behind the serve gate.",
            ],
        )

    @app.post(
        "/books/import/html-preflight",
        response_model=BookHtmlImportPreflightOut,
        status_code=202,
        tags=["books"],
    )
    async def book_html_import_preflight(
        req: BookHtmlImportPreflightIn,
    ) -> BookHtmlImportPreflightOut:
        """Prepare the HTML-first import gate without touching the file.

        This records that the operator claims legal access and wants Antiek
        HTML hosting, but it does not accept an upload, read a local path, fetch
        a URL, convert content, ingest into the graph, or serve the book.
        """
        if not req.acknowledge_no_upload_or_ingest:
            raise HTTPException(
                status_code=400,
                detail="html_import_preflight_ack_required",
            )
        if not req.has_legal_access:
            raise HTTPException(
                status_code=400,
                detail="legal_access_required",
            )

        fmt = req.file_format
        return BookHtmlImportPreflightOut(
            import_preflight_id=_book_html_import_preflight_id(req),
            status="ready_for_operator_file",
            title=req.title.strip(),
            author=req.author.strip() if req.author else None,
            source_request_id=req.source_request_id.strip() if req.source_request_id else None,
            file_name=req.file_name.strip() if req.file_name else None,
            file_format=fmt,
            import_target="antiek_html",
            external_call_performed=False,
            file_uploaded=False,
            file_read_attempted=False,
            ingest_attempted=False,
            graph_mutation_performed=False,
            html_conversion_required=fmt != "html",
            html_hosting_required=True,
            required_operator_steps=[
                "Attach or upload the legally obtained file in a later explicit import step.",
                "Run conversion into Antiek HTML after the file gate validates format and rights.",
                "Host the readable copy behind the existing book serve gate before it appears on the shelf.",
            ],
            policy_notes=[
                "No upload, file read, URL fetch, conversion, graph write, or full-text serve happened in this preflight.",
                "The readable asset remains HTML-first and must pass the serve gate before Library/Reader access.",
            ],
        )

    @app.post(
        "/books/import/file-handoff",
        response_model=BookHtmlFileHandoffOut,
        status_code=202,
        tags=["books"],
    )
    async def book_html_file_handoff(
        req: BookHtmlFileHandoffIn,
    ) -> BookHtmlFileHandoffOut:
        """Record operator file handoff metadata without accepting the file.

        This is the seam between "I legally obtained the file" and a later
        sandboxed converter. The endpoint stores no bytes, reads no path, fetches
        no storage reference, converts nothing, and does not mutate the graph.
        """
        preflight_id = req.import_preflight_id.strip()
        if not preflight_id.startswith("bookimp-"):
            raise HTTPException(status_code=400, detail="invalid_import_preflight_id")
        if not req.acknowledge_manual_storage_only:
            raise HTTPException(status_code=400, detail="manual_storage_ack_required")
        if not req.acknowledge_no_file_read_or_conversion:
            raise HTTPException(
                status_code=400,
                detail="file_handoff_no_read_ack_required",
            )

        checksum = req.checksum_sha256.strip().casefold() if req.checksum_sha256 else None
        if checksum is not None and any(ch not in "0123456789abcdef" for ch in checksum):
            raise HTTPException(status_code=400, detail="invalid_sha256_checksum")

        fmt = req.file_format
        return BookHtmlFileHandoffOut(
            handoff_id=_book_html_file_handoff_id(req),
            status="ready_for_conversion_review",
            import_preflight_id=preflight_id,
            file_name=req.file_name.strip(),
            file_format=fmt,
            storage_ref=req.storage_ref.strip(),
            checksum_sha256=checksum,
            import_target="antiek_html",
            storage_ref_recorded=True,
            upload_accepted=False,
            external_call_performed=False,
            file_read_attempted=False,
            conversion_attempted=False,
            ingest_attempted=False,
            graph_mutation_performed=False,
            html_conversion_required=fmt != "html",
            html_hosting_required=True,
            required_operator_steps=[
                "Review the recorded storage reference and checksum before any converter receives access.",
                "Run a later sandboxed conversion job that reads the file only after explicit operator approval.",
                "Publish the converted HTML only after the serve gate validates rights and servability.",
            ],
            policy_notes=[
                "No upload bytes were accepted; only operator-supplied storage metadata was recorded.",
                "No file path, storage reference, or URL was opened, fetched, converted, ingested, or served.",
            ],
        )

    @app.post(
        "/books/import/conversion-review",
        response_model=BookHtmlConversionReviewOut,
        status_code=202,
        tags=["books"],
    )
    async def book_html_conversion_review(
        req: BookHtmlConversionReviewIn,
    ) -> BookHtmlConversionReviewOut:
        """Approve the next converter shape without running the converter.

        This is a no-side-effect review receipt. The converter itself remains a
        later, explicit job that may read the handed-off file only inside the
        stated sandbox after operator approval.
        """
        handoff_id = req.handoff_id.strip()
        preflight_id = req.import_preflight_id.strip()
        if not handoff_id.startswith("bookhand-"):
            raise HTTPException(status_code=400, detail="invalid_handoff_id")
        if not preflight_id.startswith("bookimp-"):
            raise HTTPException(status_code=400, detail="invalid_import_preflight_id")
        if not req.acknowledge_sandbox_required:
            raise HTTPException(status_code=400, detail="conversion_sandbox_ack_required")
        if not req.acknowledge_no_conversion_run:
            raise HTTPException(status_code=400, detail="conversion_no_run_ack_required")

        return BookHtmlConversionReviewOut(
            conversion_review_id=_book_html_conversion_review_id(req),
            status="ready_for_explicit_conversion_job",
            handoff_id=handoff_id,
            import_preflight_id=preflight_id,
            converter=req.converter,
            sandbox_profile=req.sandbox_profile,
            output_format=req.output_format,
            storage_ref_read=False,
            file_read_attempted=False,
            conversion_attempted=False,
            output_written=False,
            ingest_attempted=False,
            graph_mutation_performed=False,
            html_hosting_required=True,
            serve_gate_required=True,
            required_operator_steps=[
                "Run the converter only as a separate explicit job with the approved sandbox profile.",
                "Write Antiek HTML output to a review location before any graph ingest or shelf publication.",
                "Pass the converted HTML through the book serve gate before Reader or Library availability.",
            ],
            policy_notes=[
                "No storage reference or file bytes were read during conversion review.",
                "No converter ran, no HTML output was written, and no graph or shelf state changed.",
            ],
        )

    @app.post(
        "/books/import/conversion-result",
        response_model=BookHtmlConversionResultOut,
        status_code=202,
        tags=["books"],
    )
    async def book_html_conversion_result(
        req: BookHtmlConversionResultIn,
    ) -> BookHtmlConversionResultOut:
        """Record converted HTML output metadata without reading or publishing it."""
        conversion_review_id = req.conversion_review_id.strip()
        handoff_id = req.handoff_id.strip()
        if not conversion_review_id.startswith("bookconv-"):
            raise HTTPException(status_code=400, detail="invalid_conversion_review_id")
        if not handoff_id.startswith("bookhand-"):
            raise HTTPException(status_code=400, detail="invalid_handoff_id")
        if not req.acknowledge_output_metadata_only:
            raise HTTPException(status_code=400, detail="output_metadata_ack_required")
        if not req.acknowledge_no_publish_or_serve:
            raise HTTPException(status_code=400, detail="no_publish_or_serve_ack_required")

        checksum = (
            req.html_checksum_sha256.strip().casefold() if req.html_checksum_sha256 else None
        )
        if checksum is not None and any(ch not in "0123456789abcdef" for ch in checksum):
            raise HTTPException(status_code=400, detail="invalid_sha256_checksum")

        return BookHtmlConversionResultOut(
            conversion_result_id=_book_html_conversion_result_id(req),
            status="ready_for_serve_gate_review",
            conversion_review_id=conversion_review_id,
            handoff_id=handoff_id,
            html_output_ref=req.html_output_ref.strip(),
            html_checksum_sha256=checksum,
            page_count_estimate=req.page_count_estimate,
            import_target="antiek_html",
            output_metadata_recorded=True,
            output_ref_fetched=False,
            html_output_read=False,
            ingest_attempted=False,
            graph_mutation_performed=False,
            shelf_publication_attempted=False,
            full_text_served=False,
            serve_gate_required=True,
            required_operator_steps=[
                "Review the converted HTML output in a later explicit serve-gate step.",
                "Validate rights, structure, and checksum before any graph ingest or shelf publication.",
                "Publish to Library/Reader only after the serve gate approves full-text servability.",
            ],
            policy_notes=[
                "Only converted-output metadata was recorded; the HTML output reference was not opened or fetched.",
                "No ingest, graph mutation, shelf publication, or full-text serving happened.",
            ],
        )

    @app.post(
        "/books/import/serve-gate-review",
        response_model=BookHtmlServeGateReviewOut,
        status_code=202,
        tags=["books"],
    )
    async def book_html_serve_gate_review(
        req: BookHtmlServeGateReviewIn,
    ) -> BookHtmlServeGateReviewOut:
        """Record rights/servability review without publishing to the shelf."""
        conversion_result_id = req.conversion_result_id.strip()
        if not conversion_result_id.startswith("bookout-"):
            raise HTTPException(status_code=400, detail="invalid_conversion_result_id")
        if not req.acknowledge_rights_reviewed:
            raise HTTPException(status_code=400, detail="rights_review_ack_required")
        if not req.acknowledge_no_publication:
            raise HTTPException(status_code=400, detail="no_publication_ack_required")

        publication_allowed = req.servability_decision == "servable_full_text"
        return BookHtmlServeGateReviewOut(
            serve_gate_review_id=_book_html_serve_gate_review_id(req),
            status="ready_for_publication_request" if publication_allowed else "blocked",
            conversion_result_id=conversion_result_id,
            title=req.title.strip(),
            author=req.author.strip() if req.author else None,
            rights_basis=req.rights_basis,
            servability_decision=req.servability_decision,
            import_target="antiek_html",
            rights_review_recorded=True,
            html_output_read=False,
            ingest_attempted=False,
            graph_mutation_performed=False,
            shelf_publication_attempted=False,
            full_text_served=False,
            publication_allowed_next=publication_allowed,
            required_operator_steps=[
                "Submit a separate publication request only if the servability decision allows full-text publication.",
                "Persist the converted HTML through the book ingest path only after publication approval.",
                "Expose the book in Library/Reader only after substrate servability state is written.",
            ],
            policy_notes=[
                "Rights and servability review metadata was recorded; converted HTML was not read.",
                "No ingest, graph mutation, shelf publication, or full-text serving happened in this review.",
            ],
        )

    @app.post(
        "/books/import/publication-request",
        response_model=BookHtmlPublicationRequestOut,
        status_code=202,
        tags=["books"],
    )
    async def book_html_publication_request(
        req: BookHtmlPublicationRequestIn,
    ) -> BookHtmlPublicationRequestOut:
        """Record publication intent without writing substrate/shelf state."""
        serve_gate_review_id = req.serve_gate_review_id.strip()
        conversion_result_id = req.conversion_result_id.strip()
        if not serve_gate_review_id.startswith("bookserve-"):
            raise HTTPException(status_code=400, detail="invalid_serve_gate_review_id")
        if not conversion_result_id.startswith("bookout-"):
            raise HTTPException(status_code=400, detail="invalid_conversion_result_id")
        if not req.acknowledge_publication_intent:
            raise HTTPException(status_code=400, detail="publication_intent_ack_required")
        if not req.acknowledge_no_ingest_or_serve:
            raise HTTPException(status_code=400, detail="no_ingest_or_serve_ack_required")

        return BookHtmlPublicationRequestOut(
            publication_request_id=_book_html_publication_request_id(req),
            status="ready_for_explicit_publish_job",
            serve_gate_review_id=serve_gate_review_id,
            conversion_result_id=conversion_result_id,
            document_id_hint=req.document_id_hint.strip() if req.document_id_hint else None,
            shelf_visibility=req.shelf_visibility,
            import_target="antiek_html",
            publication_intent_recorded=True,
            ingest_attempted=False,
            graph_mutation_performed=False,
            shelf_publication_attempted=False,
            full_text_served=False,
            reader_route_created=False,
            required_operator_steps=[
                "Run a separate publish job that writes the Antiek HTML asset into substrate.",
                "Verify the resulting document id through the existing book serve gate.",
                "Expose the Reader route only after substrate servability state confirms full-text access.",
            ],
            policy_notes=[
                "Publication intent was recorded only; no graph, shelf, or reader state was written.",
                "No full text was served and no Reader route was created by this request.",
            ],
        )

    @app.post(
        "/books/import/publish-job",
        response_model=BookHtmlPublishJobOut,
        status_code=201,
        tags=["books"],
    )
    async def book_html_publish_job(req: BookHtmlPublishJobIn) -> BookHtmlPublishJobOut:
        """Explicitly publish inline Antiek HTML through the existing book gate.

        This is the first write in the staged import chain. It still does not
        read any external file or output reference: the caller must provide the
        HTML body inline, and the resulting Reader availability is governed by
        the existing documents/content_class + book_assets serve gate.
        """
        publication_request_id = req.publication_request_id.strip()
        serve_gate_review_id = req.serve_gate_review_id.strip()
        document_id = req.document_id.strip()
        if not publication_request_id.startswith("bookpub-"):
            raise HTTPException(status_code=400, detail="invalid_publication_request_id")
        if not serve_gate_review_id.startswith("bookserve-"):
            raise HTTPException(status_code=400, detail="invalid_serve_gate_review_id")
        if not req.acknowledge_write_to_library:
            raise HTTPException(status_code=400, detail="write_to_library_ack_required")
        if not req.acknowledge_full_text_servable:
            raise HTTPException(status_code=400, detail="full_text_servable_ack_required")

        content_class = _PUBLISH_CONTENT_CLASS_BY_RIGHTS[req.rights_basis]
        db = _resolve_db_path()
        from runtime.db_lock import connect_write
        from substrate.books.ingest import register_book
        from substrate.graph.ops import insert_document

        con = connect_write(db, purpose="books:html_publish_job")
        try:
            exists = con.execute(
                "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1",
                [document_id],
            ).fetchone()
            if exists:
                raise HTTPException(status_code=409, detail="document_id_exists")
            insert_document(
                con,
                document_id=document_id,
                source_tier=2,
                document_type="book",
                source_uri=f"antiek://book-import/{publication_request_id}",
                title=req.title.strip(),
                author=req.author.strip() if req.author else None,
                raw_text=req.html_body,
                metadata={
                    "import_target": "antiek_html",
                    "publication_request_id": publication_request_id,
                    "serve_gate_review_id": serve_gate_review_id,
                    "rights_basis": req.rights_basis,
                },
                content_class=content_class,
            )
            asset = register_book(
                con,
                document_id=document_id,
                content_class=content_class,
                page_count=req.page_count,
                pagination_scheme="html_section",
                provenance=f"Antiek HTML import publication request {publication_request_id}",
                license_basis=req.license_basis.strip(),
            )
        finally:
            con.close()

        return BookHtmlPublishJobOut(
            publish_job_id=_book_html_publish_job_id(req),
            status="published_to_private_library",
            publication_request_id=publication_request_id,
            serve_gate_review_id=serve_gate_review_id,
            document_id=document_id,
            title=req.title.strip(),
            author=req.author.strip() if req.author else None,
            import_target="antiek_html",
            content_class=content_class,
            servability=asset.servability.value,
            servable_full_text=asset.servable_full_text,
            document_inserted=True,
            book_asset_registered=True,
            graph_mutation_performed=True,
            shelf_publication_attempted=True,
            reader_route_created=True,
            full_text_served=False,
            open_route=f"/read/{document_id}",
            policy_notes=[
                "Inline Antiek HTML was written through the existing document/book substrate path.",
                "No external file, storage reference, URL, provider, checkout, or spend path was touched.",
                "This endpoint did not serve full text; subsequent reads still pass through the serve gate.",
            ],
        )

    @app.get("/books/{document_id}", response_model=BookDetail, tags=["books"])
    async def get_book(document_id: str) -> BookDetail:
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            asset = get_book_asset(con, document_id)
        finally:
            con.close()
        if asset is None:
            raise HTTPException(status_code=404, detail="book_not_found")
        return BookDetail.from_asset(asset)

    @app.get(
        "/books/{document_id}/full-text",
        response_model=FullTextResponse,
        tags=["books"],
    )
    async def get_book_full_text(document_id: str) -> FullTextResponse:
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            result = serve_full_text_guarded(con, document_id)
        finally:
            con.close()
        if not result.found:
            raise HTTPException(status_code=404, detail="book_not_found")
        # SPR-09 M4 — record the SERVE leg into the arXiv fetch→serve→accrue
        # compliance trace. Hooked at the ENDPOINT (not inside serve_guard.py,
        # which a parallel builder owns), AFTER the guard returns. Only an arXiv
        # doc carries a canonical_url (https://arxiv.org/abs/<id>), from which we
        # derive the arxiv_id; non-arXiv books emit no audit row. §9.0: we record
        # the served/gated REASON + tier + servable flag only — NEVER the body.
        # Defensively isolated: a failure in the audit layer must never break the
        # serve (wrap + log), and the audit write takes its own write lock.
        _record_arxiv_serve_audit(db, document_id, result)
        return FullTextResponse(
            document_id=result.document_id,
            servable=result.servable,
            servability=result.servability.value if result.servability else None,
            full_text=result.full_text,
            snippet=result.snippet,
            title=result.title,
            author=result.author,
            reason=result.reason,
            tier=result.tier,
            ad_eligible=result.ad_eligible,
            canonical_url=result.canonical_url,
            license=result.license,
        )

    @app.post(
        "/books/{document_id}/ad-impressions",
        response_model=RecordImpressionsResponse,
        status_code=202,
        tags=["books"],
    )
    async def record_ad_impressions(
        document_id: str, req: RecordImpressionsRequest
    ) -> RecordImpressionsResponse:
        """Record reader ad impressions + attention for a session and
        accrue to the book's rights-holder escrow (Read SPR-05 → SPR-09).

        The browser flushes a session's slot impressions here. The
        attention rule (focused dwell ≥ threshold; idle tab excluded) is
        applied SERVER-SIDE — the client's claimed attention is not
        trusted. Accrual reuses ``accrue_reading_session`` (dedup by
        impression_id, zero-buyer-safe, accrual≠disbursement)."""
        from runtime.db_lock import connect_write
        from substrate.ad_inventory.reader_impressions import record_raw_impression
        from substrate.marketplace_metrics.book_escrow import accrue_reading_session

        impressions = [
            record_raw_impression(
                session_id=req.session_id,
                document_id=document_id,
                slot_id=item.slot_id,
                page_index=item.page_index,
                fill_kind=item.fill_kind,
                revenue_usd_cents=item.revenue_usd_cents,
                focused_dwell_ms=item.focused_dwell_ms,
                tab_focused=item.tab_focused,
            )
            for item in req.impressions
        ]
        db = _resolve_db_path()
        con = connect_write(db, purpose="read/ad_impressions")
        try:
            result = accrue_reading_session(
                con,
                document_id=document_id,
                impressions=impressions,
                session_id=req.session_id,
            )
        finally:
            con.close()
        return RecordImpressionsResponse(
            document_id=document_id,
            recorded=len(impressions),
            attention_impressions=result.attention_impressions,
            accrued_to_escrow_cents=result.accrued_to_escrow_cents,
        )

    @app.post(
        "/books/{document_id}/spin-research",
        response_model=SpinResearchResponse,
        status_code=202,
        tags=["books"],
    )
    async def spin_research(document_id: str, req: SpinResearchRequest) -> SpinResearchResponse:
        """Spin a deep research from a book passage (Read SPR-08).

        Builds the GATE-SAFE seed server-side (a gated book contributes
        only its snippet + metadata, never full text — even if the client
        sent the passage body), requests a child investigation seeded with
        it, and records the two-way passage↔research provenance link. The
        seed is built and consumed here so gated full text never crosses
        into a research via the browser.
        """
        from runtime.db_lock import connect_read
        from substrate.books.passage_research import (
            build_research_seed,
            link_passage_to_research,
        )
        from substrate.event_log import emit_typed
        from substrate.research_artifact import export_research_artifact
        from substrate.schemas import InvestigationStartRequestedPayload

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            seed = build_research_seed(
                con,
                document_id=document_id,
                page_index=req.page_index,
                passage_text=req.passage_text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            con.close()

        import uuid as _uuid

        investigation_id = f"inv-{_uuid.uuid4().hex[:12]}"
        spawn_context = f"read: passage {document_id} p{req.page_index}"
        event_id = emit_typed(
            investigation_id,
            InvestigationStartRequestedPayload(
                question=seed.seed_text,
                context=f"Spun from a book passage. Servability: {seed.servability}.",
                spawn_context=spawn_context,
            ),
            role="read/spin_research",
            policy_id="read/books/spin_research",
        )
        if event_id is None:
            raise HTTPException(
                status_code=503,
                detail="Event log is disabled (ANTIEK_EVENTS_DISABLED).",
            )
        link_passage_to_research(
            document_id=document_id,
            page_index=req.page_index,
            investigation_id=investigation_id,
        )
        artifact_path: str | None = None
        twin_notes_path: str | None = None
        if req.export_artifact:
            exported = export_research_artifact(
                investigation_id,
                db_path=db,
                emit_event=False,
                generating_role="read/spin_research",
            )
            artifact_path = str(exported.path)
            twin_notes_path = str(exported.twin_notes_path)
        return SpinResearchResponse(
            investigation_id=investigation_id,
            document_id=document_id,
            page_index=req.page_index,
            gated=seed.gated,
            servability=seed.servability,
            seed_preview=seed.seed_text[:240] + ("…" if len(seed.seed_text) > 240 else ""),
            artifact_path=artifact_path,
            twin_notes_path=twin_notes_path,
        )

    # ── SPR-08 M2 — talk-to-book (multi-turn, page-cited, gate-safe) ──
    @app.post(
        "/books/{document_id}/ask",
        response_model=AskBookResponse,
        tags=["books"],
    )
    async def ask_book(
        document_id: str, req: AskBookRequest, request: Request,
    ) -> AskBookResponse:
        """Answer one talk-to-book turn, page-cited, over THIS book only.

        Retrieval is scoped to ``document_id`` through the §9.0 gate. For the
        AUTHENTICATED OWNER (resolved server-side from the auth middleware via
        ``_owner_read_policy_tag``) the gate runs on the PRIVILEGED
        ``operator_only`` tag, so the owner can talk to HIS OWN gated/personal
        book in full. For any non-owner / unauthenticated caller (which, when
        enforcement is on, is 401'd by the middleware before reaching here) the
        gate stays non-privileged, so a withheld book's body never reaches the
        model context or a citation. A book with no extractable text (or one the
        gate fully withholds) returns an honest ungrounded answer WITHOUT
        dispatching a model (no hallucination). The model is dispatched through
        the ONE Hermes-routed path (§16); 503 when no provider is keyed.
        """
        from runtime.db_lock import connect_read
        from substrate.books.book_qa import Turn, answer_book_question
        from substrate.dispatch.base import ProviderError
        from substrate.graph.search import SentenceTransformerEmbedding

        # Confirm the book exists (honest 404 rather than an empty answer).
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            asset = get_book_asset(con, document_id)
        finally:
            con.close()
        if asset is None:
            raise HTTPException(status_code=404, detail="book_not_found")

        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:  # sentence-transformers not installed
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        con = connect_read(db)
        try:
            try:
                result = answer_book_question(
                    con,
                    document_id=document_id,
                    question=req.question,
                    model=model,
                    investigation_id=f"read-{document_id}",
                    history=[Turn(question=t.question, answer=t.answer) for t in req.history],
                    research_tier=req.research_tier,
                    # §9.0: privileged ONLY for the authenticated owner (resolved
                    # server-side); non-owner / unauth callers stay gated.
                    policy_tag=_owner_read_policy_tag(request),
                )
            except ProviderError as exc:
                # No keyed provider — honest 503, never a fabricated answer.
                raise HTTPException(status_code=503, detail=f"dispatch_unavailable: {exc}") from exc
        finally:
            con.close()

        return AskBookResponse(
            answer=result.answer,
            citations=[
                CitationResponse(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    page_index=c.page_index,
                    page_resolved=c.page_resolved,
                    snippet=c.snippet,
                )
                for c in result.citations
            ],
            grounded=result.grounded,
            context_chunk_count=result.context_chunk_count,
        )

    # ── SPR-08 M1 — corpus search over the owned graph (NET-NEW) ──
    @app.get(
        "/corpus/search",
        response_model=CorpusSearchResponse,
        tags=["books"],
    )
    async def corpus_search(
        request: Request,
        q: str,
        limit: int = 20,
        document_id: str | None = None,
    ) -> CorpusSearchResponse:
        """Search the owned corpus by a natural-language query. Wraps
        ``substrate.graph.search.search`` through the §9.0 gate. For the
        AUTHENTICATED OWNER (resolved server-side from the auth middleware via
        ``_owner_read_policy_tag``) the gate runs on the PRIVILEGED
        ``operator_only`` tag, so the owner can search across HIS OWN
        gated/personal corpus. For any non-owner / unauthenticated caller (401'd
        by the middleware before reaching here when enforcement is on) the gate
        stays non-privileged and excludes restricted/personal content.
        ``document_id`` optionally scopes to one document. The Library's typed
        query + file-drop bias both POST text here (file = a query SIGNAL, never
        ingested)."""
        from runtime.db_lock import connect_read
        from substrate.books.page_anchor import page_index_from_section_path
        from substrate.graph.search import SentenceTransformerEmbedding, search

        if not q.strip():
            return CorpusSearchResponse(query=q, hits=[], count=0)
        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            res = search(
                con, q, model=model, top_k=max(1, limit), document_id=document_id,
                # §9.0: privileged ONLY for the authenticated owner (resolved
                # server-side); non-owner / unauth callers stay gated.
                policy_tag=_owner_read_policy_tag(request),
            )
        finally:
            con.close()

        hits: list[CorpusSearchHit] = []
        for r in res["results"]:
            page_index = page_index_from_section_path(r.get("section_path"))
            text = r.get("chunk_text", "") or ""
            hits.append(
                CorpusSearchHit(
                    chunk_id=r.get("chunk_id", ""),
                    document_id=r.get("document_id", ""),
                    document_title=r.get("document_title"),
                    page_index=page_index,
                    page_resolved=page_index is not None,
                    snippet=text[:240] + ("…" if len(text) > 240 else ""),
                    similarity=r.get("similarity", 0.0),
                )
            )
        return CorpusSearchResponse(query=q, hits=hits, count=len(hits))

    # ── SPR-08 M4 — meta-reading deliverable (PROPOSED, owned-corpus-only) ──
    @app.post(
        "/corpus/meta-reading",
        response_model=MetaReadingResponse,
        status_code=201,
        tags=["books"],
    )
    async def meta_reading(req: MetaReadingRequest) -> MetaReadingResponse:
        """Generate + SAVE a one-shot, READ-ONLY, page-cited synthesis over the
        OWNED corpus (Read SPR-08 M4). INTERNET-AGNOSTIC: retrieval is ONLY
        ``search`` over owned document ids — no acquisition / open-web call. The
        HARD length-box is built up front (a degenerate size → 422 with a stated
        bound). The deliverable is persisted as a re-openable Read asset through
        the single-writer typed-event funnel (NOT a new silo). PROPOSED boundary
        (sign-off pending) — reversible to a soft corpus scope.
        """
        import uuid as _uuid

        from runtime.db_lock import connect_read
        from substrate.books.meta_reading import MetaReadingError, generate_meta_reading
        from substrate.dispatch.base import ProviderError
        from substrate.event_log import emit_typed
        from substrate.graph.search import SentenceTransformerEmbedding
        from substrate.schemas.events import (
            MetaReadingCitation,
            ReadMetaReadingGeneratedPayload,
        )

        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        asset_id = f"mr-{_uuid.uuid4().hex[:12]}"
        investigation_id = f"read-meta-{asset_id}"
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            try:
                deliverable = generate_meta_reading(
                    con,
                    prompt=req.prompt,
                    unit=req.length_unit,
                    amount=req.length_amount,
                    model=model,
                    investigation_id=investigation_id,
                    scope=req.corpus_scope,
                    document_ids=req.document_ids,
                    research_tier=req.research_tier,
                )
            except MetaReadingError as exc:
                # Degenerate length (0 / negative / above the cap) — stated bound.
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except ProviderError as exc:
                raise HTTPException(status_code=503, detail=f"dispatch_unavailable: {exc}") from exc
        finally:
            con.close()

        citations = [
            CitationResponse(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                page_index=c.page_index,
                page_resolved=c.page_resolved,
                snippet=c.snippet,
            )
            for c in deliverable.citations
        ]

        # Persist the deliverable as substrate truth (re-open / narrate /
        # promote). NOT a side-store — it rides the single-writer funnel. An
        # empty deliverable is NOT saved (nothing to re-open); honest empty.
        if not deliverable.empty:
            event_id = emit_typed(
                investigation_id,
                ReadMetaReadingGeneratedPayload(
                    asset_id=asset_id,
                    prompt=req.prompt,
                    report=deliverable.report,
                    length_unit=deliverable.length_box.unit,
                    length_amount=deliverable.length_box.amount,
                    truncated=deliverable.truncated,
                    corpus_scope=deliverable.corpus_scope,
                    corpus_document_ids=deliverable.corpus_document_ids,
                    citations=[
                        MetaReadingCitation(
                            chunk_id=c.chunk_id,
                            document_id=c.document_id,
                            page_index=c.page_index,
                            page_resolved=c.page_resolved,
                        )
                        for c in deliverable.citations
                    ],
                ),
                role="read/meta_reading",
                policy_id="read/meta_reading",
            )
            if event_id is None:
                raise HTTPException(
                    status_code=503,
                    detail="Event log is disabled (ANTIEK_EVENTS_DISABLED).",
                )

        return MetaReadingResponse(
            asset_id=asset_id,
            report=deliverable.report,
            citations=citations,
            length_unit=deliverable.length_box.unit,
            length_amount=deliverable.length_box.amount,
            word_budget=deliverable.length_box.word_budget,
            truncated=deliverable.truncated,
            corpus_scope=deliverable.corpus_scope,
            corpus_document_ids=deliverable.corpus_document_ids,
            empty=deliverable.empty,
            context_chunk_count=deliverable.context_chunk_count,
        )

    # ── SPR-13 — personal document space ────────────────────────────
    #
    # The reader's "personal bed of information that labels itself": their
    # CREATED deliverables (SPR-08 meta-readings) + saved reads (SPR-07
    # source.read history), reconstructed from the event log — NO new store.
    # Distinct from /books (the raw library of source books). These selectors
    # live in substrate/books/personal_space.py and reuse the SAME embedding
    # model SPR-04 curate + §7 search use (no new embedder).

    def _book_title_resolver(document_id: str) -> str | None:
        """Map a read document_id → its book title so a saved read shows the
        book's name, not its id. Best-effort: a non-book / missing doc resolves
        to None and the caller falls back to the id (honest, never fabricated)."""
        from runtime.db_lock import connect_read

        try:
            con = connect_read(_resolve_db_path())
            try:
                asset = get_book_asset(con, document_id)
            finally:
                con.close()
            return asset.title if asset else None
        except Exception:
            return None

    @app.get("/meta-readings", response_model=PersonalSpaceResponse, tags=["books"])
    async def list_personal_space() -> PersonalSpaceResponse:
        """List the personal-space assets — created deliverables + saved reads,
        newest first (Read SPR-13 M1). Substrate-backed (event-log scan), NOT a
        new document store. Each asset's ``open_route`` re-opens it into the
        SPR-08 meta-doc view / the SPR-07 reader."""
        from substrate.books.personal_space import list_personal_assets

        assets = list_personal_assets(book_title_resolver=_book_title_resolver)
        return PersonalSpaceResponse(
            assets=[PersonalAssetResponse(**a.to_dict()) for a in assets],
            count=len(assets),
        )

    @app.get(
        "/meta-readings/categories",
        response_model=CategorizedSpaceResponse,
        tags=["books"],
    )
    async def personal_space_categories() -> CategorizedSpaceResponse:
        """Cluster the personal-space assets into SYSTEM-named categories (Read
        SPR-13 M2). The system names the categories from each cluster's salient
        terms; the user never hand-organizes folders. Deterministic on a fixed
        corpus; honest recency fallback below the stability bound (rigor #1).
        Reuses the SAME embedding model — NO new embedder; an unavailable model
        degrades to the recency fallback rather than failing the request."""
        from substrate.books.personal_space import (
            categorize_assets,
            list_personal_assets,
        )

        assets = list_personal_assets(book_title_resolver=_book_title_resolver)
        try:
            from substrate.graph.search import SentenceTransformerEmbedding

            model: object | None = SentenceTransformerEmbedding()
        except RuntimeError:
            model = None

        if model is None:
            # No embedder → the honest recency fallback (one bucket), never a
            # fabricated theme label. categorize_assets also self-falls-back
            # below the bound, but with no model we short-circuit here.
            from substrate.books.personal_space import (
                MIN_ASSETS_FOR_CLUSTERING,
                AssetCategory,
                CategorizedSpace,
            )

            space = CategorizedSpace(
                categories=[
                    AssetCategory(
                        category_id="recency",
                        label="Recently read & created",
                        asset_ids=[a.asset_id for a in assets],
                        ordering="recency",
                    )
                ]
                if assets
                else [],
                ordering="recency",
                stability_bound=MIN_ASSETS_FOR_CLUSTERING,
            )
        else:
            space = categorize_assets(assets, model=model)  # type: ignore[arg-type]

        return CategorizedSpaceResponse(
            categories=[
                AssetCategoryResponse(
                    category_id=c.category_id,
                    label=c.label,
                    asset_ids=c.asset_ids,
                    ordering=cast(Literal["theme", "recency"], c.ordering),
                )
                for c in space.categories
            ],
            ordering=cast(Literal["theme", "recency"], space.ordering),
            stability_bound=space.stability_bound,
        )

    @app.get(
        "/meta-readings/file-suggestion",
        response_model=FileSuggestionResponse,
        tags=["books"],
    )
    async def file_suggestion(document_id: str) -> FileSuggestionResponse:
        """Suggest research projects a personal-space document could be filed
        into (Read SPR-13 M3). Ranks candidate projects by the doc's semantic
        similarity to each project's question; returns matches above the
        justified threshold, best first (top match, or >1 on a tie — never
        auto-files). SUGGEST-ONLY: this endpoint ranks; filing is the separate
        explicit-accept ``document.filed_into_investigation`` event.

        The doc's match text is its title + its prompt (for a meta-reading) /
        title (for a saved read), reconstructed from the personal-space list —
        the reader's OWN deliverable text, not a withheld source body (§9.0)."""
        from substrate.books.personal_space import (
            list_personal_assets,
            match_document_to_investigations,
        )

        try:
            from substrate.graph.search import SentenceTransformerEmbedding

            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503, detail=f"embedding_unavailable: {exc}"
            ) from exc

        # Build the doc's match text from the personal-space asset (its own
        # deliverable text). If the id isn't a personal asset we fall back to
        # the raw document_id as the match text (still no source body).
        assets = list_personal_assets(book_title_resolver=_book_title_resolver)
        asset = next(
            (a for a in assets if document_id in (a.asset_id, *a.document_ids)),
            None,
        )
        if asset is not None:
            doc_text = " ".join(p for p in (asset.prompt, asset.title) if p)
        else:
            doc_text = document_id

        matches = match_document_to_investigations(doc_text=doc_text, model=model)
        return FileSuggestionResponse(
            document_id=document_id,
            matches=[
                ProjectMatchResponse(
                    investigation_id=m.investigation_id,
                    question=m.question,
                    score=m.score,
                )
                for m in matches
            ],
        )

    # Registered AFTER the static /meta-readings/{categories,file-suggestion}
    # routes so neither is captured as an asset_id (FastAPI matches in
    # registration order; static segments declared first win).
    @app.get(
        "/meta-readings/{asset_id}",
        response_model=SavedMetaReadingResponse,
        tags=["books"],
    )
    async def get_saved_meta_reading(asset_id: str) -> SavedMetaReadingResponse:
        """Re-open a saved meta-reading asset by id (Read SPR-13 M1). Reads the
        ``read.meta_reading.generated`` event off the log (the asset rides
        ``read-meta-{asset_id}``) — the substrate's source of truth, NOT a new
        store. The saved citations carry references (chunk/document/page), never
        a body; the generation-time snippet preview was not persisted, so it is
        an honest empty string on re-open (the page link still resolves)."""
        from substrate.event_log.events import trajectory

        investigation_id = f"read-meta-{asset_id}"
        rows = trajectory(investigation_id)
        payload = next(
            (
                (r.get("payload") or {})
                for r in rows
                if r.get("action_type") == "read.meta_reading.generated"
                and (r.get("payload") or {}).get("asset_id") == asset_id
            ),
            None,
        )
        if payload is None:
            raise HTTPException(
                status_code=404, detail=f"meta-reading asset {asset_id!r} not found."
            )
        return SavedMetaReadingResponse(
            asset_id=asset_id,
            prompt=payload.get("prompt", ""),
            report=payload.get("report", ""),
            citations=[
                CitationResponse(
                    chunk_id=c.get("chunk_id", ""),
                    document_id=c.get("document_id", ""),
                    page_index=c.get("page_index"),
                    page_resolved=bool(c.get("page_resolved", False)),
                    snippet="",
                )
                for c in (payload.get("citations") or [])
            ],
            length_unit=payload.get("length_unit", "pages"),
            length_amount=int(payload.get("length_amount", 1)),
            truncated=bool(payload.get("truncated", False)),
            corpus_scope=payload.get("corpus_scope", "hard"),
            corpus_document_ids=list(payload.get("corpus_document_ids") or []),
        )
