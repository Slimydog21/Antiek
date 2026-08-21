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
                    "scopes": ["lease", "renew", "submitted", "working", "result"],
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


def test_bridge_records_verifiable_acknowledgement_then_working(bridge_api) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    lease = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    ).json()
    base = f"/internal/agent-work/{lease['work_id']}/leases/{lease['lease_id']}"
    submitted = client.post(
        f"{base}/submitted",
        headers={**auth, "Idempotency-Key": "bridge-submit-key-0001"},
        json={
            "attempt_no": lease["attempt_no"],
            "adapter_version": "herdr-bridge/0.1",
            "herdr_target_observed": "agent-7",
        },
    )
    assert submitted.status_code == 200, submitted.text

    acknowledged = client.post(
        f"{base}/acknowledged",
        headers={**auth, "Idempotency-Key": "bridge-ack-key-0001"},
        json={
            "attempt_no": lease["attempt_no"],
            "transport_receipt_sha256": "f" * 64,
        },
    )
    working = client.post(
        f"{base}/working",
        headers={**auth, "Idempotency-Key": "bridge-working-key-0001"},
        json={"attempt_no": lease["attempt_no"]},
    )
    replay = client.post(
        f"{base}/working",
        headers={**auth, "Idempotency-Key": "bridge-working-key-0001"},
        json={"attempt_no": lease["attempt_no"]},
    )

    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["state"] == "acknowledged"
    assert working.status_code == 200, working.text
    assert working.json()["state"] == "working"
    assert replay.json() == working.json()


def test_bridge_renews_its_live_lease_and_exactly_replays(bridge_api) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    lease = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 30},
    ).json()
    path = (
        f"/internal/agent-work/{lease['work_id']}/leases/{lease['lease_id']}/renew"
    )
    headers = {**auth, "Idempotency-Key": "bridge-renew-key-0001"}

    first = client.post(
        path,
        headers=headers,
        json={"attempt_no": lease["attempt_no"], "lease_seconds": 180},
    )
    replay = client.post(
        path,
        headers=headers,
        json={"attempt_no": lease["attempt_no"], "lease_seconds": 180},
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert first.json()["state"] == "leased"
    assert first.json()["lease_expires_at"] > lease["lease_expires_at"]


def test_bridge_cannot_shorten_or_cross_credential_lease(
    bridge_api, monkeypatch
) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    lease = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 300},
    ).json()
    path = (
        f"/internal/agent-work/{lease['work_id']}/leases/{lease['lease_id']}/renew"
    )
    shorter = client.post(
        path,
        headers={**auth, "Idempotency-Key": "bridge-renew-key-0001"},
        json={"attempt_no": lease["attempt_no"], "lease_seconds": 1},
    )
    assert shorter.status_code == 200, shorter.text
    assert shorter.json()["lease_expires_at"] >= lease["lease_expires_at"]

    other_secret = "other-bridge-secret"
    scopes = ["lease", "renew", "submitted", "working", "result"]
    monkeypatch.setenv(
        "ANTIEK_BRIDGE_CREDENTIALS_JSON",
        json.dumps(
            {
                "credential-1": {
                    "secret_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                    "logical_worker_id": "research-owner",
                    "scopes": scopes,
                },
                "credential-2": {
                    "secret_sha256": hashlib.sha256(other_secret.encode()).hexdigest(),
                    "logical_worker_id": "research-owner",
                    "scopes": scopes,
                },
            }
        ),
    )
    crossed = client.post(
        path,
        headers={
            "Authorization": f"AntiekBridge credential-2.{other_secret}",
            "Idempotency-Key": "bridge-renew-key-0002",
        },
        json={"attempt_no": lease["attempt_no"], "lease_seconds": 120},
    )
    assert crossed.status_code == 410


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


def test_retryable_failure_requeues_and_rejects_the_superseded_lease(bridge_api) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    first = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    ).json()
    first_result_path = (
        f"/internal/agent-work/{first['work_id']}/leases/{first['lease_id']}/result"
    )
    failed = client.post(
        first_result_path,
        headers={**auth, "Idempotency-Key": "bridge-failure-key-0001"},
        json={
            "attempt_no": first["attempt_no"],
            "context_sha256": first["context_sha256"],
            "kind": "failure",
            "error_code": "herdr_unavailable",
            "retryable": True,
        },
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["state"] == "queued"

    second = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0002"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    ).json()
    assert second["attempt_no"] == 2
    assert second["lease_id"] != first["lease_id"]

    late = client.post(
        first_result_path,
        headers={**auth, "Idempotency-Key": "bridge-late-key-0001"},
        json={
            "attempt_no": first["attempt_no"],
            "context_sha256": first["context_sha256"],
            "kind": "reply",
            "reply_markdown": "This stale result must not be accepted.",
        },
    )
    assert late.status_code == 410

    second_failed = client.post(
        f"/internal/agent-work/{second['work_id']}/leases/{second['lease_id']}/result",
        headers={**auth, "Idempotency-Key": "bridge-failure-key-0002"},
        json={
            "attempt_no": second["attempt_no"],
            "context_sha256": second["context_sha256"],
            "kind": "failure",
            "error_code": "herdr_unavailable",
            "retryable": True,
        },
    )
    assert second_failed.status_code == 200, second_failed.text
    assert second_failed.json()["state"] == "queued"
    third = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0003"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    ).json()
    exhausted = client.post(
        f"/internal/agent-work/{third['work_id']}/leases/{third['lease_id']}/result",
        headers={**auth, "Idempotency-Key": "bridge-failure-key-0003"},
        json={
            "attempt_no": third["attempt_no"],
            "context_sha256": third["context_sha256"],
            "kind": "failure",
            "error_code": "herdr_unavailable",
            "retryable": True,
        },
    )
    assert exhausted.status_code == 200, exhausted.text
    assert exhausted.json()["state"] == "failed"
    no_fourth = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0004"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    )
    assert no_fourth.status_code == 200
    assert no_fourth.json() is None


@pytest.mark.parametrize(
    ("kind", "expected_state"),
    [("decline", "declined"), ("approval_request", "approval_requested")],
)
def test_bridge_records_terminal_agent_dispositions(
    bridge_api, kind: str, expected_state: str
) -> None:
    client, secret = bridge_api
    auth = {"Authorization": f"AntiekBridge credential-1.{secret}"}
    lease = client.post(
        "/internal/agent-work/lease",
        headers={**auth, "Idempotency-Key": "bridge-lease-key-0001"},
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    ).json()

    response = client.post(
        f"/internal/agent-work/{lease['work_id']}/leases/{lease['lease_id']}/result",
        headers={**auth, "Idempotency-Key": f"bridge-{kind}-key-0001"},
        json={
            "attempt_no": lease["attempt_no"],
            "context_sha256": lease["context_sha256"],
            "kind": kind,
            "message_markdown": "I need operator confirmation before continuing.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == expected_state
    assert response.json()["thread"]["items"][-1]["body_markdown"] == (
        "I need operator confirmation before continuing."
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
