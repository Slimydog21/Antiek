"""Hermetic tests for source pack routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.source_pack_routes import register_source_pack_routes


def _client() -> TestClient:
    app = FastAPI()
    register_source_pack_routes(app)
    return TestClient(app)


def test_build_ok() -> None:
    r = _client().post(
        "/research/source-pack/build",
        json={
            "selected": ["arxiv"],
            "readiness_by_source": {
                "arxiv": {
                    "status": "ready",
                    "adapter_importable": True,
                    "offline_probe_ok": True,
                    "runner_consumes_today": False,
                    "note": "ok",
                }
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_fetch_authorized"] is False
    assert body["included_count"] == 1
    assert body["pack_text"]


def test_unknown_source_400() -> None:
    r = _client().post(
        "/research/source-pack/build",
        json={"selected": ["nope"]},
    )
    assert r.status_code == 400


def test_extra_fields_forbidden() -> None:
    r = _client().post(
        "/research/source-pack/build",
        json={"selected": ["arxiv"], "live_fetch_authorized": True},
    )
    assert r.status_code == 422
