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
from typing import Any, Optional

from substrate.constants import SERVABLE_CONTENT_CLASSES, SERVE_SNIPPET_MAX_CHARS

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
    servability: Optional[ServabilityStatus]
    servable: bool
    full_text: Optional[str]
    snippet: Optional[str]
    title: Optional[str]
    author: Optional[str]
    reason: str
    # Rights context (populated by serve_full_text_guarded; defaulted here so
    # the bare gate and all existing construction sites are unchanged).
    tier: Optional[str] = None
    ad_eligible: bool = False
    canonical_url: Optional[str] = None
    license: Optional[str] = None


def serve_full_text(con: Any, document_id: str) -> ServeResult:
    """Resolve what body text may be served for ``document_id``.

    The single fetch returns ``content_class`` + ``raw_text`` + the
    book's ``taken_down`` flag in one query; the gate is then applied in
    code over those authoritative values. We do NOT pre-filter the SELECT
    on the allowlist, because a denial still needs to report the book's
    status and metadata — pre-filtering would erase the difference
    between "gated" and "doesn't exist", and the library needs that
    difference. The gate is no less enforced for being applied after the
    fetch: a non-servable book's ``raw_text`` never leaves this function.
    """
    row = con.execute(
        """
        SELECT d.title, d.author, d.content_class, d.raw_text,
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

    title, author, content_class, raw_text, taken_down = row
    taken_down = bool(taken_down)
    status = servability_of(content_class, taken_down=taken_down)

    if status is ServabilityStatus.TAKEN_DOWN:
        # Removal demand honoured absolutely — no body, no snippet.
        return ServeResult(
            document_id=document_id, found=True, servability=status,
            servable=False, full_text=None, snippet=None,
            title=title, author=author, reason="taken_down",
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
        )

    # Gated → bounded snippet (Authors Guild v. Google fair-use regime).
    return ServeResult(
        document_id=document_id, found=True, servability=status,
        servable=False, full_text=None, snippet=_snippet(raw_text),
        title=title, author=author, reason="gated_metadata_only",
    )


def _snippet(raw_text: Optional[str]) -> Optional[str]:
    """Bounded body excerpt for gated books. None when there's no body."""
    if not raw_text:
        return None
    if len(raw_text) <= SERVE_SNIPPET_MAX_CHARS:
        return raw_text
    return raw_text[:SERVE_SNIPPET_MAX_CHARS].rstrip() + "…"
