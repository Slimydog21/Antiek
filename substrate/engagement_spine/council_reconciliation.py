"""Explicit operator reconciliation for quarantined council call holds."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from substrate.midnight_oil.budget_ledger import BudgetLedger

from .authority import owner_qualified_id
from .collective_council import (
    CouncilPlan,
    _now,
    _plan_from_row,
    council_result_sha256,
)
from .store import AuthorizedEngagementStore


def reconcile_council_hold(
    *,
    store: AuthorizedEngagementStore,
    ledger: BudgetLedger,
    plan_id: str,
    result_id: str,
    expected_result_sha256: str,
    role: str,
    hold_id: str,
    actual_cents: int,
) -> dict[str, Any]:
    """Resolve one exact unknown hold without redispatching any model call."""

    if not isinstance(store, AuthorizedEngagementStore):
        raise TypeError("council reconciliation requires an authorized store")
    if store.authority.local_operator_compatibility:
        raise PermissionError("council reconciliation requires authentication")
    if not role.strip() or not hold_id.strip():
        raise ValueError("role and hold_id are required")
    if not isinstance(actual_cents, int) or isinstance(actual_cents, bool) or actual_cents < 0:
        raise ValueError("actual_cents must be a non-negative integer")
    receipt_id = owner_qualified_id(
        store.authority,
        "ccreconcile",
        plan_id,
        result_id,
        role,
        hold_id,
        str(actual_cents),
    )
    with store.lock_document(receipt_id):
        existing_receipt = store.get_document(receipt_id)
        if existing_receipt is not None and existing_receipt.get("state") == "complete":
            return existing_receipt

        plan_row = store.get_document(plan_id)
        result = store.get_document(result_id)
        if plan_row is None or result is None or result.get("kind") != "council_result":
            raise KeyError("council plan or result not found")
        plan = _plan_from_row(plan_row)
        if plan.state != "unknown" or result.get("state") != "unknown":
            raise ValueError("only an unknown council result can be reconciled")
        if result.get("plan_id") != plan.plan_id:
            raise ValueError("council plan/result binding is invalid")
        if council_result_sha256(result) != expected_result_sha256:
            raise ValueError("council result changed after operator review")

        member_receipts = list(result.get("member_receipts") or [])
        synth_receipt = result.get("synthesizer_receipt")
        candidates = member_receipts + ([synth_receipt] if isinstance(synth_receipt, dict) else [])
        matched = [
            receipt
            for receipt in candidates
            if isinstance(receipt, dict)
            and receipt.get("role") == role
            and receipt.get("hold_id") == hold_id
            and receipt.get("state") == "unknown"
        ]
        if len(matched) != 1:
            raise ValueError("unknown council hold receipt does not match")

        call_receipt_id = owner_qualified_id(
            store.authority, "ccreceipt", plan.plan_id, role
        )
        provider_checkpoint = store.get_document(call_receipt_id)
        if provider_checkpoint is not None:
            if provider_checkpoint.get("kind") != "council_call_receipt":
                raise ValueError("provider checkpoint is invalid")
            if provider_checkpoint.get("actual_cents") != actual_cents:
                raise ValueError("actual cost differs from durable provider checkpoint")

        applying = {
            "document_id": receipt_id,
            "kind": "council_reconciliation",
            "plan_id": plan.plan_id,
            "result_id": result_id,
            "expected_result_sha256": expected_result_sha256,
            "role": role,
            "hold_id": hold_id,
            "actual_cents": actual_cents,
            "state": "applying",
            "created_at": _now(),
        }
        store.put_document(receipt_id, applying)

        balance = ledger.resolve_unknown(hold_id, actual_cents)
        target = matched[0]
        if provider_checkpoint is not None:
            target.update(
                {
                    "state": "complete",
                    "actual_cents": actual_cents,
                    "provider_receipt_id": provider_checkpoint.get("provider_receipt_id"),
                    "output_sha256": provider_checkpoint.get("output_sha256"),
                    "output_text": provider_checkpoint.get("output_text"),
                    "cited_spawn_ids": provider_checkpoint.get("cited_spawn_ids") or [],
                    "cited_source_ref_ids": provider_checkpoint.get("cited_source_ref_ids") or [],
                    "cited_twin_note_ids": provider_checkpoint.get("cited_twin_note_ids") or [],
                    "hold_id": None,
                    "error_type": None,
                }
            )
            provider_checkpoint["settlement_state"] = "reconciled"
            provider_checkpoint["reconciled_at"] = _now()
            store.put_document(call_receipt_id, provider_checkpoint)
        else:
            target.update(
                {
                    "state": "reconciled_without_output",
                    "actual_cents": actual_cents,
                    "hold_id": None,
                    "error_type": "OperatorReconciledUnknown",
                }
            )

        remaining_unknowns = [
            receipt
            for receipt in candidates
            if isinstance(receipt, dict) and receipt.get("state") == "unknown"
        ]
        terminal_state = "unknown" if remaining_unknowns else "failed"
        if not remaining_unknowns:
            balance = ledger.release(plan.plan_id)
        result.update(
            {
                "state": terminal_state,
                "member_receipts": member_receipts,
                "synthesizer_receipt": synth_receipt,
                "spent_cents": balance.spent_cents,
                "held_cents": balance.held_cents,
                "completed_at": _now(),
            }
        )
        store.put_document(result_id, result)
        terminal_plan = CouncilPlan(**{**plan.__dict__, "state": terminal_state})
        store.put_document(
            plan.plan_id,
            {
                "document_id": plan.plan_id,
                "kind": "council_plan",
                **terminal_plan.to_dict(),
            },
        )
        complete = {
            **applying,
            "state": "complete",
            "terminal_council_state": terminal_state,
            "balance": asdict(balance),
            "completed_at": _now(),
        }
        store.put_document(receipt_id, complete)
        persisted = store.get_document(receipt_id)
        assert persisted is not None
        return persisted


__all__ = ["reconcile_council_hold"]
