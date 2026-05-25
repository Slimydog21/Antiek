"""Reading-surface contract — the seam-#1 resolution. **PROVISIONAL.**

Owned by **DRW SPR-10** (the shared reading surface). As of this sprint
DRW SPR-10 is **not yet implemented** — there is no reading-surface module in
the tree (verified: no ``reader_surface``/``ReaderSurface`` under
``substrate/`` or ``runtime/``). So this contract is **PROVISIONAL**: it pins
the *extension points* Read SPR-03 (specialize-by-composition) and Write
SPR-07 (trace-into) compose against, marked so the SPR-08 conformance harness
treats it as not-yet-pinned.

This resolves **seam #1**: Read's own README waffled ("build the shared pieces
here and have DRW consume them"). One owner ends the ambiguity. DRW SPR-10 is
the canonical reader; Read and Write compose against this contract; neither
forks a second reading surface. If DRW SPR-10 slips, downstream builds against
this conformance-tested stub.

It is a ``Protocol`` (a behavioral shape — render a region, anchor a note,
locate a node in document space), not a Pydantic data model, so it is excluded
from TS codegen. The honest move is to keep it small and explicitly
provisional rather than invent a precise surface DRW has not yet designed
(rigor #1 — a confidently-wrong contract is worse than an honestly-incomplete
one, because three products build against it).

PROVISIONAL — pinned by: DRW SPR-10. What is unknown: the concrete region /
anchor / locator types. What is committed: that there is exactly one reading
surface and Read/Write compose against it (they do not fork).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# Sentinel a downstream consumer (and the SPR-08 harness) can read to know
# this contract's shape is not yet load-bearing.
PROVISIONAL: bool = True
PINNED_BY: str = "DRW SPR-10"


@runtime_checkable
class ReaderSurfaceContract(Protocol):
    """The extension points a reading surface exposes. **Provisional** — the
    parameter/return types are ``Any`` until DRW SPR-10 lands the real shapes;
    the method *names* are the committed composition seam.

    * ``render_region`` — render a document region (Read specializes this).
    * ``anchor_note`` — anchor an insight/question note to a region (the
      living-note surface).
    * ``locate_node`` — resolve a graph node id to its position in document
      space (Write SPR-07 trace-to-source composes against this).
    """

    def render_region(self, document_id: str, region: Any) -> Any: ...

    def anchor_note(self, node_id: str, region: Any) -> Any: ...

    def locate_node(self, node_id: str) -> Any: ...
