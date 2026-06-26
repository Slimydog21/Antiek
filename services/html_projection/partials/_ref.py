"""Shared ref-resolution helper for ref-bearing partials (HPRJ SPR-02 / M6).

Centralises the M6 tombstone contract so every ref-bearing partial applies
it identically. The contract (from ``context.py``):

  - A block with a ``ref_id`` AND a resolver → resolver returns
    ``ResolvedRef`` (render payload) or ``Tombstone`` (render tombstone).
  - A block with a ``ref_id`` but NO resolver → render the MISSING
    tombstone (``deleted_at=None``). Without a resolver, refs cannot be
    verified live, so the surface says so rather than inventing content.
  - A block with NO ``ref_id`` → not a ref; the partial renders inline
    content (the caller's responsibility).

``resolve_or_tombstone`` returns ``(ResolvedRef | None, tombstone_html)``.
If a tombstone was rendered, ``tombstone_html`` is non-empty and
``ResolvedRef`` is None (the caller returns the tombstone immediately).
If the ref resolved, ``ResolvedRef`` is set and ``tombstone_html`` is "".
If there is no ref_id, both are None/"" (caller renders inline).
"""

from __future__ import annotations

from typing import Any, Optional

from ..context import RenderContext, ResolvedRef, Tombstone
from ..escape import escape_text
from . import tombstone as tombstone_partial


def kind_label(block_type: str) -> str:
    """Human label for a block type's referenced object (mirrors
    ``context._kind_label``)."""
    return {
        "claim_card": "claim",
        "region_embed": "region",
        "note": "note",
        "question_card": "question",
        "cross_doc_link": "document",
        "chat_exchange": "exchange",
        "master_md_section": "synthesis",
        "image": "image",
    }.get(block_type, block_type)


def resolve_or_tombstone(
    ref_id: str,
    block_type: str,
    ctx: RenderContext,
) -> tuple[Optional[ResolvedRef], str]:
    """Resolve a ref or render its tombstone.

    Returns ``(resolved, tombstone_html)``. Exactly one of the two is
    meaningful:
      - ref resolved → ``(ResolvedRef, "")`` — caller renders payload.
      - ref missing/deleted → ``(None, "<tombstone html>")`` — caller
        returns the tombstone immediately.
      - no ref_id (``ref_id`` empty) → ``(None, "")`` — caller renders
        inline content (the block isn't a ref).
    """
    if not ref_id:
        return None, ""
    if ctx.resolver is None:
        # No resolver attached → missing tombstone (honest: cannot verify
        # live, so we don't invent content).
        tomb = Tombstone(
            kind=kind_label(block_type),
            deleted_at=None,
            prior_text=None,
            ref_id=ref_id,
        )
        return None, tombstone_partial.render(tomb)
    resolved = ctx.resolver(ref_id, block_type)
    if isinstance(resolved, Tombstone):
        return None, tombstone_partial.render(resolved)
    assert isinstance(resolved, ResolvedRef)
    return resolved, ""


__all__ = ["kind_label", "resolve_or_tombstone"]
