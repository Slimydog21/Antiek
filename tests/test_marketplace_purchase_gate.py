"""Red-proof tests for marketplace purchase gate."""

from __future__ import annotations

import pytest

from substrate.books.marketplace_purchase_gate import (
    PurchaseGateError,
    evaluate_purchase_gate,
)


def test_free_miss_allows_intent() -> None:
    d = evaluate_purchase_gate(
        title="Unknown Book",
        author="Anon",
        free_copy_preflight={"freely_available": False},
    )
    body = d.to_dict()
    assert body["purchase_intent_allowed"] is True
    assert body["purchase_executed"] is False
    assert body["path"] == "purchase_intent_after_free_miss"
    assert body["authority"] == "purchase_gate_advisory"


def test_free_hit_blocks_intent() -> None:
    d = evaluate_purchase_gate(
        title="Walden",
        free_copy_preflight={"freely_available": True, "source": "gutenberg"},
    )
    assert d.purchase_intent_allowed is False
    assert d.path == "use_free_copy"
    assert any("free copy available" in r for r in d.reasons)


def test_skip_requires_ack() -> None:
    with pytest.raises(PurchaseGateError, match="operator_skip_acknowledged"):
        evaluate_purchase_gate(
            title="X",
            skip_free_copy=True,
            operator_skip_acknowledged=False,
        )
    d = evaluate_purchase_gate(
        title="X",
        skip_free_copy=True,
        operator_skip_acknowledged=True,
    )
    assert d.purchase_intent_allowed is True
    assert d.path == "skip_free_copy"


def test_missing_preflight_without_skip() -> None:
    with pytest.raises(PurchaseGateError, match="free_copy_preflight"):
        evaluate_purchase_gate(title="X")


def test_invent_freely_available_rejected() -> None:
    with pytest.raises(PurchaseGateError, match="freely_available"):
        evaluate_purchase_gate(
            title="X",
            free_copy_preflight={"freely_available": "no"},
        )


def test_never_executes_purchase() -> None:
    d = evaluate_purchase_gate(
        title="X",
        free_copy_preflight={"freely_available": False},
    )
    assert d.to_dict()["purchase_executed"] is False
