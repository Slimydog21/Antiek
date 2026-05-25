"""Collision #1 guard — ReaderSurfaceContract single owner (seam #1).

DRW SPR-10 owns the one reading surface; Read SPR-03 specializes by
composition and Write SPR-07 traces into it via the same contract; neither
forks a second reader. DRW SPR-10 is unbuilt, so the contract is **provisional**
(``substrate.contracts.reading_surface.PROVISIONAL == True``) and Read/Write
compose against this conformance-tested stub until it lands.

Named invariant a maintainer greps: "Read composes the reader contract, never
forks" = this test file. The test proves:

* the contract exposes the three composition extension points
  (``render_region`` / ``anchor_note`` / ``locate_node``);
* a Read-style specialization and a Write-style tracer both *satisfy* the
  contract by composition (runtime_checkable Protocol), without subclassing —
  the "compose, don't fork" shape;
* the contract is flagged provisional + DRW-owned so SPR-08 treats it as
  not-yet-load-bearing.

Rigor #3: a fork that drops an extension point FAILS the structural check.
"""

from __future__ import annotations

from typing import Any

from substrate.contracts.reading_surface import (
    PINNED_BY,
    PROVISIONAL,
    ReaderSurfaceContract,
)


def test_contract_is_provisional_and_drw_owned():
    """The ownership flag SPR-08's harness reads: provisional, pinned by
    DRW SPR-10."""
    assert PROVISIONAL is True
    assert PINNED_BY == "DRW SPR-10"


def test_extension_points_present():
    """The three composition extension points are the committed seam."""
    for name in ("render_region", "anchor_note", "locate_node"):
        assert hasattr(ReaderSurfaceContract, name), name


def test_read_specialization_composes_against_contract():
    """Read SPR-03 specializes by composition — a class that *implements* the
    contract surface (not subclasses it) satisfies the runtime_checkable
    Protocol. This is the 'compose, don't fork' shape."""

    class ReadBookReader:
        """Stands in for Read SPR-03's book reader — composes the surface."""

        def __init__(self) -> None:
            self._surface: Any = None  # composes the DRW surface, does not BE it

        def render_region(self, document_id: str, region: Any) -> Any:
            return {"document_id": document_id, "region": region, "pdf": True}

        def anchor_note(self, node_id: str, region: Any) -> Any:
            return {"node_id": node_id, "region": region}

        def locate_node(self, node_id: str) -> Any:
            return {"node_id": node_id, "document_id": "doc-1"}

    assert isinstance(ReadBookReader(), ReaderSurfaceContract)


def test_write_tracer_composes_against_same_contract():
    """Write SPR-07 trace-to-source composes against the SAME contract
    (``locate_node`` resolves a node id to document space) — not a second
    surface."""

    class WriteTracer:
        def render_region(self, document_id: str, region: Any) -> Any:
            return None

        def anchor_note(self, node_id: str, region: Any) -> Any:
            return None

        def locate_node(self, node_id: str) -> Any:
            # trace-to-source: node → its position in document space
            return {"node_id": node_id, "document_id": "src-doc", "region_id": "r-9"}

    assert isinstance(WriteTracer(), ReaderSurfaceContract)


def test_a_fork_dropping_an_extension_point_fails():
    """Rigor #3 — a 'second reading surface' that drops an extension point does
    NOT satisfy the contract. The structural check is what stops a silent
    fork."""

    class ForkedSurface:
        # missing locate_node — a fork that can't be traced into
        def render_region(self, document_id: str, region: Any) -> Any:
            return None

        def anchor_note(self, node_id: str, region: Any) -> Any:
            return None

    assert not isinstance(ForkedSurface(), ReaderSurfaceContract)
