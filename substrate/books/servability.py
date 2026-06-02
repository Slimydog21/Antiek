"""Servability projection — the Read workflow's legal gate vocabulary
(SPR-01 M2; master-spec §9.0 / §9.10).

This module answers one question with one source of truth: *given a
book's license state, may Antiek serve its full text?* The answer is
DERIVED from the document's ``content_class`` (the column the chunk-search
G1 gate already keys off — see ``substrate/graph/search.py``) plus a
book-level ``taken_down`` override. It is never stored as a second
authoritative column, because a parallel servability flag would drift
from G1, and a gate that can drift is a gate that fails open.

Two deliberate asymmetries make this defensible:

1. **Deny-by-default.** Full-text serving uses an ALLOWLIST
   (``SERVABLE_CONTENT_CLASSES``). The chunk-search gate in search.py uses
   a *denylist* — NULL content_class passes there as legacy/grandfathered.
   Here, NULL / unknown / restricted resolves to ``gated_metadata_only``
   and is never served full text. Serving a whole book is a far higher-
   liability act than returning a ≤500-char research snippet, so the gate
   is correspondingly stricter — over the same column, so nothing drifts.

2. **Takedown is an override, not a license mutation.** A taken-down
   public-domain book is still public-domain; ``taken_down`` takes
   precedence in the projection but the underlying license is preserved
   (on the book_assets row) so takedown is reversible. See
   ``substrate.books.takedown``.

Legal lineage encoded in the default: *Hachette v. Internet Archive*
(2nd Cir. 2024) killed structural fair use for aggregate-and-serve, and
*Bartz v. Anthropic* (~$1.5B) priced post-serve damages far above the
cost of pre-serve gating. Defaulting unknown-provenance content to
servable is precisely the enjoined Internet-Archive pattern. We refuse it.
"""

from __future__ import annotations

from enum import Enum

from substrate.constants import (
    BOOK_DEFAULT_SERVABILITY,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)


class ServabilityStatus(str, Enum):
    """The presentation vocabulary the library + reader render. Derived
    from ``(content_class, taken_down)`` by :func:`servability_of`; never
    stored as an authoritative column. ``str``-valued so it serializes
    straight into JSON/API responses and compares cleanly against the
    ``substrate.constants.BOOK_SERVABILITY_STATUSES`` tuple."""

    PUBLIC_DOMAIN = "public_domain"
    PLATFORM_AUTHORED = "platform_authored"
    PUBLISHER_OPTED_IN = "publisher_opted_in"
    # A truthful status for a source-declared open license (CC-BY / CC-BY-SA):
    # servable, but NOT a §9.10 publisher opt-in. Deliberately NOT folded into
    # PUBLISHER_OPTED_IN — these works were opened at the source, not claimed
    # by a publisher.
    SOURCE_DECLARED_OPEN = "source_declared_open"
    GATED_METADATA_ONLY = "gated_metadata_only"
    TAKEN_DOWN = "taken_down"
    # Owner-reads-in-full / public-non-servable (Personal-Reading Lane SPR-01).
    # content_class='personal_reading' is the owner's private third-party reading:
    # the owner reads it in full on the personal/operator path, but it is NEVER
    # publicly servable and NEVER ad-attributable. Deliberately NOT a member of
    # _SERVABLE_STATUSES below — is_servable_full_text(PERSONAL_READABLE) is False
    # — and NOT mapped through _CONTENT_CLASS_TO_STATUS, so the drift assertion
    # (_PROJECTED_SERVABLE == SERVABLE_CONTENT_CLASSES) is untouched. It is a
    # distinct status from GATED_METADATA_ONLY so the library can render "your
    # reading" (owner can open it in full) distinctly from a gated book (the
    # owner cannot read a gated copyrighted book in full).
    PERSONAL_READABLE = "personal_readable"


# content_class → servable ServabilityStatus. Only the four allowlisted
# content classes (SERVABLE_CONTENT_CLASSES) map to a full-text-servable
# status; everything else falls through to GATED_METADATA_ONLY below.
# Kept consistent with SERVABLE_CONTENT_CLASSES by the assertion at the
# bottom of this module — the two cannot silently drift.
_CONTENT_CLASS_TO_STATUS: dict[str, ServabilityStatus] = {
    "public_domain": ServabilityStatus.PUBLIC_DOMAIN,
    "user_owned": ServabilityStatus.PLATFORM_AUTHORED,
    "user_public_contribution": ServabilityStatus.PLATFORM_AUTHORED,
    "opt_in_licensed": ServabilityStatus.PUBLISHER_OPTED_IN,
    "source_declared_open": ServabilityStatus.SOURCE_DECLARED_OPEN,
}

# The statuses that permit full-text serving. The complement of this set
# within ServabilityStatus is the "metadata/snippet only" zone.
_SERVABLE_STATUSES: frozenset[ServabilityStatus] = frozenset({
    ServabilityStatus.PUBLIC_DOMAIN,
    ServabilityStatus.PLATFORM_AUTHORED,
    ServabilityStatus.PUBLISHER_OPTED_IN,
    ServabilityStatus.SOURCE_DECLARED_OPEN,
})


def servability_of(
    content_class: str | None,
    *,
    taken_down: bool = False,
) -> ServabilityStatus:
    """Project ``(content_class, taken_down)`` to a ServabilityStatus.

    The single source of the mapping. Both the serve path and the
    library API resolve servability through here, so there is exactly one
    place the legal classification is decided.

    Precedence:

    1. ``taken_down`` wins over everything → ``TAKEN_DOWN``. A removal
       demand is honoured regardless of the underlying license.
    2. An allowlisted ``content_class`` maps to its servable status.
    3. ``personal_reading`` resolves to ``PERSONAL_READABLE`` (owner reads in
       full / public never servable) — a DISTINCT branch BEFORE the generic
       fall-through so it is not silently flattened to gated (the owner CAN read
       it in full, a gated copyrighted book they cannot; the library renders the
       two differently). It is still non-servable on the public path
       (``is_servable_full_text(PERSONAL_READABLE)`` is False).
    4. Everything else — ``restricted_pending_opt_in``, ``None``, an
       unrecognised value — resolves to ``GATED_METADATA_ONLY``
       (deny-by-default). This is the branch that catches "aggregated
       from online with unknown rights".
    """
    if taken_down:
        return ServabilityStatus.TAKEN_DOWN
    if content_class == PERSONAL_READING_CONTENT_CLASS:
        return ServabilityStatus.PERSONAL_READABLE
    if content_class is None:
        return ServabilityStatus.GATED_METADATA_ONLY
    return _CONTENT_CLASS_TO_STATUS.get(
        content_class, ServabilityStatus.GATED_METADATA_ONLY
    )


def is_servable_full_text(status: ServabilityStatus) -> bool:
    """Whether a book in this status may have its full text served.

    The serve path (``substrate.books.serve``) gates on the same
    ``SERVABLE_CONTENT_CLASSES`` allowlist at the SQL layer; this
    predicate is the in-memory equivalent for callers that already hold a
    resolved status. Both derive from the same constant, so the UI-layer
    answer and the data-layer answer cannot disagree."""
    return status in _SERVABLE_STATUSES


# ---------------------------------------------------------------------------
# Drift guard — the projection and the SQL allowlist share one source.
# ---------------------------------------------------------------------------

# The set of content classes that the projection maps to a servable status
# MUST equal SERVABLE_CONTENT_CLASSES (the SQL allowlist used in serve.py).
# If a future edit adds a servable content_class to one but not the other,
# import of this module fails loudly rather than letting the data-layer
# gate and the UI-layer predicate silently disagree.
_PROJECTED_SERVABLE = {
    cc for cc, st in _CONTENT_CLASS_TO_STATUS.items() if st in _SERVABLE_STATUSES
}
assert set(SERVABLE_CONTENT_CLASSES) == _PROJECTED_SERVABLE, (
    "servability projection drifted from SERVABLE_CONTENT_CLASSES: "
    f"projection={_PROJECTED_SERVABLE!r} allowlist={set(SERVABLE_CONTENT_CLASSES)!r}. "
    "These two MUST stay equal or the data-layer gate and the UI predicate "
    "will disagree. Fix substrate/constants.py and this module together."
)

# The default status for unknown-provenance content is the gated one.
assert ServabilityStatus.GATED_METADATA_ONLY.value == BOOK_DEFAULT_SERVABILITY, (
    "BOOK_DEFAULT_SERVABILITY must be the gated_metadata_only status — "
    "deny-by-default is the entire point of this gate."
)
