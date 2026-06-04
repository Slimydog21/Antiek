"""Collision #1 guard — ReaderSurfaceContract single owner (seam #1).

────────────────────────────────────────────────────────────────────────────
SUPERSEDED (in part) by antiek-reader SPR-01. DO NOT DELETE — antiek-reader
SPR-09 deletes this file once the REAL conformance test (which asserts every
door routes to the one ``<Reader>`` and no second renderer is importable) is
green. See ``substrate/contracts/__tests__/test_reader_conformance.py`` for the
pinned SPR-09 assertions and ``reading_surface.py`` for the ownership transfer.

Two things changed under SPR-01:
  * ``reading_surface.PROVISIONAL`` flipped to ``False`` and ``PINNED_BY`` moved
    off the never-built "DRW SPR-10" to "antiek-reader SPR-01". So the old
    ``test_contract_is_provisional_and_drw_owned`` below is now intentionally
    INVERTED and is marked ``xfail`` (it documents the prior state; it is not a
    live gate).
  * The contract method signatures are now concrete (``Region`` /
    ``RenderedRegion`` / ``AnchoredNote``), not ``Any``. The structural
    composition tests below STILL pass — an ``Any``-typed implementation
    remains assignable to the runtime_checkable Protocol — so they are kept
    live as the "compose, don't fork" structural guard until SPR-09's real
    conformance test replaces them.

Named invariant a maintainer greps: "Read composes the reader contract, never
forks" = this test file (and, going forward, the SPR-09 conformance harness).

Rigor #3: a fork that drops an extension point FAILS the structural check.
"""

from __future__ import annotations

from typing import Any

import pytest

from substrate.contracts.reading_surface import (
    PINNED_BY,
    PROVISIONAL,
    ReaderSurfaceContract,
)


@pytest.mark.xfail(
    reason="SUPERSEDED by antiek-reader SPR-01: PROVISIONAL flipped to False and "
    "PINNED_BY moved off the never-built DRW SPR-10 to 'antiek-reader SPR-01'. "
    "This test documents the prior state; SPR-09 deletes it.",
    strict=True,
)
def test_contract_is_provisional_and_drw_owned():
    """The ownership flag the conformance harness reads. NOW INVERTED — SPR-01
    pinned the seam, so this xfails by design (kept as a superseded record)."""
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
