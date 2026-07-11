"""Contract and composition proofs for the two-vendor web layer."""

from decimal import Decimal

import pytest

from acquisition.web_layer.cost import estimate_cost


def test_cost_examples_are_hand_computed_to_the_cent() -> None:
    # 2 Exa searches × $0.007 = $0.014, which rounds to $0.01 to the cent.
    exa = estimate_cost("exa", "search", 2)
    assert exa.usd_estimate == Decimal("0.014")
    assert exa.usd_estimate.quantize(Decimal("0.01")) == Decimal("0.01")

    # 3 Jina URL reads × $0.00 = $0.00 exactly.
    jina = estimate_cost("jina", "extract", 3)
    assert jina.usd_estimate == Decimal("0.00")
    assert jina.usd_estimate.quantize(Decimal("0.01")) == Decimal("0.00")


def test_cost_rejects_negative_units_and_unknown_pairs() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        estimate_cost("exa", "search", -1)
    with pytest.raises(ValueError, match="unsupported vendor operation"):
        estimate_cost("jina", "search", 1)
