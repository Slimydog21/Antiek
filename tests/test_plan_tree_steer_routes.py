"""Tests for interfaces/research/api/plan_tree_steer_routes.py — gap A / P0 steer route.

The route consumes ``substrate/research_plan_tree.py`` (#2038) directly; these tests
verify the actuation seam: transition-law enforcement, status consistency (TOCTOU),
node presence, ack fail-closed, the honest outcome projection, and schema hardening.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.plan_tree_steer_routes import (
    register_plan_tree_steer_routes,
)


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    register_plan_tree_steer_routes(app)
    return TestClient(app)


def _tree() -> list[dict]:
    """A minimal steerable tree: root with one chasing leaf (one pending leaf)."""
    return [
        {
            "node_id": "root",
            "sub_question": "What is X?",
            "status": "chasing",
            "parent_node_id": None,
        },
        {
            "node_id": "leaf-1",
            "sub_question": "Why does X matter?",
            "status": "chasing",
            "parent_node_id": "root",
        },
    ]


def _steer(
    *,
    node_id: str = "leaf-1",
    from_status: str = "chasing",
    to_status: str = "done",
    operator_ack: bool = True,
    tree: list[dict] | None = None,
    investigation_id: str = "inv-1",
) -> dict:
    return {
        "investigation_id": investigation_id,
        "node_id": node_id,
        "from_status": from_status,
        "to_status": to_status,
        "operator_ack": operator_ack,
        "current_tree": tree if tree is not None else _tree(),
    }


# ---------------------------------------------------------------------------
# valid steer — advisory intent + honest outcome projection
# ---------------------------------------------------------------------------


def test_valid_steer_returns_advisory_intent(client: TestClient) -> None:
    res = client.post("/research/plan-tree/steer", json=_steer())
    assert res.status_code == 200
    body = res.json()
    assert body["transition_valid"] is True
    assert body["applied"] is False  # advisory — never executed
    assert body["authority"] == "advisory"
    assert body["node_id"] == "leaf-1"
    assert body["from_status"] == "chasing"
    assert body["to_status"] == "done"


def test_steer_to_done_projects_complete_when_last_leaf_done(client: TestClient) -> None:
    # leaf-1 is the only leaf; steering chasing -> done completes the plan.
    res = client.post("/research/plan-tree/steer", json=_steer(to_status="done"))
    assert res.status_code == 200
    assert res.json()["resulting_complete"] is True


def test_steer_that_leaves_pending_projects_incomplete(client: TestClient) -> None:
    # Two leaves; steering one to done still leaves the other pending.
    tree = _tree() + [
        {
            "node_id": "leaf-2",
            "sub_question": "How is X measured?",
            "status": "chasing",
            "parent_node_id": "root",
        }
    ]
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(node_id="leaf-1", to_status="done", tree=tree),
    )
    assert res.status_code == 200
    assert res.json()["resulting_complete"] is False


def test_planned_to_chasing_is_valid(client: TestClient) -> None:
    tree = [
        {"node_id": "r", "sub_question": "q", "status": "chasing", "parent_node_id": None},
        {"node_id": "n", "sub_question": "q2", "status": "planned", "parent_node_id": "r"},
    ]
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(node_id="n", from_status="planned", to_status="chasing", tree=tree),
    )
    assert res.status_code == 200
    assert res.json()["transition_valid"] is True


# ---------------------------------------------------------------------------
# the transition law is the single source of truth — rejected steers = 422
# ---------------------------------------------------------------------------


def test_done_to_planned_rejected_erases_work(client: TestClient) -> None:
    tree = [
        {"node_id": "r", "sub_question": "q", "status": "done", "parent_node_id": None},
        {"node_id": "n", "sub_question": "q2", "status": "done", "parent_node_id": "r"},
    ]
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(node_id="n", from_status="done", to_status="planned", tree=tree),
    )
    assert res.status_code == 422
    assert "incoherent steer" in res.json()["detail"]


def test_deprioritized_to_done_rejected_fakes_completion(client: TestClient) -> None:
    tree = [
        {"node_id": "r", "sub_question": "q", "status": "chasing", "parent_node_id": None},
        {
            "node_id": "n",
            "sub_question": "q2",
            "status": "deprioritized",
            "parent_node_id": "r",
        },
    ]
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(node_id="n", from_status="deprioritized", to_status="done", tree=tree),
    )
    assert res.status_code == 422


def test_chasing_to_planned_rejected(client: TestClient) -> None:
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(from_status="chasing", to_status="planned"),
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# consistency (TOCTOU) — from_status must match the node's actual status
# ---------------------------------------------------------------------------


def test_from_status_mismatch_is_409(client: TestClient) -> None:
    # node is actually chasing; caller claims it is planned (stale view).
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(from_status="planned", to_status="chasing"),
    )
    assert res.status_code == 409
    assert "mismatch" in res.json()["detail"]


# ---------------------------------------------------------------------------
# node presence + ack fail-closed
# ---------------------------------------------------------------------------


def test_missing_node_is_404(client: TestClient) -> None:
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(node_id="does-not-exist"),
    )
    assert res.status_code == 404


def test_operator_ack_false_is_400_fail_closed(client: TestClient) -> None:
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(operator_ack=False),
    )
    assert res.status_code == 400
    assert "operator_ack" in res.json()["detail"]


# ---------------------------------------------------------------------------
# schema hardening — extra forbidden, strict bool
# ---------------------------------------------------------------------------


def test_extra_fields_rejected(client: TestClient) -> None:
    payload = _steer()
    payload["rogue_field"] = "inject"  # type: ignore[typeddict-unknown-key]
    res = client.post("/research/plan-tree/steer", json=payload)
    assert res.status_code == 422


def test_operator_ack_string_not_coerced(client: TestClient) -> None:
    payload = _steer()
    payload["operator_ack"] = "true"  # type: ignore[typeddict-item]
    res = client.post("/research/plan-tree/steer", json=payload)
    assert res.status_code == 422  # strict bool rejects string


def test_empty_tree_rejected(client: TestClient) -> None:
    payload = _steer(tree=[])
    res = client.post("/research/plan-tree/steer", json=payload)
    assert res.status_code == 422  # min_length=1


# ---------------------------------------------------------------------------
# deprioritized leaf excluded from the outcome projection (honesty)
# ---------------------------------------------------------------------------


def test_deprioritize_last_leaf_projects_complete(client: TestClient) -> None:
    # leaf-1 is the only leaf; steering it chasing -> deprioritized excludes it
    # from completion, so the plan is complete (nothing pending, nothing forced-done).
    res = client.post(
        "/research/plan-tree/steer",
        json=_steer(to_status="deprioritized"),
    )
    assert res.status_code == 200
    assert res.json()["resulting_complete"] is True
