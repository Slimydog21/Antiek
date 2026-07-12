"""API tests for engagement spine routes (process-local store MVP)."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

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
from processing.embedding import (  # noqa: E402
    _reset_default_provider,
    set_default_embedding_provider,
)
from runtime.db_lock import connect_read  # noqa: E402
from substrate.engagement_spine import record_twin_insight  # noqa: E402
from substrate.graph_per_user.runtime import (  # noqa: E402
    owner_graph_db_path,
    owner_graph_events_dir,
)


class _PromotionEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [byte / 255.0 for byte in digest[: self.dimension]]


class _FailSecondPromotionEmbedding(_PromotionEmbedding):
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, text: str) -> list[float]:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("injected second-note embedding failure")
        return super().encode(text)


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
    assert [row["session_id"] for row in listed.json()["sessions"]] == sorted([first, second])

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
    assert eng_mod._eng().get_document("asset-a")["body_text"] == ("Authoritative parent body.")
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
    assert replay.json()["result_parent_sha256"] == committed.json()["result_parent_sha256"]


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


def test_owned_collective_discovery_pages_canonical_rows(client):
    unit_ids: list[str] = []
    for index in range(2):
        material = {
            "owner_id": "__operator__",
            "source_session_ids": ["fsess_1111111111111111"],
            "query": f"unit-{index}",
            "unit": {
                "asset_ids": ["asset"],
                "spawn_count": 0,
                "twin_count": 0,
                "ref_count": 0,
                "output_count": 0,
                "recommended_research_tier": "deep",
            },
        }
        preview_sha = eng_mod.collective_preview_sha256(material)
        unit_id = f"cunit_{preview_sha[:24]}"
        unit_ids.append(unit_id)
        eng_mod._eng().mutate_owned_document(
            unit_id,
            "__operator__",
            lambda _current, uid=unit_id, sha=preview_sha, mat=material: {
                "document_type": "collective_research_unit",
                "collective_unit_id": uid,
                "preview_sha256": sha,
                "created_at": "2026-07-12T00:00:00Z",
                "state": "confirmed",
                "material": mat,
                "html": "<article>unit</article>",
                "view_format": "html",
            },
        )
    unit_ids.sort()
    first_unit = eng_mod._eng().get_owned_document(unit_ids[0], "__operator__")
    assert first_unit is not None
    for index in range(7):
        eng_mod.append_collective_lineage(
            store=eng_mod._eng(),
            owner_id="__operator__",
            unit=first_unit,
            child_kind="written_analysis",
            child_id=f"collective_draft_{index:024x}",
            initial_state="draft",
            created_at=f"2026-07-12T00:00:0{index}Z",
            provenance={"request_sha256": f"request-{index}"},
        )

    first = client.get("/engagement/sessions/collective/owned?limit=1")
    assert first.status_code == 200, first.text
    assert [row["collective_unit_id"] for row in first.json()["collectives"]] == [unit_ids[0]]
    assert first.json()["next_cursor"] == unit_ids[0]
    first_summary = first.json()["collectives"][0]
    assert len(first_summary["lineage"]) == 5
    assert first_summary["lineage_count_is_lower_bound"] is True
    assert first_summary["lineage_next_cursor"].startswith("cedge_")
    next_lineage = client.get(
        f"/engagement/sessions/collective/{unit_ids[0]}/lineage",
        params={"limit": 5, "cursor": first_summary["lineage_next_cursor"]},
    )
    assert next_lineage.status_code == 200, next_lineage.text
    assert next_lineage.json()["count"] == 2
    assert next_lineage.json()["next_cursor"] is None
    second = client.get(
        "/engagement/sessions/collective/owned",
        params={"limit": 1, "cursor": first.json()["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    assert [row["collective_unit_id"] for row in second.json()["collectives"]] == [unit_ids[1]]
    assert second.json()["next_cursor"] is None
    unavailable = client.get(
        "/engagement/sessions/collective/owned",
        params={"cursor": "cunit_ffffffffffffffffffffffff"},
    )
    assert unavailable.status_code == 409
    physical_row = eng_mod._eng().get_owned_document(unit_ids[0], "__operator__")
    assert physical_row is not None
    eng_mod._eng().put_document(unit_ids[0], {**physical_row, "collective_unit_id": unit_ids[1]})
    identity_drift = client.get("/engagement/sessions/collective/owned?limit=1")
    assert identity_drift.status_code == 409
    tampered_material = dict(physical_row["material"])
    eng_mod._eng().put_document(
        unit_ids[0],
        {
            **physical_row,
            "collective_unit_id": unit_ids[0],
            "material": {**tampered_material, "query": "tampered after confirmation"},
        },
    )
    cryptographic_drift = client.get("/engagement/sessions/collective/owned?limit=1")
    assert cryptographic_drift.status_code == 409


def test_confirmed_collective_can_launch_research_and_html_draft(client, monkeypatch):
    session_ids: list[str] = []
    for index, asset in enumerate(("collective-a", "collective-b"), 1):
        opened = client.post(
            "/engagement/sessions/open",
            json={
                "asset_id": asset,
                "selection_text": f"Question {index}",
                "region_id": f"source-{index}",
                "research_tier": "deep",
            },
        )
        assert opened.status_code == 200, opened.text
        session_ids.append(opened.json()["session_id"])
        completed = client.post(
            "/engagement/sessions/complete-flywheel",
            json={
                "session_id": opened.json()["session_id"],
                "output_text": f"<script>hostile {index}</script> research finding",
                "insights": [f"Twin insight {index}"],
                "questions": [],
            },
        )
        assert completed.status_code == 200, completed.text

    preview_request = {
        "session_ids": session_ids,
        "allow_cross_asset": True,
        "include_twin_preview": True,
        "include_prompt_block": True,
        "include_html": True,
    }
    preview = client.post("/engagement/sessions/collective", json=preview_request)
    assert preview.status_code == 200, preview.text
    assert preview.json()["output_count"] == 2
    assert "research finding" in preview.json()["prompt_block"]
    revision = preview.json()["collective_preview_sha256"]

    confirmation = client.post(
        "/engagement/sessions/collective/confirm",
        json={
            **preview_request,
            "expected_preview_sha256": revision,
            "idempotency_key": "collective-confirm-001",
        },
    )
    assert confirmation.status_code == 200, confirmation.text
    unit_id = confirmation.json()["collective_unit_id"]
    assert confirmation.json()["preview_sha256"] == revision
    replay = client.post(
        "/engagement/sessions/collective/confirm",
        json={
            **preview_request,
            "expected_preview_sha256": revision,
            "idempotency_key": "collective-confirm-001",
        },
    )
    assert replay.json()["collective_unit_id"] == unit_id

    append_lineage = eng_mod.append_collective_lineage

    def fail_after_child(**_kwargs):
        raise ValueError("injected child-before-lineage crash")

    monkeypatch.setattr(eng_mod, "append_collective_lineage", fail_after_child)
    interrupted = client.post(
        f"/engagement/sessions/collective/{unit_id}/launch-research",
        json={
            "idempotency_key": "collective-launch-001",
            "anchor_asset_id": "collective-a",
            "view_mode": "floating",
            "research_tier": "wrestle",
        },
    )
    assert interrupted.status_code == 409
    monkeypatch.setattr(eng_mod, "append_collective_lineage", append_lineage)
    launched = client.post(
        f"/engagement/sessions/collective/{unit_id}/launch-research",
        json={
            "idempotency_key": "collective-launch-001",
            "anchor_asset_id": "collective-a",
            "view_mode": "floating",
            "research_tier": "wrestle",
        },
    )
    assert launched.status_code == 200, launched.text
    assert launched.json()["source_collective_id"] == unit_id
    assert launched.json()["source_collective_preview_sha256"] == revision
    launched_replay = client.post(
        f"/engagement/sessions/collective/{unit_id}/launch-research",
        json={
            "idempotency_key": "collective-launch-001",
            "anchor_asset_id": "collective-a",
            "view_mode": "floating",
            "research_tier": "wrestle",
        },
    )
    assert launched_replay.json()["session_id"] == launched.json()["session_id"]
    launch_conflict = client.post(
        f"/engagement/sessions/collective/{unit_id}/launch-research",
        json={
            "idempotency_key": "collective-launch-001",
            "anchor_asset_id": "collective-a",
            "view_mode": "full",
            "research_tier": "wrestle",
        },
    )
    assert launch_conflict.status_code == 409
    bad_anchor = client.post(
        f"/engagement/sessions/collective/{unit_id}/launch-research",
        json={
            "idempotency_key": "collective-launch-002",
            "anchor_asset_id": "not-a-member",
        },
    )
    assert bad_anchor.status_code == 400

    draft = client.post(
        f"/engagement/sessions/collective/{unit_id}/written-analysis",
        json={"idempotency_key": "collective-writing-001"},
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["source_session_ids"] == session_ids
    assert "&lt;script&gt;hostile" in draft.json()["html"]
    assert "<script>hostile" not in draft.json()["html"]
    assert "Twin insight" in draft.json()["html"]
    reopened_draft = client.get(
        f"/engagement/sessions/collective/{unit_id}/written-analysis/{draft.json()['document_id']}"
    )
    assert reopened_draft.status_code == 200, reopened_draft.text
    assert reopened_draft.json()["html"] == draft.json()["html"]

    discovery = client.get("/engagement/sessions/collective/owned?limit=1")
    assert discovery.status_code == 200, discovery.text
    assert discovery.json()["count"] == 1
    assert discovery.json()["collectives"][0]["collective_unit_id"] == unit_id
    assert {edge["child_kind"] for edge in discovery.json()["collectives"][0]["lineage"]} == {
        "research_session",
        "written_analysis",
    }
    assert (
        next(
            edge
            for edge in discovery.json()["collectives"][0]["lineage"]
            if edge["child_kind"] == "research_session"
        )["current_state"]
        == "reserved"
    )

    child_complete = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": launched.json()["session_id"],
            "output_text": "Cohesive child result",
            "insights": [],
            "questions": [],
        },
    )
    assert child_complete.status_code == 200
    detail = client.get(f"/engagement/sessions/collective/{unit_id}")
    assert detail.status_code == 200, detail.text
    research_edge = next(
        edge for edge in detail.json()["lineage"] if edge["child_kind"] == "research_session"
    )
    assert research_edge["current_state"] == "complete"
    assert detail.json()["material"]["source_session_ids"] == session_ids

    source_before = eng_mod._eng().get_owned_spawn(preview.json()["spawn_ids"][0], "__operator__")
    stale = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": session_ids[0],
            "output_text": "Changed after review",
            "insights": [],
            "questions": [],
        },
    )
    assert stale.status_code == 200
    refused = client.post(
        "/engagement/sessions/collective/confirm",
        json={
            **preview_request,
            "expected_preview_sha256": revision,
            "idempotency_key": "collective-confirm-stale",
        },
    )
    assert refused.status_code == 409
    assert source_before is not None

    oversized = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": session_ids[0],
            "output_text": "x" * 500_001,
            "insights": [],
            "questions": [],
        },
    )
    assert oversized.status_code == 422
    lineage_id = f"collective_lineage_{unit_id}"
    lineage = eng_mod._eng().get_owned_document(lineage_id, "__operator__")
    assert lineage is not None
    forged_edges = list(lineage["edges"])
    forged_edges[0] = {**forged_edges[0], "edge_id": f"cedge_{'f' * 24}"}
    eng_mod._eng().put_document(lineage_id, {**lineage, "edges": forged_edges})
    forged = client.get(f"/engagement/sessions/collective/{unit_id}/lineage")
    assert forged.status_code == 409


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
    assert [row["session_id"] for row in alice_list["sessions"]] == [alice["session_id"]]
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


def test_owner_session_discovery_is_cross_asset_bounded_and_private():
    reset_engagement_stores()
    app = FastAPI()

    @app.middleware("http")
    async def attach_test_owner(request: Request, call_next):
        request.state.user_id = request.headers.get("x-test-owner", "")
        return await call_next(request)

    register_engagement_routes(app)
    client = TestClient(app)

    def open_for(owner: str, asset: str, passage: str) -> dict:
        response = client.post(
            "/engagement/sessions/open",
            headers={"x-test-owner": owner},
            json={"asset_id": asset, "selection_text": passage, "force_new": True},
        )
        assert response.status_code == 200, response.text
        return response.json()

    alice = [
        open_for("alice", "asset-a", "alice first"),
        open_for("alice", "asset-b", "alice second"),
    ]
    bob = open_for("bob", "asset-a", "bob private")

    first_page = client.get(
        "/engagement/sessions/owned?limit=1",
        headers={"x-test-owner": "alice"},
    )
    assert first_page.status_code == 200, first_page.text
    first_body = first_page.json()
    assert first_body["count"] == 1
    assert first_body["next_cursor"] == first_body["sessions"][0]["session_id"]
    second_page = client.get(
        "/engagement/sessions/owned",
        headers={"x-test-owner": "alice"},
        params={"cursor": first_body["next_cursor"]},
    )
    discovered_ids = {
        first_body["sessions"][0]["session_id"],
        *[row["session_id"] for row in second_page.json()["sessions"]],
    }
    assert discovered_ids == {row["session_id"] for row in alice}
    assert bob["session_id"] not in discovered_ids
    assert {row["parent_asset_id"] for row in second_page.json()["sessions"]} <= {
        "asset-a",
        "asset-b",
    }

    bob_list = client.get("/engagement/sessions/owned", headers={"x-test-owner": "bob"}).json()
    assert [row["session_id"] for row in bob_list["sessions"]] == [bob["session_id"]]
    assert (
        client.get(
            "/engagement/sessions/owned?cursor=fsess_0000000000000000",
            headers={"x-test-owner": "alice"},
        ).status_code
        == 400
    )


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


def test_owner_graph_readiness_is_authenticated_and_non_disclosing(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owners"))
    reset_engagement_stores()
    app = FastAPI()

    @app.middleware("http")
    async def attach_test_owner(request: Request, call_next):
        request.state.user_id = request.headers.get("x-test-owner", "")
        return await call_next(request)

    register_engagement_routes(app)
    client = TestClient(app)
    response = client.get("/engagement/graph/readiness", headers={"x-test-owner": "alice"})
    assert response.status_code == 200
    assert response.json()["owner_graph_scope"] == "unmaterialized"
    assert response.json()["materialized"] is False
    assert response.json()["graph_read"] is False
    assert response.json()["node_count"] == 0
    assert set(response.json()) == {
        "owner_graph_scope",
        "materialized",
        "graph_path_sha256",
        "node_count",
        "graph_read",
        "embedding_space_status",
    }
    assert not (tmp_path / "owners").exists()

    from processing.embedding import HashEmbedding
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import promote_insight
    from substrate.graph.schema import init_database

    bob_path = owner_graph_db_path("bob")
    con = connect_write(bob_path, purpose="readiness_embedding_compatibility")
    try:
        init_database(con)
        promote_insight(
            text="Bob pinned embedding memory",
            investigation_id="inv-bob-readiness",
            embedding_provider=HashEmbedding(8),
            con=con,
            emit_events=False,
        )
    finally:
        con.close()
    set_default_embedding_provider(HashEmbedding(16))
    mismatch = client.get("/engagement/graph/readiness", headers={"x-test-owner": "bob"})
    assert mismatch.json()["embedding_space_status"] == "configured_mismatch"
    set_default_embedding_provider(HashEmbedding(8))
    compatible = client.get("/engagement/graph/readiness", headers={"x-test-owner": "bob"})
    assert compatible.json()["embedding_space_status"] == "compatible"

    unreadable_path = Path(owner_graph_db_path("alice"))
    unreadable_path.write_text("not a duckdb file", encoding="utf-8")
    unreadable = client.get("/engagement/graph/readiness", headers={"x-test-owner": "alice"})
    assert unreadable.status_code == 200
    assert unreadable.json()["owner_graph_scope"] == "unreadable"
    assert unreadable.json()["materialized"] is True
    assert unreadable.json()["graph_read"] is False
    assert unreadable.json()["node_count"] == 0
    assert unreadable.json()["embedding_space_status"] == "unreadable"

    monkeypatch.delenv("ANTIEK_ALLOW_UNAUTHENTICATED_LOCAL", raising=False)
    no_identity_app = FastAPI()
    register_engagement_routes(no_identity_app)
    missing_identity = TestClient(no_identity_app).get("/engagement/graph/readiness")
    assert missing_identity.status_code == 401
    _reset_default_provider()


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


def test_confirmed_merge_recovers_after_parent_write_before_receipt_settle(client, monkeypatch):
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
    assert recovered.json()["result_parent_sha256"] == recovered.json()["document_sha256"]


def test_confirmed_twin_promotion_is_owner_isolated_and_replayable(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owner-graphs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    set_default_embedding_provider(_PromotionEmbedding())
    reset_engagement_stores(root=tmp_path / "engagement")
    app = FastAPI()

    @app.middleware("http")
    async def attach_test_owner(request: Request, call_next):
        request.state.user_id = request.headers.get("x-test-owner", "")
        return await call_next(request)

    register_engagement_routes(app)
    client = TestClient(app)
    sessions: dict[str, dict] = {}
    try:
        for owner in ("alice", "bob"):
            headers = {"x-test-owner": owner}
            opened = client.post(
                "/engagement/sessions/open",
                headers=headers,
                json={
                    "asset_id": "same-asset",
                    "selection_text": "same private source",
                    "region_id": "same-region",
                },
            ).json()
            sessions[owner] = opened
            recorded = client.post(
                f"/engagement/sessions/{opened['session_id']}/twins",
                headers=headers,
                json={"kind": "insight", "text": "Identical private insight"},
            )
            assert recorded.status_code == 200, recorded.text
            preview = client.post(
                f"/engagement/sessions/{opened['session_id']}/twins/promote-preview",
                headers=headers,
                json={"kinds": ["insight"]},
            )
            assert preview.status_code == 200, preview.text
            preview_body = preview.json()
            assert preview_body["graph_write"] is False
            confirm_body = {
                "kinds": ["insight"],
                "expected_preview_sha256": preview_body["promotion_preview_sha256"],
                "idempotency_key": f"{owner}-confirm-001",
            }
            confirmed = client.post(
                f"/engagement/sessions/{opened['session_id']}/twins/promote-confirm",
                headers=headers,
                json=confirm_body,
            )
            assert confirmed.status_code == 200, confirmed.text
            result = confirmed.json()
            assert result["graph_write"] is True
            assert result["twin_context_mode"] == "confirmed_mutating"
            assert result["owner_graph_scope"] == "physically_isolated"
            replay = client.post(
                f"/engagement/sessions/{opened['session_id']}/twins/promote-confirm",
                headers=headers,
                json=confirm_body,
            )
            assert replay.status_code == 200
            assert replay.json() == result

        alice_path = owner_graph_db_path("alice")
        bob_path = owner_graph_db_path("bob")
        assert alice_path != bob_path
        for path in (alice_path, bob_path):
            con = connect_read(path)
            try:
                rows = con.execute(
                    "SELECT canonical_label FROM nodes WHERE node_type = 'insight'"
                ).fetchall()
            finally:
                con.close()
            assert rows == [("Identical private insight",)]
        for owner, path in (("alice", alice_path), ("bob", bob_path)):
            events_dir = owner_graph_events_dir(owner, path)
            assert events_dir is not None
            event_text = "".join(
                event_file.read_text(encoding="utf-8")
                for event_file in Path(events_dir).rglob("*")
                if event_file.is_file()
            )
            assert "Identical private insight" in event_text
        shared_events = tmp_path / "events"
        assert not shared_events.exists() or not any(shared_events.rglob("*"))

        hidden = client.post(
            f"/engagement/sessions/{sessions['alice']['session_id']}/twins/promote-confirm",
            headers={"x-test-owner": "bob"},
            json={
                "kinds": ["insight"],
                "expected_preview_sha256": "0" * 64,
                "idempotency_key": "foreign-confirm-001",
            },
        )
        assert hidden.status_code == 404
    finally:
        _reset_default_provider()


def test_twin_promotion_rejects_preview_drift_before_graph_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owner-graphs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    set_default_embedding_provider(_PromotionEmbedding())
    reset_engagement_stores(root=tmp_path / "engagement")
    app = FastAPI()

    @app.middleware("http")
    async def attach_owner(request: Request, call_next):
        request.state.user_id = "alice"
        return await call_next(request)

    register_engagement_routes(app)
    client = TestClient(app)
    try:
        session = client.post(
            "/engagement/sessions/open",
            json={"asset_id": "drift-asset", "selection_text": "source"},
        ).json()
        route = f"/engagement/sessions/{session['session_id']}/twins"
        assert client.post(route, json={"kind": "insight", "text": "First"}).status_code == 200
        preview = client.post(f"{route}/promote-preview", json={}).json()
        assert (
            client.post(route, json={"kind": "question", "text": "New question?"}).status_code
            == 200
        )
        refused = client.post(
            f"{route}/promote-confirm",
            json={
                "expected_preview_sha256": preview["promotion_preview_sha256"],
                "idempotency_key": "drift-confirm-001",
            },
        )
        assert refused.status_code == 409
        assert "preview changed" in refused.json()["detail"]
        assert not os.path.exists(owner_graph_db_path("alice"))
    finally:
        _reset_default_provider()


def test_twin_promotion_recovers_after_graph_commit_before_receipt_settle(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owner-graphs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    set_default_embedding_provider(_PromotionEmbedding())
    reset_engagement_stores(root=tmp_path / "engagement")
    app = FastAPI()

    @app.middleware("http")
    async def attach_owner(request: Request, call_next):
        request.state.user_id = "alice"
        return await call_next(request)

    register_engagement_routes(app)
    client = TestClient(app)
    try:
        session = client.post(
            "/engagement/sessions/open",
            json={"asset_id": "crash-asset", "selection_text": "source"},
        ).json()
        route = f"/engagement/sessions/{session['session_id']}/twins"
        client.post(route, json={"kind": "insight", "text": "Crash-safe insight"})
        preview = client.post(f"{route}/promote-preview", json={}).json()
        body = {
            "expected_preview_sha256": preview["promotion_preview_sha256"],
            "idempotency_key": "crash-confirm-001",
        }
        real_settle = eng_mod.settle_promotion_receipt
        calls = 0

        def crash_once(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected crash after graph commit")
            return real_settle(**kwargs)

        monkeypatch.setattr(eng_mod, "settle_promotion_receipt", crash_once)
        with pytest.raises(RuntimeError, match="after graph commit"):
            client.post(f"{route}/promote-confirm", json=body)
        recovered = client.post(f"{route}/promote-confirm", json=body)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["promotion_receipt_state"] == "applied"
        con = connect_read(owner_graph_db_path("alice"))
        try:
            assert (
                con.execute(
                    "SELECT count(*) FROM nodes WHERE canonical_label = 'Crash-safe insight'"
                ).fetchone()[0]
                == 1
            )
        finally:
            con.close()
    finally:
        _reset_default_provider()


def test_twin_promotion_rolls_back_graph_and_outbox_before_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_USER_GRAPH_DIR", str(tmp_path / "owner-graphs"))
    set_default_embedding_provider(_FailSecondPromotionEmbedding())
    reset_engagement_stores(root=tmp_path / "engagement")
    app = FastAPI()

    @app.middleware("http")
    async def attach_owner(request: Request, call_next):
        request.state.user_id = "alice"
        return await call_next(request)

    register_engagement_routes(app)
    client = TestClient(app)
    try:
        session = client.post(
            "/engagement/sessions/open",
            json={"asset_id": "atomic-asset", "selection_text": "source"},
        ).json()
        route = f"/engagement/sessions/{session['session_id']}/twins"
        client.post(route, json={"kind": "insight", "text": "First atomic note"})
        client.post(route, json={"kind": "question", "text": "Second atomic note?"})
        preview = client.post(f"{route}/promote-preview", json={}).json()
        body = {
            "expected_preview_sha256": preview["promotion_preview_sha256"],
            "idempotency_key": "atomic-confirm-001",
        }
        with pytest.raises(RuntimeError, match="second-note embedding failure"):
            client.post(f"{route}/promote-confirm", json=body)

        graph_path = owner_graph_db_path("alice")
        con = connect_read(graph_path)
        try:
            assert con.execute("SELECT count(*) FROM nodes").fetchone()[0] == 0
            outbox_exists = con.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'twin_promotion_event_outbox'"
            ).fetchone()[0]
            if outbox_exists:
                assert (
                    con.execute("SELECT count(*) FROM twin_promotion_event_outbox").fetchone()[0]
                    == 0
                )
        finally:
            con.close()
        events_dir = owner_graph_events_dir("alice", graph_path)
        assert events_dir is not None
        assert not any(Path(events_dir).glob("*.jsonl"))

        set_default_embedding_provider(_PromotionEmbedding())
        recovered = client.post(f"{route}/promote-confirm", json=body)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["promoted_count"] == 2
    finally:
        _reset_default_provider()


def test_operator_confirm_keeps_canonical_graph_compatibility(client, tmp_path, monkeypatch):
    operator_graph = tmp_path / "operator.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(operator_graph))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "operator-events"))
    set_default_embedding_provider(_PromotionEmbedding())
    try:
        session = client.post(
            "/engagement/sessions/open",
            json={"asset_id": "operator-asset", "selection_text": "source"},
        ).json()
        route = f"/engagement/sessions/{session['session_id']}/twins"
        client.post(route, json={"kind": "insight", "text": "Operator memory"})
        preview = client.post(f"{route}/promote-preview", json={}).json()
        confirmed = client.post(
            f"{route}/promote-confirm",
            json={
                "expected_preview_sha256": preview["promotion_preview_sha256"],
                "idempotency_key": "operator-confirm-001",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["owner_graph_scope"] == "operator_canonical"
        assert operator_graph.is_file()
        assert owner_graph_db_path("__operator__") == str(operator_graph)
    finally:
        _reset_default_provider()
