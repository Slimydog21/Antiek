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
        "youtube", "polygon", "fmp", "edgar",
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
