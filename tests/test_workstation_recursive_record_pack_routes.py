"""Hermetic tests for workstation recursive record pack routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.workstation_recursive_record_pack_routes import (
    register_workstation_recursive_record_pack_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_workstation_recursive_record_pack_routes(app)
    return TestClient(app)


def test_compose_ok() -> None:
    r = _client().post(
        "/research/workstation-record-pack/compose",
        json={
            "session_id": "sess-1",
            "items": [
                {
                    "record_id": "r1",
                    "kind": "insight",
                    "text": "scaling holds",
                    "weight": 0.9,
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["pack_ready"] is True
    assert body["authority"] == "workstation_recursive_record_pack_advisory"


def test_empty_ok() -> None:
    r = _client().post(
        "/research/workstation-record-pack/compose",
        json={"session_id": "s", "items": []},
    )
    assert r.status_code == 200
    assert r.json()["pack_ready"] is False
    assert r.json()["record_persisted"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/workstation-record-pack/compose",
        json={
            "session_id": "s",
            "items": [],
            "record_persisted": True,
        },
    )
    assert r.status_code == 422
