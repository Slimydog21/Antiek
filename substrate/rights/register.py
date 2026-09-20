"""Unified cross-source rights registration — the single deny-by-default
chokepoint every acquisition source threads its rights through.

WHY THIS EXISTS (reframe finding #5): before this module, only the books path
(``substrate.books.ingest.register_book``) established a document's
``content_class`` + ``ip_holder_id``. The other acquisition sources (arxiv,
urls, podcasts, interview, twitter, voice, youtube) called ``insert_document``
directly, leaving the gate columns NULL — so the deny-by-default rights
substrate compounded for books alone. This module lifts the books pattern into
a source-agnostic registrar so every source inherits the same deny-by-default
rights stamping, IP attribution, and post-write serve-guard self-check.

The document row MUST already exist: the acquisition layer inserts it, then
registers. This preserves the substrate->acquisition layering (substrate never
reads PDFs or inserts documents on a source's behalf).

``register_book`` delegates its rights core here. Migrating the remaining
adapters is gated on a per-source ``content_class`` decision (master-spec §9.0 —
a legal-gate call, operator-owned; the diligence rationale lives in the reframe
spec workspace, not this repo) — this module makes that migration a one-line call
per adapter, not a per-adapter reinvention.

PURE substrate: imports only ``runtime`` + lower ``substrate`` modules. The
serve-guard self-check is lazy-imported to avoid a substrate.rights ->
substrate.books cycle (``substrate.books.ingest`` imports this module).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from runtime.db_lock import LockedConnection
from substrate import ip_holders
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    PERSONAL_READING_CONTENT_CLASS,
)
from substrate.graph.ops import update_document_gate_columns


class SourceKind(StrEnum):
    """What kind of source a document came from.

    Drives escrow eligibility: a ``user_content`` document has no external
    rights holder who could ever be paid, so it is excluded *by construction*
    from any escrow/payout pool. Encoding that as a source-kind tag at the
    registration chokepoint makes the exclusion structural, not a downstream
    filter a future payout query could forget.
    """

    LICENSED_PUBLISHER = "licensed_publisher"  # a book claimed via the §9.10 opt-in flow
    ACADEMIC_PREPRINT = "academic_preprint"    # arXiv / open-access papers
    USER_CONTENT = "user_content"              # the operator's own / -captured media: voice, interview, twitter, youtube
    WEB = "web"                                # fetched third-party web pages


# Source kinds that must NEVER mint or accrue to an escrow account: the
# operator's own captures and user-captured media have no external rights
# holder. Defense-in-depth — even if a caller passes a ``rights_holder_name``,
# the registrar refuses to create escrow for these kinds.
_NON_ESCROW_SOURCE_KINDS: frozenset[SourceKind] = frozenset({SourceKind.USER_CONTENT})


# The canonical content-class vocabulary the substrate may stamp on a document.
# ONE home — ``substrate.books.ingest`` imports this rather than re-literalling
# it. A value outside the set is a typo: raise loudly rather than silently gate
# (a silent mis-stamp is a rights hazard, not a convenience).
VALID_CONTENT_CLASSES: frozenset[str] = frozenset({
    "public_domain",
    "opt_in_licensed",
    "source_declared_open",
    "user_owned",
    "user_public_contribution",
    "restricted_pending_opt_in",
    PERSONAL_READING_CONTENT_CLASS,  # Personal-Reading Lane SPR-01 — owner-readable, non-servable
})


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"source registration requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write(db_path)."
        )


def resolve_or_create_ip_holder(con: LockedConnection, display_name: str) -> str:
    """Find a ``pre_onboarded`` ip_holders account by display name, or create
    one. Idempotent on ``display_name`` so re-ingesting the same rights
    holder's works doesn't fan out into duplicate escrow accounts.

    The account is created ``pre_onboarded`` — no notification is sent (that
    gates on G2 lawyer review + operator action per §9.10). Escrow may accrue
    from v1; nothing routes until the holder claims.
    """
    _require_locked(con)
    for holder in ip_holders.list_all(con):
        if holder.display_name == display_name:
            return str(holder.ip_holder_id)
    return str(ip_holders.create_pre_onboarded(con, display_name=display_name))


def register_source_document(
    con: LockedConnection,
    *,
    document_id: str,
    source_kind: SourceKind,
    content_class: str | None = None,
    ip_holder_id: str | None = None,
    rights_holder_name: str | None = None,
    run_self_check: bool = True,
) -> str:
    """Register an already-inserted document's rights, deny-by-default. The
    single chokepoint every source routes through. Returns the resolved
    ``content_class``.

    Steps, all under the caller's single write lock:

    1. The document row must already exist (insert before register) — else
       ``ValueError`` (a register with no row is a caller bug, not a silent
       no-op).
    2. ``content_class`` resolves to ``GATED_DEFAULT_CONTENT_CLASS`` when not
       given (deny-by-default); an explicit value must be in
       :data:`VALID_CONTENT_CLASSES` (a typo raises).
    3. Escrow: a ``user_content`` source is escrow-excluded BY CONSTRUCTION —
       passing it an ``ip_holder_id`` OR a ``rights_holder_name`` RAISES (it has
       no external rights holder to ever pay). Otherwise ``ip_holder_id`` is used
       directly if given; else, if ``rights_holder_name`` is given, a
       ``pre_onboarded`` account is found-or-created.
    4. The gate columns are set via the sanctioned
       :func:`substrate.graph.ops.update_document_gate_columns` primitive (the
       only way to mutate these indexed columns on a row that already has
       chunks / a book_assets row). ``ip_holder_id`` is written only when one
       was resolved — never nulled out by a re-register.
    5. If ``run_self_check`` (default ``True``): the post-write serve-guard
       self-check runs in the same txn — a stamp the SPR-02 serve guard would
       reject raises here, loudly, instead of leaking at read time. This
       generalizes the ``acquisition/arxiv/store.py`` T1-store precedent.

    SCOPE OF THE GUARANTEE (intellectual honesty): this validates that
    ``content_class`` is a KNOWN class (spelling) — NOT that it is the legally
    CORRECT class for the source. For a non-arXiv source an explicit servable
    ``content_class`` is trusted as given: the caller's rights determination is
    the safety surface, and for the deferred adapters that determination is a
    master-spec §9.0 legal-gate call. The self-check (step 5) is the only
    INDEPENDENT cross-check and it bites ONLY on arXiv ``<license>`` drift; a
    valid-but-wrong servable class on a non-arXiv doc is not caught here.
    """
    _require_locked(con)

    stored = con.execute(
        "SELECT content_class, ip_holder_id FROM documents "
        "WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if stored is None:
        raise ValueError(
            f"{document_id} has no documents row — insert the document before "
            "registering its rights (acquisition inserts, then registers)."
        )

    resolved_class = content_class or GATED_DEFAULT_CONTENT_CLASS
    if resolved_class not in VALID_CONTENT_CLASSES:
        raise ValueError(
            f"unrecognised content_class {resolved_class!r}; expected one of "
            f"{sorted(VALID_CONTENT_CLASSES)}"
        )

    # user_content is escrow-excluded BY CONSTRUCTION: the operator's own / -captured
    # media has no external rights holder to ever pay, so passing an explicit
    # ip_holder_id OR a rights_holder_name is a category error — RAISE, making the
    # exclusion structural rather than a silent skip a caller could route an explicit
    # id around (the path the verifier-critic found open at b25b275).
    if source_kind in _NON_ESCROW_SOURCE_KINDS and (ip_holder_id or rights_holder_name):
        raise ValueError(
            f"{source_kind.value} is escrow-excluded by construction — it has no "
            f"external rights holder; passing ip_holder_id / rights_holder_name is "
            f"a category error. Omit both for user-captured content."
        )
    resolved_ip = ip_holder_id
    if resolved_ip is None and rights_holder_name:
        resolved_ip = resolve_or_create_ip_holder(con, rights_holder_name)

    stored_class, stored_ip = stored
    set_content_class = stored_class != resolved_class
    set_ip_holder_id = resolved_ip is not None and stored_ip != resolved_ip
    if set_content_class or set_ip_holder_id:
        update_document_gate_columns(
            con,
            document_id,
            content_class=resolved_class,
            set_content_class=set_content_class,
            ip_holder_id=resolved_ip,
            set_ip_holder_id=set_ip_holder_id,
        )

    if run_self_check:
        # Generalize the arxiv/store.py precedent: a promotion the SPR-02 serve
        # guard would reject must fail at WRITE time, in this txn — never leak
        # at read time. Lazy import breaks the substrate.rights -> substrate.books
        # cycle (books.ingest imports this module).
        from substrate.books.serve_guard import serve_full_text_guarded

        serve_full_text_guarded(con, document_id)

    return resolved_class
