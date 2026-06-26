"""Tombstone partial (HPRJ SPR-02 / M6).

Renders the tombstone for a deleted/missing substrate ref. This is the
SAME tombstone the live notebook surface shows (master-spec §16.4;
``substrate/notebooks/__init__.py`` lines 20-21: "This claim was deleted
on YYYY-MM-DD; prior text was...").

The tombstone contract is load-bearing: a reader comparing the live
notebook surface and a rendered projection of the same doc-model must see
the same tombstone for the same deleted ref. That consistency is what
makes the projection a trustworthy artifact formfactor (the Thariq
thesis). If the projection invented a different tombstone, a reader would
not know whether the ref was deleted in the substrate or dropped by the
projector.

Two cases, both non-crashing, both non-silent:

  - DELETED ref (``tombstone.deleted_at`` is set): "This <kind> was
    deleted on <date>; prior text was <prior_text>." (prior_text omitted
    when absent.)
  - MISSING ref (``tombstone.deleted_at`` is None — resolver returned no
    record): "This <kind> reference (<ref_id>) could not be resolved."
    Distinct from deleted: the substrate has no deletion event, so we do
    not claim one. Honest about the failure mode.

The ref_id surfaces in the missing case so a reader can locate the
dangling reference; in the deleted case the deletion event is the
locator, so ref_id is omitted to match the live surface's wording.
"""

from __future__ import annotations

from ..context import Tombstone
from ..escape import escape_text


def render(tombstone: Tombstone) -> str:
    """Render a tombstone as an HTML fragment."""
    kind = escape_text(tombstone.kind)
    out = ['<div class="antiek-block antiek-tombstone">']
    if tombstone.deleted_at is not None:
        out.append(
            f'<span class="antiek-tombstone-label">'
            f"This {kind} was deleted on {escape_text(tombstone.deleted_at)}"
            f"</span>"
        )
        if tombstone.prior_text:
            out.append(
                f'; prior text was &ldquo;{escape_text(tombstone.prior_text)}&rdquo;.'
            )
        else:
            out.append(".")
    else:
        ref_id = escape_text(tombstone.ref_id)
        out.append(
            f'<span class="antiek-tombstone-label">'
            f"This {kind} reference ({ref_id}) could not be resolved."
            f"</span>"
        )
    out.append("</div>")
    return "".join(out)


__all__ = ["render"]
