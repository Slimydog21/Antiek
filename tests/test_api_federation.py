"""Federation API tests (Sprint 30+ thread 1)."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-api-federation-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(
        create_app(register_wrestling=False, register_providers=False),
    )


# ── Partner registry CRUD ──────────────────────────────────────────


def test_register_returns_one_time_secret_then_public_view_hides_it(isolated_db):
    c = _client()
    r = c.post(
        "/federation/partners",
        json={
            "display_name": "Partner Lab",
            "substrate_url": "https://lab.example",
            "partner_id": "prt-lab",
            "operator_notes": "first partner",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["partner_id"] == "prt-lab"
    assert body["state"] == "pending_handshake"
    assert "shared_secret_hex" in body
    secret = body["shared_secret_hex"]
    assert len(secret) == 64

    # Subsequent reads must NOT carry the secret.
    r = c.get("/federation/partners/prt-lab")
    assert r.status_code == 200
    assert "shared_secret_hex" not in r.json()

    # Listing also hides it.
    r = c.get("/federation/partners")
    assert r.status_code == 200
    for p in r.json()["partners"]:
        assert "shared_secret_hex" not in p


def test_trust_then_revoke_terminal(isolated_db):
    c = _client()
    c.post(
        "/federation/partners",
        json={
            "display_name": "X", "substrate_url": "https://x",
            "partner_id": "prt-x",
        },
    )
    r = c.post(
        "/federation/partners/prt-x/trust", json={"operator_notes": "ok"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "trusted"
    r = c.post(
        "/federation/partners/prt-x/revoke",
        json={"revocation_reason": "leak"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "revoked"
    # Re-revoke refused.
    r = c.post(
        "/federation/partners/prt-x/revoke",
        json={"revocation_reason": "leak again"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "partner_already_revoked"


def test_trust_from_already_trusted_refused(isolated_db):
    c = _client()
    c.post(
        "/federation/partners",
        json={
            "display_name": "X", "substrate_url": "https://x",
            "partner_id": "prt-x",
        },
    )
    c.post(
        "/federation/partners/prt-x/trust", json={"operator_notes": ""},
    )
    r = c.post(
        "/federation/partners/prt-x/trust", json={"operator_notes": ""},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "invalid_transition"


def test_duplicate_partner_id_refused(isolated_db):
    c = _client()
    body = {
        "display_name": "X", "substrate_url": "https://x",
        "partner_id": "prt-dup",
    }
    r1 = c.post("/federation/partners", json=body)
    assert r1.status_code == 201
    r2 = c.post("/federation/partners", json=body)
    assert r2.status_code == 409
    assert r2.json()["detail"]["error"]["code"] == "duplicate_partner_id"


def test_unknown_partner_404(isolated_db):
    c = _client()
    r = c.get("/federation/partners/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "partner_not_found"


# ── FederationConfig singleton ─────────────────────────────────────


def test_config_default_is_strict(isolated_db):
    c = _client()
    r = c.get("/federation/config")
    assert r.status_code == 200
    body = r.json()
    assert body["allowed_partner_substrates"] == []
    assert body["require_opt_in_for_outbound_citations"] is True
    assert body["require_attribution_for_outbound_citations"] is True


def test_config_update_then_read_roundtrip(isolated_db):
    c = _client()
    r = c.put(
        "/federation/config",
        json={
            "allowed_partner_substrates": ["prt-a", "prt-b"],
            "require_opt_in_for_outbound_citations": False,
            "require_attribution_for_outbound_citations": True,
        },
    )
    assert r.status_code == 200
    r = c.get("/federation/config")
    body = r.json()
    assert body["allowed_partner_substrates"] == ["prt-a", "prt-b"]
    assert body["require_opt_in_for_outbound_citations"] is False
    assert body["require_attribution_for_outbound_citations"] is True


# ── Outbound citation gates ────────────────────────────────────────


def _outbound_body(**overrides) -> dict:
    base = dict(
        partner_id="prt-b",
        referencing_user_id="user-a",
        referencing_investigation_id="inv-a-1",
        referenced_user_id="user-b",
        referenced_note_id="note-b",
        revenue_routing_handle="opaque-handle",
        referenced_user_opted_in=True,
        referenced_user_attribution_consented=True,
    )
    base.update(overrides)
    return base


def test_outbound_refused_when_partner_not_allowed(isolated_db):
    c = _client()
    # Allowed list empty by default.
    r = c.post("/federation/outbound-citation", json=_outbound_body())
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "partner_not_allowed"


def test_outbound_refused_when_partner_not_trusted(isolated_db):
    c = _client()
    c.post(
        "/federation/partners",
        json={
            "display_name": "B", "substrate_url": "https://b",
            "partner_id": "prt-b",
        },
    )
    c.put(
        "/federation/config",
        json={
            "allowed_partner_substrates": ["prt-b"],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    r = c.post("/federation/outbound-citation", json=_outbound_body())
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "partner_not_trusted"


def test_outbound_happy_path_signs_token(isolated_db):
    c = _client()
    c.post(
        "/federation/partners",
        json={
            "display_name": "B", "substrate_url": "https://b",
            "partner_id": "prt-b",
        },
    )
    c.post(
        "/federation/partners/prt-b/trust", json={"operator_notes": ""},
    )
    c.put(
        "/federation/config",
        json={
            "allowed_partner_substrates": ["prt-b"],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    r = c.post("/federation/outbound-citation", json=_outbound_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["partner_id"] == "prt-b"
    assert body["revenue_routing_handle"] == "opaque-handle"
    assert body["signed_token"].startswith("v1.")
    # The reference_id is a fresh xref- id.
    assert body["reference_id"].startswith("xref-")


def test_outbound_refused_when_user_not_opted_in(isolated_db):
    c = _client()
    c.post(
        "/federation/partners",
        json={
            "display_name": "B", "substrate_url": "https://b",
            "partner_id": "prt-b",
        },
    )
    c.post(
        "/federation/partners/prt-b/trust", json={"operator_notes": ""},
    )
    c.put(
        "/federation/config",
        json={
            "allowed_partner_substrates": ["prt-b"],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    r = c.post(
        "/federation/outbound-citation",
        json=_outbound_body(referenced_user_opted_in=False),
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "opt_in_required"


# ── Inbound citation receiver ──────────────────────────────────────


def _trusted_partner_with_secret(c, partner_id: str = "prt-b") -> str:
    r = c.post(
        "/federation/partners",
        json={
            "display_name": "B", "substrate_url": "https://b",
            "partner_id": partner_id,
        },
    )
    secret = r.json()["shared_secret_hex"]
    c.post(
        f"/federation/partners/{partner_id}/trust",
        json={"operator_notes": ""},
    )
    c.put(
        "/federation/config",
        json={
            "allowed_partner_substrates": [partner_id],
            "require_opt_in_for_outbound_citations": True,
            "require_attribution_for_outbound_citations": True,
        },
    )
    return secret


def test_inbound_happy_path_roundtrip(isolated_db):
    c = _client()
    _trusted_partner_with_secret(c)
    out = c.post("/federation/outbound-citation", json=_outbound_body())
    assert out.status_code == 200
    token = out.json()["signed_token"]
    r = c.post(
        "/federation/inbound-citation",
        json={"partner_id": "prt-b", "token": token},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is True
    assert body["rejection"] is None
    assert body["referencing_user_id"] == "user-a"
    assert body["referenced_user_id"] == "user-b"
    assert body["revenue_routing_handle"] == "opaque-handle"
    assert body["receiver_reference_id"].startswith("xref-in-")


def test_inbound_replay_rejected(isolated_db):
    c = _client()
    _trusted_partner_with_secret(c)
    out = c.post("/federation/outbound-citation", json=_outbound_body())
    token = out.json()["signed_token"]
    r1 = c.post(
        "/federation/inbound-citation",
        json={"partner_id": "prt-b", "token": token},
    )
    assert r1.json()["accepted"] is True
    # Replay → rejected with REPLAY_DETECTED.
    r2 = c.post(
        "/federation/inbound-citation",
        json={"partner_id": "prt-b", "token": token},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["accepted"] is False
    assert body["rejection"] == "replay_detected"


def test_inbound_unknown_partner_refused(isolated_db):
    c = _client()
    r = c.post(
        "/federation/inbound-citation",
        json={"partner_id": "prt-ghost", "token": "anything"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False
    # No allowed_partner_substrates yet → partner_not_allowed first.
    assert body["rejection"] == "partner_not_allowed"


def test_inbound_token_invalid_refused(isolated_db):
    c = _client()
    _trusted_partner_with_secret(c)
    r = c.post(
        "/federation/inbound-citation",
        json={"partner_id": "prt-b", "token": "v1.junk.0.0.junk"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False
    assert body["rejection"] == "token_invalid"
    # Detail must NOT leak the offending token.
    assert "v1.junk" not in body["detail"]


def test_inbound_does_not_leak_secret_in_any_response(isolated_db):
    c = _client()
    secret = _trusted_partner_with_secret(c)
    out = c.post("/federation/outbound-citation", json=_outbound_body())
    r = c.post(
        "/federation/inbound-citation",
        json={"partner_id": "prt-b", "token": out.json()["signed_token"]},
    )
    assert secret not in r.text
    assert "shared_secret_hex" not in r.text
