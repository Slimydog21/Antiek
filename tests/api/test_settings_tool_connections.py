from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.settings_tool_connections import (
    register_settings_tool_connection_routes,
)
from runtime.byok.store import list_credentials
from substrate.auth.magic_link import mint_session_cookie

SECRET = "AIza" + "z" * 24
AUTH_SECRET = "tool-settings-test-auth-secret-at-least-32-bytes"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "user-a@example.test,user-b@example.test")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_TOOL_CONNECTIONS_PATH", str(tmp_path / "tools.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    monkeypatch.setenv("ANTIEK_CONNECTOR_QUOTA_DIR", str(tmp_path / "quota"))
    with TestClient(create_app(register_wrestling=False, register_providers=False)) as value:
        yield value


def _cookie(user_id: str) -> dict[str, str]:
    return {
        "ANTIEK_SESSION": mint_session_cookie(
            user_id=user_id,
            email=f"{user_id}@example.test",
        )
    }


def test_inventory_connect_replace_disconnect_and_no_secret_echo(client, tmp_path) -> None:
    cookies = _cookie("user-a")
    initial = client.get("/settings/tools", cookies=cookies)
    assert initial.status_code == 200
    assert initial.headers["cache-control"] == "private, no-store"
    assert [item["vendor"] for item in initial.json()["connections"]] == [
        "youtube", "polygon", "fmp", "edgar", "x",
    ]

    created = client.put(
        "/settings/tools/youtube",
        json={"credential": SECRET},
        cookies=cookies,
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "configured_unverified"
    assert created.json()["credential_present"] is True
    assert SECRET not in created.text
    assert "cred-x-" not in created.text

    replacement = "AIza" + "y" * 24
    replaced = client.put(
        "/settings/tools/youtube",
        json={"credential": replacement},
        cookies=cookies,
    )
    assert replaced.status_code == 200
    assert len(list_credentials(artifact_path=str(tmp_path / "credentials.enc"))) == 1

    removed = client.delete("/settings/tools/youtube", cookies=cookies)
    assert removed.status_code == 200
    assert removed.json() == {"removed": "youtube"}
    assert list_credentials(artifact_path=str(tmp_path / "credentials.enc")) == []


def test_two_sessions_cannot_see_or_remove_each_others_connection(client) -> None:
    assert client.put(
        "/settings/tools/youtube",
        json={"credential": SECRET},
        cookies=_cookie("user-a"),
    ).status_code == 200
    rows_b = client.get("/settings/tools", cookies=_cookie("user-b")).json()["connections"]
    youtube_b = next(item for item in rows_b if item["vendor"] == "youtube")
    assert youtube_b["status"] == "unconfigured"
    assert client.delete(
        "/settings/tools/youtube", cookies=_cookie("user-b"),
    ).status_code == 404
    rows_a = client.get("/settings/tools", cookies=_cookie("user-a")).json()["connections"]
    assert next(item for item in rows_a if item["vendor"] == "youtube")[
        "credential_present"
    ] is True


def test_unauthenticated_and_spoofed_headers_refuse(client) -> None:
    response = client.put(
        "/settings/tools/youtube",
        json={"credential": SECRET},
        headers={"X-User-Id": "user-a", "X-Auth-Method": "antiek_session_cookie"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "auth_method",
    ["cloudflare_access_email", "cloudflare_service_token", "bearer_token"],
)
def test_shared_operator_auth_cannot_claim_owner_scoped_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_method: str,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_TOOL_CONNECTIONS_PATH", str(tmp_path / "tools.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    app = FastAPI()

    @app.middleware("http")
    async def _shared_operator_identity(request: Request, call_next):
        request.state.user_id = "__operator__"
        request.state.auth_method = auth_method
        return await call_next(request)

    register_settings_tool_connection_routes(app)
    with TestClient(app) as shared_client:
        assert shared_client.get("/settings/tools").status_code == 401
        assert shared_client.put(
            "/settings/tools/youtube", json={"credential": SECRET}
        ).status_code == 401
        assert shared_client.delete("/settings/tools/youtube").status_code == 401
    assert list_credentials(artifact_path=str(tmp_path / "credentials.enc")) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"credential": "bad-prefix-but-long-enough"},
        {"credential": SECRET, "owner_user_id": "user-b"},
        {"api_key": SECRET},
    ],
)
def test_invalid_payload_is_value_free(client, payload) -> None:
    response = client.put(
        "/settings/tools/youtube",
        json=payload,
        cookies=_cookie("user-a"),
    )
    assert response.status_code == 422
    assert SECRET not in response.text
    assert "bad-prefix-but-long-enough" not in response.text


def test_edgar_contact_is_write_only(client) -> None:
    contact = "researcher@example.test"
    response = client.put(
        "/settings/tools/edgar",
        json={"credential": contact},
        cookies=_cookie("user-a"),
    )
    assert response.status_code == 200
    assert response.json()["credential_kind"] == "contact"
    inventory = client.get("/settings/tools", cookies=_cookie("user-a"))
    assert contact not in inventory.text


def test_oversized_and_malformed_bodies_are_bounded_and_value_free(client) -> None:
    secret = "AIza" + "s" * 2_000
    oversized = client.put(
        "/settings/tools/youtube", content='{"credential":"' + secret + '"}',
        headers={"content-type": "application/json"}, cookies=_cookie("user-a"),
    )
    assert oversized.status_code == 413
    assert secret not in oversized.text
    malformed = client.put(
        "/settings/tools/youtube", content='{"credential":"SENTINEL',
        headers={"content-type": "application/json"}, cookies=_cookie("user-a"),
    )
    assert malformed.status_code == 422
    assert "SENTINEL" not in malformed.text


def test_quota_copy_discloses_host_global_scope(client) -> None:
    response = client.put(
        "/settings/tools/youtube", json={"credential": SECRET}, cookies=_cookie("user-a")
    )
    assert "Host-global shared" in response.json()["quota"]["note"]


def _row(payload: dict, vendor: str) -> dict:
    return next(item for item in payload["connections"] if item["vendor"] == vendor)


def test_x_tool_quota_quotes_a_sourced_pay_per_use_cost_not_an_allowance(client) -> None:
    """The X row must say what a search costs, not just how often it may run.

    X retired the flat 200-USD Basic tier to new signups on 2026-02-06 and now
    bills pay-per-use credits per post RETURNED, so the request ceiling this
    row used to show alone implied an allowance the user does not have.
    """
    payload = client.get("/settings/tools", cookies=_cookie("user-a")).json()
    quota = _row(payload, "x")["quota"]

    # The number, pinned as a literal: 25 posts at the published 0.005 USD read.
    assert quota["estimated_cost_usd"] == 0.125

    note = quota["cost_note"]
    assert note is not None
    assert "pay-per-use" in note
    assert "$0.005 per post returned" in note
    # Sourced and dated, because an unsourced price is what this field prevents.
    assert "https://docs.x.com/x-api/getting-started/pricing" in note
    assert "2026-09-21" in note
    # And explicitly NOT a balance read; X publishes no billing endpoint.
    assert "cannot read your credit balance" in note
    # The retired flat tier must not be quoted back at the user anywhere.
    assert "$200" not in note and "200 dollars" not in note

    # The ceiling is still disclosed, and is now named as Antiek's own brake
    # rather than something the provider grants.
    assert quota["limit"] == 25
    assert "not a provider allowance" in quota["note"]


def test_x_tool_quota_cost_is_not_invented_for_vendors_without_a_sourced_rate(
    client,
) -> None:
    """Silence beats a made-up number for every vendor whose rate is unsourced."""
    payload = client.get("/settings/tools", cookies=_cookie("user-a")).json()
    for vendor in ("youtube", "polygon", "fmp", "edgar"):
        quota = _row(payload, vendor)["quota"]
        assert quota["estimated_cost_usd"] is None, vendor
        assert quota["cost_note"] is None, vendor


def test_tool_connections_inventory_marks_which_vendors_are_searchable(client) -> None:
    """A stored key is only "configured" if some surface will spend it.

    Polygon, FMP and EDGAR are connectable, and nothing on main calls their
    connectors outside the resolver itself, so a user who pastes a paid key
    was told "configured" over zero behaviour. The payload now says which
    vendors a research surface actually reads; the panel labels the rest
    "connected, not yet used". The flag is pinned per vendor so that adding a
    consuming branch is the only way to flip it.
    """
    payload = client.get("/settings/tools", cookies=_cookie("user-a")).json()
    flags = {item["vendor"]: item["searchable"] for item in payload["connections"]}
    assert flags == {
        "youtube": True,
        "x": True,
        "polygon": False,
        "fmp": False,
        "edgar": False,
    }

    # Storing a key does not promote the vendor: the row a PUT hands back
    # is configured_unverified AND still not searchable.
    stored = client.put(
        "/settings/tools/polygon",
        json={"credential": "polygon-key-" + "p" * 24},
        cookies=_cookie("user-a"),
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["status"] == "configured_unverified"
    assert stored.json()["searchable"] is False
