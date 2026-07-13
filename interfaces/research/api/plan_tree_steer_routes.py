"""Plan-tree steer route — validate an operator's mid-flight plan steer (gap A / P0).

The competitive spec (§3 P0) names the visible/steerable research-plan tree as the
one real trail where Antiek trailed the field, and specifies the steer route:

    Route: PATCH /investigations/{id}/plan/{node_id} (steer status) — advisory until
    operator ack; the cascade reads the updated plan on its next iteration.

``substrate/research_plan_tree.py`` (#2038) is the pure model — the transition law
(``validate_status_transition``) and the structural/outcome folds (``validate_plan_tree``).
THIS route is the actuation seam: it takes the operator's steer (the node to steer, the
caller's view of its current status, the desired status) plus the current plan tree, and
VALIDATES the steer is coherent before the cascade reads it. It never executes: the result
is an advisory intent (``applied=False``, ``authority="advisory"``); the cascade applies the
steer on its next iteration.

**Hard-to-vary properties (load-bearing):**

* **The transition law is the single source of truth.** This route consumes
  ``validate_status_transition`` directly — it never re-implements or vendors the table.
  A rejected transition (``done → planned`` erases work; ``deprioritized → done`` fakes
  completion) is REJECTED here (HTTP 422), never silently advisory. There is one steering
  law, shared with the substrate.
* **Status consistency (no TOCTOU).** The caller supplies ``from_status`` (its view of the
  node's current status); the route requires it to match the node's actual ``status`` in the
  supplied current tree. A mismatch → HTTP 409 (the caller is steering a node that moved
  under it — the same pin philosophy as the draft-promotion hash match in #1846).
* **The projected outcome is honest.** A valid steer returns the plan's resulting
  ``complete`` verdict AFTER the steer is applied (a copy of the tree with the node's status
  updated, re-validated). The operator sees "after this steer, the plan is complete" or
  "still N leaves pending" — the honest projection, not a guess. ``resulting_complete`` is
  ``None`` if the steered tree is not steerable (can't assess outcome over a broken structure).
* **Pure + advisory.** No dispatch, no spawn, no graph write, no persistence. The cascade
  reads the steered tree; this route validates + projects.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from substrate.research_plan_tree import (
    PlanNode,
    PlanTreeError,
    validate_plan_tree,
    validate_status_transition,
)

plan_tree_steer_router = APIRouter(
    prefix="/research/plan-tree",
    tags=["plan-tree-steer"],
)

PlanStatus = Literal["planned", "chasing", "done", "deprioritized", "branched"]


class PlanNodeBody(BaseModel):
    """One node in the caller's current view of the plan tree."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=256)
    sub_question: str = Field(min_length=1, max_length=4096)
    status: PlanStatus
    parent_node_id: str | None = None
    investigation_id: str | None = None


class SteerRequest(BaseModel):
    """An operator's mid-flight steer of one plan node."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(min_length=1, max_length=256)
    node_id: str = Field(min_length=1, max_length=256)
    from_status: PlanStatus
    to_status: PlanStatus
    operator_ack: bool = Field(strict=True)
    current_tree: list[PlanNodeBody] = Field(min_length=1)


class SteerIntent(BaseModel):
    """The advisory result of validating a steer. Never executed here."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    node_id: str
    from_status: PlanStatus
    to_status: PlanStatus
    transition_valid: bool
    applied: bool
    resulting_complete: bool | None
    authority: str
    notes: list[str]


def _to_plan_node(body: PlanNodeBody) -> PlanNode:
    return PlanNode(
        node_id=body.node_id,
        sub_question=body.sub_question,
        status=body.status,
        parent_node_id=body.parent_node_id,
        investigation_id=body.investigation_id,
    )


def _validate_steer(
    *,
    node_id: str,
    from_status: str,
    to_status: str,
    operator_ack: bool,
    current_nodes: list[PlanNode],
) -> SteerIntent:
    """Pure validation of one steer. Raises HTTPException on hard failures.

    A hard failure is one the caller must fix before retrying: a missing node
    (404), a stale from_status (409), or an incoherent transition rejected by
    the law (422). A valid steer returns the advisory intent + projected outcome.
    """
    target = next((n for n in current_nodes if n.node_id == node_id), None)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"node {node_id!r} not found in the current plan tree",
        )
    if not operator_ack:
        raise HTTPException(
            status_code=400,
            detail="operator_ack must be true to steer a plan node (fail closed)",
        )
    if target.status != from_status:
        raise HTTPException(
            status_code=409,
            detail=(
                f"from_status mismatch: caller supplied {from_status!r} but the node's "
                f"actual status is {target.status!r} — the plan moved; re-read and retry"
            ),
        )
    try:
        transition_valid = validate_status_transition(from_status, to_status)
    except PlanTreeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not transition_valid:
        raise HTTPException(
            status_code=422,
            detail=(
                f"incoherent steer: {from_status} -> {to_status} is not in the transition "
                "law (it would erase completed work or fake completion of never-run work)"
            ),
        )

    # Project the outcome: a copy of the tree with the node steered, re-validated.
    steered = [
        PlanNode(
            node_id=n.node_id,
            sub_question=n.sub_question,
            status=to_status if n.node_id == node_id else n.status,
            parent_node_id=n.parent_node_id,
            investigation_id=n.investigation_id,
        )
        for n in current_nodes
    ]
    report = validate_plan_tree(steered)
    resulting_complete = report.complete

    notes: list[str] = [
        f"transition {from_status} -> {to_status} coherent (validated against the one law)",
        "applied=false — advisory; the cascade reads the steered tree on its next iteration",
    ]
    if resulting_complete is True:
        notes.append("resulting_complete=true — every non-deprioritized leaf would be done")
    elif resulting_complete is False:
        pending = len(report.pending_leaf_ids)
        notes.append(
            f"resulting_complete=false — {pending} non-deprioritized leaf/leaves still pending"
        )
    else:
        notes.append("resulting_complete=null — steered tree not steerable; outcome unassessed")

    return SteerIntent(
        investigation_id="",  # filled by the route handler from the path/body
        node_id=node_id,
        from_status=from_status,  # type: ignore[arg-type]
        to_status=to_status,  # type: ignore[arg-type]
        transition_valid=True,
        applied=False,
        resulting_complete=resulting_complete,
        authority="advisory",
        notes=notes,
    )


@plan_tree_steer_router.post("/steer", response_model=SteerIntent)
def steer_plan_node(req: SteerRequest) -> SteerIntent:
    """Validate an operator's steer of one plan node. Advisory — never executes."""
    try:
        current_nodes = [_to_plan_node(n) for n in req.current_tree]
    except (PlanTreeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    intent = _validate_steer(
        node_id=req.node_id,
        from_status=req.from_status,
        to_status=req.to_status,
        operator_ack=req.operator_ack,
        current_nodes=current_nodes,
    )
    intent.investigation_id = req.investigation_id
    return intent


def register_plan_tree_steer_routes(app: FastAPI) -> None:
    app.include_router(plan_tree_steer_router)


__all__ = [
    "plan_tree_steer_router",
    "register_plan_tree_steer_routes",
    "SteerRequest",
    "SteerIntent",
]
