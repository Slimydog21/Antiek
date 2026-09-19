"""DRW SPR-06 transport — the cascade/research REST + SSE surface.

Exercises the wired router via the real ``create_app`` over a tmp DB: the
full operator journey (plan → edit → approve → launch → watch → steer →
cost), the approval gate refusal, durable recovery from the event log, and
an SSE stream smoke. The browse loop is the SPR-02 demo loop, so the journey
is deterministic without a live model or network.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr

STUB_LAUNCH = {"expected_gather_mode": "contract_stub", "allow_contract_stub": True}
LAUNCH_HEADERS = {"Idempotency-Key": "test-launch-attempt"}


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        import hashlib

        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture
def client(monkeypatch):
    # Import here so collection of this module does not load all of app.py
    # (ANT-H2V: wrong ::node_id used to hang 30+ min before SIGTERM).
    from interfaces.research.api.app import create_app

    tmpdir = tempfile.mkdtemp(prefix="cascade-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "artifacts"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # Hermetic embedding (no sentence-transformers) for plan persistence + funnel.
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    # Boot-attested MiMo readiness without reading the operator's real key or
    # making a provider call. Individual readiness tests override this set.
    app.state.registered_providers = {"xiaomi"}
    return TestClient(app)


def _make_approved_plan(client, sub_questions=("sub one", "sub two")):
    r = client.post(
        "/research/plans", json={"problem": "the big problem", "sub_questions": list(sub_questions)}
    )
    assert r.status_code == 200, r.text
    root = r.json()["root_node_id"]
    client.post(f"/research/plans/{root}/approve", json={"approver": "operator"})
    return root


def test_session_routes_hide_foreign_account(tmp_path, monkeypatch):
    from interfaces.research.api.app import create_app

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "multi.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.com,bob@example.com")
    monkeypatch.delenv("ANTIEK_AUTH_SECRET", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    multi = TestClient(create_app(register_wrestling=False, register_providers=False))
    multi.app.state.registered_providers = {"xiaomi"}
    alice = {"Cf-Access-Authenticated-User-Email": "alice@example.com"}
    bob = {"Cf-Access-Authenticated-User-Email": "bob@example.com"}

    created = multi.post(
        "/research/plans",
        json={"problem": "private problem", "sub_questions": ["private leaf"]},
        headers=alice,
    )
    root = created.json()["root_node_id"]
    bob_created = multi.post(
        "/research/plans",
        json={"problem": "private problem", "sub_questions": ["private leaf"]},
        headers=bob,
    )
    assert bob_created.status_code == 200
    assert bob_created.json()["root_node_id"] != root

    owner_before = multi.get(f"/research/plans/{root}", headers=alice)
    assert owner_before.status_code == 200
    root_local_id = owner_before.json()["tree"]["root"]["local_id"]
    foreign_operations = (
        multi.get(f"/research/plans/{root}", headers=bob),
        multi.post(
            f"/research/plans/{root}/edit",
            json={"op": "reword", "target_local_id": root_local_id, "question": "stolen"},
            headers=bob,
        ),
        multi.post(
            f"/research/plans/{root}/approve",
            json={"approver": "bob"},
            headers=bob,
        ),
        multi.post(
            f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers={**bob, **LAUNCH_HEADERS}
        ),
    )
    absent_operations = (
        multi.get("/research/plans/plan-absent", headers=bob),
        multi.post(
            "/research/plans/plan-absent/edit",
            json={"op": "reword", "target_local_id": root_local_id, "question": "stolen"},
            headers=bob,
        ),
        multi.post(
            "/research/plans/plan-absent/approve",
            json={"approver": "bob"},
            headers=bob,
        ),
        multi.post(
            "/research/plans/plan-absent/launch",
            json=STUB_LAUNCH,
            headers={**bob, **LAUNCH_HEADERS},
        ),
    )
    assert all(response.status_code == 404 for response in foreign_operations)
    assert [response.json() for response in foreign_operations] == [
        response.json() for response in absent_operations
    ]
    assert multi.get(f"/research/plans/{root}", headers=alice).json() == owner_before.json()

    approved = multi.post(
        f"/research/plans/{root}/approve",
        json={"approver": "forged-client-approver"},
        headers=alice,
    )
    assert approved.status_code == 200
    approved_by = approved.json()["approval"]["approved_by"]
    assert approved_by != "forged-client-approver"
    assert approved_by.startswith("acct-")
    with cr._write("assert_plan_tenancy") as con:
        rows = con.execute(
            "SELECT plan_id, account_digest, investigation_digest "
            "FROM cascade_plan_authority ORDER BY plan_id"
        ).fetchall()
    assert len(rows) == 2
    assert len({row[0] for row in rows}) == 2
    assert len({row[1] for row in rows}) == 2
    assert len({row[2] for row in rows}) == 2
    launched = multi.post(
        f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers={**alice, **LAUNCH_HEADERS}
    )
    assert launched.status_code == 200, launched.text
    session_id = launched.json()["session_id"]

    owner = multi.get(f"/research/sessions/{session_id}", headers=alice)
    foreign = multi.get(f"/research/sessions/{session_id}", headers=bob)
    absent = multi.get("/research/sessions/session-absent", headers=bob)
    assert owner.status_code == 200
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json()
    owner_attempt = multi.get(
        f"/research/plans/{root}/launch-attempt", headers={**alice, **LAUNCH_HEADERS}
    )
    foreign_attempt = multi.get(
        f"/research/plans/{root}/launch-attempt", headers={**bob, **LAUNCH_HEADERS}
    )
    absent_attempt = multi.get(
        "/research/plans/plan-absent/launch-attempt", headers={**bob, **LAUNCH_HEADERS}
    )
    assert owner_attempt.status_code == 200
    assert foreign_attempt.status_code == absent_attempt.status_code == 404
    assert foreign_attempt.json() == absent_attempt.json()


def _poll_until_terminal(client, session_id, timeout_s=5.0):
    deadline = time.time() + timeout_s
    states = ["pending"]
    while time.time() < deadline:
        r = client.get(f"/research/sessions/{session_id}")
        assert r.status_code == 200, r.text
        states = [x["state"] for x in r.json()["researches"]]
        if all(s in ("done", "stopped", "failed", "budget_halted") for s in states):
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} not terminal in {timeout_s}s; states={states}")


# --------------------------------------------------------------------------
# Plan lifecycle (SPR-05 over HTTP)
# --------------------------------------------------------------------------


def test_budget_defaults_reads_the_contract(client):
    # The entry UI shows "estimated up to $X for N researches" off this, so it
    # must be the BudgetCap contract default, not a hardcoded API number.
    from runtime.research_runner import BudgetCap

    r = client.get("/research/budget-defaults")
    assert r.status_code == 200, r.text
    body = r.json()
    cap = BudgetCap()
    assert body["per_research_cost_usd"] == cap.cost_usd
    assert body["per_research_max_steps"] == cap.max_steps
    # SPR-05: the monitor reads the real host-local semaphore cap off the
    # contract for its honest "N running, M queued" — not a hardcoded UI number.
    from runtime.research_runner.host_local import DEFAULT_MAX_CONCURRENCY

    assert body["host_local_max_concurrency"] == DEFAULT_MAX_CONCURRENCY


def test_create_plan_returns_editable_tree(client):
    r = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a", "b", "c"]})
    assert r.status_code == 200
    body = r.json()
    assert body["root_node_id"]
    assert len(body["tree"]["root"]["children"]) == 3


def test_get_plan_not_launchable_before_approval(client):
    root = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a"]}).json()[
        "root_node_id"
    ]
    r = client.get(f"/research/plans/{root}")
    assert r.status_code == 200 and r.json()["launchable"] is False


def test_approve_makes_launchable_and_edit_reopens_gate(client):
    root = client.post(
        "/research/plans", json={"problem": "P", "sub_questions": ["a", "b"]}
    ).json()["root_node_id"]
    assert client.post(f"/research/plans/{root}/approve", json={}).json()["launchable"] is True
    # Editing re-opens the gate.
    tree = client.get(f"/research/plans/{root}").json()["tree"]
    child_local = tree["root"]["children"][0]["local_id"]
    r = client.post(
        f"/research/plans/{root}/edit",
        json={"op": "reword", "target_local_id": child_local, "question": "reworded"},
    )
    assert r.status_code == 200 and r.json()["launchable"] is False


# --------------------------------------------------------------------------
# Launch gate
# --------------------------------------------------------------------------


def test_launch_refuses_unapproved_plan(client):
    root = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a"]}).json()[
        "root_node_id"
    ]
    r = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=LAUNCH_HEADERS)
    assert r.status_code == 409
    assert "not approved" in r.json()["detail"]


def test_gather_status_is_authenticated_no_store_and_secret_free(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")
    monkeypatch.setenv("EXA_API_KEY", "must-not-appear")
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_DISABLED", raising=False)
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", raising=False)
    root = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a"]}).json()[
        "root_node_id"
    ]
    response = client.get(f"/research/plans/{root}/gather-status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["gather_mode"] == "exa_reasoning"
    assert body["network_retrieval"] is True
    assert body["exa_key_installed"] is True
    assert body["legal_gate_bypassed"] is False
    assert body["legal_policy"]["schema_version"] == 1
    assert body["legal_policy"]["migration_state"] == "current"
    assert len(body["legal_policy"]["policy_snapshot_sha256"]) == 64
    # The account snapshot is present, but no ratified issuer is configured.
    assert body["production_defensible"] is False
    assert "must-not-appear" not in response.text


def test_gather_status_unhandled_failure_is_generic_no_store(client, monkeypatch):
    root = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a"]}).json()[
        "root_node_id"
    ]
    monkeypatch.setattr(
        cr,
        "legal_policy_readiness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret detail")),
    )
    response = client.get(f"/research/plans/{root}/gather-status")
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "legal-policy operation failed"}
    assert "secret detail" not in response.text


def test_multi_source_status_is_reviewed_secret_free_and_not_prematurely_activated(
    client, monkeypatch, tmp_path
):
    manifest = tmp_path / "subscriptions.json"
    manifest.write_text(
        '{"publications":[{"name":"Research","feed_url":"https://writer.example/feed"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "multi_source")
    monkeypatch.setenv("EXA_API_KEY", "exa-secret")
    monkeypatch.setenv("PARALLEL_API_KEY", "parallel-secret")
    monkeypatch.setenv("ANTIEK_SUBSTACK_SUBSCRIPTIONS", str(manifest))
    root = _make_approved_plan(client, ("one", "two"))

    response = client.get(f"/research/plans/{root}/gather-status")
    assert response.status_code == 200
    body = response.json()
    reviewed = body["reviewed_gather_plan"]
    assert body["gather_mode"] == "authorized_multi_source"
    assert body["network_retrieval"] is True
    assert body["parallel_key_installed"] is True
    assert body["multi_source_execution_activated"] is True
    assert body["launch_ready"] is False
    assert reviewed["leaf_count"] == 2
    assert reviewed["sources"] == ["exa", "parallel", "arxiv", "substack"]
    assert all(
        value != "0" * 64 for value in reviewed["source_configuration_sha256"].values()
    )
    assert len(reviewed["fingerprint"]) == 64
    assert reviewed["launch_max_cost_micros"] == 30_000
    assert "writer.example" not in response.text
    assert "exa-secret" not in response.text
    assert "parallel-secret" not in response.text


def test_multi_source_launch_rejects_stale_fingerprint_before_claim(
    client, monkeypatch, tmp_path
):
    manifest = tmp_path / "subscriptions.json"
    manifest.write_text(
        '{"publications":[{"name":"Research","feed_url":"https://writer.example/feed"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "multi_source")
    monkeypatch.setenv("EXA_API_KEY", "installed")
    monkeypatch.setenv("PARALLEL_API_KEY", "installed")
    monkeypatch.setenv("ANTIEK_SUBSTACK_SUBSCRIPTIONS", str(manifest))
    root = _make_approved_plan(client, ("one",))
    reviewed = client.get(f"/research/plans/{root}/gather-status").json()[
        "reviewed_gather_plan"
    ]
    before = set(cr._SESSIONS)

    stale = client.post(
        f"/research/plans/{root}/launch",
        json={
            "expected_gather_mode": "authorized_multi_source",
            "expected_gather_plan_fingerprint": "0" * 64,
        },
        headers={"Idempotency-Key": "multi-stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "research gather plan changed; review launch again"
    locked = client.post(
        f"/research/plans/{root}/launch",
        json={
            "expected_gather_mode": "authorized_multi_source",
            "expected_gather_plan_fingerprint": reviewed["fingerprint"],
        },
        headers={"Idempotency-Key": "multi-current"},
    )
    assert locked.status_code == 503
    assert locked.json()["detail"] == "configured research gather is not ready"
    assert set(cr._SESSIONS) == before
    with cr._write("assert_multi_source_zero_claim") as con:
        assert con.execute("SELECT count(*) FROM cascade_launch_attempts").fetchone() == (0,)


def test_multi_source_key_rotation_invalidates_review_before_claim(
    client, monkeypatch, tmp_path
):
    manifest = tmp_path / "subscriptions.json"
    manifest.write_text(
        '{"publications":[{"name":"Research","feed_url":"https://writer.example/feed"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "multi_source")
    monkeypatch.setenv("EXA_API_KEY", "reviewed-key")
    monkeypatch.setenv("PARALLEL_API_KEY", "installed")
    monkeypatch.setenv("ANTIEK_SUBSTACK_SUBSCRIPTIONS", str(manifest))
    root = _make_approved_plan(client, ("one",))
    reviewed = client.get(f"/research/plans/{root}/gather-status").json()[
        "reviewed_gather_plan"
    ]
    monkeypatch.setenv("EXA_API_KEY", "rotated-key")

    response = client.post(
        f"/research/plans/{root}/launch",
        json={
            "expected_gather_mode": "authorized_multi_source",
            "expected_gather_plan_fingerprint": reviewed["fingerprint"],
        },
        headers={"Idempotency-Key": "multi-key-rotation"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "research gather plan changed; review launch again"
    with cr._write("assert_key_rotation_zero_claim") as con:
        assert con.execute("SELECT count(*) FROM cascade_launch_attempts").fetchone() == (0,)


def test_multi_source_launch_forwards_exact_reviewed_template_to_factory(
    client, monkeypatch, tmp_path
):
    from types import SimpleNamespace

    manifest = tmp_path / "subscriptions.json"
    manifest.write_text(
        '{"publications":[{"name":"Research","feed_url":"https://writer.example/feed"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "multi_source")
    monkeypatch.setenv("EXA_API_KEY", "installed")
    monkeypatch.setenv("PARALLEL_API_KEY", "installed")
    monkeypatch.setenv("ANTIEK_SUBSTACK_SUBSCRIPTIONS", str(manifest))
    readiness = {
        "schema_version": 1,
        "policy_snapshot_sha256": "a" * 64,
        "issuer_state": "configured",
        "write_enforcement_version": 1,
        "read_enforcement_version": 1,
        "migration_state": "current",
        "production_defensible": True,
        "reason_code": None,
    }
    monkeypatch.setattr(
        cr, "legal_policy_readiness", lambda *args, **kwargs: SimpleNamespace(to_dict=lambda: readiness)
    )
    monkeypatch.setattr(cr, "require_policy_snapshot", lambda *args, **kwargs: None)
    root = _make_approved_plan(client, ("one", "two"))
    reviewed = client.get(f"/research/plans/{root}/gather-status").json()[
        "reviewed_gather_plan"
    ]
    seen: dict[str, object] = {}

    def factory(**kwargs: object):
        seen.update(kwargs)
        return cr.make_contract_gather_stub(steps=1, cost_per_step=0)

    monkeypatch.setattr(cr, "_research_loop_factory", factory)
    response = client.post(
        f"/research/plans/{root}/launch",
        json={
            "expected_gather_mode": "authorized_multi_source",
            "expected_gather_plan_fingerprint": reviewed["fingerprint"],
        },
        headers={"Idempotency-Key": "multi-activate"},
    )
    assert response.status_code == 200, response.text
    assert seen["gather_mode"] == "authorized_multi_source"
    assert seen["multi_source_launch_plan"].fingerprint == reviewed["fingerprint"]
    assert seen["multi_source_feed_urls"] == ("https://writer.example/feed",)
    assert len(seen["authority"].account_digest) == 64


def test_multi_source_underfunded_runner_budgets_fail_before_claim(
    client, monkeypatch, tmp_path
):
    from types import SimpleNamespace

    manifest = tmp_path / "subscriptions.json"
    manifest.write_text(
        '{"publications":[{"name":"Research","feed_url":"https://writer.example/feed"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "multi_source")
    monkeypatch.setenv("EXA_API_KEY", "installed")
    monkeypatch.setenv("PARALLEL_API_KEY", "installed")
    monkeypatch.setenv("ANTIEK_SUBSTACK_SUBSCRIPTIONS", str(manifest))
    readiness = {
        "schema_version": 1,
        "policy_snapshot_sha256": "a" * 64,
        "issuer_state": "configured",
        "write_enforcement_version": 1,
        "read_enforcement_version": 1,
        "migration_state": "current",
        "production_defensible": True,
        "reason_code": None,
    }
    monkeypatch.setattr(
        cr, "legal_policy_readiness", lambda *args, **kwargs: SimpleNamespace(to_dict=lambda: readiness)
    )
    root = _make_approved_plan(client, ("one", "two"))
    reviewed = client.get(f"/research/plans/{root}/gather-status").json()[
        "reviewed_gather_plan"
    ]
    common = {
        "expected_gather_mode": "authorized_multi_source",
        "expected_gather_plan_fingerprint": reviewed["fingerprint"],
    }
    per_leaf = client.post(
        f"/research/plans/{root}/launch",
        json={**common, "per_research_budget_usd": 0.014999},
        headers={"Idempotency-Key": "multi-underfunded-leaf"},
    )
    aggregate = client.post(
        f"/research/plans/{root}/launch",
        json={**common, "aggregate_budget_usd": 0.029999},
        headers={"Idempotency-Key": "multi-underfunded-total"},
    )
    assert per_leaf.status_code == aggregate.status_code == 409
    assert "per-research budget" in per_leaf.json()["detail"]
    assert "aggregate budget" in aggregate.json()["detail"]
    with cr._write("assert_underfunded_multi_zero_claim") as con:
        assert con.execute("SELECT count(*) FROM cascade_launch_attempts").fetchone() == (0,)


def test_legal_policy_middleware_does_not_swallow_unrelated_failure(client, monkeypatch):
    class BrokenBudgetCap:
        def __init__(self):
            raise RuntimeError("unrelated failure")

    monkeypatch.setattr(cr, "BudgetCap", BrokenBudgetCap)
    with pytest.raises(RuntimeError, match="unrelated failure"):
        client.get("/research/budget-defaults")


def test_cited_policy_dry_run_apply_and_revoke_are_explicit_no_store(client):
    root = _make_approved_plan(client, ("a",))
    event = {
        "matcher_kind": "domain",
        "matcher_value": "Example.COM",
        "decision": "allow",
        "citation_ref": "license:operator-1",
        "issuer_id": "operator",
        "reason_code": "licensed_source",
    }
    with cr._write("policy_count_before_dry_run") as con:
        before = con.execute("SELECT count(*) FROM legal_policy_events").fetchone()
    preview = client.post(f"/research/plans/{root}/legal-policy/dry-run", json=event)
    assert preview.status_code == 200, preview.text
    assert preview.headers["cache-control"] == "no-store"
    assert preview.json()["normalized_matcher_value"] == "example.com"
    assert preview.json()["applied"] is False
    with cr._write("policy_count_after_dry_run") as con:
        assert con.execute("SELECT count(*) FROM legal_policy_events").fetchone() == before

    applied = client.post(
        f"/research/plans/{root}/legal-policy/events",
        json=event,
        headers={"Idempotency-Key": "policy-apply-1"},
    )
    assert applied.status_code == 201, applied.text
    assert applied.headers["cache-control"] == "no-store"
    event_id = applied.json()["event_id"]
    replay = client.post(
        f"/research/plans/{root}/legal-policy/events",
        json=event,
        headers={"Idempotency-Key": "policy-apply-1"},
    )
    assert replay.status_code == 201
    assert replay.json()["event_id"] == event_id
    assert replay.json()["idempotency_replayed"] is True
    conflict = client.post(
        f"/research/plans/{root}/legal-policy/events",
        json={**event, "decision": "deny"},
        headers={"Idempotency-Key": "policy-apply-1"},
    )
    assert conflict.status_code == 409
    assert conflict.headers["cache-control"] == "no-store"
    revoked = client.post(
        f"/research/plans/{root}/legal-policy/revoke",
        json={
            "event_id": event_id,
            "matcher_kind": "domain",
            "matcher_value": "example.com",
            "citation_ref": "license:operator-1-revoked",
            "issuer_id": "operator",
            "reason_code": "license_revoked",
        },
        headers={"Idempotency-Key": "policy-revoke-1"},
    )
    assert revoked.status_code == 201, revoked.text
    assert revoked.headers["cache-control"] == "no-store"
    assert revoked.json()["revoked_event_id"] == event_id
    assert revoked.json()["policy_snapshot_sha256"] != applied.json()["policy_snapshot_sha256"]


def test_policy_api_rejects_uncited_or_checkbox_shaped_authority(client):
    root = _make_approved_plan(client, ("a",))
    missing_citation = client.post(
        f"/research/plans/{root}/legal-policy/events",
        json={
            "matcher_kind": "domain",
            "matcher_value": "example.com",
            "decision": "allow",
            "issuer_id": "operator",
            "reason_code": "licensed_source",
        },
        headers={"Idempotency-Key": "policy-invalid-1"},
    )
    checkbox = client.post(
        f"/research/plans/{root}/legal-policy/events",
        json={
            "matcher_kind": "domain",
            "matcher_value": "example.com",
            "decision": "allow",
            "citation_ref": "license:1",
            "issuer_id": "operator",
            "reason_code": "licensed_source",
            "lawyer_approved": True,
        },
        headers={"Idempotency-Key": "policy-invalid-2"},
    )
    assert missing_citation.status_code == checkbox.status_code == 422
    assert missing_citation.headers["cache-control"] == "no-store"
    assert checkbox.headers["cache-control"] == "no-store"
    with cr._write("assert_no_uncited_policy") as con:
        assert con.execute("SELECT count(*) FROM legal_policy_events").fetchone() == (0,)


def test_dispatch_lease_recovery_requires_terminal_evidence_and_replays(client):
    from substrate.event_log import log_event_authorized
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.legal_gate.policy_store import account_policy_authority
    from substrate.legal_gate.readiness import (
        claim_policy_dispatch_lease,
        legal_policy_readiness,
    )
    from substrate.multi_user.auth import operator_claims

    root = _make_approved_plan(client, ("a",))
    holder = InvestigationAuthority(operator_claims().user_id, root)
    with cr._write("test_claim_recoverable_dispatch") as con:
        authority = account_policy_authority(holder)
        snapshot = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert snapshot is not None
        lease_id, _gate = claim_policy_dispatch_lease(
            con,
            authority,
            holder_investigation_digest=holder.investigation_digest,
            holder_investigation_id=root,
            expected_sha256=snapshot,
            ttl_seconds=1,
        )
        con.execute(
            "UPDATE legal_policy_dispatch_leases SET acquired_at = TIMESTAMP '2000-01-01', "
            "expires_at = TIMESTAMP '2000-01-02' WHERE lease_id = ?",
            [lease_id],
        )
    log_event_authorized(
        holder,
        "legal_policy.dispatch_claimed",
        payload={"lease_id": lease_id, "policy_snapshot_sha256": snapshot},
    )

    listed = client.get(f"/research/plans/{root}/legal-policy/dispatch-leases")
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    assert listed.json()["leases"][0]["recovery_state"] == "active"
    refused = client.post(
        f"/research/plans/{root}/legal-policy/dispatch-leases/{lease_id}/recover",
        json={},
        headers={"Idempotency-Key": "recover-1"},
    )
    assert refused.status_code == 409
    with cr._write("assert_expiry_did_not_recover") as con:
        assert con.execute(
            "SELECT count(*) FROM legal_policy_dispatch_leases WHERE lease_id = ?", [lease_id]
        ).fetchone() == (1,)

    log_event_authorized(holder, "investigation.completed", payload={"outcome": "complete"})
    recoverable = client.get(f"/research/plans/{root}/legal-policy/dispatch-leases")
    assert recoverable.json()["leases"][0]["recovery_state"] == "terminal_recoverable"
    recovered = client.post(
        f"/research/plans/{root}/legal-policy/dispatch-leases/{lease_id}/recover",
        json={},
        headers={"Idempotency-Key": "recover-1"},
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["recovered"] is True
    assert recovered.json()["idempotency_replayed"] is False
    replay = client.post(
        f"/research/plans/{root}/legal-policy/dispatch-leases/{lease_id}/recover",
        json={},
        headers={"Idempotency-Key": "recover-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["idempotency_replayed"] is True


def test_dispatch_lease_recovery_body_is_closed(client):
    root = _make_approved_plan(client, ("a",))
    response = client.post(
        f"/research/plans/{root}/legal-policy/dispatch-leases/missing/recover",
        json={"force": True, "terminal": True},
        headers={"Idempotency-Key": "forged-recovery"},
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_dispatch_recovery_rejects_prelease_terminal_and_restart(client):
    from substrate.event_log import log_event_authorized
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.legal_gate.policy_store import account_policy_authority
    from substrate.legal_gate.readiness import claim_policy_dispatch_lease, legal_policy_readiness
    from substrate.multi_user.auth import operator_claims

    root = _make_approved_plan(client, ("a",))
    holder = InvestigationAuthority(operator_claims().user_id, root)
    log_event_authorized(holder, "investigation.completed", payload={"outcome": "old"})
    with cr._write("claim_after_old_terminal") as con:
        authority = account_policy_authority(holder)
        snapshot = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert snapshot is not None
        lease_id, _gate = claim_policy_dispatch_lease(
            con,
            authority,
            holder_investigation_digest=holder.investigation_digest,
            holder_investigation_id=root,
            expected_sha256=snapshot,
        )
    log_event_authorized(
        holder,
        "legal_policy.dispatch_claimed",
        payload={"lease_id": lease_id, "policy_snapshot_sha256": snapshot},
    )
    old = client.post(
        f"/research/plans/{root}/legal-policy/dispatch-leases/{lease_id}/recover",
        json={},
        headers={"Idempotency-Key": "old-terminal"},
    )
    assert old.status_code == 409

    log_event_authorized(holder, "investigation.completed", payload={"outcome": "new"})
    log_event_authorized(
        holder, "investigation.start_requested", payload={"sub_question": "restart"}
    )
    restarted = client.post(
        f"/research/plans/{root}/legal-policy/dispatch-leases/{lease_id}/recover",
        json={},
        headers={"Idempotency-Key": "restarted-holder"},
    )
    assert restarted.status_code == 409
    with cr._write("assert_restart_kept_lease") as con:
        assert con.execute(
            "SELECT count(*) FROM legal_policy_dispatch_leases WHERE lease_id = ?", [lease_id]
        ).fetchone() == (1,)


def test_dispatch_lease_listing_and_recovery_are_account_isolated(tmp_path, monkeypatch):
    from interfaces.research.api.app import create_app
    from substrate.event_log import log_event_authorized
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.legal_gate.policy_store import account_policy_authority
    from substrate.legal_gate.readiness import claim_policy_dispatch_lease, legal_policy_readiness
    from substrate.multi_user.auth import account_user_id

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "multi-lease.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.com,bob@example.com")
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    multi = TestClient(create_app(register_wrestling=False, register_providers=False))
    alice_h = {"Cf-Access-Authenticated-User-Email": "alice@example.com"}
    bob_h = {"Cf-Access-Authenticated-User-Email": "bob@example.com"}
    alice_root = multi.post(
        "/research/plans",
        json={"problem": "Alice root question", "sub_questions": ["alice leaf question"]},
        headers=alice_h,
    ).json()["root_node_id"]
    bob_root = multi.post(
        "/research/plans",
        json={"problem": "Bob root question", "sub_questions": ["bob leaf question"]},
        headers=bob_h,
    ).json()["root_node_id"]
    holder = InvestigationAuthority(account_user_id("alice@example.com"), alice_root)
    with cr._write("claim_alice_only_lease") as con:
        authority = account_policy_authority(holder)
        snapshot = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert snapshot is not None
        lease_id, _gate = claim_policy_dispatch_lease(
            con,
            authority,
            holder_investigation_digest=holder.investigation_digest,
            holder_investigation_id=alice_root,
            expected_sha256=snapshot,
        )
    log_event_authorized(
        holder,
        "legal_policy.dispatch_claimed",
        payload={
            "lease_id": lease_id,
            "policy_snapshot_sha256": snapshot,
        },
    )
    log_event_authorized(holder, "investigation.completed", payload={"outcome": "done"})

    assert multi.get(
        f"/research/plans/{bob_root}/legal-policy/dispatch-leases", headers=bob_h
    ).json() == {"count": 0, "leases": []}
    hidden = multi.post(
        f"/research/plans/{bob_root}/legal-policy/dispatch-leases/{lease_id}/recover",
        json={},
        headers={**bob_h, "Idempotency-Key": "bob-cannot-recover"},
    )
    assert hidden.status_code == 404
    alice = multi.get(f"/research/plans/{alice_root}/legal-policy/dispatch-leases", headers=alice_h)
    assert alice.json()["count"] == 1


def test_dispatch_recovery_stream_lock_fences_concurrent_restart(client, monkeypatch):
    import substrate.legal_gate.readiness as readiness
    from substrate.event_log import log_event_authorized
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.legal_gate.policy_store import account_policy_authority
    from substrate.multi_user.auth import operator_claims

    root = _make_approved_plan(client, ("fenced leaf",))
    holder = InvestigationAuthority(operator_claims().user_id, root)
    with cr._write("claim_fenced_recovery") as con:
        authority = account_policy_authority(holder)
        snapshot = readiness.legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert snapshot is not None
        lease_id, _gate = readiness.claim_policy_dispatch_lease(
            con,
            authority,
            holder_investigation_digest=holder.investigation_digest,
            holder_investigation_id=root,
            expected_sha256=snapshot,
        )
    log_event_authorized(
        holder,
        "legal_policy.dispatch_claimed",
        payload={
            "lease_id": lease_id,
            "policy_snapshot_sha256": snapshot,
        },
    )
    log_event_authorized(holder, "investigation.completed", payload={"outcome": "done"})

    original = readiness.recover_policy_dispatch_lease
    restart_started = threading.Event()
    restart_future = None
    executor = ThreadPoolExecutor(max_workers=1)

    def wrapped(*args, **kwargs):
        nonlocal restart_future
        restart_future = executor.submit(
            lambda: (
                restart_started.set(),
                log_event_authorized(
                    holder,
                    "investigation.start_requested",
                    payload={"sub_question": "restart"},
                ),
            )
        )
        assert restart_started.wait(timeout=1)
        time.sleep(0.05)
        assert restart_future is not None and not restart_future.done()
        return original(*args, **kwargs)

    monkeypatch.setattr(readiness, "recover_policy_dispatch_lease", wrapped)
    recovered = client.post(
        f"/research/plans/{root}/legal-policy/dispatch-leases/{lease_id}/recover",
        json={},
        headers={"Idempotency-Key": "fenced-recovery"},
    )
    assert recovered.status_code == 200, recovered.text
    assert restart_future is not None
    restart_future.result(timeout=2)
    executor.shutdown(wait=True)


def test_launch_rejects_silent_stub_and_mode_drift_before_session(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "stub")
    root = _make_approved_plan(client, ("a",))
    before = set(cr._SESSIONS)
    silent = client.post(
        f"/research/plans/{root}/launch",
        json={"expected_gather_mode": "contract_stub", "allow_contract_stub": False},
        headers=LAUNCH_HEADERS,
    )
    assert silent.status_code == 409
    drift = client.post(
        f"/research/plans/{root}/launch",
        json={"expected_gather_mode": "exa_reasoning", "allow_contract_stub": True},
        headers=LAUNCH_HEADERS,
    )
    assert drift.status_code == 409
    assert set(cr._SESSIONS) == before


def test_launch_rejects_unready_exa_before_session(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    root = _make_approved_plan(client, ("a",))
    before = set(cr._SESSIONS)
    response = client.post(
        f"/research/plans/{root}/launch",
        json={"expected_gather_mode": "exa_reasoning", "allow_contract_stub": False},
        headers=LAUNCH_HEADERS,
    )
    assert response.status_code == 503
    assert set(cr._SESSIONS) == before


def test_safe_gather_stub_refuses_recursive_context(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "stub")
    root = _make_approved_plan(client, ("Assess prior research",))
    response = client.post(
        f"/research/plans/{root}/launch",
        json={**STUB_LAUNCH, "recursive_asset_ids": ["prior-research"]},
        headers=LAUNCH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "recursive context requires the Exa reasoning research mode"
    )


def test_launch_refuses_before_claim_when_no_candidate_is_boot_ready(client):
    root = _make_approved_plan(client, ("one",))
    client.app.state.registered_providers = {"zai", "deepseek"}
    before = set(cr._SESSIONS)
    response = client.post(
        f"/research/plans/{root}/launch",
        json=STUB_LAUNCH,
        headers={"Idempotency-Key": "no-ready-driver"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "no boot-ready provider is available for research tier deep"
    )
    assert set(cr._SESSIONS) == before
    with cr._write("assert_no_ready_driver_zero_claim") as con:
        assert con.execute("SELECT count(*) FROM cascade_launch_attempts").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM cascade_plan_launch_authority").fetchone() == (0,)


def test_driver_readiness_preview_is_boot_attested_secret_free_and_no_store(client):
    client.app.state.registered_providers = {"openai_chat", "xiaomi"}
    ready = client.get("/research/driver-readiness?research_tier=wrestle")
    assert ready.status_code == 200
    assert ready.headers["cache-control"] == "no-store"
    assert ready.json() == {
        "research_tier": "wrestle",
        "ready": True,
        "provider": "openai_chat",
        "model": "gpt-5.6-sol",
        "candidate_rank": 1,
        "availability_source": "boot_registered_providers",
        "reason": "GPT-5.6 Sol — highest-quality long-horizon research lane.",
    }
    client.app.state.registered_providers = {"zai", "deepseek"}
    unavailable = client.get("/research/driver-readiness?research_tier=deep")
    assert unavailable.status_code == 200
    assert unavailable.headers["cache-control"] == "no-store"
    assert unavailable.json()["ready"] is False
    assert unavailable.json()["provider"] is None
    assert unavailable.json()["model"] is None


# --------------------------------------------------------------------------
# Full launch → watch → cost journey
# --------------------------------------------------------------------------


def test_launch_watch_and_cost(client):
    from substrate.event_log import trajectory_authorized

    root = _make_approved_plan(client, ("a", "b", "c"))
    r = client.post(
        f"/research/plans/{root}/launch",
        json={**STUB_LAUNCH, "per_research_budget_usd": 1.0},
        headers=LAUNCH_HEADERS,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gather_receipt"]["gather_mode"] == "contract_stub"
    assert body["driver_receipt"]["research_tier"] == "deep"
    assert body["driver_receipt"]["reviewed_primary_provider"] == "xiaomi"
    assert body["driver_receipt"]["reviewed_primary_model"] == "mimo-v2.5-pro"
    assert body["driver_receipt"]["availability_source"] == "boot_registered_providers"
    assert body["driver_receipt"]["candidate_rank"] == 2
    receipt_text = str(body["driver_receipt"]).lower()
    assert "secret" not in receipt_text
    assert "api_key" not in receipt_text
    assert "token" not in receipt_text
    assert body["gather_receipt"]["network_retrieval"] is False
    sid = body["session_id"]
    launched = next(
        row
        for row in trajectory_authorized(cr._SESSIONS[sid]._authority(sid))
        if row["action_type"] == "cascade.launched"
    )
    assert launched["payload"]["gather_receipt"] == body["gather_receipt"]
    assert launched["payload"]["driver_receipt"] == body["driver_receipt"]
    assert len(body["researches"]) == 3
    final = _poll_until_terminal(client, sid)
    assert all(x["state"] == "done" for x in final["researches"])
    # Cost meter reflects contract gather stub (3 researches × 2 steps × 0.01).
    cost = client.get(f"/research/sessions/{sid}/cost").json()
    assert cost["session_total_usd"] == pytest.approx(0.06)
    assert cost["session_total_usd"] == pytest.approx(sum(cost["per_research"].values()))


def test_launch_constructs_the_exact_reviewed_gather_mode(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "stub")
    root = _make_approved_plan(client, ("a",))
    seen: list[str | None] = []
    original = cr._research_loop_factory

    def recording_factory(
        *,
        gather_mode=None,
        reasoning_projected_max_cost_usd=0.25,
        research_tier="deep",
        reasoning_provider_override=None,
        reasoning_model_override=None,
        reasoning_allowed_routes=None,
    ):
        seen.append(gather_mode)
        # Simulate mutable process configuration after the launch snapshot.
        monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")
        return original(
            gather_mode=gather_mode,
            reasoning_projected_max_cost_usd=reasoning_projected_max_cost_usd,
            research_tier=research_tier,
            reasoning_provider_override=reasoning_provider_override,
            reasoning_model_override=reasoning_model_override,
            reasoning_allowed_routes=reasoning_allowed_routes,
        )

    monkeypatch.setattr(cr, "_research_loop_factory", recording_factory)
    response = client.post(
        f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=LAUNCH_HEADERS
    )
    assert response.status_code == 200, response.text
    assert seen == ["contract_stub"]
    assert response.json()["gather_receipt"]["gather_mode"] == "contract_stub"


def test_relaunch_same_approved_plan_allocates_fresh_session_and_leaves(client):
    root = _make_approved_plan(client, ("one", "two"))
    first = client.post(
        f"/research/plans/{root}/launch",
        json=STUB_LAUNCH,
        headers={"Idempotency-Key": "intentional-run-1"},
    )
    second = client.post(
        f"/research/plans/{root}/launch",
        json=STUB_LAUNCH,
        headers={"Idempotency-Key": "intentional-run-2"},
    )

    assert first.status_code == second.status_code == 200
    first_body, second_body = first.json(), second.json()
    assert first_body["session_id"] != second_body["session_id"]
    first_leaves = {item["investigation_id"] for item in first_body["researches"]}
    second_leaves = {item["investigation_id"] for item in second_body["researches"]}
    assert first_leaves.isdisjoint(second_leaves)


def test_same_launch_attempt_replays_one_durable_session_after_eviction(client):
    root = _make_approved_plan(client, ("one", "two"))
    headers = {"Idempotency-Key": "recover-this-attempt"}
    first = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["idempotency_replayed"] is False
    cr._SESSIONS.pop(first_body["session_id"], None)
    # The entry surface approves before each attempt. Refreshing approval audit
    # metadata for the same structural plan version must not break recovery.
    assert (
        client.post(f"/research/plans/{root}/approve", json={"approver": "operator"}).status_code
        == 200
    )

    replay = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json() == {**first_body, "idempotency_replayed": True}
    with cr._write("assert_one_launch_attempt") as con:
        assert con.execute(
            "SELECT count(*), count(DISTINCT session_id) FROM cascade_launch_attempts"
        ).fetchone() == (1, 1)
        stored = con.execute(
            "SELECT idempotency_key_digest, response_json FROM cascade_launch_attempts"
        ).fetchone()
    assert stored is not None
    assert stored[0] != headers["Idempotency-Key"]
    assert headers["Idempotency-Key"] not in stored[1]


def test_launch_attempt_fingerprint_conflict_is_zero_dispatch(client):
    root = _make_approved_plan(client, ("one",))
    headers = {"Idempotency-Key": "fingerprint-conflict"}
    first = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert first.status_code == 200, first.text
    before = set(cr._SESSIONS)
    conflict = client.post(
        f"/research/plans/{root}/launch",
        json={**STUB_LAUNCH, "research_tier": "wrestle"},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert set(cr._SESSIONS) == before


@pytest.mark.parametrize(
    "body",
    [
        {**STUB_LAUNCH, "research_tier": "raw-model"},
        {**STUB_LAUNCH, "provider_override": "openai"},
        {**STUB_LAUNCH, "model_override": "gpt-arbitrary"},
    ],
)
def test_launch_refuses_raw_driver_authority(client, body):
    root = _make_approved_plan(client, ("one",))
    response = client.post(
        f"/research/plans/{root}/launch",
        json=body,
        headers={"Idempotency-Key": "raw-driver-refused"},
    )
    assert response.status_code == 422
    assert not cr._SESSIONS


def test_launch_conditionally_freezes_the_exact_reviewed_tree(client, monkeypatch):
    root = _make_approved_plan(client, ("one",))
    monkeypatch.setattr(cr, "plan_tree_fingerprint", lambda _tree: "stale-review")
    response = client.post(
        f"/research/plans/{root}/launch",
        json=STUB_LAUNCH,
        headers={"Idempotency-Key": "stale-plan-review"},
    )
    assert response.status_code == 409
    assert not cr._SESSIONS
    with cr._write("assert_stale_review_rollback") as con:
        assert con.execute("SELECT count(*) FROM cascade_launch_attempts").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM cascade_plan_launch_authority").fetchone() == (0,)


def test_corrupt_completed_attempt_response_fails_closed(client):
    root = _make_approved_plan(client, ("one",))
    headers = {"Idempotency-Key": "corrupt-response"}
    first = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert first.status_code == 200, first.text
    before = set(cr._SESSIONS)
    with cr._write("corrupt_launch_attempt") as con:
        con.execute(
            'UPDATE cascade_launch_attempts SET response_json = \'{"session_id":"forged"}\''
        )
    replay = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert replay.status_code == 409
    assert set(cr._SESSIONS) == before


def test_concurrent_same_attempt_creates_exactly_one_session(client):
    root = _make_approved_plan(client, ("one", "two"))
    headers = {"Idempotency-Key": "concurrent-attempt"}

    def invoke():
        return client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _index: invoke(), range(2)))
    assert all(response.status_code in {200, 409} for response in responses)
    accepted = [response.json() for response in responses if response.status_code == 200]
    assert accepted
    assert len({body["session_id"] for body in accepted}) == 1
    if len(accepted) == 2:
        assert sorted(body["idempotency_replayed"] for body in accepted) == [False, True]
    with cr._write("assert_concurrent_attempt") as con:
        assert con.execute("SELECT count(*) FROM cascade_launch_attempts").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM cascade_plan_launch_authority").fetchone() == (1,)


def test_claimed_but_unsealed_launch_refuses_automatic_redispatch(client, monkeypatch):
    root = _make_approved_plan(client, ("one",))
    headers = {"Idempotency-Key": "unknown-outcome"}

    def fail_completion(*_args, **_kwargs):
        raise cr.LaunchAttemptConflict("injected receipt-store failure")

    monkeypatch.setattr(cr, "complete_launch_attempt_authorized", fail_completion)
    first = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert first.status_code == 503
    before = set(cr._SESSIONS)
    assert len(before) == 1
    _poll_until_terminal(client, next(iter(before)))
    retry = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "launch_outcome_unknown"
    assert retry.json()["detail"]["session_id"] in before
    assert set(cr._SESSIONS) == before

    status = client.get(f"/research/plans/{root}/launch-attempt", headers=headers)
    assert status.status_code == 200, status.text
    assert status.headers["cache-control"] == "no-store"
    assert status.json() == {
        "plan_id": root,
        "session_id": retry.json()["detail"]["session_id"],
        "state": "claimed",
        "response_integrity": None,
        "session_authority_present": True,
        "launch_evidence_present": True,
        "action": "inspect_session",
    }


def test_completed_launch_attempt_status_survives_eviction_and_is_read_only(client):
    root = _make_approved_plan(client, ("one",))
    headers = {"Idempotency-Key": "durable-attempt-status"}
    launched = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert launched.status_code == 200, launched.text
    session_id = launched.json()["session_id"]
    cr._SESSIONS.pop(session_id, None)
    before_tasks = set(cr._SESSION_TASKS)
    with cr._write("attempt_status_counts_before") as con:
        before = con.execute(
            "SELECT (SELECT count(*) FROM cascade_launch_attempts), "
            "(SELECT count(*) FROM cascade_plan_launch_authority)"
        ).fetchone()
    first = client.get(f"/research/plans/{root}/launch-attempt", headers=headers)
    second = client.get(f"/research/plans/{root}/launch-attempt", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["state"] == "completed"
    assert first.json()["response_integrity"] is True
    assert first.json()["action"] == "inspect_session"
    assert set(cr._SESSION_TASKS) == before_tasks
    with cr._write("attempt_status_counts_after") as con:
        after = con.execute(
            "SELECT (SELECT count(*) FROM cascade_launch_attempts), "
            "(SELECT count(*) FROM cascade_plan_launch_authority)"
        ).fetchone()
    assert after == before


def test_launch_attempt_status_absent_and_corrupt_fail_closed(client):
    root = _make_approved_plan(client, ("one",))
    absent = client.get(
        f"/research/plans/{root}/launch-attempt",
        headers={"Idempotency-Key": "absent-attempt"},
    )
    assert absent.status_code == 404
    assert absent.headers["cache-control"] == "no-store"
    missing = client.get(f"/research/plans/{root}/launch-attempt")
    assert missing.status_code == 422
    assert missing.headers["cache-control"] == "no-store"

    headers = {"Idempotency-Key": "status-corruption"}
    launched = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert launched.status_code == 200
    with cr._write("corrupt_attempt_status") as con:
        con.execute("UPDATE cascade_launch_attempts SET response_fingerprint = 'forged'")
    corrupt = client.get(f"/research/plans/{root}/launch-attempt", headers=headers)
    assert corrupt.status_code == 409
    assert corrupt.headers["cache-control"] == "no-store"


def test_claim_before_session_bind_is_visible_but_not_inspectable(client, monkeypatch):
    root = _make_approved_plan(client, ("one",))
    headers = {"Idempotency-Key": "claim-before-bind"}

    def fail_bind(*_args, **_kwargs):
        raise cr.InvestigationAccessDenied("injected bind failure")

    monkeypatch.setattr(cr, "bind_child_investigation", fail_bind)
    launched = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=headers)
    assert launched.status_code == 404
    status = client.get(f"/research/plans/{root}/launch-attempt", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json() == {
        "plan_id": root,
        "session_id": status.json()["session_id"],
        "state": "claimed",
        "response_integrity": None,
        "session_authority_present": False,
        "launch_evidence_present": False,
        "action": "await_operator_reconciliation",
    }
    assert not cr._SESSIONS
    assert not cr._SESSION_TASKS


def test_launch_requires_a_canonical_idempotency_key_before_claim(client):
    root = _make_approved_plan(client, ("one",))
    missing = client.post(f"/research/plans/{root}/launch", json=STUB_LAUNCH)
    malformed = client.post(
        f"/research/plans/{root}/launch",
        json=STUB_LAUNCH,
        headers={"Idempotency-Key": " padded "},
    )
    assert missing.status_code == malformed.status_code == 422
    with cr._write("assert_no_malformed_attempt") as con:
        assert con.execute("SELECT count(*) FROM cascade_launch_attempts").fetchone() == (0,)


def test_launch_resolves_authenticated_recursive_assets_into_start_pack(client, monkeypatch):
    from interfaces.research.api.engagement_routes import get_account_engagement_store
    from substrate.engagement_spine import record_twin_insight
    from substrate.event_log import trajectory
    from substrate.graph.ops import insert_deliverable
    from substrate.research_artifact import operator_authority
    from substrate.research_artifact.render import render_html
    from substrate.research_artifact.schema import ResearchArtifactBody
    from substrate.research_artifact.storage import FilesystemArtifactStore

    asset_id = "recursive-launch-asset"
    foreign_id = "recursive-foreign-asset"
    with cr._write("test_recursive_launch") as con:
        insert_deliverable(
            con,
            deliverable_id=asset_id,
            title="Prior research",
            deliverable_kind="research_memo",
            owner_user_id="__operator__",
        )
        insert_deliverable(
            con,
            deliverable_id=foreign_id,
            title="Foreign research",
            deliverable_kind="research_memo",
            owner_user_id="other-owner",
        )
    record_twin_insight(
        asset_id,
        "Prior adoption evidence changes the working thesis.",
        store=get_account_engagement_store("__operator__"),
    )
    record_twin_insight(
        foreign_id,
        "Foreign secret must not enter the prompt or receipt.",
        store=get_account_engagement_store("other-owner"),
    )
    artifact_id = "recursive-artifact-notes"
    FilesystemArtifactStore().write(
        operator_authority(artifact_id),
        render_html(
            ResearchArtifactBody(
                investigation_id=artifact_id,
                problem_question="Prior research",
                source_event_ids=["evt-artifact-source"],
                agent_notes=["Artifact note preserves a contrary interpretation."],
            )
        ),
    )
    root = _make_approved_plan(client, ("Assess adoption evidence",))
    consuming_loop = cr.make_contract_gather_stub(steps=1, cost_per_step=0.0)
    consuming_loop.consumes_prompt_context = True
    monkeypatch.setattr(cr, "_research_loop_factory", lambda **_kwargs: consuming_loop)
    launched = client.post(
        f"/research/plans/{root}/launch",
        json={
            **STUB_LAUNCH,
            "recursive_asset_ids": [asset_id, foreign_id],
            "recursive_artifact_ids": [artifact_id],
        },
        headers=LAUNCH_HEADERS,
    )
    assert launched.status_code == 200, launched.text
    body = launched.json()
    _poll_until_terminal(client, body["session_id"])
    leaf_id = body["researches"][0]["investigation_id"]
    pack_event = next(
        row for row in trajectory(leaf_id) if row["action_type"] == "context_pack.assembled"
    )
    receipt = pack_event["payload"]["recursive_context"]
    assert len(receipt["included_units"]) == 2
    assert {unit["authority"] for unit in receipt["included_units"]} == {
        "engagement_twin",
        "artifact_note",
    }
    assert "Prior adoption evidence" not in json.dumps(receipt)
    assert "contrary interpretation" not in json.dumps(receipt)
    assert "Foreign secret" not in json.dumps(pack_event)


def test_production_exa_factory_marks_real_reasoning_consumer(monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")
    loop = cr._research_loop_factory()
    assert getattr(loop, "consumes_prompt_context", False) is True


def test_recursive_outcome_resolves_server_receipt_and_supports_opt_out(client):
    from pathlib import Path

    from substrate.context_pack import LayerSource, build_canonical_recursive_pack
    from substrate.context_pack.knowledge_reuse import assemble_context_pack_with_reuse
    from substrate.engagement_spine import InMemoryEngagementStore, record_twin_insight
    from substrate.event_log import emit_typed
    from substrate.investigation_tenancy import InvestigationAuthority, bind_legacy_stream_lease
    from substrate.multi_user.auth import operator_claims
    from substrate.schemas import DispatchCallPayload

    store = InMemoryEngagementStore()
    record_twin_insight("asset", "Private unit prose.", store=store)
    recursive_pack = build_canonical_recursive_pack(
        store=store,
        owner_user_id="__operator__",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "__operator__",
        goal="private unit",
    )
    investigation_id = "inv-recursive-outcome-api"
    bind_legacy_stream_lease(
        InvestigationAuthority(
            operator_claims().user_id,
            investigation_id,
            Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]),
        ),
        provenance="test_recursive_outcome_start",
    )
    assembled = assemble_context_pack_with_reuse(
        role="user_agent",
        investigation_id=investigation_id,
        layers=[LayerSource(kind="session", source="question", content="Question")],
        units=[],
        include_reuse=False,
        recursive_notes_pack=recursive_pack,
    ).pack
    assert assembled.event_id
    dispatch_event_id = emit_typed(
        investigation_id,
        DispatchCallPayload(
            provider="fake",
            model="fake-model",
            tier="pro",
            target_role="user_agent",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0,
            latency_ms=1,
            prompt_hash="sha256:test",
            context_pack_event_id=assembled.event_id,
        ),
        role="user_agent",
        policy_id="fake/fake-model",
    )
    response = client.post(
        "/research/recursive-context/outcomes",
        json={
            "observation_id": "explicit-save-1",
            "investigation_id": investigation_id,
            "context_pack_event_id": assembled.event_id,
            "outcome": "saved",
        },
    )
    assert response.status_code == 200, response.text
    receipt = response.json()["receipt"]
    assert receipt["dispatch_event_id"] == dispatch_event_id
    assert receipt["outcome"] == "saved"
    assert receipt["signal_source"] == "explicit_user"
    assert "Private unit prose" not in json.dumps(response.json())
    duplicate = client.post(
        "/research/recursive-context/outcomes",
        json={
            "observation_id": "explicit-save-1",
            "investigation_id": investigation_id,
            "context_pack_event_id": assembled.event_id,
            "outcome": "saved",
        },
    )
    assert duplicate.status_code == 200
    foreign_pack = build_canonical_recursive_pack(
        store=store,
        owner_user_id="other-owner",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "other-owner",
        goal="private unit",
    )
    foreign_investigation = "inv-recursive-outcome-foreign"
    foreign_context = assemble_context_pack_with_reuse(
        role="user_agent",
        investigation_id=foreign_investigation,
        layers=[LayerSource(kind="session", source="question", content="Question")],
        units=[],
        include_reuse=False,
        recursive_notes_pack=foreign_pack,
    ).pack
    assert foreign_context.event_id
    emit_typed(
        foreign_investigation,
        DispatchCallPayload(
            provider="fake",
            model="fake-model",
            tier="pro",
            target_role="user_agent",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0,
            latency_ms=1,
            prompt_hash="sha256:foreign",
            context_pack_event_id=foreign_context.event_id,
        ),
        role="user_agent",
        policy_id="fake/fake-model",
    )
    foreign = client.post(
        "/research/recursive-context/outcomes",
        json={
            "observation_id": "foreign-save-1",
            "investigation_id": foreign_investigation,
            "context_pack_event_id": foreign_context.event_id,
            "outcome": "saved",
        },
    )
    assert foreign.status_code == 404
    deleted = client.delete("/research/recursive-context/outcomes")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted_receipt_count": 1, "opted_out": True}


# --------------------------------------------------------------------------
# SPR-05 B1 — the cascade fan-out is VISIBLE in the monitor's data source.
#
# MyResearch sources from GET /investigations. Before the fix, that endpoint
# only discovered ``inv-`` files, so a launched cascade's session + leaves
# (``session-…`` / ``…-leaf-N``) NEVER appeared — exactly the "launch N in one
# window" the sprint exists for. This test drives the REAL HTTP launch path
# and asserts the leaves show up in GET /investigations grouped under the
# session (parent_investigation_id == session_id), connecting the launch path
# to the monitor's data source — not hand-built rows.
# --------------------------------------------------------------------------


def test_launched_cascade_appears_in_investigations_grouped_under_session(client):
    root = _make_approved_plan(client, ("alpha", "beta", "gamma"))
    r = client.post(
        f"/research/plans/{root}/launch",
        json={**STUB_LAUNCH, "per_research_budget_usd": 1.0},
        headers=LAUNCH_HEADERS,
    )
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _poll_until_terminal(client, sid)

    rows = client.get("/investigations", params={"limit": 200}).json()["investigations"]
    by_id = {row["investigation_id"]: row for row in rows}

    # All three leaves are present…
    leaf_ids = [f"{sid}-leaf-{i}" for i in range(3)]
    for lid in leaf_ids:
        assert lid in by_id, f"cascade leaf {lid} missing from the monitor list"
        # …grouped under the session (the link the monitor groups by)…
        assert by_id[lid]["parent_investigation_id"] == sid, by_id[lid]
        # …carrying the leaf's sub-question (so the row is not "Untitled")…
        assert by_id[lid]["question"] in ("alpha", "beta", "gamma"), by_id[lid]
        # …and a real terminal status, not stuck "working".
        assert by_id[lid]["status"] == "completed", by_id[lid]

    # The session parent is itself a row (so the group has a head to nest
    # under), discovered despite carrying no ``inv-`` prefix.
    assert sid in by_id, "cascade session parent missing from the monitor list"


# --------------------------------------------------------------------------
# SPR-05 B2 — a budget-halted research does NOT read as "working" forever.
#
# host_local emits investigation.chase_halted (no terminal completed/failed)
# on a budget halt. The list endpoint must treat that as terminal — matching
# cascade_session.reconstruct_session's BUDGET_HALTED — so the monitor shows
# it as "stopped", never a research that runs forever.
# --------------------------------------------------------------------------


def test_budget_halted_cascade_is_not_working_in_investigations(client):
    # A tiny aggregate cap: the per-research demo loop spends ~0.03 (3×0.01),
    # so a cap below the second research's launch forces a chase-halt that the
    # monitor must surface as terminal, not running.
    root = _make_approved_plan(client, ("a", "b", "c", "d"))
    r = client.post(
        f"/research/plans/{root}/launch",
        json={**STUB_LAUNCH, "per_research_budget_usd": 1.0, "aggregate_budget_usd": 0.04},
        headers=LAUNCH_HEADERS,
    )
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _poll_until_terminal(client, sid)

    rows = client.get("/investigations", params={"limit": 200}).json()["investigations"]
    cascade_rows = [x for x in rows if x["investigation_id"].startswith(sid)]
    assert cascade_rows, "cascade researches missing from the monitor list"

    # Not one cascade research is left reading "working"/running — every one is
    # terminal (completed for those that fit the cap, stopped for the halted).
    assert all(x["status"] != "in_progress" for x in cascade_rows), cascade_rows
    # At least one was budget-halted and surfaces as the honest stopped state
    # (the aggregate cap is small enough to halt a launch).
    assert any(x["status"] == "stopped" for x in cascade_rows), cascade_rows
    # The halted state agrees with the reconstruct path (the honest one).
    from orchestration.cascade_session import reconstruct_session

    rec = reconstruct_session(sid)
    halted = {r.investigation_id for r in rec.researches if r.state == "budget_halted"}
    listed_stopped = {x["investigation_id"] for x in cascade_rows if x["status"] == "stopped"}
    assert halted <= listed_stopped, (halted, listed_stopped)


# --------------------------------------------------------------------------
# SPR-05 MINOR — a stopped research surfaces as "stopped", not "done".
#
# Stop/cancel finishes through investigation.completed with outcome=stopped/
# cancelled. The list endpoint must read the outcome so the spec's "stop one;
# reload" gate shows it honestly, not as a completed research.
# --------------------------------------------------------------------------


def test_stopped_research_surfaces_as_stopped_not_done(client):
    from pathlib import Path

    from substrate.event_log import log_event
    from substrate.investigation_tenancy import InvestigationAuthority, bind_legacy_stream_lease
    from substrate.multi_user.auth import operator_claims
    from substrate.schemas import ActionType

    # Synthesize the exact event trail host_local writes for a stopped run:
    # start_requested → completed{outcome: stopped}. (The mid-flight stop path
    # itself is covered by test_steer_endpoint_wiring + the runner unit; here we
    # pin that the LIST endpoint reads the outcome, the M1-vocabulary gap.)
    iid = "inv-stopped-001"
    bind_legacy_stream_lease(
        InvestigationAuthority(
            operator_claims().user_id,
            iid,
            Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]),
        ),
        provenance="test_event_start",
    )
    log_event(
        iid,
        ActionType.INVESTIGATION_START_REQUESTED,
        payload={"question": "A question the operator stopped"},
        role="user_agent",
    )
    log_event(
        iid, ActionType.INVESTIGATION_COMPLETED, payload={"outcome": "stopped"}, role="user_agent"
    )

    rows = client.get("/investigations", params={"limit": 200}).json()["investigations"]
    row = next(x for x in rows if x["investigation_id"] == iid)
    assert row["status"] == "stopped", row
    # And the status filter narrows to it.
    stopped = client.get("/investigations", params={"status": "stopped"}).json()["investigations"]
    assert any(x["investigation_id"] == iid for x in stopped), stopped


# --------------------------------------------------------------------------
# Steer (slow loop so the command lands mid-flight)
# --------------------------------------------------------------------------


def test_steer_endpoint_wiring(client):
    # Endpoint contract: routes the command, safe no-op on a terminal
    # research, 400 on a bad command, 404 on a dead session. The mid-flight
    # steer *isolation* (one research stops, siblings continue) is proven
    # deterministically at the service layer in test_parallel_orchestration —
    # re-testing that timing through a request/response harness that does not
    # run a continuous loop would be flaky, not rigorous.
    root = _make_approved_plan(client, ("a", "b"))
    sid = client.post(
        f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=LAUNCH_HEADERS
    ).json()["session_id"]
    _poll_until_terminal(client, sid)
    iid = f"{sid}-leaf-0"
    # A command to a finished research is a safe no-op (200), not a crash.
    r = client.post(f"/research/sessions/{sid}/researches/{iid}/steer", json={"kind": "stop"})
    assert r.status_code == 200, r.text
    # Unknown command → 400.
    r = client.post(f"/research/sessions/{sid}/researches/{iid}/steer", json={"kind": "explode"})
    assert r.status_code == 400
    # Dead session → 404.
    r = client.post("/research/sessions/no-such-session/researches/x/steer", json={"kind": "stop"})
    assert r.status_code == 404


# --------------------------------------------------------------------------
# Durable recovery from the event log (session evicted / restart)
# --------------------------------------------------------------------------


def test_session_reconstructs_after_eviction(client):
    root = _make_approved_plan(client, ("a", "b"))
    sid = client.post(
        f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=LAUNCH_HEADERS
    ).json()["session_id"]
    _poll_until_terminal(client, sid)
    # Simulate a restart: drop the in-memory session.
    cr._SESSIONS.pop(sid, None)
    r = client.get(f"/research/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["live"] is False
    assert {x["investigation_id"] for x in body["researches"]} == {f"{sid}-leaf-0", f"{sid}-leaf-1"}
    assert body["all_terminal"] is True


# --------------------------------------------------------------------------
# SSE stream smoke
# --------------------------------------------------------------------------


def test_session_stream_emits_events(client):
    root = _make_approved_plan(client, ("a",))
    sid = client.post(
        f"/research/plans/{root}/launch", json=STUB_LAUNCH, headers=LAUNCH_HEADERS
    ).json()["session_id"]
    kinds = []
    with client.stream("GET", f"/research/sessions/{sid}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if not line:
                continue
            text = line if isinstance(line, str) else line.decode()
            if text.startswith("data: "):
                kinds.append(json.loads(text[len("data: ") :]).get("kind"))
            if kinds and kinds[-1] == "session_done":
                break
    assert "session_done" in kinds
    assert any(k in ("plan", "step", "note", "status") for k in kinds)


def test_prod_research_loop_factory_uses_contract_gather_stub():
    """ANT-DRL-04: prod factory must not return make_demo_loop."""
    import inspect

    src = inspect.getsource(cr._research_loop_factory)
    assert "make_contract_gather_stub" in src
    assert "make_demo_loop" not in src
    assert callable(cr._research_loop_factory())
