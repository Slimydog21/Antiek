"""G2/G3 honesty on public opportunities (accrue now / disburse later)."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-g2g3-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    monkeypatch.setenv("ANTIEK_STRIPE_PROVIDER", "mock")
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_opportunities_honesty_surfaces_g2g3_gated(client):
    r = client.get("/speak/opportunities")
    assert r.status_code == 200
    h = r.json()["honesty"]
    assert h["public_publishing"] == "gated_G2_G3"
    assert h["disbursement"] == "gated_G2_G3_accrue_escrow_only"
    assert h["money_model"] == "accrue_escrow_now_disburse_after_legal_review"
    assert "live" not in h["disbursement"] or h["disbursement"].startswith("gated")


def test_opportunities_honesty_publishing_live_when_flag(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    h = client.get("/speak/opportunities").json()["honesty"]
    assert h["public_publishing"] == "live"
    # Stripe still mock → disbursement gated
    assert h["disbursement"].startswith("gated")


def test_economics_read_path_still_reports_gates(client):
    pid = client.post(
        "/speak/projects",
        json={"title": "Bio", "publish_intent": "will_be_public"},
    ).json()["project_id"]
    r = client.get(f"/speak/projects/{pid}/economics")
    assert r.status_code == 200
    body = r.json()
    assert body["public_publishing_allowed"] is False
    assert body["disbursement_allowed"] is False
    assert "G2" in body["public_publishing_reason"] or "gated" in body["public_publishing_reason"]
