"""Book registration — provenance, rights holder, deny-by-default gate
(SPR-01 M5).

This is the substrate-side half of book ingestion. It takes a book that
has already been read and inserted as a ``documents`` row (the acquisition
layer's job — see ``acquisition/books/adapter.ingest_servable_book``) and:

1. Establishes the book's ``content_class``. The default for any book
   without an explicitly-established servable license — including
   anything aggregated "from online" with unknown rights — is the gated
   state (``GATED_DEFAULT_CONTENT_CLASS``). Deny-by-default is enforced
   here, at the write, not hoped for at the read.
2. Threads an ``ip_holder_id`` onto the document so escrow can later
   accrue to the right rights holder (SPR-09). When the rights holder is
   named, a pre-onboarded ``ip_holders`` account is found-or-created.
3. Writes the ``book_assets`` row (TOC, pagination, cover, provenance,
   license basis).
4. Emits a ``book.servability_changed`` audit event when registration
   moves the book across the servable / gated line.

It does NOT read PDFs or insert documents — that would invert the
substrate→acquisition layering. The acquisition layer (which legitimately
imports substrate) orchestrates read → insert → register.
"""

from __future__ import annotations

from typing import Any

from runtime.db_lock import LockedConnection
from substrate import ip_holders
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS, SYSTEM_INVESTIGATION_ID
from substrate.event_log import emit_typed
from substrate.graph.ops import update_document_gate_columns
from substrate.schemas.events import BookServabilityChangedPayload

from .model import BookAsset, TocItem, get_book_asset, upsert_book_asset
from .servability import servability_of

# The content_class vocabulary a book may legitimately carry. A book is
# never ``user_owned``-only in the per-user sense here (single operator),
# but platform-authored books (Write workflow) use user_owned /
# user_public_contribution. Validated so a typo can't silently create an
# unrecognised class that the projection would then gate by default —
# we want the typo to fail loudly, not fail safe-but-silent.
_VALID_BOOK_CONTENT_CLASSES: frozenset[str] = frozenset({
    "public_domain",
    "opt_in_licensed",
    "source_declared_open",  # source-declared open license (CC-BY / CC-BY-SA); servable
    "user_owned",
    "user_public_contribution",
    "restricted_pending_opt_in",
})


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"book registration requires a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path)."
        )


def resolve_or_create_ip_holder(con: LockedConnection, display_name: str) -> str:
    """Find a pre-onboarded ``ip_holders`` account by display name, or
    create one. Idempotent on display_name so re-ingesting the same
    publisher's books doesn't fan out into duplicate escrow accounts.

    The created account is ``pre_onboarded`` — no notification is sent
    (that gates on G2 lawyer review + operator action per §9.10). Escrow
    can accrue from v1; nothing routes until the publisher claims.
    """
    _require_locked(con)
    for holder in ip_holders.list_all(con):
        if holder.display_name == display_name:
            return holder.ip_holder_id
    return ip_holders.create_pre_onboarded(con, display_name=display_name)


def register_book(
    con: LockedConnection,
    *,
    document_id: str,
    content_class: str | None = None,
    rights_holder_name: str | None = None,
    ip_holder_id: str | None = None,
    toc: list[TocItem] | None = None,
    page_count: int = 0,
    pagination_scheme: str = "pdf_page",
    cover_uri: str | None = None,
    provenance: str | None = None,
    license_basis: str | None = None,
) -> BookAsset:
    """Register an already-inserted book document as a Read-workflow book.

    ``content_class``:
      - ``None`` → ``GATED_DEFAULT_CONTENT_CLASS`` (deny-by-default). This
        is the branch for "aggregated from online, unknown rights".
      - an explicit value → must be in ``_VALID_BOOK_CONTENT_CLASSES``
        (a typo raises rather than silently gating).

    ``ip_holder_id`` is used directly if given; otherwise, if
    ``rights_holder_name`` is given, a pre-onboarded account is
    found-or-created and its id is used; otherwise the document's
    ip_holder_id is left as-is (may be NULL — allowed by the
    provenance-chain invariant).

    Returns the resulting :class:`BookAsset` (with derived servability).
    """
    _require_locked(con)

    doc = con.execute(
        "SELECT content_class FROM documents WHERE document_id = ?", [document_id]
    ).fetchone()
    if doc is None:
        raise ValueError(
            f"{document_id} has no documents row — insert the book document "
            "(acquisition/books) before registering it."
        )
    prev_content_class = doc[0]

    resolved_class = content_class or GATED_DEFAULT_CONTENT_CLASS
    if resolved_class not in _VALID_BOOK_CONTENT_CLASSES:
        raise ValueError(
            f"unrecognised book content_class {resolved_class!r}; "
            f"expected one of {sorted(_VALID_BOOK_CONTENT_CLASSES)}"
        )

    resolved_ip = ip_holder_id
    if resolved_ip is None and rights_holder_name:
        resolved_ip = resolve_or_create_ip_holder(con, rights_holder_name)

    # Set the gate columns on the document via the sanctioned primitive
    # (raw UPDATE of these indexed columns fails on DuckDB 1.5.2 once
    # chunks/book_assets reference the row). ip_holder_id is only
    # overwritten when we resolved one — never nulled out by a re-register.
    update_document_gate_columns(
        con,
        document_id,
        content_class=resolved_class,
        set_content_class=True,
        ip_holder_id=resolved_ip,
        set_ip_holder_id=resolved_ip is not None,
    )

    upsert_book_asset(
        con,
        document_id=document_id,
        toc=toc,
        page_count=page_count,
        pagination_scheme=pagination_scheme,
        cover_uri=cover_uri,
        provenance=provenance,
        license_basis=license_basis,
    )

    # Audit the servability transition iff it actually moved.
    prev_status = servability_of(prev_content_class, taken_down=False)
    new_status = servability_of(resolved_class, taken_down=False)
    if prev_status != new_status:
        emit_typed(
            SYSTEM_INVESTIGATION_ID,
            BookServabilityChangedPayload(
                from_status=prev_status.value,
                to_status=new_status.value,
                reason=license_basis or f"registered with content_class={resolved_class}",
            ),
            document_id=document_id,
            role="read/books",
            policy_id="read/books/ingest",
        )

    asset = get_book_asset(con, document_id)
    assert asset is not None  # just wrote it
    return asset
