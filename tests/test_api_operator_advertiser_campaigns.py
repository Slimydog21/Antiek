"""Operator advertiser-campaign API tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_store(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-advertiser-campaigns-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    store_path = os.path.join(tmpdir, "advertisers.sqlite")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_ADVERTISER_STORE_PATH", store_path)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield store_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client() -> TestClient:
    return TestClient(
        create_app(register_wrestling=False, register_providers=False),
    )


def _campaign_payload(**overrides):
    payload = {
        "advertiser_name": "Acme Recruiting",
        "contact_email": "ads@acme.example",
        "sector": "recruiting",
        "sub_sector": "executive-search",
        "intent": "hiring_manager",
        "target_topics": ["talent density", "org design"],
        "creative_headline": "Hire better operators",
        "creative_url": "https://acme.example/hire",
        "daily_budget_cents": 2500,
    }
    payload.update(overrides)
    return payload


def test_operator_advertiser_campaigns_empty(isolated_store):
    resp = _client().get("/operator/advertiser-campaigns")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"campaigns": []}


def test_operator_advertiser_campaign_create_and_list(isolated_store):
    c = _client()

    created = c.post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(
            advertiser_id="adv-acme",
            status="active",
            legal_gate_passed=True,
        ),
    )
    listed = c.get("/operator/advertiser-campaigns")

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["campaign_id"].startswith("cam-")
    assert body["advertiser_id"] == "adv-acme"
    assert body["advertiser_name"] == "Acme Recruiting"
    assert body["sector"] == "recruiting"
    assert body["intent"] == "hiring_manager"
    assert body["target_topics"] == ["talent density", "org design"]
    assert body["creative_url"] == "https://acme.example/hire"
    assert body["daily_budget_cents"] == 2500
    assert body["status"] == "active"
    assert body["impressions"] == 0
    assert body["clicks"] == 0
    assert body["spend_cents"] == 0
    assert listed.status_code == 200, listed.text
    assert listed.json()["campaigns"] == [body]


def test_operator_advertiser_campaign_create_trims_creative_url(isolated_store):
    c = _client()

    created = c.post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(creative_url="  https://acme.example/hire  "),
    )
    listed = c.get("/operator/advertiser-campaigns")

    assert created.status_code == 201, created.text
    assert created.json()["creative_url"] == "https://acme.example/hire"
    assert listed.status_code == 200, listed.text
    assert listed.json()["campaigns"][0]["creative_url"] == "https://acme.example/hire"


@pytest.mark.parametrize(
    "creative_url",
    [
        "javascript:alert(1)",
        "data:text/html,owned",
        "/relative/path",
        "example.com/no-scheme",
        " ",
    ],
)
def test_operator_advertiser_campaign_rejects_unsafe_creative_urls(
    isolated_store,
    creative_url,
):
    resp = _client().post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(creative_url=creative_url),
    )

    assert resp.status_code == 422


def test_operator_advertiser_campaign_status_filter_and_patch(isolated_store):
    c = _client()
    draft = c.post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(advertiser_id="adv-one", status="draft"),
    ).json()
    active = c.post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(
            advertiser_id="adv-two",
            status="active",
            legal_gate_passed=True,
        ),
    ).json()

    filtered = c.get("/operator/advertiser-campaigns?status=active")
    patched = c.patch(
        f"/operator/advertiser-campaigns/{draft['campaign_id']}/status",
        json={"status": "paused"},
    )

    assert filtered.status_code == 200, filtered.text
    assert [row["campaign_id"] for row in filtered.json()["campaigns"]] == [
        active["campaign_id"],
    ]
    assert patched.status_code == 200, patched.text
    assert patched.json()["campaign_id"] == draft["campaign_id"]
    assert patched.json()["status"] == "paused"


def test_operator_advertiser_campaign_patch_unknown_returns_404(isolated_store):
    resp = _client().patch(
        "/operator/advertiser-campaigns/cam-missing/status",
        json={"status": "paused"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "campaign_not_found"


def test_operator_advertiser_campaign_active_requires_legal_gate(isolated_store):
    c = _client()
    draft = c.post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(advertiser_id="adv-one", status="draft"),
    ).json()

    blocked_create = c.post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(advertiser_id="adv-two", status="active"),
    )
    blocked_patch = c.patch(
        f"/operator/advertiser-campaigns/{draft['campaign_id']}/status",
        json={"status": "active"},
    )
    allowed_patch = c.patch(
        f"/operator/advertiser-campaigns/{draft['campaign_id']}/status",
        json={"status": "active", "legal_gate_passed": True},
    )

    assert blocked_create.status_code == 409
    assert blocked_create.json()["detail"]["error"]["code"] == "legal_gate"
    assert blocked_patch.status_code == 409
    assert blocked_patch.json()["detail"]["error"]["code"] == "legal_gate"
    assert allowed_patch.status_code == 200
    assert allowed_patch.json()["status"] == "active"


def test_operator_advertiser_campaign_rejects_negative_budget(isolated_store):
    resp = _client().post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(daily_budget_cents=-1),
    )

    assert resp.status_code == 422


def test_operator_advertiser_campaigns_use_operator_auth(
    isolated_store,
    monkeypatch,
):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "op-secret")
    c = _client()

    blocked = c.get("/operator/advertiser-campaigns")
    blocked_post = c.post(
        "/operator/advertiser-campaigns",
        json=_campaign_payload(),
    )
    allowed = c.get(
        "/operator/advertiser-campaigns",
        headers={"Authorization": "Bearer op-secret"},
    )

    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "operator_auth_required"
    assert blocked_post.status_code == 401
    assert allowed.status_code == 200


def test_operator_advertiser_campaigns_do_not_import_money_movers():
    source = Path(
        "interfaces/research/api/operator_advertiser_campaigns.py",
    ).read_text(encoding="utf-8")
    assert "transfer_initiator" not in source
    assert "stripe_connect" not in source
    assert "payout" not in source
