"""Uniform provenance reference validation."""

from __future__ import annotations

import pytest

from substrate.provenance import InvalidReference, validate_ref, validate_refs


def test_validate_ref_accepts_only_canonical_refs() -> None:
    assert validate_ref(" chunk-1 ", {"chunk-1", "chunk-2"}) == "chunk-1"
    assert validate_ref("chunk-fake", {"chunk-1", "chunk-2"}) is None
    assert validate_ref("", {"chunk-1"}) is None
    assert validate_ref(None, {"chunk-1"}) is None


def test_validate_refs_drops_invalid_and_deduplicates_in_order() -> None:
    result = validate_refs(
        ["chunk-1", "chunk-fake", " chunk-2 ", "chunk-1"],
        {"chunk-1", "chunk-2"},
    )
    assert result.valid == ("chunk-1", "chunk-2")
    assert result.invalid == ("chunk-fake",)


def test_validate_refs_can_raise_on_fabricated_ref() -> None:
    with pytest.raises(InvalidReference, match="canonical set"):
        validate_refs(["chunk-1", "chunk-fake"], {"chunk-1"}, on_invalid="raise")
