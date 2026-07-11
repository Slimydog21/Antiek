"""Hermetic tests for pure recursive twin bind."""

from __future__ import annotations

import pytest

from substrate.recursive_twin_bind import (
    RecursiveTwinBindError,
    evaluate_recursive_twin_bind,
)


def test_operator_empty_scaffold() -> None:
    d = evaluate_recursive_twin_bind(
        parent_asset_id="asset-1",
        source="operator",
        llm_filled=False,
        gated=False,
    )
    assert d.bind_allowed is True
    assert d.twin_created is False
    assert d.to_dict()["twin_created"] is False
    assert d.insights == ()


def test_operator_lists() -> None:
    d = evaluate_recursive_twin_bind(
        parent_asset_id="asset-1",
        source="operator",
        llm_filled=False,
        gated=False,
        insights=["claim X"],
        questions=["why?"],
    )
    assert d.bind_allowed is True
    assert d.insights == ("claim X",)
    assert d.questions == ("why?",)


def test_gated_blocks() -> None:
    d = evaluate_recursive_twin_bind(
        parent_asset_id="asset-1",
        source="operator",
        llm_filled=False,
        gated=True,
        insights=["drop"],
    )
    assert d.bind_allowed is False
    assert d.insights == ()
    assert d.twin_created is False


def test_strict_bools() -> None:
    with pytest.raises(RecursiveTwinBindError, match="gated"):
        evaluate_recursive_twin_bind(
            parent_asset_id="a",
            source="operator",
            llm_filled=False,
            gated="false",  # type: ignore[arg-type]
        )
    with pytest.raises(RecursiveTwinBindError, match="llm_filled"):
        evaluate_recursive_twin_bind(
            parent_asset_id="a",
            source="operator",
            llm_filled="false",  # type: ignore[arg-type]
            gated=False,
        )


def test_llm_note_taker_rules() -> None:
    with pytest.raises(RecursiveTwinBindError, match="llm_filled"):
        evaluate_recursive_twin_bind(
            parent_asset_id="a",
            source="llm_note_taker",
            llm_filled=False,
            gated=False,
            insights=["x"],
        )
    with pytest.raises(RecursiveTwinBindError, match="non-empty"):
        evaluate_recursive_twin_bind(
            parent_asset_id="a",
            source="llm_note_taker",
            llm_filled=True,
            gated=False,
        )
    d = evaluate_recursive_twin_bind(
        parent_asset_id="a",
        source="llm_note_taker",
        llm_filled=True,
        gated=False,
        questions=["why?"],
    )
    assert d.bind_allowed is True
    assert d.llm_filled is True


def test_unknown_denies() -> None:
    d = evaluate_recursive_twin_bind(
        parent_asset_id="a",
        source="unknown",
        llm_filled=False,
        gated=False,
    )
    assert d.bind_allowed is False


def test_unknown_plus_llm_filled_throws() -> None:
    with pytest.raises(RecursiveTwinBindError, match="llm_note_taker"):
        evaluate_recursive_twin_bind(
            parent_asset_id="a",
            source="unknown",
            llm_filled=True,
            gated=False,
            insights=["should not mask"],
        )
