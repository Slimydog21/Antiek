"""The serving-boundary guard — the single place a full body leaves Antiek
storage on the serving side (SPR-02 M2).

This lives in ``substrate.books`` (adjacent to ``serve.py``, the binding gate it
wraps) because it is PURE SUBSTRATE LOGIC: it imports only
``substrate.books.serve`` + ``substrate.rights`` and touches no HTTP/API
concern. ``interfaces/research/api/serve_guard.py`` is a thin re-export shim
over this module, preserving the SPR-02 M2 named file path for callers in the
interfaces layer without forcing a ``substrate -> interfaces`` import.

This composes the two independent, deny-by-default gates whose AND is the
serving boundary the spec demands a body "physically cannot" cross when the
license forbids it:

1. **content_class gate** — ``substrate.books.serve.serve_full_text``. The
   binding gate: it returns a ``full_text`` body ONLY when
   ``documents.content_class`` is in ``SERVABLE_CONTENT_CLASSES``; otherwise a
   bounded snippet (or nothing). It already fails closed. We REUSE it verbatim —
   this guard does not re-implement, weaken, or duplicate it.

2. **license-tier gate** — an INDEPENDENT cross-check keyed off the immutable
   arXiv ``<license>`` URI. For any document whose ``documents.metadata`` JSON
   carries a ``license_uri`` (i.e. an arXiv OAI row — written by
   ``acquisition.arxiv.oai_persist._record_metadata``), we re-derive the rights
   tier from that raw URI via ``resolve_tier`` and ask ``body_servable``. If the
   content_class gate cleared a body the LICENSE forbids ({T1} only on the
   current commercial surface), that is silent rights drift — the cardinal sin —
   and we raise ``T3BodyServeError``.

Why two gates instead of trusting the one. The danger is a refactor (or a
corrupt ``content_class`` / a wrongly-stored ``rights_tier``) that lets a
non-{T1} full-text body be served from Antiek storage — a redistribution (or
NC-commercial-use) violation. A single gate keyed off ``content_class`` cannot
catch its own corruption; an INDEPENDENT check off the raw, immutable
``<license>`` element can. That is why this guard re-derives the tier from
``license_uri`` and deliberately does NOT trust the stored ``rights_tier``
value: the whole point is to detect the case where a stored verdict disagrees
with the license.

Why it is a transparent pass-through TODAY (zero regression). Every existing
book is non-arXiv → no ``license_uri`` in metadata → ``_tier_for_document``
returns ``None`` → the tier arm is SKIPPED → behaviour is byte-identical to a
bare ``serve_full_text`` call. Every arXiv row today sits at the gated floor
(``restricted_pending_opt_in``), so ``serve_full_text`` returns
``full_text=None`` and the tier arm never even looks at the license. The guard
only grows teeth when SPR-04 starts promoting T1 bodies — at which point a
drift between the promoted ``content_class`` and the license is caught here.

This module is the ONE sanctioned caller of ``serve_full_text`` on the serving
side; ``tools/lint/serve_guard_check.py`` enforces that mechanically.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from substrate.books.serve import ServeResult, serve_full_text
from substrate.rights import (
    RightsTier,
    T3BodyServeError,
    body_servable,
    resolve_tier,
)


def _tier_for_document(con: Any, document_id: str) -> Optional[RightsTier]:
    """Re-derive the rights tier for ``document_id`` from its IMMUTABLE arXiv
    ``<license>`` URI, INDEPENDENTLY of any stored tier verdict.

    Reads ``documents.metadata`` (a TEXT-JSON column) and extracts the
    ``license_uri`` the OAI persist path stamped in. Returns:

      * ``resolve_tier(license_uri)`` when the row carries a ``license_uri`` —
        the tier derived FRESH from the raw license, so a corrupt stored
        ``rights_tier`` / ``content_class`` cannot launder a body past this arm.
      * ``None`` when the row is missing, has no metadata, has unparseable
        metadata, or has no ``license_uri`` (every non-arXiv book) — the tier
        arm is then SKIPPED, leaving behaviour identical to bare serving.

    Deliberately does NOT read ``metadata['rights_tier']``: an independent
    re-derivation off the license element is the entire defense. A present-but-
    empty/whitespace ``license_uri`` still flows through ``resolve_tier``, which
    deny-by-defaults it to T3 — i.e. a blanked-out license is treated as the
    most restrictive tier, not skipped.
    """
    row = con.execute(
        "SELECT metadata FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    try:
        metadata = json.loads(row[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        # Unparseable metadata is not a license signal — skip the tier arm and
        # let the content_class gate stand alone (it already failed closed if it
        # cleared this body). We do not infer a tier from a corrupt blob.
        return None
    if not isinstance(metadata, dict) or "license_uri" not in metadata:
        return None
    return resolve_tier(metadata["license_uri"])


def serve_full_text_guarded(con: Any, document_id: str) -> ServeResult:
    """Serve a full body through BOTH the content_class gate and an independent
    license-tier cross-check.

    Delegates to the binding ``serve_full_text`` gate, then — ONLY when that
    gate is about to emit a body (``full_text is not None``) — re-derives the
    rights tier from the immutable ``license_uri`` and refuses (raises
    ``T3BodyServeError``) if the license does not permit a body to leave storage
    on the current commercial surface ({T1} only). On the normal gated path
    ``full_text`` is ``None``, so the tier arm never fires; for a non-arXiv book
    the tier is ``None`` and is skipped. The result object is returned UNCHANGED
    in every non-drift case — the guard preserves ``.servable`` / ``.full_text``
    / ``.snippet`` exactly so callers' downstream branching is untouched.
    """
    result = serve_full_text(con, document_id)
    if result.full_text is not None:
        tier = _tier_for_document(con, document_id)
        if tier is not None and not body_servable(tier):
            raise T3BodyServeError(
                f"RIGHTS DRIFT: serve gate cleared a full body for "
                f"{document_id!r} (content_class -> servable, reason="
                f"{result.reason!r}) but its arXiv <license> resolves to "
                f"{tier.value} — a non-body-servable tier ({tier!r}). A body "
                f"present whose license forbids redistribution from Antiek "
                f"storage is the cardinal redistribution violation; refusing "
                f"to emit it. The body-servable tier is T1 only on the current "
                f"commercial surface (T2 CC-BY-NC is non-commercial-display "
                f"only, coherent with acquisition.licenses_core); this is the "
                f"deny-by-default serving boundary (master-spec §9.0)."
            )
    return result


__all__ = ["serve_full_text_guarded"]
