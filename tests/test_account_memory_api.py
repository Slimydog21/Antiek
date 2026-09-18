from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from substrate.auth import mint_session_cookie
from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    register_provider,
    reset_provider_registry,
)
from substrate.graph.schema import init_database_at_path

_SECRET = "account-memory-api-test-" + "x" * 48
_EMAIL = "owner@example.test"


class _Provider:
    name = "zai"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def call(self, **kwargs: Any) -> RawProviderResponse:
        self.prompts.append(str(kwargs["prompt"]))
        return RawProviderResponse(
            text='{"shape":"synthesis","synthesis_text":"ok"}',
            raw_usage={},
            finish_reason="stop",
            latency_ms=1,
            request_id="memory-api-test",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=0, output_tokens=0)


@pytest.fixture(autouse=True)
def _providers() -> None:
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = str(tmp_path / "memory.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    init_database_at_path(db_path)
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


def _cookie(owner: str) -> dict[str, str]:
    return {"ANTIEK_SESSION": mint_session_cookie(user_id=owner, email=_EMAIL)}


def _payload(value: str, at: datetime) -> dict[str, object]:
    return {
        "subject": "operator",
        "predicate": "prefers_editor",
        "object": value,
        "provenance": {"source_ref": f"conversation-{value}"},
        "valid_from": at.isoformat(),
    }


def test_post_get_are_owner_isolated_and_supersede_is_current_only(client: TestClient) -> None:
    first_at = datetime.now(UTC) - timedelta(seconds=2)
    first = client.post(
        "/account/memory", cookies=_cookie("owner-a"), json=_payload("vim", first_at)
    )
    other = client.post(
        "/account/memory", cookies=_cookie("owner-b"), json=_payload("emacs", first_at)
    )
    assert first.status_code == 200 and first.json()["action"] == "ADD"
    assert other.status_code == 200
    assert first.json()["item"]["provenance"]["authority"] == "antiek_session_cookie"
    assert "authority_owner_user_id" not in first.json()["item"]["provenance"]

    updated = client.post(
        "/account/memory",
        cookies=_cookie("owner-a"),
        json=_payload("zed", first_at + timedelta(seconds=1)),
    )
    assert updated.status_code == 200
    assert updated.json()["action"] == "SUPERSEDE"
    assert [
        row["object"]
        for row in client.get(
            "/account/memory?q=editor&limit=8", cookies=_cookie("owner-a")
        ).json()["items"]
    ] == ["zed"]
    assert [
        row["object"]
        for row in client.get("/account/memory", cookies=_cookie("owner-b")).json()["items"]
    ] == ["emacs"]

    provider = _Provider()
    register_provider(provider)
    thought = client.post(
        "/thought-partner", cookies=_cookie("owner-a"), json={"prompt": "which editor?"}
    )
    assert thought.status_code == 200
    assert provider.prompts and "zed" in provider.prompts[0]
    assert "vim" not in provider.prompts[0] and "emacs" not in provider.prompts[0]


@pytest.mark.parametrize("owner", ["shared", "service", "local"])
def test_private_memory_rejects_non_distinct_owner(client: TestClient, owner: str) -> None:
    """Shared and machine identities get no owner, and no e-mail fallback rescues them.

    ``__operator__`` is deliberately absent from this list — see the test below. These
    three are: no authentication path mints them, so their presence means a genuinely
    shared or service context, and they stay hard-refused even with a verified address.
    """
    response = client.post(
        "/account/memory", cookies=_cookie(owner), json=_payload("secret", datetime.now(UTC))
    )
    assert response.status_code == 401
    assert "secret" not in response.text


def test_operator_sentinel_resolves_to_a_stable_derived_owner(client: TestClient) -> None:
    """The single-operator storage sentinel is a person, proved by the verified e-mail.

    Every production login mints ``user_id="__operator__"``, so before this the predicate
    returned None for every real session and all three consumers — account-memory context,
    the account-memory routes and the document-ingest route — were unreachable. The ingest
    route answered a bare 401 to the operator on his own deployment.
    """
    written = client.post(
        "/account/memory",
        cookies=_cookie("__operator__"),
        json=_payload("kate", datetime.now(UTC)),
    )
    assert written.status_code == 200, written.text

    # Stable across sessions: a second login with the same verified address reads it back.
    read = client.get("/account/memory?q=editor&limit=8", cookies=_cookie("__operator__"))
    assert read.status_code == 200
    assert [row["object"] for row in read.json()["items"]] == ["kate"]


def test_operator_sentinel_without_a_verified_email_still_fails_closed(
    client: TestClient,
) -> None:
    """No address, no owner. The fallback must not invent one."""
    from substrate.auth import mint_session_cookie

    response = client.post(
        "/account/memory",
        cookies={"ANTIEK_SESSION": mint_session_cookie(user_id="__operator__", email="")},
        json=_payload("secret", datetime.now(UTC)),
    )
    assert response.status_code in {401, 403}
    assert "secret" not in response.text


def test_derived_owner_is_opaque_distinct_and_stable() -> None:
    """Unit-level properties of the derivation, independent of the HTTP stack."""
    from types import SimpleNamespace

    from interfaces.research.api.account_memory_identity import (
        SESSION_AUTH_METHOD,
        distinct_signed_owner,
    )

    def owner_for(email: str | None, user_id: str = "__operator__") -> str | None:
        request = SimpleNamespace(
            state=SimpleNamespace(
                auth_method=SESSION_AUTH_METHOD, user_id=user_id, user_email=email
            )
        )
        return distinct_signed_owner(request)  # type: ignore[arg-type]

    first = owner_for("Owner@Example.test")
    assert first is not None
    # Stable across logins and case/whitespace normalized.
    assert first == owner_for("  owner@example.TEST  ")
    # Distinct between people.
    assert first != owner_for("other@example.test")
    # Opaque: the address does not appear in the stored owner value.
    assert "owner" not in first.removeprefix("acct_")
    assert "@" not in first and "example" not in first
    # Malformed or missing addresses yield no owner.
    assert owner_for(None) is None
    assert owner_for("") is None
    assert owner_for("not-an-email") is None
    assert owner_for("a@b@c") is None
    # A genuine per-user id is returned verbatim, never hashed.
    assert owner_for("owner@example.test", user_id="usr_real_123") == "usr_real_123"


def test_schema_missing_fails_closed_without_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blank = tmp_path / "blank.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(blank))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    from interfaces.research.api.app import create_app

    local = TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )
    response = local.get("/account/memory", cookies=_cookie("owner-a"))
    assert response.status_code == 503
    assert response.json() == {"detail": "account memory unavailable"}


@pytest.mark.parametrize("key", ["authority_owner", " Authority_Request_Id ", "AUTHORITY_spoof"])
def test_client_cannot_supply_server_authority_provenance(
    client: TestClient,
    key: str,
) -> None:
    payload = _payload("secret", datetime.now(UTC))
    payload["provenance"] = {"source_ref": "source", key: "forged"}
    response = client.post("/account/memory", cookies=_cookie("owner-a"), json=payload)
    assert response.status_code == 422
    assert "forged" not in response.text and "secret" not in response.text


def test_augmented_provenance_is_rechecked_against_serialized_bound(
    client: TestClient,
) -> None:
    payload = _payload("secret", datetime.now(UTC))
    # Client JSON fits alone, but server-owned authority makes the final record exceed 8 KiB.
    payload["provenance"] = {"source_ref": "x" * 8_140}
    response = client.post("/account/memory", cookies=_cookie("owner-a"), json=payload)
    assert response.status_code == 422
    assert "secret" not in response.text


@pytest.mark.parametrize("raw", ['["TOP LEVEL SECRET"]', '"TOP LEVEL SECRET"'])
def test_non_object_body_is_value_free(client: TestClient, raw: str) -> None:
    response = client.post(
        "/account/memory",
        cookies=_cookie("owner-a"),
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "memory write is invalid"}
    assert "TOP LEVEL SECRET" not in response.text


def test_overlong_query_is_value_free(client: TestClient) -> None:
    secret = "QUERY SECRET " + "x" * 600
    response = client.get("/account/memory", cookies=_cookie("owner-a"), params={"q": secret})
    assert response.status_code == 422
    assert response.json() == {"detail": "memory query is invalid"}
    assert secret not in response.text and "QUERY SECRET" not in response.text
