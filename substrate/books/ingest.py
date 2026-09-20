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
from substrate.constants import SYSTEM_INVESTIGATION_ID
from substrate.event_log import emit_typed

# Re-export so acquisition/opt_in/intake.py's historical
# ``from substrate.books.ingest import resolve_or_create_ip_holder`` keeps resolving;
# the function's ONE home is now substrate.rights.register (the cross-source chokepoint).
from substrate.rights.register import (
    VALID_CONTENT_CLASSES,
    SourceKind,
    register_source_document,
    resolve_or_create_ip_holder,  # noqa: F401
)
from substrate.schemas.events import BookServabilityChangedPayload

from .model import BookAsset, TocItem, get_book_asset, upsert_book_asset
from .servability import servability_of

# The content_class vocabulary a book may legitimately carry — now an ALIAS of the
# canonical cross-source vocabulary in substrate.rights.register (ONE home, so the
# book path and the registration chokepoint cannot drift). Kept under this name
# because test_oa_licenses / test_licenses_classify / test_arxiv_licenses assert that
# resolved classes are members of it.
_VALID_BOOK_CONTENT_CLASSES: frozenset[str] = VALID_CONTENT_CLASSES


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"book registration requires a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path)."
        )


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
    emit_servability_audit: bool = True,
) -> BookAsset:
    """Register an already-inserted book document as a Read-workflow book.

    Delegates its rights core (content_class resolve + deny-by-default validation,
    ip_holder threading, gate-column write) to
    ``substrate.rights.register.register_source_document`` — the one cross-source
    chokepoint — then writes the book_asset row + audits any servability transition.

    ``content_class``:
      - ``None`` → deny-by-default gated class.
      - an explicit value → must be a known content class (a typo raises
        ``unrecognised content_class`` rather than silently gating).

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

    # Delegate the rights core — content_class resolve + deny-by-default validation,
    # ip_holder threading, and the gate-column write — to the ONE cross-source
    # registration chokepoint, so the book path can never drift from every other
    # source's rights handling. Books is a licensed-publisher source. run_self_check
    # is False: register_book has never run the post-write serve-guard self-check
    # (that is the arXiv-store precedent the chokepoint generalizes), so omitting it
    # here is behaviour-preserving.
    resolved_class = register_source_document(
        con,
        document_id=document_id,
        source_kind=SourceKind.LICENSED_PUBLISHER,
        content_class=content_class,
        ip_holder_id=ip_holder_id,
        rights_holder_name=rights_holder_name,
        run_self_check=False,
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
    if emit_servability_audit and prev_status != new_status:
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
