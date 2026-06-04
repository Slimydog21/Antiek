"""Reading-surface contract — the seam-#1 resolution. **PINNED.**

Owned by **antiek-reader SPR-01** (The Unified Reader). This is the one-owner
seam every reading surface composes against: render a region, anchor a note,
locate a node in document space. It commits exactly one invariant —

    *there is exactly one reading surface and Read/Write compose against it
    (they do not fork)*

— and SPR-01 makes that invariant enforceable by replacing the ``Any``-typed
provisional Protocol with concrete types tied to ``document_model``.

────────────────────────────────────────────────────────────────────────────
OWNERSHIP TRANSFER — DRW SPR-10 → antiek-reader SPR-01 (rigor #5; a governance
act, logged here so a future maintainer finds the answer in the file).

This contract was previously ``PINNED_BY = "DRW SPR-10"`` and marked
``PROVISIONAL = True``, waiting on a "shared reading surface" DRW sprint. That
sprint was **never built** — verified on 2026-06-04 against the tree at
origin/main@80cc3a4:

* ``substrate/contracts/drw_sprint_lock.py`` carries DRW sprint 10
  (``reading-surface``) with ``status="provisional"`` — the DRW deliverable was
  never built, so it stays provisional as a DRW sprint; the lock's inline
  comment now records that ownership of ``ReaderSurfaceContract`` moved here
  (the lock never moved it to a "live"/"implemented" DRW status).
* No ``reader_surface`` / ``ReaderSurface`` *implementation* module exists under
  ``substrate/`` or ``runtime/`` — only this contract file. (A tree search for
  ``*reader*surface*`` / ``*reading*surface*`` returns this file alone.)

The operator's antiek-reader spec chose the full structured document model and
the one ``<Reader>``; eight sprints are blocked on a pinned seam. So ownership
moves to antiek-reader SPR-01, which DOES pin the shapes (``Region`` /
``RenderedRegion`` / ``AnchoredNote`` over ``document_model``). The
"exactly one reading surface … they do not fork" invariant is now enforced by
**SPR-09's conformance harness** (which asserts every door routes to the one
``<Reader>`` and no second renderer is importable) rather than left aspirational.

WHAT WOULD REVERSE THIS: if a real arXiv-extraction round-trip in SPR-02 proved
the ``document_model`` shape cannot carry a region a renderer needs (e.g. a
bbox-anchored region pdf.js requires that has no char range), ``Region`` would
gain an optional locator field — an additive change, not a return to
``PROVISIONAL``. Ownership does not move back to DRW SPR-10 (it was never built).

────────────────────────────────────────────────────────────────────────────
The data types here (``Region`` / ``RenderedRegion`` / ``AnchoredNote``) are
Pydantic models tied to ``document_model`` and so are part of the codegen
surface. The contract itself is a ``Protocol`` (a behavioral shape) and is
EXCLUDED from TS codegen, exactly as the contracts package excludes behavioral
Protocols. ``render_region`` / ``anchor_note`` / ``locate_node`` are the
committed composition seam (Read specializes render; the living-note surface
anchors; Write SPR-07 trace-to-source locates).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .document_model import Document

# Sentinel a downstream consumer (and the SPR-09 conformance harness) reads to
# know this contract's shape IS load-bearing now. Flipped from True by SPR-01.
PROVISIONAL: bool = False
# Ownership moved off the never-built "DRW SPR-10" to the spec that pins it.
PINNED_BY: str = "antiek-reader SPR-01"


# ───────────────────────────────────────────────────────────────────────────
# The concrete region / rendered-region / anchored-note types.
#
# ``Region`` is a span in DOCUMENT space — the same coordinate system the
# document model and the existing ``DocumentRegionSelectedPayload`` use
# (``char_start`` / ``char_end``). ``block_id`` names the block; the char range
# is OPTIONAL because a whole-block region (or a not-yet-extracted PDF region)
# has no char offsets — the same shape the event payload already models.
# ───────────────────────────────────────────────────────────────────────────


class Region(BaseModel):
    """A span in document space: a ``block_id`` within ``document_id``, with an
    OPTIONAL ``char_start``/``char_end`` range when the selection is sub-block.

    Reuses the ``char_start`` / ``char_end`` vocabulary of
    ``substrate.schemas.events.DocumentRegionSelectedPayload`` rather than
    coining ``offset`` / ``span``. A whole-block region omits the char range; a
    sub-block highlight carries it (with ``char_end >= char_start``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    block_id: str
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _ordered_range(self) -> Region:
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError(
                f"Region char range is reversed: char_end ({self.char_end}) < "
                f"char_start ({self.char_start})."
            )
        # A half-open range (only one bound) is meaningless: a sub-block region
        # needs both ends or neither (neither ⇒ whole-block).
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError(
                "Region char range must specify BOTH char_start and char_end "
                "(a sub-block span) or NEITHER (a whole-block region)."
            )
        return self


class RenderedRegion(BaseModel):
    """The result of rendering a region: the ``Region`` echoed back plus the
    full typed-block ``Document`` the surface renders for it. A surface returns
    the typed ``Document`` (not an HTML string) so Read/Write compose over the
    SAME typed model the one Reader renders — there is no second, stringly-typed
    render path to fork into."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    region: Region
    document: Document


class AnchoredNote(BaseModel):
    """A note (an insight/question graph node) anchored to a region. Carries the
    ``node_id`` and the ``Region`` it is anchored to, so the living-note surface
    can re-locate the note when the document re-renders. ``node_id`` is the
    content-addressed graph node id (the same identity ``InsightNodeContract`` /
    ``QuestionNodeContract`` pin)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    region: Region


@runtime_checkable
class ReaderSurfaceContract(Protocol):
    """The extension points the one reading surface exposes. The method names
    are the committed composition seam; the parameter/return types are now
    concrete (``Region`` / ``RenderedRegion`` / ``AnchoredNote`` over
    ``document_model``), no longer ``Any``.

    * ``render_region`` — render a document region (Read specializes this).
    * ``anchor_note`` — anchor an insight/question note to a region (the
      living-note surface).
    * ``locate_node`` — resolve a graph node id to its position in document
      space (Write SPR-07 trace-to-source composes against this).

    INVARIANT (enforced, not aspirational): there is exactly one reading surface
    and Read/Write compose against it (they do not fork). SPR-09's conformance
    harness asserts this — every door routes to the one ``<Reader>`` and no
    second document renderer is importable in the production bundle.
    """

    def render_region(self, document_id: str, region: Region) -> RenderedRegion: ...

    def anchor_note(self, node_id: str, region: Region) -> AnchoredNote: ...

    def locate_node(self, node_id: str) -> Region: ...
