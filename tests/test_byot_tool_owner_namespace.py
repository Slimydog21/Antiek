"""A tool connected in Settings must be found by the search that spends it.

``settings_tool_connections._owner`` returned ``request.state.user_id`` verbatim.
Every production login mints ``__operator__`` on a session cookie, so a
connection was WRITTEN under ``__operator__`` while ``research_tool_search`` READ
it under the derived ``acct_<hash>``. The registry hashes the owner into the row
key, so the two never named the same row: connecting a tool succeeded and every
search or ingest that would spend it answered 503.

#3382 aligned the tokens lane (model keys) on the same derived owner. These
tests pin the tools lane to it: write and read resolve one owner, that owner is
the one a model key from the same login lands under, and a key pasted into
Settings is the key the vendor receives.
"""

from __future__ import annotations

import types
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import runtime.connectors.youtube as youtube_connector
from interfaces.research.api import research_tool_search
from interfaces.research.api.account_memory_identity import derive_owner_from_verified_email
from interfaces.research.api.app import create_app
from interfaces.research.api.owner_byot_dispatch import authenticated_distinct_owner
from interfaces.research.api.research_tool_search import _owner as read_owner
from interfaces.research.api.research_tool_search import _PublicError
from interfaces.research.api.settings_models_admin import request_owner_user_id
from interfaces.research.api.settings_tool_connections import _owner as write_owner
from substrate.auth.magic_link import mint_session_cookie

ADDRESS = "operator@example.test"
OTHER_ADDRESS = "second-operator@example.test"
SESSION = "antiek_session_cookie"
SECRET = "AIza" + "RoundTrip0" * 3


def _request(*, auth_method: str | None, user_id: str, email: str | None = ADDRESS) -> Any:
    return SimpleNamespace(
        state=SimpleNamespace(auth_method=auth_method, user_id=user_id, user_email=email)
    )


def _write(request: Any) -> str | None:
    try:
        return write_owner(request)
    except HTTPException as exc:
        assert exc.status_code == 401
        return None


def _read(request: Any) -> str | None:
    try:
        return read_owner(request)
    except _PublicError as exc:
        assert exc.status == 401
        return None


# ---------------------------------------------------------------------------
# The two halves resolve one owner, and it is the tokens lane's owner
# ---------------------------------------------------------------------------


def test_a_real_login_writes_and_reads_tools_under_the_derived_owner() -> None:
    request = _request(auth_method=SESSION, user_id="__operator__")
    owner = write_owner(request)
    assert owner == derive_owner_from_verified_email(ADDRESS)
    assert owner == read_owner(request)


def test_tools_and_model_keys_from_one_login_share_one_owner() -> None:
    """The #3382 tokens write path and the BYOT spend path agree with both tool halves."""
    request = _request(auth_method=SESSION, user_id="__operator__")
    assert (
        write_owner(request)
        == read_owner(request)
        == request_owner_user_id(request)
        == authenticated_distinct_owner(request)
    )


@pytest.mark.parametrize("auth_method", [SESSION, "bearer_token", "cloudflare_service_token",
                                         "cloudflare_access_email", "unauthenticated_local", None])
@pytest.mark.parametrize("user_id", ["__operator__", "user-7f3a", "shared", "service", "local", ""])
@pytest.mark.parametrize("email", [ADDRESS, None, "not-an-email"])
def test_write_and_read_never_disagree(auth_method: str | None, user_id: str,
                                       email: str | None) -> None:
    """Either both halves refuse or both name the same owner, for every identity shape."""
    request = _request(auth_method=auth_method, user_id=user_id, email=email)
    assert _write(request) == _read(request)


@pytest.mark.parametrize(
    ("auth_method", "user_id", "email"),
    [
        ("bearer_token", "__operator__", ADDRESS),
        ("cloudflare_service_token", "__operator__", ADDRESS),
        ("unauthenticated_local", "__operator__", ADDRESS),
        (SESSION, "shared", ADDRESS),
        (SESSION, "__operator__", None),
    ],
)
def test_the_write_half_fails_closed(auth_method: str, user_id: str, email: str | None) -> None:
    assert _write(_request(auth_method=auth_method, user_id=user_id, email=email)) is None


def test_a_genuine_per_user_id_passes_through_unchanged() -> None:
    request = _request(auth_method=SESSION, user_id="user-7f3a")
    assert write_owner(request) == read_owner(request) == "user-7f3a"


# ---------------------------------------------------------------------------
# End to end: the real app, a real login cookie, the real registry and BYOK
# store and the real YouTube connector. Only the vendor's HTTP is mocked.
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "tool-owner-namespace-test-secret-32-bytes-min")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{ADDRESS},{OTHER_ADDRESS}")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_TOOL_CONNECTIONS_PATH", str(tmp_path / "tools.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    monkeypatch.setenv("ANTIEK_CONNECTOR_QUOTA_DIR", str(tmp_path / "quota"))
    monkeypatch.setenv("ANTIEK_TOOL_SEARCH_JOURNAL", str(tmp_path / "journal.sqlite3"))
    with TestClient(create_app(register_wrestling=False, register_providers=False)) as client:
        yield client


@pytest.fixture
def vendor_keys(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """The ``key`` query param of every YouTube request that left the connector."""
    seen: list[str | None] = []

    def vendor(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("key"))
        return httpx.Response(200, json={"items": [{
            "id": {"kind": "youtube#video", "videoId": "dQw4w9WgXcQ"},
            "snippet": {"title": "hit", "channelTitle": "chan"},
        }]})

    real_client = httpx.Client
    shim = types.ModuleType("httpx")
    shim.__dict__.update(httpx.__dict__)
    shim.Client = lambda **kw: real_client(transport=httpx.MockTransport(vendor), **kw)  # type: ignore[attr-defined]
    monkeypatch.setattr(youtube_connector, "httpx", shim)
    return seen


def _cookie(email: str) -> dict[str, str]:
    # Exactly what every login path in auth.py mints.
    return {"ANTIEK_SESSION": mint_session_cookie(user_id="__operator__", email=email)}


def _search(client: TestClient, email: str, op: str) -> httpx.Response:
    return client.post("/research/tools/search", cookies=_cookie(email), json={
        "operation_id": f"search_operation_{op}", "vendor": "youtube",
        "query": "fusion materials", "max_results": 5,
    })


def test_a_key_connected_in_settings_is_the_key_search_spends(
    app_client: TestClient, vendor_keys: list[str | None]
) -> None:
    put = app_client.put(
        "/settings/tools/youtube", json={"credential": SECRET}, cookies=_cookie(ADDRESS)
    )
    assert put.status_code == 200, put.text

    found = _search(app_client, ADDRESS, "round_trip_01")

    assert found.status_code == 200, found.text
    assert [c["external_id"] for c in found.json()["candidates"]] == ["dQw4w9WgXcQ"]
    assert vendor_keys == [SECRET]


def test_a_key_connected_in_settings_is_the_key_ingest_resolves(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved: list[object] = []

    def fetch_and_ingest(connector: object, body: Any) -> research_tool_search.IngestResponse:
        resolved.append(connector)
        return research_tool_search.IngestResponse(
            operation_id=body.operation_id, vendor=body.vendor, external_id=body.external_id,
            status="completed", ingest_status="ingested", document_id="doc-1",
            chunks_written=1, skipped_reason=None, title="t",
            content_class="personal_reading", source_tier=3,
        )

    monkeypatch.setattr(research_tool_search, "_fetch_and_ingest", fetch_and_ingest)
    assert app_client.put(
        "/settings/tools/youtube", json={"credential": SECRET}, cookies=_cookie(ADDRESS)
    ).status_code == 200

    ingested = app_client.post("/research/tools/ingest", cookies=_cookie(ADDRESS), json={
        "operation_id": "ingest_operation_round_trip", "vendor": "youtube",
        "external_id": "dQw4w9WgXcQ",
    })

    assert ingested.status_code == 200, ingested.text
    assert [type(c).__name__ for c in resolved] == ["YouTubeDataConnector"]


def test_a_second_allowlisted_operator_cannot_spend_the_first_ones_key(
    app_client: TestClient, vendor_keys: list[str | None]
) -> None:
    assert app_client.put(
        "/settings/tools/youtube", json={"credential": SECRET}, cookies=_cookie(ADDRESS)
    ).status_code == 200

    theirs = _search(app_client, OTHER_ADDRESS, "second_operator")

    assert theirs.status_code == 503
    assert vendor_keys == []
