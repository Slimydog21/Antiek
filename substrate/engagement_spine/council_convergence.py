"""Explicit, replayable convergence choices for completed live councils."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from .authority import owner_qualified_id
from .collective import collective_research_html, merge_spawns_collective
from .collective_council import (
    COUNCIL_PLAN_VERSION,
    council_result_sha256,
    get_council_plan,
)
from .merge import merge_product_payload
from .store import AuthorizedEngagementStore
from .twin_promote import twin_promote_context_payload

ConvergenceMode = Literal["offline_collective", "draft_combined", "into_parent"]


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CouncilConvergenceDecision:
    action_id: str
    plan_id: str
    result_id: str
    expected_result_sha256: str
    mode: ConvergenceMode
    parent_asset_id: str | None
    promotion_note_ids: tuple[str, ...]
    state: Literal["applying", "complete"]
    merge_output: dict[str, Any] | None
    promotion_output: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": COUNCIL_PLAN_VERSION,
            **self.__dict__,
            "promotion_note_ids": list(self.promotion_note_ids),
        }


def _load_complete_result(
    result_id: str, *, store: AuthorizedEngagementStore
) -> dict[str, Any]:
    row = store.get_document(result_id)
    if row is None or row.get("kind") != "council_result":
        raise KeyError("council result not found")
    if row.get("state") != "complete" or not str(row.get("html") or "").strip():
        raise ValueError("only a complete HTML council result can converge")
    return row


def apply_council_convergence(
    *,
    store: AuthorizedEngagementStore,
    plan_id: str,
    result_id: str,
    expected_result_sha256: str,
    mode: ConvergenceMode,
    parent_asset_id: str | None = None,
    promotion_note_ids: tuple[str, ...] | list[str] = (),
    promote_insight_fn: Any = None,
    promote_question_fn: Any = None,
) -> CouncilConvergenceDecision:
    """Apply one explicit, hash-bound convergence decision idempotently.

    The default ``offline_collective`` path writes no source document and no
    graph node. Merge and promotion effects occur only when named in this
    request and are recorded in the durable action receipt.
    """

    if not isinstance(store, AuthorizedEngagementStore):
        raise TypeError("council convergence requires an authorized store")
    if store.authority.local_operator_compatibility:
        raise PermissionError("council convergence requires an authenticated account")
    if mode not in {"offline_collective", "draft_combined", "into_parent"}:
        raise ValueError("invalid council convergence mode")
    result = _load_complete_result(result_id, store=store)
    actual_result_sha = council_result_sha256(result)
    if expected_result_sha256 != actual_result_sha:
        raise ValueError("council result changed after operator review")
    plan = get_council_plan(plan_id, store=store)
    if plan is None or plan.state != "complete" or result.get("plan_id") != plan.plan_id:
        raise ValueError("council plan/result binding is invalid")
    note_ids = tuple(dict.fromkeys(str(note).strip() for note in promotion_note_ids))
    if any(not note for note in note_ids):
        raise ValueError("promotion note IDs must be nonempty")
    parents = {member.parent_asset_id for member in plan.members}
    if mode != "offline_collective" and (
        len(parents) != 1 or not parent_asset_id or parent_asset_id not in parents
    ):
        raise ValueError("document merge requires one exact shared parent asset")
    if note_ids:
        if not parent_asset_id or parent_asset_id not in parents:
            raise ValueError("explicit twin promotion requires an exact member parent asset")
        available_notes = {
            str(note.get("note_id"))
            for note in store.list_twins(parent_asset_id)
            if isinstance(note, dict) and note.get("note_id")
        }
        if not set(note_ids).issubset(available_notes):
            raise ValueError("promotion contains an unavailable twin note")
    action_identity = {
        "plan_id": plan.plan_id,
        "result_id": result_id,
        "expected_result_sha256": expected_result_sha256,
        "mode": mode,
        "parent_asset_id": parent_asset_id,
        "promotion_note_ids": list(note_ids),
    }
    action_id = owner_qualified_id(
        store.authority, "ccaction", _sha(action_identity)
    )
    with store.lock_document(action_id):
        existing = store.get_document(action_id)
        if existing is not None:
            if existing.get("decision_sha256") != _sha(action_identity):
                raise RuntimeError("council convergence action identity collision")
            if existing.get("state") == "complete":
                return _decision_from_row(existing)
        applying = CouncilConvergenceDecision(
            action_id=action_id,
            plan_id=plan.plan_id,
            result_id=result_id,
            expected_result_sha256=expected_result_sha256,
            mode=mode,
            parent_asset_id=parent_asset_id,
            promotion_note_ids=note_ids,
            state="applying",
            merge_output=None,
            promotion_output=None,
        )
        store.put_document(
            action_id,
            {
                "document_id": action_id,
                "kind": "council_convergence",
                "decision_sha256": _sha(action_identity),
                **applying.to_dict(),
            },
        )

    spawn_ids = [member.spawn_id for member in plan.members]
    merge_output: dict[str, Any]
    if mode == "offline_collective":
        unit = merge_spawns_collective(
            spawn_ids, store=store, include_twin_promote=False
        )
        merge_output = {
            **unit.to_dict(),
            "prompt_block": unit.prompt_block(),
            "html": collective_research_html(unit),
            "source_mutated": False,
        }
    else:
        assert parent_asset_id is not None
        merge_output = merge_product_payload(
            parent_asset_id,
            spawn_ids,
            store=store,
            mode=mode,
            include_html=True,
        )

    promotion_output = None
    if note_ids:
        assert parent_asset_id is not None
        promotion_output = twin_promote_context_payload(
            parent_asset_id,
            store=store,
            note_ids=list(note_ids),
            include_html=True,
            promote_insight_fn=promote_insight_fn,
            promote_question_fn=promote_question_fn,
        )

    complete = CouncilConvergenceDecision(
        **{
            **applying.__dict__,
            "state": "complete",
            "merge_output": merge_output,
            "promotion_output": promotion_output,
        }
    )
    with store.lock_document(action_id):
        store.put_document(
            action_id,
            {
                "document_id": action_id,
                "kind": "council_convergence",
                "decision_sha256": _sha(action_identity),
                **complete.to_dict(),
            },
        )
    return complete


def _decision_from_row(row: dict[str, Any]) -> CouncilConvergenceDecision:
    return CouncilConvergenceDecision(
        action_id=str(row["action_id"]),
        plan_id=str(row["plan_id"]),
        result_id=str(row["result_id"]),
        expected_result_sha256=str(row["expected_result_sha256"]),
        mode=row["mode"],
        parent_asset_id=row.get("parent_asset_id"),
        promotion_note_ids=tuple(row.get("promotion_note_ids") or ()),
        state=row["state"],
        merge_output=row.get("merge_output"),
        promotion_output=row.get("promotion_output"),
    )


__all__ = [
    "CouncilConvergenceDecision",
    "ConvergenceMode",
    "apply_council_convergence",
]
