from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.midnight_oil import (
    ADAPTER_KEYS,
    GateReceipt,
    MidnightOilRequest,
    is_known_adapter_key,
    preflight_midnight_oil,
    validate_receipt_chain,
)


def _receipt(
    index: int,
    *,
    adapter_key: str | None = None,
    prerequisites: tuple[str, ...] = (),
    run_id: str = "run-1",
) -> GateReceipt:
    return GateReceipt(
        receipt_id=f"receipt-{index}",
        run_id=run_id,
        adapter_key=adapter_key or ADAPTER_KEYS[index],
        status=f"blocked_{adapter_key or ADAPTER_KEYS[index]}_unimplemented",
        prerequisite_receipt_ids=prerequisites,
        blockers=(f"adapter {index} is not configured",),
        required_invariants=(f"prerequisite invariant {index}",),
    )


def test_adapter_key_catalog_is_exact_and_forward_key_check_is_explicit() -> None:
    assert len(ADAPTER_KEYS) == len(set(ADAPTER_KEYS)) == 7
    assert all(is_known_adapter_key(key) for key in ADAPTER_KEYS)
    assert not is_known_adapter_key("future_adapter")
    assert GateReceipt(
        receipt_id="future",
        run_id="run-1",
        adapter_key="future_adapter",
        status="blocked_future_adapter_unimplemented",
    ).adapter_key == "future_adapter"


@pytest.mark.parametrize(
    "side_effect",
    (
        "dispatch_performed",
        "budget_reserved",
        "provider_calls_made",
        "retrieval_performed",
        "graph_mutated",
        "final_artifact_created",
    ),
)
def test_gate_receipt_cannot_claim_side_effects(side_effect: str) -> None:
    with pytest.raises(ValidationError, match="cannot claim side effects"):
        GateReceipt.model_validate(
            {
                "receipt_id": "bad",
                "run_id": "run-1",
                "adapter_key": ADAPTER_KEYS[0],
                "status": f"blocked_{ADAPTER_KEYS[0]}_unimplemented",
                side_effect: True,
            }
        )


def test_chain_accepts_ordered_provenance() -> None:
    chain = [
        _receipt(0),
        _receipt(1, prerequisites=("receipt-0",)),
        _receipt(2, prerequisites=("receipt-0", "receipt-1")),
    ]
    validate_receipt_chain(chain)
    payload = chain[2].model_dump(mode="json")
    assert payload["blockers"] == ["adapter 2 is not configured"]
    assert payload["required_invariants"] == ["prerequisite invariant 2"]


def test_gate_status_is_bound_to_adapter_key() -> None:
    with pytest.raises(ValidationError, match="status must be"):
        GateReceipt(
            receipt_id="mismatch",
            run_id="run-1",
            adapter_key=ADAPTER_KEYS[0],
            status=f"blocked_{ADAPTER_KEYS[1]}_unimplemented",
        )


def test_chain_names_dangling_receipt() -> None:
    chain = [_receipt(0), _receipt(1, prerequisites=("missing",))]
    with pytest.raises(ValueError, match="receipt-1.*dangling.*missing"):
        validate_receipt_chain(chain)


def test_chain_names_duplicate_adapter_owner() -> None:
    chain = [_receipt(0), _receipt(1, adapter_key=ADAPTER_KEYS[0])]
    with pytest.raises(ValueError, match="receipt-1.*duplicates adapter_key.*receipt-0"):
        validate_receipt_chain(chain)


def test_chain_names_mixed_run() -> None:
    chain = [_receipt(0), _receipt(1, run_id="run-2")]
    with pytest.raises(ValueError, match="receipt-1.*mixed run_id"):
        validate_receipt_chain(chain)


def test_cent_residual_is_deliberately_owned_by_final_role() -> None:
    result = preflight_midnight_oil(
        MidnightOilRequest(
            goal="pin cent allocation",
            work_minutes=90,
            price_ceiling_usd=10.03,
            source_policy=["web"],
            operator_acknowledged_spend=True,
        )
    )
    assert [plan.budget_usd for plan in result.role_plans] == [1.5, 4.51, 2.0, 2.02]
    assert sum(round(plan.budget_usd * 100) for plan in result.role_plans) == 1003
