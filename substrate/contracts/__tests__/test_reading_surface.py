"""Tests for the concretized reading-surface contract (Reader SPR-01 M2).

Proves the seam is de-provisionalized for real: no ``Any`` in the method
signatures, the data types are concrete and tied to ``document_model``, the
ownership flag moved off the never-built DRW SPR-10, and the runtime_checkable
Protocol still recognizes a composing implementation (the "compose, don't fork"
shape) while rejecting a fork that drops an extension point.
"""

from __future__ import annotations

import inspect
import typing

import pytest

from substrate.contracts.document_model import Document
from substrate.contracts.reading_surface import (
    PINNED_BY,
    PROVISIONAL,
    AnchoredNote,
    ReaderSurfaceContract,
    Region,
    RenderedRegion,
)


# ───────────────────────────────────────────────────────────────────────────
# De-provisionalization gate.
# ───────────────────────────────────────────────────────────────────────────


def test_seam_is_pinned_not_provisional():
    assert PROVISIONAL is False
    assert PINNED_BY == "antiek-reader SPR-01"


def test_no_Any_in_method_signatures():
    """The whole point of M2: the signatures are concrete, not ``Any``. We read
    the resolved type hints of each contract method and assert ``typing.Any``
    appears nowhere."""
    for name in ("render_region", "anchor_note", "locate_node"):
        method = getattr(ReaderSurfaceContract, name)
        hints = typing.get_type_hints(method)
        assert typing.Any not in hints.values(), (
            f"{name} still has an Any-typed parameter/return: {hints}"
        )


def test_signatures_are_the_concrete_types():
    """``render_region(document_id: str, region: Region) -> RenderedRegion``,
    ``anchor_note(node_id: str, region: Region) -> AnchoredNote``,
    ``locate_node(node_id: str) -> Region``."""
    rr = typing.get_type_hints(ReaderSurfaceContract.render_region)
    assert rr["region"] is Region and rr["return"] is RenderedRegion and rr["document_id"] is str

    an = typing.get_type_hints(ReaderSurfaceContract.anchor_note)
    assert an["region"] is Region and an["return"] is AnchoredNote and an["node_id"] is str

    ln = typing.get_type_hints(ReaderSurfaceContract.locate_node)
    assert ln["return"] is Region and ln["node_id"] is str


def test_contract_remains_a_runtime_checkable_protocol():
    assert getattr(ReaderSurfaceContract, "_is_runtime_protocol", False) is True
    assert issubclass(ReaderSurfaceContract, typing.Protocol)  # type: ignore[arg-type]


# ───────────────────────────────────────────────────────────────────────────
# The concrete region/rendered/anchored types.
# ───────────────────────────────────────────────────────────────────────────


def test_region_whole_block_omits_char_range():
    r = Region(document_id="d", block_id="b")
    assert r.char_start is None and r.char_end is None


def test_region_sub_block_carries_ordered_range():
    r = Region(document_id="d", block_id="b", char_start=5, char_end=40)
    assert r.char_start == 5 and r.char_end == 40


def test_region_rejects_reversed_range():
    with pytest.raises(Exception):
        Region(document_id="d", block_id="b", char_start=40, char_end=5)


def test_region_rejects_half_open_range():
    with pytest.raises(Exception):
        Region(document_id="d", block_id="b", char_start=5)
    with pytest.raises(Exception):
        Region(document_id="d", block_id="b", char_end=5)


def test_region_reuses_char_offset_vocabulary():
    """``Region`` uses ``char_start`` / ``char_end`` — the SAME names the
    existing ``DocumentRegionSelectedPayload`` uses — not ``offset`` / ``span``."""
    fields = set(Region.model_fields)
    assert {"document_id", "block_id", "char_start", "char_end"} == fields


def test_rendered_region_carries_a_typed_document_slice():
    r = Region(document_id="d", block_id="b")
    rr = RenderedRegion(region=r, document=Document(id="d", title="t"))
    assert isinstance(rr.document, Document)
    assert rr.region is r


def test_anchored_note_binds_node_to_region():
    r = Region(document_id="d", block_id="b", char_start=0, char_end=3)
    note = AnchoredNote(node_id="insight-abc", region=r)
    assert note.node_id == "insight-abc" and note.region == r


# ───────────────────────────────────────────────────────────────────────────
# Compose-don't-fork structural guard (carried forward, now over concrete types).
# ───────────────────────────────────────────────────────────────────────────


def test_a_composing_reader_satisfies_the_contract():
    class OneReader:
        def render_region(self, document_id: str, region: Region) -> RenderedRegion:
            return RenderedRegion(region=region, document=Document(id=document_id, title=""))

        def anchor_note(self, node_id: str, region: Region) -> AnchoredNote:
            return AnchoredNote(node_id=node_id, region=region)

        def locate_node(self, node_id: str) -> Region:
            return Region(document_id="d", block_id="b")

    assert isinstance(OneReader(), ReaderSurfaceContract)


def test_a_fork_dropping_an_extension_point_fails():
    class ForkedSurface:
        def render_region(self, document_id: str, region: Region) -> RenderedRegion: ...

        def anchor_note(self, node_id: str, region: Region) -> AnchoredNote: ...

        # missing locate_node — a fork that cannot be traced into.

    assert not isinstance(ForkedSurface(), ReaderSurfaceContract)


def test_signatures_have_three_extension_points():
    sig_names = [
        n
        for n, m in inspect.getmembers(ReaderSurfaceContract, predicate=inspect.isfunction)
        if not n.startswith("_")
    ]
    assert set(sig_names) == {"render_region", "anchor_note", "locate_node"}
