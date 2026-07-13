"""API tests for Midnight Oil create → recommend → approve."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from test_midnight_oil_consent_routes import _client  # noqa: E402

from substrate.engagement_spine import InMemoryEngagementStore  # noqa: E402
from substrate.midnight_oil.graph_projection import (  # noqa: E402
    GraphProjectionPending,
    GraphProjectionRefused,
)
from substrate.midnight_oil.job import (  # noqa: E402
    MidnightOilGraphEffectReceipt,
    _job_from_row,
    put_job_state,
)
from substrate.midnight_oil.job_store import OperationState  # noqa: E402


@pytest.fixture
def client(tmp_path):
    return _client(tmp_path)[0]


def test_create_consent_flow(client):
    headers = {"x-test-user": "alice"}
    r = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={
            "goals": ["Deep-research residual gaps in Antiek workstation."],
            "duration_minutes": 60,
            "model_id": "default",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommended_price_ceiling_usd"] > 0
    assert body["status"] == "awaiting_approval"
    assert body["view_format"] == "html"
    assert body["runnable"] is False
    assert body["acceptance_policy_version"] == 1
    assert body["acceptance_policy"] == {
        "policy_version": 1,
        "required_coverage": "insights_and_output_paragraphs",
        "exploratory_questions": "operational_only",
        "external_receipts": "local_canonical_chunk_required",
        "unsupported_output": "retain_operational_only",
        "legacy_rows": "legacy_unverified",
    }
    assert body["research_brief_state"] == "proposed"
    assert len(body["research_brief_hash"]) == 64
    assert body["approved_research_brief_hash"] is None
    assert body["research_result_state"] == "none"
    assert body["deposit_state"] == "pending"
    assert body["graph_projection_state"] == "pending"
    assert body["graph_projection_reason"] is None
    assert "html" in body
    job_id = body["job_id"]

    # The legacy float approval contract is gone.
    bad = client.post(
        "/midnight-oil/approve",
        headers=headers,
        json={
            "job_id": job_id,
            "ceiling_usd": body["recommended_price_ceiling_usd"] * 0.1,
        },
    )
    assert bad.status_code == 422

    missing_ack = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"use_recommended": True},
    )
    assert missing_ack.status_code == 400
    assert "acknowledgement is required" in missing_ack.text
    assert "token" not in missing_ack.text.lower()

    ok = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"use_recommended": True, "acceptance_policy_version": 1},
    )
    assert ok.status_code == 200
    approved = ok.json()
    assert approved["ceiling_cents"] > 0
    assert approved["acceptance_policy_version"] == 1
    assert approved["research_brief_state"] == "approved"
    assert approved["research_brief_hash"] == body["research_brief_hash"]
    assert approved["approved_research_brief_hash"] == body["research_brief_hash"]
    assert approved["graph_projection_state"] == "pending"
    assert approved["graph_projection_reason"] is None
    assert ok.headers["cache-control"] == "no-store"

    got = client.get(f"/midnight-oil/jobs/{job_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["runnable"] is False
    assert got.json()["view_format"] == "html"
    assert got.json()["research_brief_state"] == "approved"
    assert got.json()["research_brief_hash"] == body["research_brief_hash"]
    assert got.json()["approved_research_brief_hash"] == body["research_brief_hash"]


def test_force_below_api(client):
    headers = {"x-test-user": "alice"}
    r = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["g"], "duration_minutes": 30, "model_id": "default"},
    )
    job_id = r.json()["job_id"]
    r2 = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"ceiling_cents": 1, "force_below": True, "acceptance_policy_version": 1},
    )
    assert r2.status_code == 200
    assert r2.json()["ceiling_cents"] == 1


def test_job_status_exposes_only_safe_graph_projection_navigation(tmp_path):
    client, deps = _client(tmp_path)
    headers = {"x-test-user": "alice"}
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["g"], "duration_minutes": 30},
    ).json()
    raw = deps.jobs.get_job(created["job_id"])
    assert raw is not None
    node_id = "node-" + "1" * 16
    deliverable_id = "dlv-" + "2" * 16
    raw["graph_projection_state"] = "complete"
    raw["graph_effect_receipt"] = {
        "schema_version": 1,
        "owner_user_id": "alice",
        "deliverable_id": deliverable_id,
        "section_ids": ["sec-" + "3" * 16],
        "node_ids": [node_id],
        "edge_ids": ["edge-" + "4" * 16],
        "html_sha256": "5" * 64,
        "evidence_sha256": "6" * 64,
        "deep_links": [
            f"antiek://deliverable/{deliverable_id}",
            f"antiek://node/{node_id}",
        ],
    }
    deps.jobs.put_job(raw)

    response = client.get(f"/midnight-oil/jobs/{created['job_id']}", headers=headers)
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["graph_projection_state"] == "complete"
    assert body["graph_node_ids"] == [node_id]
    assert body["graph_deliverable_id"] == deliverable_id
    assert "owner_user_id" not in body
    assert "html_sha256" not in body


def test_job_status_exposes_closed_graph_projection_reason(tmp_path):
    client, deps = _client(tmp_path)
    headers = {"x-test-user": "alice"}
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["g"], "duration_minutes": 30},
    ).json()
    raw = deps.jobs.get_job(created["job_id"])
    assert raw is not None
    raw["graph_projection_state"] = "refused"
    raw["graph_projection_reason"] = "claim_coverage_missing"
    deps.jobs.put_job(raw)

    body = client.get(f"/midnight-oil/jobs/{created['job_id']}", headers=headers).json()
    assert body["graph_projection_state"] == "refused"
    assert body["graph_projection_reason"] == "claim_coverage_missing"


def _retryable_terminal(client, deps, tmp_path, *, reason="graph_lock_unavailable"):
    created = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "alice"},
        json={"goals": ["g"], "duration_minutes": 30},
    ).json()
    job_id = created["job_id"]
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id=job_id)
    assert authority is not None
    deps.owner_jobs._jobs[("alice", job_id)] = replace(  # type: ignore[attr-defined]
        authority,
        operation_state=OperationState.COMPLETE,
    )
    raw = deps.jobs.get_job(job_id)
    assert raw is not None
    terminal = replace(
        _job_from_row(raw),
        status="complete",
        deposit_state="complete",
        deposit_document_id="doc-retryable",
        graph_projection_state="pending",
        graph_projection_reason=reason,
    )
    put_job_state(terminal, store=deps.jobs)
    client.app.state.engagement_store = InMemoryEngagementStore()
    client.app.state.engagement_graph_db_path = tmp_path / "graph.duckdb"
    return job_id, terminal


def _graph_receipt() -> MidnightOilGraphEffectReceipt:
    deliverable_id = "dlv-" + "1" * 16
    node_id = "node-" + "2" * 16
    return MidnightOilGraphEffectReceipt(
        schema_version=1,
        owner_user_id="alice",
        deliverable_id=deliverable_id,
        section_ids=("sec-" + "3" * 16,),
        node_ids=(node_id,),
        edge_ids=("edge-" + "4" * 16,),
        html_sha256="5" * 64,
        evidence_sha256="6" * 64,
        deep_links=(
            f"antiek://deliverable/{deliverable_id}",
            f"antiek://node/{node_id}",
        ),
    )


def test_graph_admission_retry_is_owner_bound_and_projection_only(tmp_path, monkeypatch):
    client, deps = _client(tmp_path)
    job_id, terminal = _retryable_terminal(client, deps, tmp_path)
    calls = []

    def projection_only(*args, **kwargs):
        calls.append((args, kwargs))
        admitted = replace(
            terminal,
            graph_projection_state="complete",
            graph_projection_reason=None,
            graph_effect_receipt=_graph_receipt(),
        )
        put_job_state(admitted, store=deps.jobs)
        return SimpleNamespace(job=admitted)

    monkeypatch.setattr(
        "interfaces.research.api.midnight_oil_routes.resume_terminal_projection",
        projection_only,
    )
    hidden = client.post(
        f"/midnight-oil/jobs/{job_id}/graph-admission/retry",
        headers={"x-test-user": "mallory"},
    )
    assert hidden.status_code == 404
    assert calls == []

    response = client.post(
        f"/midnight-oil/jobs/{job_id}/graph-admission/retry",
        headers={"x-test-user": "alice"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["graph_projection_state"] == "complete"
    assert response.json()["graph_projection_reason"] is None
    assert len(calls) == 1
    assert calls[0][0] == (job_id,)
    assert calls[0][1]["owner_user_id"] == "alice"
    assert set(calls[0][1]) == {
        "owner_user_id",
        "owner_jobs",
        "store",
        "engagement_store",
        "graph_db_path",
    }


def test_graph_admission_retry_rejects_caller_authority(tmp_path, monkeypatch):
    client, deps = _client(tmp_path)
    job_id, _ = _retryable_terminal(client, deps, tmp_path)
    monkeypatch.setattr(
        "interfaces.research.api.midnight_oil_routes.resume_terminal_projection",
        lambda *args, **kwargs: pytest.fail("invalid body reached projection"),
    )

    response = client.post(
        f"/midnight-oil/jobs/{job_id}/graph-admission/retry",
        headers={"x-test-user": "alice"},
        json={"owner_user_id": "mallory", "reason": "graph_lock_unavailable"},
    )

    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == "graph admission retry body must be empty"


@pytest.mark.parametrize(
    ("exception", "state", "reason", "status_code"),
    [
        (
            GraphProjectionPending("graph_lock_unavailable"),
            "pending",
            "graph_lock_unavailable",
            202,
        ),
        (
            GraphProjectionRefused("claim_coverage_missing"),
            "refused",
            "claim_coverage_missing",
            200,
        ),
    ],
)
def test_graph_admission_retry_returns_canonical_projection_outcome(
    tmp_path, monkeypatch, exception, state, reason, status_code
):
    client, deps = _client(tmp_path)
    job_id, terminal = _retryable_terminal(client, deps, tmp_path)

    def projection_outcome(*args, **kwargs):
        put_job_state(
            replace(
                terminal,
                graph_projection_state=state,
                graph_projection_reason=reason,
            ),
            store=deps.jobs,
        )
        raise exception

    monkeypatch.setattr(
        "interfaces.research.api.midnight_oil_routes.resume_terminal_projection",
        projection_outcome,
    )
    response = client.post(
        f"/midnight-oil/jobs/{job_id}/graph-admission/retry",
        headers={"x-test-user": "alice"},
    )

    assert response.status_code == status_code
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["graph_projection_state"] == state
    assert response.json()["graph_projection_reason"] == reason


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("pending", None),
        ("refused", "claim_coverage_missing"),
        ("refused", "policy_authority_drift"),
        ("complete", None),
    ],
)
def test_graph_admission_retry_rejects_nonretryable_states(
    tmp_path, monkeypatch, state, reason
):
    client, deps = _client(tmp_path)
    job_id, terminal = _retryable_terminal(client, deps, tmp_path)
    changed = replace(
        terminal,
        graph_projection_state=state,
        graph_projection_reason=reason,
        graph_effect_receipt=_graph_receipt() if state == "complete" else None,
    )
    put_job_state(changed, store=deps.jobs)
    monkeypatch.setattr(
        "interfaces.research.api.midnight_oil_routes.resume_terminal_projection",
        lambda *args, **kwargs: pytest.fail("nonretryable state reached projection"),
    )
    response = client.post(
        f"/midnight-oil/jobs/{job_id}/graph-admission/retry",
        headers={"x-test-user": "alice"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "graph admission is not retryable"


def test_graph_admission_retry_rejects_reconciliation_failure(tmp_path, monkeypatch):
    client, deps = _client(tmp_path)
    job_id, _ = _retryable_terminal(client, deps, tmp_path)
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id=job_id)
    assert authority is not None
    deps.owner_jobs._jobs[("alice", job_id)] = replace(  # type: ignore[attr-defined]
        authority,
        operation_state=OperationState.FAILED_RECONCILE,
    )
    monkeypatch.setattr(
        "interfaces.research.api.midnight_oil_routes.resume_terminal_projection",
        lambda *args, **kwargs: pytest.fail("reconciliation state reached projection"),
    )

    response = client.post(
        f"/midnight-oil/jobs/{job_id}/graph-admission/retry",
        headers={"x-test-user": "alice"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "graph admission retry requires a terminal operation"


def test_create_rejects_empty_goals(client):
    r = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "alice"},
        json={"goals": ["  "], "duration_minutes": 10},
    )
    assert r.status_code == 422
