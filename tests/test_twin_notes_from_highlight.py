"""Tests for highlight → twin seed pure module."""

from __future__ import annotations

import pytest

from substrate.twin_notes.from_highlight import (
    HighlightTwinError,
    build_highlight_twin_seed,
)


def test_valid_seed_with_operator_insights() -> None:
    seed = build_highlight_twin_seed(
        parent_asset_id="asset-1",
        highlight="Transformers scale with compute.",
        insights=["scaling laws matter"],
        questions=["how far?"],
    )
    d = seed.to_dict()
    assert d["llm_filled"] is False
    assert d["authority"] == "highlight_seed_only"
    assert d["insights"] == ["scaling laws matter"]
    kwargs = seed.record_kwargs()
    assert kwargs["parent_asset_id"] == "asset-1"
    assert "highlight" not in kwargs  # store record does not take highlight body


def test_gated_fails_closed() -> None:
    with pytest.raises(HighlightTwinError, match="gated"):
        build_highlight_twin_seed(
            parent_asset_id="a",
            highlight="secret",
            gated=True,
        )


def test_empty_highlight_rejected() -> None:
    with pytest.raises(HighlightTwinError, match="highlight"):
        build_highlight_twin_seed(parent_asset_id="a", highlight="   ")


def test_does_not_invent_insights_from_highlight() -> None:
    seed = build_highlight_twin_seed(
        parent_asset_id="a",
        highlight="Important claim about X.",
    )
    assert seed.insights == ()
    assert seed.questions == ()
    assert any("no insights" in n for n in seed.notes)


def test_gated_must_be_bool() -> None:
    with pytest.raises(HighlightTwinError, match="gated"):
        build_highlight_twin_seed(
            parent_asset_id="a",
            highlight="x",
            gated="yes",  # type: ignore[arg-type]
        )
