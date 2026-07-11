"""Hermetic tests for floating deep research routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_deep_research_routes import (
    register_floating_deep_research_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_deep_research_routes(app)
    return TestClient(app)


def test_spawn_ok() -> None:
    r = _client().post(
        "/research/floating-deep-research/spawn",
        json={
            "parent_asset_id": "asset-1",
            "highlight": "interesting claim",
            "gated": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["status"] == "proposed"


def test_spawn_gated_400() -> None:
    r = _client().post(
        "/research/floating-deep-research/spawn",
        json={
            "parent_asset_id": "asset-1",
            "highlight": "secret",
            "gated": True,
        },
    )
    assert r.status_code == 400
    assert "gated" in r.json()["detail"].lower()


def test_spawn_extra_forbid() -> None:
    r = _client().post(
        "/research/floating-deep-research/spawn",
        json={
            "parent_asset_id": "a",
            "highlight": "h",
            "gated": False,
            "live_dispatched": True,
        },
    )
    assert r.status_code == 422


def test_spawn_strict_bool() -> None:
    r = _client().post(
        "/research/floating-deep-research/spawn",
        json={
            "parent_asset_id": "a",
            "highlight": "h",
            "gated": "false",
        },
    )
    assert r.status_code == 422


def test_draft_merge_and_collective() -> None:
    c = _client()
    a = c.post(
        "/research/floating-deep-research/spawn",
        json={"parent_asset_id": "p", "highlight": "one", "gated": False},
    ).json()
    b = c.post(
        "/research/floating-deep-research/spawn",
        json={
            "parent_asset_id": "p",
            "highlight": "two different",
            "gated": False,
        },
    ).json()
    draft = c.post(
        "/research/floating-deep-research/draft-merge",
        json={"instance": a},
    )
    assert draft.status_code == 200
    assert draft.json()["merge_executed"] is False

    done_a = c.post(
        "/research/floating-deep-research/complete",
        json={"instance": a},
    ).json()
    done_b = c.post(
        "/research/floating-deep-research/complete",
        json={"instance": b},
    ).json()
    pack = c.post(
        "/research/floating-deep-research/collective-pack",
        json={"instances": [done_a, done_b]},
    )
    assert pack.status_code == 200
    assert pack.json()["pack_dispatched"] is False
    assert len(pack.json()["instance_ids"]) == 2


def test_full_merge_requires_ack() -> None:
    c = _client()
    inst = c.post(
        "/research/floating-deep-research/spawn",
        json={"parent_asset_id": "p", "highlight": "h", "gated": False},
    ).json()
    done = c.post(
        "/research/floating-deep-research/complete",
        json={"instance": inst},
    ).json()
    bad = c.post(
        "/research/floating-deep-research/full-merge",
        json={"instance": done, "operator_ack": False},
    )
    assert bad.status_code == 400
    ok = c.post(
        "/research/floating-deep-research/full-merge",
        json={"instance": done, "operator_ack": True},
    )
    assert ok.status_code == 200
    assert ok.json()["merge_executed"] is False
