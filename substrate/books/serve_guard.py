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
book is non-arXiv → no ``license_uri`` in metadata → ``_rights_context``
returns a tier of ``None`` → the tier arm is SKIPPED → the SERVE DECISION is
identical to a bare ``serve_full_text`` call. Every arXiv row today sits at the
gated floor
(``restricted_pending_opt_in``), so ``serve_full_text`` returns
``full_text=None`` and the tier arm never even looks at the license. The guard
only grows teeth when SPR-04 starts promoting T1 bodies — at which point a
drift between the promoted ``content_class`` and the license is caught here.

This module is the ONE sanctioned caller of ``serve_full_text`` on the serving
side; ``tools/lint/serve_guard_check.py`` enforces that mechanically.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, NamedTuple

from substrate.books.servability import is_servable_full_text, servability_of
from substrate.books.serve import ServeResult, serve_full_text
from substrate.constants import (
    PERSONAL_READABLE_CONTENT_CLASSES,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.rights import (
    RightsTier,
    T3BodyServeError,
    ads_allowed,
    body_servable,
    resolve_tier,
)


class LinkBackMissingError(RuntimeError):
    """Raised when the guard would emit a full body for an arXiv document
    (a tier-resolved row) WITHOUT a ``canonical_url`` link-back (SPR-09 M2).

    arXiv's terms require attribution back to the canonical arxiv.org abstract
    page for any served body. ``canonical_url`` is derived as
    ``https://arxiv.org/abs/{arxiv_id}`` ONLY when ``arxiv_id`` is present in
    metadata; if a body-servable arXiv row is missing its ``arxiv_id`` (so the
    link-back would be ``None``) emitting the body would ship it with NO
    attribution. The guard refuses rather than serve an un-attributed arXiv
    body — the same deny-by-default posture as the T3 body guard. (A non-arXiv
    document — ``tier is None`` — is UNCONSTRAINED: its ``canonical_url`` is
    legitimately ``None``.)"""


class _RightsContext(NamedTuple):
    """The arXiv rights context read ONCE from ``documents.metadata``.

    ``tier`` is the FRESH license-derived tier (re-derived off the immutable
    ``license_uri`` via ``resolve_tier``, NEVER the stored ``rights_tier`` — so a
    corrupt stored verdict cannot launder a body past the drift cross-check);
    ``arxiv_id`` and ``license_uri`` are the raw values the OAI persist path
    stamped in (``acquisition.arxiv.oai_persist._record_metadata``). All three
    are ``None`` for a non-arXiv document (a row with no ``license_uri`` key),
    which is how the serve contract distinguishes "arXiv paper" from "existing
    book" downstream."""

    tier: RightsTier | None
    arxiv_id: str | None
    license_uri: str | None


def _rights_context(con: Any, document_id: str) -> _RightsContext:
    """Read ``documents.metadata`` ONCE and project the arXiv rights context.

    This is the SINGLE metadata read that backs BOTH the drift cross-check (via
    ``.tier``) and the serve-contract enrichment (tier / canonical_url /
    license). Defensive parsing: a missing row / missing metadata / unparseable
    JSON / no ``license_uri`` key all yield a non-arXiv document (everything
    ``None``), so the tier arm is skipped and behaviour is identical to bare
    serving. For an arXiv row it returns the tier RE-DERIVED from the immutable
    ``license_uri`` (so a corrupt stored ``rights_tier`` cannot launder
    anything), plus the ``arxiv_id`` and ``license_uri`` the persist path wrote.
    A present-but-blank ``license_uri`` is still an arXiv signal: it flows through
    ``resolve_tier`` to T3 (deny-by-default), and its ``arxiv_id`` is still read.
    """
    row = con.execute(
        "SELECT metadata FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None or row[0] is None:
        return _RightsContext(None, None, None)
    return _rights_context_from_metadata(row[0])


def _rights_context_from_metadata(raw_metadata: object) -> _RightsContext:
    try:
        metadata = (
            json.loads(raw_metadata)
            if isinstance(raw_metadata, str)
            else raw_metadata
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        # Unparseable metadata is not a license signal — treat as non-arXiv so
        # the tier arm is skipped and the content_class gate stands alone (it
        # already failed closed if it cleared this body). We do not infer a tier
        # from a corrupt blob.
        return _RightsContext(None, None, None)
    if not isinstance(metadata, dict) or "license_uri" not in metadata:
        return _RightsContext(None, None, None)
    license_uri = metadata["license_uri"]
    arxiv_id = metadata.get("arxiv_id")
    # A whitespace-only arxiv_id is NOT a usable id: it would yield a bogus
    # canonical_url ``https://arxiv.org/abs/   `` (and pass the link-back check
    # with a meaningless link). Gate on a non-empty STRIPPED string so a
    # blank/whitespace arxiv_id is treated as absent — the link-back invariant
    # then refuses the body (deny-by-default) instead of shipping a junk link.
    usable_arxiv_id = (
        arxiv_id if isinstance(arxiv_id, str) and arxiv_id.strip() else None
    )
    return _RightsContext(
        tier=resolve_tier(license_uri),
        arxiv_id=usable_arxiv_id,
        license_uri=license_uri if isinstance(license_uri, str) else None,
    )


def guard_candidate_full_text(
    raw_text: str | None,
    content_class: str | None,
    metadata: object,
    *,
    owner: bool = False,
    taken_down: bool = False,
) -> str | None:
    """Apply the stored-body serve rules before an atomic document insert.

    A not-yet-persisted row has no takedown record. This function otherwise
    mirrors the content-class and immutable-license arms used by
    :func:`serve_full_text_guarded`, allowing writers to derive dependent
    declarations before their single INSERT without an unguarded body path.
    """
    status = servability_of(content_class, taken_down=taken_down)
    owner_readable = (
        owner
        and content_class == PERSONAL_READING_CONTENT_CLASS
        and content_class in PERSONAL_READABLE_CONTENT_CLASSES
    )
    publicly_servable = (
        is_servable_full_text(status)
        and content_class in SERVABLE_CONTENT_CLASSES
    )
    body = raw_text if owner_readable or publicly_servable else None
    if body is None:
        return None
    ctx = _rights_context_from_metadata(metadata)
    if ctx.tier is not None and not body_servable(ctx.tier):
        raise T3BodyServeError(
            "RIGHTS DRIFT: candidate content_class permits a full body but "
            f"its immutable license resolves to {ctx.tier.value}"
        )
    if ctx.tier is not None and ctx.arxiv_id is None:
        raise LinkBackMissingError(
            "LINK-BACK MISSING: candidate arXiv body has no usable arxiv_id"
        )
    return body


def guard_document_candidate_full_text(
    con: Any,
    document_id: str,
    content_class: str | None,
    *,
    owner: bool = False,
) -> str | None:
    """Project a proposed class over stored bytes without exposing them.

    Used by the rights writer to derive the dependent twin declaration before
    one atomic UPDATE changes both fields.
    """
    row = con.execute(
        "SELECT d.raw_text, d.metadata, COALESCE(b.taken_down, FALSE) "
        "FROM documents d LEFT JOIN book_assets b ON d.document_id=b.document_id "
        "WHERE d.document_id=?",
        [document_id],
    ).fetchone()
    if row is None:
        return None
    return guard_candidate_full_text(
        None if row[0] is None else str(row[0]),
        content_class,
        row[1],
        owner=owner,
        taken_down=bool(row[2]),
    )


def serve_full_text_guarded(
    con: Any, document_id: str, *, owner: bool = False
) -> ServeResult:
    """Serve a full body through BOTH the content_class gate and an independent
    license-tier cross-check, and stamp the arXiv RIGHTS context onto the result.

    Delegates to the binding ``serve_full_text`` gate, then — ONLY when that
    gate is about to emit a body (``full_text is not None``) — re-derives the
    rights tier from the immutable ``license_uri`` and refuses (raises
    ``T3BodyServeError``) if the license does not permit a body to leave storage
    on the current commercial surface ({T1} only). On the normal gated path
    ``full_text`` is ``None``, so the tier arm never fires; for a non-arXiv book
    the tier is ``None`` and is skipped.

    On the non-drift path the result is returned with the four rights fields
    POPULATED so a data-driven reader (Read SPR-05) reads tier / ad-eligibility /
    canonical link / license off the backend response, never a local flag. The
    serve-decision fields (``.servable`` / ``.full_text`` / ``.snippet``) are
    preserved EXACTLY (``dataclasses.replace`` only adds the rights fields), so
    callers' downstream branching is untouched. There is ONE read of
    ``documents.metadata`` — ``_rights_context`` — and its ``.tier`` backs BOTH
    the drift cross-check and the enrichment, so the two can never diverge.

    The ad-eligibility rule is REGRESSION-SAFE:
      * arXiv document (tier resolvable) → ``ads_allowed(tier)`` (T1 only).
      * non-arXiv document (tier ``None``) → ``servable`` — preserving today's
        behaviour where the reader mounts ad rails on any servable book.
    Ad-eligibility is derived ONLY from ``substrate.rights.ads_allowed`` /
    ``resolve_tier`` (the single source of truth), never re-derived from
    license/content_class here.
    """
    # ``owner`` threads to the binding content_class gate: True admits the
    # operator's personal_reading content (the §9.0 owner-read privilege),
    # False withholds it. The license-tier arm below fires EITHER way — a
    # non-T1 arXiv body never leaves storage, even on the owner path (so it
    # can never slip into a model's system_context via the context picker).
    result = serve_full_text(con, document_id, owner=owner)
    ctx = _rights_context(con, document_id)
    canonical_url = (
        f"https://arxiv.org/abs/{ctx.arxiv_id}" if ctx.arxiv_id else None
    )
    if result.full_text is not None:
        if ctx.tier is not None and not body_servable(ctx.tier):
            raise T3BodyServeError(
                f"RIGHTS DRIFT: serve gate cleared a full body for "
                f"{document_id!r} (content_class -> servable, reason="
                f"{result.reason!r}) but its arXiv <license> resolves to "
                f"{ctx.tier.value} — a non-body-servable tier ({ctx.tier!r}). A "
                f"body present whose license forbids redistribution from Antiek "
                f"storage is the cardinal redistribution violation; refusing "
                f"to emit it. The body-servable tier is T1 only on the current "
                f"commercial surface (T2 CC-BY-NC is non-commercial-display "
                f"only, coherent with acquisition.licenses_core); this is the "
                f"deny-by-default serving boundary (master-spec §9.0)."
            )
        # Link-back invariant (SPR-09 M2): a body emitted for an ARXIV document
        # (tier resolved) MUST carry a canonical_url back to arxiv.org. The only
        # way an arXiv body reaches here without one is a missing arxiv_id in
        # metadata (canonical_url stays None). Refuse rather than serve an
        # un-attributed arXiv body. Non-arXiv docs (tier None) are unconstrained:
        # their canonical_url is legitimately None and this branch is skipped.
        if ctx.tier is not None and canonical_url is None:
            raise LinkBackMissingError(
                f"LINK-BACK MISSING: serve gate cleared a full body for arXiv "
                f"document {document_id!r} (tier {ctx.tier.value}, license "
                f"{ctx.license_uri!r}) but no canonical_url could be derived — "
                f"its metadata carries no usable arxiv_id, so the served body "
                f"would ship with NO attribution back to the canonical "
                f"arxiv.org/abs page. arXiv's terms require link-back for any "
                f"served body; refusing to emit an un-attributed arXiv body "
                f"(deny-by-default, master-spec §9.0)."
            )
    # arXiv → ads gate on the tier (T1 only); non-arXiv → preserve today's
    # "ad rail on any servable book" behaviour. Single source of truth: ads_allowed.
    ad_eligible = ads_allowed(ctx.tier) if ctx.tier is not None else result.servable
    return dataclasses.replace(
        result,
        tier=ctx.tier.value if ctx.tier is not None else None,
        ad_eligible=ad_eligible,
        canonical_url=canonical_url,
        license=ctx.license_uri,
    )


__all__ = [
    "guard_candidate_full_text",
    "guard_document_candidate_full_text",
    "serve_full_text_guarded",
    "LinkBackMissingError",
]
