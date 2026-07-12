"""API tests for engagement spine routes (process-local store MVP)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from substrate.engagement_spine import record_twin_insight  # noqa: E402


def _operator_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def attach_operator(request: Request, call_next):
        request.state.user_id = "__operator__"
        request.state.auth_method = "test_operator"
        return await call_next(request)

    return app


@pytest.fixture
def client():
    reset_engagement_stores()
    app = _operator_app()
    register_engagement_routes(app)
    return TestClient(app)


def test_spawn_attach_context_collective(client):
    r = client.post(
        "/engagement/spawn-from-highlight",
        json={
            "asset_id": "paper-1",
            "selection_text": "Attention is all you need.",
            "region_id": "r1",
            "references": ["https://arxiv.org/abs/1706.03762"],
            "model_id": "glm-test",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spawn_id"].startswith("spn_")
    assert body["view_format"] == "html"
    assert len(body["source_references"]) == 1
    spawn_id = body["spawn_id"]

    r2 = client.post(
        "/engagement/attach-refs",
        json={
            "spawn_id": spawn_id,
            "references": ["https://research.substack.com/p/attention"],
        },
    )
    assert r2.status_code == 200
    assert len(r2.json()["source_references"]) == 2
    # Residual (ko): attach-refs surfaces reserved spawn research_tier.
    assert r2.json().get("research_tier") in ("fast", "deep", "wrestle")

    # Seed a twin into the process store for promote path
    record_twin_insight(
        "paper-1",
        "Self-attention is content-addressed routing.",
        store=eng_mod._eng(),
    )

    r3 = client.post(
        "/engagement/research-context",
        json={"asset_id": "paper-1", "spawn_id": spawn_id},
    )
    assert r3.status_code == 200
    ctx = r3.json()
    assert ctx["view_format"] == "html"
    assert ctx["twin_count"] >= 1
    assert ctx["ref_count"] == 2
    assert "prompt_block" in ctx
    assert "Self-attention" in ctx["prompt_block"]

    # Second spawn for collective
    r4 = client.post(
        "/engagement/spawn-from-highlight",
        json={
            "asset_id": "paper-2",
            "selection_text": "Residual learning.",
            "region_id": "r2",
            "references": ["https://arxiv.org/abs/1512.03385"],
        },
    )
    spawn2 = r4.json()["spawn_id"]
    r5 = client.post(
        "/engagement/collective",
        json={"spawn_ids": [spawn_id, spawn2], "include_twin_promote": True},
    )
    assert r5.status_code == 200
    col = r5.json()
    assert col["collective_id"].startswith("col_")
    assert col["spawn_count"] == 2
    assert "prompt_block" in col
    # Residual (oi): multi-spawn collective feeds Antiek-bench recursive rewrite.
    assert "usage_event" in col
    assert col["usage_event"]["source"] == "collective_merge"
    assert col["usage_event"]["outcome"] == "worked"
    assert col["usage_event"]["task_class"] in (
        "synthesize",
        "distill",
        "wrestle",
        "book_qa",
    )


def test_session_open_and_flywheel(client):
    r = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "book-x",
            "selection_text": "A passage worth deep research.",
            "region_id": "bx1",
            "references": ["2402.03300"],
            "view_mode": "floating",
            "research_tier": "wrestle",
        },
    )
    assert r.status_code == 200
    open_body = r.json()
    session_id = open_body["session_id"]
    assert session_id.startswith("fsess_")
    # Residual (ji): open echoes research_tier when provided.
    assert open_body.get("research_tier") == "wrestle"
    # Residual (nw): session open feeds Antiek-bench (floating_deep_research).
    assert "usage_event" in open_body
    assert open_body["usage_event"]["outcome"] == "worked"
    assert open_body["usage_event"]["task_class"] == "wrestle"
    assert open_body["usage_event"]["source"] == "floating_deep_research"

    r2 = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": session_id,
            "output_text": "Analysis complete.",
            "insights": ["Finding from deep research session."],
            "questions": ["What remains open?"],
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "complete"
    assert body["view_format"] == "html"
    assert body["context"]["twin_count"] >= 1
    assert "prompt_block" in body
    assert "usage_event" in body
    assert body["usage_event"]["outcome"] == "worked"
    # Residual (jt): wrestle session → wrestle bench task_class (not distill).
    assert body.get("research_tier") == "wrestle"
    assert body["usage_event"].get("task_class") == "wrestle"


def test_session_workstation_lifecycle_collective_and_merge(client):
    def open_session(asset: str, region: str, text: str) -> str:
        response = client.post(
            "/engagement/sessions/open",
            json={
                "asset_id": asset,
                "selection_text": text,
                "region_id": region,
                "references": ["https://arxiv.org/abs/1706.03762"],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["session_id"]

    first = open_session("asset-a", "r1", "<script>alert(1)</script> first")
    second = open_session("asset-a", "r2", "second")
    foreign = open_session("asset-b", "r3", "foreign")

    listed = client.get("/engagement/sessions/asset/asset-a")
    assert listed.status_code == 200
    assert listed.json()["count"] == 2
    assert [row["session_id"] for row in listed.json()["sessions"]] == sorted(
        [first, second]
    )

    projected = client.get(f"/engagement/sessions/{first}")
    assert projected.status_code == 200
    assert projected.json()["view_format"] == "html"
    assert "<script>alert(1)</script>" not in projected.json()["html"]

    full = client.put(
        f"/engagement/sessions/{first}/view",
        json={"mode": "full", "expected_mode": "floating"},
    )
    assert full.status_code == 200
    assert full.json()["view_mode"] == "full"
    replay = client.put(
        f"/engagement/sessions/{first}/view",
        json={"mode": "full", "expected_mode": "floating"},
    )
    assert replay.status_code == 200
    stale = client.put(
        f"/engagement/sessions/{first}/view",
        json={"mode": "floating", "expected_mode": "floating"},
    )
    assert stale.status_code == 409

    completed_ids = (first, second, foreign)
    for session_id in completed_ids:
        done = client.post(
            "/engagement/sessions/complete-flywheel",
            json={
                "session_id": session_id,
                "output_text": f"Research output for {session_id}",
                "insights": [f"Insight from {session_id}"],
                "questions": [f"Question from {session_id}?"],
            },
        )
        assert done.status_code == 200, done.text

    context = client.post(
        "/engagement/sessions/context",
        json={
            "session_id": first,
            "include_twin_preview": True,
            "include_prompt_block": True,
            "include_html": True,
        },
    )
    assert context.status_code == 200, context.text
    assert context.json()["twin_count"] >= 1
    assert "prompt_block" in context.json()
    assert "html" in context.json()
    assert context.json()["twin_context_mode"] == "preview_non_mutating"

    refused = client.post(
        "/engagement/sessions/collective",
        json={"session_ids": [first, foreign]},
    )
    assert refused.status_code == 400
    collective = client.post(
        "/engagement/sessions/collective",
        json={
            "session_ids": [first, foreign],
            "allow_cross_asset": True,
            "include_twin_preview": True,
            "include_prompt_block": True,
        },
    )
    assert collective.status_code == 200, collective.text
    assert collective.json()["spawn_count"] == 2
    assert set(collective.json()["asset_ids"]) == {"asset-a", "asset-b"}
    assert collective.json()["source_session_ids"] == [first, foreign]

    eng_mod._eng().put_document(
        "asset-a",
        {
            "document_id": "asset-a",
            "title": "Parent",
            "body_text": "Authoritative parent body.",
            "license": "operator-owned",
            "revision": 7,
        },
    )
    draft = client.post(
        "/engagement/sessions/merge",
        json={"parent_asset_id": "asset-a", "session_ids": [first, second]},
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["mode"] == "draft_combined"
    assert draft.json()["draft_leaves_parent"] is True
    assert eng_mod._eng().get_document("asset-a")["body_text"] == (
        "Authoritative parent body."
    )
    unconfirmed = client.post(
        "/engagement/sessions/merge",
        json={
            "parent_asset_id": "asset-a",
            "session_ids": [first],
            "mode": "into_parent",
        },
    )
    assert unconfirmed.status_code == 400
    parent_revision = draft.json()["parent_revision_sha256"]
    committed = client.post(
        "/engagement/sessions/merge",
        json={
            "parent_asset_id": "asset-a",
            "session_ids": [first, second],
            "mode": "into_parent",
            "confirm_parent_write": True,
            "expected_parent_sha256": parent_revision,
            "idempotency_key": "merge-lifecycle-001",
        },
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["document_id"] == "asset-a"
    parent_after = eng_mod._eng().get_document("asset-a")
    assert parent_after is not None
    assert parent_after["license"] == "operator-owned"
    assert parent_after["revision"] == 7
    replay = client.post(
        "/engagement/sessions/merge",
        json={
            "parent_asset_id": "asset-a",
            "session_ids": [first, second],
            "mode": "into_parent",
            "confirm_parent_write": True,
            "expected_parent_sha256": parent_revision,
            "idempotency_key": "merge-lifecycle-001",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["merge_receipt_id"] == committed.json()["merge_receipt_id"]
    assert replay.json()["result_parent_sha256"] == committed.json()[
        "result_parent_sha256"
    ]


def test_session_workstation_contract_rejects_unsafe_shapes(client):
    unknown = client.get("/engagement/sessions/../../secret")
    assert unknown.status_code in {400, 404}
    extra = client.post(
        "/engagement/sessions/context",
        json={"session_id": "fsess_0123456789abcdef", "unexpected": True},
    )
    assert extra.status_code == 422
    duplicate = client.post(
        "/engagement/sessions/collective",
        json={
            "session_ids": [
                "fsess_0123456789abcdef",
                "fsess_0123456789abcdef",
            ]
        },
    )
    assert duplicate.status_code == 422

    opened = client.post(
        "/engagement/sessions/open",
        json={"asset_id": "parent-safe", "selection_text": "unfinished"},
    )
    assert opened.status_code == 200
    session_id = opened.json()["session_id"]
    incomplete = client.post(
        "/engagement/sessions/merge",
        json={"parent_asset_id": "parent-safe", "session_ids": [session_id]},
    )
    assert incomplete.status_code == 400

    row = eng_mod._sess().get_session(session_id)
    assert row is not None
    row["parent_asset_id"] = "tampered-parent"
    eng_mod._sess().put_session(row)
    integrity = client.get(f"/engagement/sessions/{session_id}")
    assert integrity.status_code == 409


def test_session_open_twin_chase_usage_source(client):
    """Residual (nw): Twin chase goal_hint → usage source=twin_chase."""
    r = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "paper-y",
            "selection_text": "[question] What follows?\n\n[insight] Claim X",
            "goal_hint": "Twin chase on paper-y: 2 note(s) (questions=1, insights=1) · note_ids=q1,i1",
            "view_mode": "floating",
            "research_tier": "deep",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("research_tier") == "deep"
    assert body["usage_event"]["source"] == "twin_chase"
    assert body["usage_event"]["task_class"] == "synthesize"
    assert body["usage_event"]["outcome"] == "worked"
    assert body["usage_event"]["prompt_hint_present"] is True
    assert "prompt_hint" not in body["usage_event"]


def test_session_open_highlight_dr_launch_usage_source(client):
    """Residual (asu/asv): highlighted passage/synthesis goal_hint → highlight_dr_launch."""
    r = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "doc-read",
            "selection_text": "Attention is content-addressable memory.",
            "goal_hint": "Deep-research the highlighted passage from reading",
            "view_mode": "floating",
            "research_tier": "deep",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["usage_event"]["source"] == "highlight_dr_launch"
    assert body["usage_event"]["task_class"] == "synthesize"
    assert body["usage_event"]["outcome"] == "worked"
    assert body["usage_event"]["prompt_hint_present"] is True
    assert "prompt_hint" not in body["usage_event"]

    # Residual (asv): ResearchWorkstation HighlightToolbar synthesis path.
    r2 = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "synth-1",
            "selection_text": "Synthesis claim under test.",
            "goal_hint": "Deep-research the highlighted synthesis passage",
            "view_mode": "full",
            "research_tier": "wrestle",
        },
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["usage_event"]["source"] == "highlight_dr_launch"
    assert body2["usage_event"]["task_class"] == "wrestle"


def test_attach_unknown_spawn_404(client):
    r = client.post(
        "/engagement/attach-refs",
        json={"spawn_id": "spn_missing", "references": ["1706.03762"]},
    )
    assert r.status_code == 404


def test_spawn_rejects_empty_selection(client):
    r = client.post(
        "/engagement/spawn-from-highlight",
        json={"asset_id": "a", "selection_text": "  "},
    )
    assert r.status_code == 400


def test_durable_file_store_survives_reset_rebuild(tmp_path, monkeypatch):
    """ANTIEK_ENGAGEMENT_DIR → FileEngagementStore; data survives store rebuild."""
    monkeypatch.setenv("ANTIEK_ENGAGEMENT_DIR", str(tmp_path / "eng-data"))
    reset_engagement_stores()
    app = _operator_app()
    register_engagement_routes(app)
    c = TestClient(app)
    r = c.post(
        "/engagement/spawn-from-highlight",
        json={
            "asset_id": "durable-asset",
            "selection_text": "durable passage",
            "region_id": "d1",
            "references": ["1706.03762"],
        },
    )
    assert r.status_code == 200
    spawn_id = r.json()["spawn_id"]

    # Rebuild stores from same dir (simulates process restart)
    reset_engagement_stores()
    app2 = _operator_app()
    register_engagement_routes(app2)
    c2 = TestClient(app2)
    r2 = c2.post(
        "/engagement/attach-refs",
        json={"spawn_id": spawn_id, "references": ["https://x.substack.com/p/y"]},
    )
    assert r2.status_code == 200, r2.text
    kinds = {ref["kind"] for ref in r2.json()["source_references"]}
    assert "arxiv" in kinds
    assert "substack" in kinds


def test_session_routes_isolate_authenticated_owners():
    reset_engagement_stores()
    app = FastAPI()

    @app.middleware("http")
    async def attach_test_owner(request: Request, call_next):
        request.state.user_id = request.headers.get("x-test-owner", "__operator__")
        return await call_next(request)

    register_engagement_routes(app)
    c = TestClient(app)

    def open_for(owner: str) -> dict:
        response = c.post(
            "/engagement/sessions/open",
            headers={"x-test-owner": owner},
            json={
                "asset_id": "shared-logical-asset",
                "selection_text": "same highlighted passage",
                "region_id": "same-region",
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    alice = open_for("alice")
    bob = open_for("bob")
    assert alice["session_id"] != bob["session_id"]
    assert alice["spawn_id"] != bob["spawn_id"]
    assert alice["owner_id"] == "alice"
    assert bob["owner_id"] == "bob"

    hidden = c.get(
        f"/engagement/sessions/{alice['session_id']}",
        headers={"x-test-owner": "bob"},
    )
    assert hidden.status_code == 404
    alice_list = c.get(
        "/engagement/sessions/asset/shared-logical-asset",
        headers={"x-test-owner": "alice"},
    ).json()
    bob_list = c.get(
        "/engagement/sessions/asset/shared-logical-asset",
        headers={"x-test-owner": "bob"},
    ).json()
    assert [row["session_id"] for row in alice_list["sessions"]] == [
        alice["session_id"]
    ]
    assert [row["session_id"] for row in bob_list["sessions"]] == [bob["session_id"]]

    for owner, session, insight in (
        ("alice", alice, "alice private finding"),
        ("bob", bob, "bob private finding"),
    ):
        completed = c.post(
            "/engagement/sessions/complete-flywheel",
            headers={"x-test-owner": owner},
            json={
                "session_id": session["session_id"],
                "output_text": insight,
                "insights": [insight],
            },
        )
        assert completed.status_code == 200, completed.text
    alice_context = c.post(
        "/engagement/sessions/context",
        headers={"x-test-owner": "alice"},
        json={"session_id": alice["session_id"], "include_twin_preview": True},
    ).json()
    context_text = str(alice_context["twin_units"])
    assert "alice private finding" in context_text
    assert "bob private finding" not in context_text
    legacy_bypass = c.post(
        "/engagement/merge",
        headers={"x-test-owner": "alice"},
        json={
            "parent_asset_id": "shared-logical-asset",
            "spawn_ids": [alice["spawn_id"]],
        },
    )
    assert legacy_bypass.status_code == 403


def test_session_routes_require_explicit_identity(monkeypatch):
    monkeypatch.delenv("ANTIEK_ALLOW_UNAUTHENTICATED_LOCAL", raising=False)
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    response = TestClient(app).post(
        "/engagement/sessions/open",
        json={"asset_id": "asset", "selection_text": "passage"},
    )
    assert response.status_code == 401


def test_ownerless_legacy_session_is_quarantined(client):
    session_id = "fsess_3333333333333333"
    eng_mod._sess().put_session(
        {
            "session_id": session_id,
            "parent_asset_id": "legacy-asset",
            "spawn_id": "spn_legacy",
            "investigation_id": "inv_legacy",
            "status": "reserved",
            "view_mode": "floating",
        }
    )
    response = client.get(f"/engagement/sessions/{session_id}")
    assert response.status_code == 409
    assert response.json()["detail"] == "session ownership requires reconciliation"


def test_session_capability_parity_is_owner_native():
    reset_engagement_stores()
    app = FastAPI()

    @app.middleware("http")
    async def attach_test_owner(request: Request, call_next):
        request.state.user_id = request.headers.get("x-test-owner", "")
        return await call_next(request)

    register_engagement_routes(app)
    c = TestClient(app)

    def open_for(owner: str) -> dict:
        response = c.post(
            "/engagement/sessions/open",
            headers={"x-test-owner": owner},
            json={
                "asset_id": "shared-capability-asset",
                "selection_text": "same passage",
                "region_id": "same-capability-region",
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    alice = open_for("alice")
    bob = open_for("bob")
    alice_headers = {"x-test-owner": "alice"}
    bob_headers = {"x-test-owner": "bob"}

    attached = c.post(
        f"/engagement/sessions/{alice['session_id']}/references",
        headers=alice_headers,
        json={"references": ["1706.03762"], "hydrate": True},
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["source_references"][0]["kind"] == "arxiv"
    assert attached.json()["hydrated_assets"][0]["view_format"] == "html"

    seeded_progress = c.post(
        f"/engagement/sessions/{alice['session_id']}/progress/seed",
        headers=alice_headers,
    )
    assert seeded_progress.status_code == 200
    appended = c.post(
        f"/engagement/sessions/{alice['session_id']}/progress",
        headers=alice_headers,
        json={"stage": "complete", "message": "Alice finished"},
    )
    assert appended.status_code == 200
    assert appended.json()["event_count"] == 5
    bob_progress = c.get(
        f"/engagement/sessions/{bob['session_id']}/progress",
        headers=bob_headers,
    )
    assert bob_progress.json()["event_count"] == 0

    seeded_twins = c.post(
        f"/engagement/sessions/{alice['session_id']}/twins/seed",
        headers=alice_headers,
        json={"title": "Alice source", "body_text": "Alice private body"},
    )
    assert seeded_twins.status_code == 200
    recorded = c.post(
        f"/engagement/sessions/{alice['session_id']}/twins",
        headers=alice_headers,
        json={"kind": "insight", "text": "Alice capability insight"},
    )
    assert recorded.status_code == 200
    alice_twins = c.get(
        f"/engagement/sessions/{alice['session_id']}/twins",
        headers=alice_headers,
    ).json()
    bob_twins = c.get(
        f"/engagement/sessions/{bob['session_id']}/twins",
        headers=bob_headers,
    ).json()
    assert any(note["text"] == "Alice capability insight" for note in alice_twins["notes"])
    assert bob_twins["note_count"] == 0

    preview = c.post(
        f"/engagement/sessions/{alice['session_id']}/twins/promote-preview",
        headers=alice_headers,
        json={"query": "Alice"},
    )
    assert preview.status_code == 200
    assert preview.json()["twin_context_mode"] == "preview_non_mutating"
    evidence = c.get(
        f"/engagement/sessions/{alice['session_id']}/evidence",
        headers=alice_headers,
    )
    assert evidence.status_code == 200
    assert evidence.json()["ref_count"] == 1
    assert evidence.json()["insight_count"] >= 1
    searched = c.post(
        f"/engagement/sessions/{alice['session_id']}/context-search",
        headers=alice_headers,
        json={"query": "capability"},
    )
    assert searched.status_code == 200
    assert searched.json()["hit_count"] >= 1

    foreign = c.get(
        f"/engagement/sessions/{alice['session_id']}/evidence",
        headers=bob_headers,
    )
    assert foreign.status_code == 404


def test_confirmed_merge_recovers_after_parent_write_before_receipt_settle(
    client, monkeypatch
):
    opened = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "crash-parent",
            "selection_text": "receipt crash seam",
            "region_id": "crash-region",
        },
    ).json()
    session_id = opened["session_id"]
    done = client.post(
        "/engagement/sessions/complete-flywheel",
        json={"session_id": session_id, "output_text": "finished research"},
    )
    assert done.status_code == 200
    draft = client.post(
        "/engagement/sessions/merge",
        json={"parent_asset_id": "crash-parent", "session_ids": [session_id]},
    ).json()

    store = eng_mod._receipts()
    real_settle = store.settle
    calls = 0

    def crash_once(receipt_id: str, material_sha256: str, result_sha256: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected crash after parent CAS")
        return real_settle(receipt_id, material_sha256, result_sha256)

    monkeypatch.setattr(store, "settle", crash_once)
    body = {
        "parent_asset_id": "crash-parent",
        "session_ids": [session_id],
        "mode": "into_parent",
        "confirm_parent_write": True,
        "expected_parent_sha256": draft["parent_revision_sha256"],
        "idempotency_key": "crash-recovery-key",
    }
    with pytest.raises(RuntimeError, match="injected crash"):
        client.post("/engagement/sessions/merge", json=body)

    recovered = client.post("/engagement/sessions/merge", json=body)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["merge_receipt_state"] == "applied"
    assert recovered.json()["result_parent_sha256"] == recovered.json()[
        "document_sha256"
    ]
