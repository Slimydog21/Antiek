from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import create_feedback_thread
from substrate.feedback.store import CreateThreadCommand
from substrate.graph import ensure_initialized


@pytest.fixture()
def bridge_api(monkeypatch, tmp_path):
    db_path = str(tmp_path / "graph.duckdb")
    secret = "bridge-test-secret"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_AGENT_WORK_BRIDGE_ENABLED", "1")
    monkeypatch.setenv(
        "ANTIEK_BRIDGE_CREDENTIALS_JSON",
        json.dumps(
            {
                "credential-1": {
                    "secret_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                    "logical_worker_id": "research-owner",
                    "scopes": ["lease", "submitted", "result"],
                }
            }
        ),
    )
    ensure_initialized(db_path)
    create_feedback_thread(
        db_path,
        CreateThreadCommand(
            thread_id="fth-1",
            root_item_id="fit-1",
            work_id="wrk-1",
            owner_user_id="owner-1",
            investigation_id="inv-1",
            logical_worker_id="research-owner",
            artifact=ArtifactVersionRef("artifact-1", 1, "a" * 64, "b" * 64),
            anchor=NodeTextAnchor("insight-1", "c" * 64, 0, 4, "fact", "", " remains"),
            body_markdown="Verify this fact.",
            operation_id="feedback:create:op-1",
            request_sha256="d" * 64,
            context_sha256="e" * 64,
        ),
    )
    return TestClient(create_app(register_wrestling=False)), secret


def test_bridge_lease_rejects_missing_bridge_credential(bridge_api) -> None:
    client, _ = bridge_api

    response = client.post(
        "/internal/agent-work/lease",
        headers={"Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "bridge authentication required"}


def test_authenticated_bridge_leases_exact_worker_context_and_replays(bridge_api) -> None:
    client, secret = bridge_api
    headers = {
        "Authorization": f"AntiekBridge credential-1.{secret}",
        "Idempotency-Key": "bridge-lease-key-0001",
    }

    first = client.post(
        "/internal/agent-work/lease",
        headers=headers,
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    )
    replay = client.post(
        "/internal/agent-work/lease",
        headers=headers,
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200
    assert replay.json() == first.json()
    leased = first.json()
    assert leased["work_id"] == "wrk-1"
    assert leased["logical_worker_id"] == "research-owner"
    assert leased["comment_markdown"] == "Verify this fact."
    assert leased["anchor"]["node_id"] == "insight-1"


def test_bridge_marks_its_live_lease_submitted(bridge_api) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    lease_response = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    )
    lease = lease_response.json()

    response = client.post(
        f"/internal/agent-work/{lease['work_id']}/leases/{lease['lease_id']}/submitted",
        headers={**auth, "Idempotency-Key": "bridge-submit-key-0001"},
        json={
            "attempt_no": lease["attempt_no"],
            "adapter_version": "herdr-bridge/0.1",
            "herdr_target_observed": "agent-7",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "work_id": "wrk-1",
        "thread_id": "fth-1",
        "state": "submitted",
        "attempt_no": 1,
        "lease_id": lease["lease_id"],
    }


def test_bridge_result_appends_correlated_agent_reply(bridge_api) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    lease = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    ).json()

    response = client.post(
        f"/internal/agent-work/{lease['work_id']}/leases/{lease['lease_id']}/result",
        headers={**auth, "Idempotency-Key": "bridge-result-key-0001"},
        json={
            "attempt_no": lease["attempt_no"],
            "context_sha256": lease["context_sha256"],
            "kind": "reply",
            "reply_markdown": "The primary source confirms this fact.",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "replied"
    assert result["work_id"] == "wrk-1"
    assert result["thread"]["items"][-1]["body_markdown"] == (
        "The primary source confirms this fact."
    )


def test_lease_only_credential_cannot_submit_results(bridge_api, monkeypatch) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    lease = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    ).json()
    monkeypatch.setenv(
        "ANTIEK_BRIDGE_CREDENTIALS_JSON",
        json.dumps(
            {
                "credential-1": {
                    "secret_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                    "logical_worker_id": "research-owner",
                    "scopes": ["lease"],
                }
            }
        ),
    )

    response = client.post(
        f"/internal/agent-work/{lease['work_id']}/leases/{lease['lease_id']}/result",
        headers={**auth, "Idempotency-Key": "bridge-result-key-0001"},
        json={
            "attempt_no": lease["attempt_no"],
            "context_sha256": lease["context_sha256"],
            "kind": "reply",
            "reply_markdown": "This must not be accepted.",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "bridge credential lacks result scope"}
