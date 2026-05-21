"""Federation config endpoint + persistent store tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-fed-cfg-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


# ── Default posture ────────────────────────────────────────────────


def test_get_default_is_strict(isolated_db):
    """No row → strict default: no partners, both opt-in + attribution
    required."""
    client = _client()
    resp = client.get("/cross-graph/federation-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed_partner_substrates"] == []
    assert body["require_opt_in_for_outbound_citations"] is True
    assert body["require_attribution_for_outbound_citations"] is True


# ── PUT replaces ───────────────────────────────────────────────────


def test_put_replaces_config(isolated_db):
    client = _client()
    resp = client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": ["partner-coop", "research-net"],
            "require_opt_in_for_outbound_citations": False,
            "require_attribution_for_outbound_citations": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed_partner_substrates"] == ["partner-coop", "research-net"]
    assert body["require_opt_in_for_outbound_citations"] is False
    assert body["require_attribution_for_outbound_citations"] is True


def test_put_persists_across_requests(isolated_db):
    client = _client()
    client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": ["only-one"],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    resp = client.get("/cross-graph/federation-config")
    body = resp.json()
    assert body["allowed_partner_substrates"] == ["only-one"]


def test_put_second_call_overwrites(isolated_db):
    client = _client()
    client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": ["a", "b"],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    resp = client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": ["c"],
            "require_opt_in_for_outbound_citations": False,
            "require_attribution_for_outbound_citations": False,
        },
    )
    body = resp.json()
    assert body["allowed_partner_substrates"] == ["c"]
    assert body["require_opt_in_for_outbound_citations"] is False


# ── Validation ─────────────────────────────────────────────────────


def test_put_rejects_unsafe_partner_id(isolated_db):
    client = _client()
    resp = client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": ["../traversal"],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "invalid_partner_id"


def test_put_rejects_partner_id_with_spaces(isolated_db):
    client = _client()
    resp = client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": ["bad id"],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    assert resp.status_code == 422


# ── Empty allowed list is valid ────────────────────────────────────


def test_put_empty_allowed_is_strict_again(isolated_db):
    """An explicit empty list returns the substrate to strict-no-
    partners posture."""
    client = _client()
    client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": ["x", "y"],
            "require_opt_in_for_outbound_citations": False,
            "require_attribution_for_outbound_citations": False,
        },
    )
    resp = client.put(
        "/cross-graph/federation-config",
        json={
            "allowed_partner_substrates": [],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    body = resp.json()
    assert body["allowed_partner_substrates"] == []
    assert body["require_opt_in_for_outbound_citations"] is True
