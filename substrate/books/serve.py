"""Full-text serve path — the data-layer legal gate (SPR-01 M3).

This is where "Spotify, not Internet Archive" is enforced in code. The
serve gate decides, *at the query layer*, what body text a caller may
receive for a book. It is deliberately not a UI check: a test (and an
attacker, and a future careless frontend) that bypasses the UI and calls
this function directly still cannot pull full text out of a non-servable
book, because the gate lives in the SQL that fetches the text.

Three outcomes, mapping to the three legally-distinct regimes:

- **Servable** (public-domain / platform-authored / publisher-opted-in):
  the full ``raw_text`` is returned. Licensing makes this legal — the
  Spotify regime.
- **Gated** (unknown / restricted): at most ``SERVE_SNIPPET_MAX_CHARS`` of
  body is returned alongside metadata. Bounded snippet view is the
  *Authors Guild v. Google* (2d Cir. 2015) fair-use regime.
- **Taken down**: no body at all — not even a snippet. A removal demand
  is honoured absolutely (and the body has usually been purged from
  ``raw_text`` already by the takedown path).

The gate reuses the EXISTING ``documents.content_class`` column and the
``SERVABLE_CONTENT_CLASSES`` allowlist — the same vocabulary the
chunk-search G1 gate keys off in ``substrate/graph/search.py``. There is
no second gating mechanism to drift out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.constants import (
    PERSONAL_READABLE_CONTENT_CLASSES,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
    SERVE_SNIPPET_MAX_CHARS,
)

from .html_sanitizer import is_trusted_sanitized
from .servability import ServabilityStatus, is_servable_full_text, servability_of


@dataclass(frozen=True)
class ServeResult:
    """The outcome of a full-text serve request. ``full_text`` is populated
    ONLY for servable books; ``snippet`` is populated for gated books;
    both are ``None`` for taken-down books and for unknown document_ids.
    ``reason`` explains a denial in human terms (audit / API messaging).

    The four trailing fields carry the arXiv RIGHTS context onto the serve
    contract so a data-driven reader (Read SPR-05) can render the tier / ad
    rail / canonical link / license off the backend response rather than a
    local flag. They are populated ONLY by ``serve_full_text_guarded`` (the
    one place that already reads ``documents.metadata`` for the tier
    cross-check); the bare ``serve_full_text`` gate leaves them at their
    backward-compatible defaults, so every existing construction site and
    every non-arXiv book is byte-identical to before.

    - ``tier``: the resolved ``RightsTier`` value (``'T1'|'T2'|'T3'``) for an
      arXiv document (one carrying a ``license_uri`` in metadata); ``None``
      for a non-arXiv document, where the tier arm is skipped.
    - ``ad_eligible``: whether an ad rail may mount. For an arXiv document it
      is ``ads_allowed(tier)`` (T1 only); for a non-arXiv document it
      PRESERVES today's behaviour (``== servable``) so existing servable
      books stay ad-eligible — no regression.
    - ``canonical_url``: ``https://arxiv.org/abs/{arxiv_id}`` for an arXiv
      document; ``None`` otherwise.
    - ``license``: the arXiv ``license_uri`` (the rights anchor) for an arXiv
      document; ``None`` otherwise.
    """

    document_id: str
    found: bool
    servability: ServabilityStatus | None
    servable: bool
    full_text: str | None
    snippet: str | None
    title: str | None
    author: str | None
    reason: str
    # Rights context (populated by serve_full_text_guarded; defaulted here so
    # the bare gate and all existing construction sites are unchanged).
    tier: str | None = None
    ad_eligible: bool = False
    canonical_url: str | None = None
    license: str | None = None
    content_format: Literal["text", "html"] = "text"


def serve_full_text(con: Any, document_id: str, *, owner: bool = False) -> ServeResult:
    """Resolve what body text may be served for ``document_id``.

    The single fetch returns ``content_class`` + ``raw_text`` + the
    book's ``taken_down`` flag in one query; the gate is then applied in
    code over those authoritative values. We do NOT pre-filter the SELECT
    on the allowlist, because a denial still needs to report the book's
    status and metadata — pre-filtering would erase the difference
    between "gated" and "doesn't exist", and the library needs that
    difference. The gate is no less enforced for being applied after the
    fetch: a non-servable book's ``raw_text`` never leaves this function.

    ``owner`` (Personal-Reading Lane SPR-01) is the OWNER full-read switch and
    it defaults to ``False`` so the PUBLIC serve path is byte-identical to
    before — every existing caller (the public serve, ``serve_full_text_guarded``,
    ``curate``, ``passage_research``) stays on the narrow SERVABLE-only allowlist.
    When ``owner=True`` (the operator / personal-space reader, the only caller
    that may pass it), a ``personal_reading`` document additionally resolves to
    its FULL body — the owner reads their own fetched third-party content in
    full, exactly the lane's purpose — while everything else (servable, gated,
    taken-down) behaves identically to the public path. This widens nothing on
    the public default: the gate keys on ``PERSONAL_READABLE_CONTENT_CLASSES``
    (= servable ∪ personal_reading) ONLY on the owner branch; the public branch
    still keys on ``SERVABLE_CONTENT_CLASSES``. A taken-down personal_reading
    document is still TAKEN_DOWN for the owner too (removal is absolute).
    """
    row = con.execute(
        """
        SELECT d.title, d.author, d.content_class, d.raw_text, d.metadata,
               COALESCE(b.taken_down, FALSE) AS taken_down
        FROM documents d
        LEFT JOIN book_assets b ON d.document_id = b.document_id
        WHERE d.document_id = ?
        """,
        [document_id],
    ).fetchone()

    if row is None:
        return ServeResult(
            document_id=document_id, found=False, servability=None,
            servable=False, full_text=None, snippet=None,
            title=None, author=None, reason="document_not_found",
        )

    title, author, content_class, raw_text, metadata, taken_down = row
    taken_down = bool(taken_down)
    status = servability_of(content_class, taken_down=taken_down)

    if status is ServabilityStatus.TAKEN_DOWN:
        # Removal demand honoured absolutely — no body, no snippet. This wins
        # over the owner branch too: a taken-down book is unreadable by anyone.
        return ServeResult(
            document_id=document_id, found=True, servability=status,
            servable=False, full_text=None, snippet=None,
            title=title, author=author, reason="taken_down",
        )

    # Owner full-read (Personal-Reading Lane SPR-01). On the OWNER path only, a
    # personal_reading document resolves to its full body — the owner reads their
    # own fetched third-party content in full. ``servable`` stays False because
    # this body is NOT publicly servable / ad-eligible (the public path never
    # reaches here for personal_reading: it falls through to the gated snippet
    # branch below). The membership check is the PERSONAL_READABLE allowlist so a
    # future content_class can't sneak full text out on the owner path either.
    if (
        owner
        and content_class == PERSONAL_READING_CONTENT_CLASS
        and content_class in PERSONAL_READABLE_CONTENT_CLASSES
    ):
        return ServeResult(
            document_id=document_id, found=True, servability=status,
            servable=False, full_text=raw_text, snippet=None,
            title=title, author=author, reason="owner_personal_reading",
            content_format="html" if is_trusted_sanitized(metadata) else "text",
        )

    if is_servable_full_text(status):
        # Belt-and-suspenders: the in-memory predicate and the SQL
        # allowlist must agree. If they ever didn't, fail closed.
        if content_class not in SERVABLE_CONTENT_CLASSES:  # pragma: no cover
            return ServeResult(
                document_id=document_id, found=True, servability=status,
                servable=False, full_text=None,
                snippet=_snippet(raw_text), title=title, author=author,
                reason="gate_disagreement_failed_closed",
            )
        return ServeResult(
            document_id=document_id, found=True, servability=status,
            servable=True, full_text=raw_text, snippet=None,
            title=title, author=author, reason="servable",
            content_format="html" if is_trusted_sanitized(metadata) else "text",
        )

    # Gated → bounded snippet (Authors Guild v. Google fair-use regime).
    return ServeResult(
        document_id=document_id, found=True, servability=status,
        servable=False, full_text=None, snippet=_snippet(raw_text),
        title=title, author=author, reason="gated_metadata_only",
    )


def _snippet(raw_text: str | None) -> str | None:
    """Bounded body excerpt for gated books. None when there's no body."""
    if not raw_text:
        return None
    if len(raw_text) <= SERVE_SNIPPET_MAX_CHARS:
        return raw_text
    return raw_text[:SERVE_SNIPPET_MAX_CHARS].rstrip() + "…"
