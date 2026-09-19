"""G2 counsel + Synquery honesty — gated, no invented partnership / paid-today."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from substrate.speak.g2_synquery_honesty import (
    MONEY_MODEL,
    g2_synquery_honesty,
)
from substrate.trust_center import build_publication


def test_g2_synquery_honesty_defaults_gated(monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    monkeypatch.setenv("ANTIEK_STRIPE_PROVIDER", "mock")
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "0")
    h = g2_synquery_honesty()
    assert h["surface"] == "speak_economics"
    assert h["g2_counsel_gated"] is True
    assert h["g3_opt_in_gated"] is True
    assert h["public_publishing"] == "gated_G2_G3"
    assert h["disbursement"] == "gated_G2_G3_accrue_escrow_only"
    assert h["disbursement_allowed"] is False
    assert h["paid_today"] is False
    assert h["money_model"] == MONEY_MODEL
    assert h["synquery_partnership"] == "gated"
    assert h["synquery_gated"] is True
    assert "counsel_sign_off" in h["g2_requires"]
    assert "no_invented_partnership" in h["synquery_requires"]
    assert any("speak-residual-100" in r for r in h["decision_refs"])
    assert any("spr-10" in r for r in h["decision_refs"])
    assert any("afa-escrow" in r for r in h["decision_refs"])


def test_synquery_live_only_when_flag(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    monkeypatch.setenv("ANTIEK_STRIPE_PROVIDER", "mock")
    h = g2_synquery_honesty()
    assert h["synquery_partnership"] == "live"
    assert h["synquery_gated"] is False
    # G2 still gated — Synquery flag does not flip counsel.
    assert h["g2_counsel_gated"] is True
    assert h["paid_today"] is False


def test_trust_publication_includes_speak_economics(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "0")
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    payload = build_publication()
    assert payload.speak_economics["paid_today"] is False
    assert payload.speak_economics["synquery_gated"] is True
    assert payload.as_dict()["speak_economics"]["money_model"] == MONEY_MODEL


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-g2-synquery-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "0")
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    monkeypatch.setenv("ANTIEK_STRIPE_PROVIDER", "mock")
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_trust_center_endpoint_publishes_speak_economics(isolated_db):
    from interfaces.research.api.app import create_app

    client = TestClient(create_app())
    resp = client.get("/trust-center")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    se = body["speak_economics"]
    assert se["g2_counsel_gated"] is True
    assert se["synquery_gated"] is True
    assert se["paid_today"] is False
    assert se["money_model"] == MONEY_MODEL


def test_opportunities_honesty_surfaces_g2_synquery(isolated_db):
    from interfaces.research.api.app import create_app

    client = TestClient(create_app())
    resp = client.get("/speak/opportunities")
    assert resp.status_code == 200, resp.text
    h = resp.json()["honesty"]
    assert h["paid_today"] is False
    assert h["g2_counsel_gated"] is True
    assert h["synquery_gated"] is True
    assert h["synquery_partnership"] == "gated"
    assert h["money_model"] == MONEY_MODEL
    assert "gated_G2_G3" in h["public_publishing"]
