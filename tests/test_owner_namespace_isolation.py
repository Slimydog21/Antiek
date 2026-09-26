"""Owner-namespace isolation — the Option A deliverable test.

Two addresses on the operator allowlist must resolve to TWO distinct owners
through ``settings_models_admin.request_owner_user_id``, and neither may see
the other's models, credentials, usage, budgets, capacity or lineup through
any path keyed on it.

The app below is the REAL settings mount seam (``register_settings_budget_routes``
and friends, the same ones ``create_app`` calls) behind a test middleware that
plays the role of the operator-auth middleware for an authenticated session:
it stamps ``user_id="__operator__"`` (what every production login mints),
``auth_method="antiek_session_cookie"`` and the verified address on
``request.state.user_email`` — exactly what ``app.py``'s session-cookie path
attaches after magic-link verification and the allowlist check. Everything
downstream of that stamp is production code.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.account_memory_identity import (
    derive_owner_from_verified_email,
)
from interfaces.research.api.byot_usage_routes import register_byot_usage_routes
from interfaces.research.api.settings_budget import register_settings_budget_routes
from interfaces.research.api.settings_compute_capacity import (
    register_settings_compute_capacity_routes,
)
from interfaces.research.api.settings_lineup import register_settings_lineup_routes
from interfaces.research.api.settings_models_admin import request_owner_user_id
from interfaces.research.api.settings_privacy import register_settings_privacy_routes
from runtime.byok.store import list_credentials
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch.router import reset_provider_registry

ALICE = "alice@example.test"
BOB = "bob@example.test"

ALICE_OWNER = derive_owner_from_verified_email(ALICE)
BOB_OWNER = derive_owner_from_verified_email(BOB)

_ADD_BODY = {
    "provider_kind": "openai_compat",
    "model_id": "deepseek-chat",
    "display_name": "Alice DeepSeek",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "sk-alice-super-secret-key-1234567890",
}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "settings" / "user_models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "byok" / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "byok" / "master.key"))
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(tmp_path / "byot-usage.sqlite3"))
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(tmp_path / "settings" / "lineup.json"))
    monkeypatch.setenv("ANTIEK_TELEMETRY_DB", str(tmp_path / "telemetry" / "preferences.sqlite"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    reset_provider_registry()
    return tmp_path


def _session_app() -> FastAPI:
    """Real settings routes behind a middleware that stamps what the
    production session-cookie path stamps on ``request.state``."""
    app = FastAPI()
    register_settings_budget_routes(app)
    register_byot_usage_routes(app)
    register_settings_compute_capacity_routes(app)
    register_settings_lineup_routes(app)
    register_settings_privacy_routes(app)

    @app.middleware("http")
    async def _stamp_session(request: Request, call_next):  # noqa: ANN001, ANN202
        # Headers select the simulated caller; defaults are an authenticated
        # session-cookie request, which is what both alice and bob are.
        request.state.auth_method = request.headers.get(
            "X-Test-Method", "antiek_session_cookie"
        )
        request.state.user_id = request.headers.get("X-Test-User-Id", "__operator__")
        request.state.user_email = request.headers.get("X-Test-Email")
        return await call_next(request)

    return app


@pytest.fixture
def client(env: Path) -> Iterator[TestClient]:
    with TestClient(_session_app()) as c:
        yield c
    reset_provider_registry()


def _as(email: str) -> dict[str, str]:
    return {"X-Test-Email": email}


# ---------------------------------------------------------------------------
# The load-bearing invariant: two allowlisted addresses, two owners
# ---------------------------------------------------------------------------


def test_two_allowlisted_addresses_resolve_two_distinct_owners(client: TestClient) -> None:
    assert ALICE_OWNER is not None and BOB_OWNER is not None
    assert ALICE_OWNER != BOB_OWNER
    assert ALICE_OWNER != "__operator__" and BOB_OWNER != "__operator__"

    # ... and the route-facing predicate agrees, for both people.
    alice_models = client.get("/settings/models/user", headers=_as(ALICE))
    bob_models = client.get("/settings/models/user", headers=_as(BOB))
    assert alice_models.status_code == 200 and bob_models.status_code == 200


# ---------------------------------------------------------------------------
# Models, credentials, usage and budgets cannot cross the boundary
# ---------------------------------------------------------------------------


def test_models_credentials_usage_and_budgets_are_isolated(
    client: TestClient, env: Path
) -> None:
    created = client.post("/settings/models/user", json=_ADD_BODY, headers=_as(ALICE))
    assert created.status_code == 201
    alice_model_id = created.json()["id"]
    # The id is namespaced to alice's derived owner, never the legacy sentinel.
    assert alice_model_id.startswith("user-")
    assert alice_model_id != "user-alice-deepseek"

    # Bob's inventory is empty; alice's row is invisible to him.
    bob_inventory = client.get("/settings/models/user", headers=_as(BOB)).json()
    assert bob_inventory["count"] == 0
    assert bob_inventory["models"] == []

    # Bob cannot resolve, delete, meter or read the balance of alice's model.
    choice = {
        "authority": "user_model",
        "provider_id": alice_model_id,
        "model_id": "deepseek-chat",
    }
    assert (
        client.post("/settings/models/user/resolve", json=choice, headers=_as(BOB)).status_code
        == 409
    )
    assert (
        client.delete(f"/settings/models/user/{alice_model_id}", headers=_as(BOB)).status_code
        == 404
    )
    assert (
        client.post(
            f"/settings/usage/{alice_model_id}/limit",
            json={"limit_cents": 500},
            headers=_as(BOB),
        ).status_code
        == 404
    )
    assert (
        client.get(f"/settings/balance/{alice_model_id}", headers=_as(BOB)).status_code == 404
    )

    # The credential is stored bound to alice's owner, and to no one else.
    creds = list_credentials()
    assert len(creds) == 1
    assert creds[0].owner_user_id == ALICE_OWNER

    # Alice sets a spend cap (her budget); the ledger keys it on HER owner,
    # and Bob's usage view stays empty.
    assert (
        client.post(
            f"/settings/usage/{alice_model_id}/limit",
            json={"limit_cents": 500},
            headers=_as(ALICE),
        ).status_code
        == 200
    )
    ledger = ByotUsageLedger(db_path=env / "byot-usage.sqlite3")
    assert [row.owner_user_id for row in ledger.snapshot(ALICE_OWNER)] == [ALICE_OWNER]
    assert ledger.snapshot(BOB_OWNER) == []
    assert ledger.snapshot("__operator__") == []
    bob_usage = client.get("/settings/usage", headers=_as(BOB)).json()
    assert bob_usage["count"] == 0

    # And the same model is fully visible to alice through the same paths.
    alice_inventory = client.get("/settings/models/user", headers=_as(ALICE)).json()
    assert [row["id"] for row in alice_inventory["models"]] == [alice_model_id]
    assert (
        client.post("/settings/models/user/resolve", json=choice, headers=_as(ALICE)).status_code
        == 200
    )
    alice_usage = client.get("/settings/usage", headers=_as(ALICE)).json()
    assert [row["api_key_id"] for row in alice_usage["keys"]] == [alice_model_id]


# ---------------------------------------------------------------------------
# Compute capacity and role lineup are owner-scoped too
# ---------------------------------------------------------------------------


def test_compute_capacity_is_isolated(client: TestClient, env: Path) -> None:
    put = client.put(
        "/settings/compute-capacity",
        json={"tier": "power", "monthly_compute_units": 5000},
        headers=_as(ALICE),
    )
    assert put.status_code == 200
    assert put.json()["owner_user_id"] == ALICE_OWNER

    # Bob gets his own honest default, not alice's tier.
    bob = client.get("/settings/compute-capacity", headers=_as(BOB))
    assert bob.status_code == 200
    assert bob.json()["owner_user_id"] == BOB_OWNER
    assert bob.json()["is_default"] is True

    # Durable state holds exactly one row, owned by alice's derived owner.
    import duckdb

    con = duckdb.connect(str(env / "graph.duckdb"), read_only=True)
    try:
        rows = con.execute(
            "SELECT owner_user_id FROM owner_compute_capacity"
        ).fetchall()
    finally:
        con.close()
    assert rows == [(ALICE_OWNER,)]


def test_lineup_is_isolated(client: TestClient, env: Path) -> None:
    created = client.post("/settings/models/user", json=_ADD_BODY, headers=_as(ALICE))
    assert created.status_code == 201
    alice_model_id = created.json()["id"]

    put = client.put(
        "/settings/lineup",
        json={
            "general": {
                "writer": {
                    "provider_id": alice_model_id,
                    "model_id": "deepseek-chat",
                }
            },
            "advanced": {},
        },
        headers=_as(ALICE),
    )
    assert put.status_code == 200

    # Durable lineup keys on alice's derived owner only.
    lineup = json.loads((env / "settings" / "lineup.json").read_text())
    assert list(lineup["owners"]) == [ALICE_OWNER]

    # Bob's lineup carries no trace of alice's assignment.
    bob_view = client.get("/settings/lineup", headers=_as(BOB))
    assert bob_view.status_code == 200
    assert alice_model_id not in bob_view.text


# ---------------------------------------------------------------------------
# Fail-closed: no verified address, no owner — and no legacy read-fallback
# ---------------------------------------------------------------------------


def test_session_without_verified_email_fails_closed(client: TestClient) -> None:
    response = client.get("/settings/models/user")  # no X-Test-Email header
    assert response.status_code == 401


def test_machine_methods_cannot_claim_a_persons_namespace(client: TestClient) -> None:
    assert (
        client.post("/settings/models/user", json=_ADD_BODY, headers=_as(ALICE)).status_code
        == 201
    )
    for method in ("bearer_token", "cloudflare_service_token"):
        response = client.get(
            "/settings/models/user",
            headers={**_as(ALICE), "X-Test-Method": method},
        )
        assert response.status_code == 401, method


def test_no_derived_owner_can_read_legacy_operator_rows(client: TestClient, env: Path) -> None:
    """The anti-fallback the decision doc demands: a legacy ``__operator__``
    record is INVISIBLE to every derived owner until the explicit migration
    (tools/migrate_owner_namespace.py) re-owns it."""
    registry_path = env / "settings" / "user_models.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "user-legacy-model": {
                    "id": "user-legacy-model",
                    "owner_user_id": "__operator__",
                    "provider_kind": "openai_compat",
                    "model_id": "deepseek-chat",
                    "display_name": "Legacy Model",
                    "base_url": "https://api.deepseek.com/v1",
                    "cred_ref": "cred-x-nonexistent",
                    "enabled": True,
                }
            }
        )
    )
    registry_path.chmod(0o600)
    for email in (ALICE, BOB):
        inventory = client.get("/settings/models/user", headers=_as(email)).json()
        assert inventory["count"] == 0
        assert inventory["models"] == []


def test_unauthenticated_local_fails_closed_without_a_verified_identity(env: Path) -> None:
    """Unauthenticated access is REFUSED — the legacy ``__operator__` sentinel
    fallback was deliberately removed.

    ``request_owner_user_id`` is fail-closed by contract: "Never invents an
    owner. No implicit read-fallback that would let any derived owner claim
    legacy ``__operator__`` rows (the migration in
    ``tools/migrate_owner_namespace.py`` re-owns those explicitly)."

    This test originally asserted the OPPOSITE — that a bare app with no auth
    middleware kept the ``__operator__`` sentinel so local dev and the settings
    suites were unchanged. That behavior is gone by design (namespace Option A,
    Sprint 22 multi-user groundwork): a shared sentinel cannot name a person,
    and an implicit fallback would let any derived owner read legacy rows.
    The test is rewritten to pin the fail-closed contract, not to resurrect
    the removed behavior. If the fallback ever comes back, this fails.
    """
    app = FastAPI()
    register_settings_budget_routes(app)
    with TestClient(app) as local:
        resp = local.post("/settings/models/user", json=_ADD_BODY)
        assert resp.status_code == 401, (
            f"unauthenticated write must be refused, got {resp.status_code}; "
            "an implicit __operator__ fallback would be a namespace-escape"
        )
        # Reads are refused for the same reason — no owner, no namespace.
        assert local.get("/settings/models/user").status_code == 401
    # And nothing was written under the legacy sentinel.
    registry = env / "settings" / "user_models.json"
    if registry.exists():
        assert json.loads(registry.read_text()) == {}, (
            "no row may be minted under __operator__ without a verified identity"
        )
    reset_provider_registry()


def test_predicate_agrees_with_the_other_three(client: TestClient) -> None:
    """One person, one owner, across all four owner predicates."""
    from types import SimpleNamespace

    from interfaces.research.api.account_memory_identity import distinct_signed_owner
    from interfaces.research.api.owner_byot_dispatch import authenticated_distinct_owner

    request = SimpleNamespace(
        state=SimpleNamespace(
            auth_method="antiek_session_cookie",
            user_id="__operator__",
            user_email=ALICE,
        )
    )
    assert request_owner_user_id(request) == ALICE_OWNER
    assert distinct_signed_owner(request) == ALICE_OWNER
    assert authenticated_distinct_owner(request) == ALICE_OWNER
