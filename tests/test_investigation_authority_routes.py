from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from interfaces.research.api.app import InvestigationStartRequest, create_app
from interfaces.research.api.broadcast import EventBroadcaster
from interfaces.research.api.investigation_access import (
    authority_from_request,
    bind_new_investigation,
)
from substrate.auth import mint_magic_link_token
from substrate.event_log import emit_typed_authorized, log_event_authorized
from substrate.multi_user.auth import UserClaims
from substrate.schemas import InvestigationStartRequestedPayload, QuestionIdentifiedPayload
from tests.research_quote_support import (
    configure_research_quote_authority,
    post_signed_investigation,
)


def _request(user_id: str | None, app=None) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    if app is not None:
        scope["app"] = app
    request = Request(scope)
    if user_id is not None:
        claims = UserClaims(
            user_id=user_id,
            email=None,
            scopes=frozenset({"private_research"}),
            issued_at="2026-07-15T00:00:00Z",
        )
        request.state.user_claims = claims
        request.state.user_id = user_id
        request.state.scopes = claims.scopes
        request.state.auth_method = "session_cookie"
    return request


def _endpoint(app, path: str, method: str):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    )


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    configure_research_quote_authority(monkeypatch, tmp_path)
    return create_app(broadcaster=EventBroadcaster(), cors_origins=[])


@pytest.mark.asyncio
async def test_start_missing_identity_is_401_before_event_write(isolated_app, tmp_path):
    endpoint = _endpoint(isolated_app, "/investigations", "POST")
    with pytest.raises(HTTPException) as caught:
        await endpoint(
            InvestigationStartRequest(
                question="A sufficiently long question?",
                approved_run_ceiling_usd=1.0,
            ),
            _request(None),
        )
    assert caught.value.status_code == 401
    assert not list((tmp_path / "events").glob("*.jsonl"))


@pytest.mark.asyncio
async def test_signed_quote_binds_exact_command_before_start_write(
    isolated_app, tmp_path
):
    request = _request("alice")
    command = InvestigationStartRequest(
        investigation_id="inv-quoted",
        question="What is true?",
        context="Exact context",
        research_tier="deep",
        approved_run_ceiling_usd=2.0,
    )
    quote = await _endpoint(isolated_app, "/investigations/quote", "POST")(
        command, request
    )
    launch = command.model_copy(update={"research_quote_token": quote.quote_token})
    started = await _endpoint(isolated_app, "/investigations", "POST")(
        launch, request
    )
    assert started.investigation_id == "inv-quoted"
    replayed = await _endpoint(isolated_app, "/investigations", "POST")(
        launch, request
    )
    assert replayed == started

    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority

    rows = trajectory_authorized(
        InvestigationAuthority("alice", "inv-quoted", tmp_path / "events")
    )
    payload = rows[0]["payload"]
    assert payload["research_quote_id"] == quote.quote_id
    assert payload["research_quote_payload_sha256"] == quote.quote_payload_sha256
    assert (
        payload["research_route_manifest_fingerprint"]
        == quote.route_manifest_fingerprint
    )
    route = payload["research_route_manifest"][0]
    assert route["role"] == "decomposer"
    assert route["fallback_index"] == 0
    assert route["provider"] == "provider-test"
    assert route["model"] == "model-test"
    assert route["max_output_tokens"] == 100
    assert route["input_per_mtok"] == 1.0
    assert route["output_per_mtok"] == 2.0
    assert route["currency"] == "USD"
    assert route["source_url"] == "https://provider.example/pricing"
    assert "research_quote_token" not in str(rows)
    assert sum(row["action_type"] == "investigation.start_requested" for row in rows) == 1

    tampered = launch.model_copy(update={"context": "Changed context"})
    with pytest.raises(HTTPException) as caught:
        await _endpoint(isolated_app, "/investigations", "POST")(tampered, request)
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_signed_quote_persists_boot_ready_exact_synthesizer_driver(
    isolated_app, tmp_path
):
    isolated_app.state.registered_providers = {"provider-test"}
    request = _request("alice", isolated_app)
    from interfaces.research.api import settings_budget
    from substrate.dispatch.research_quote import build_research_route_manifest
    from substrate.dispatch.router import DispatchConfig

    manifest = build_research_route_manifest(
        DispatchConfig.from_yaml(settings_budget._dispatch_config_path())
    )
    selected = next(row for row in manifest.routes if row.role == "synthesizer")
    command = InvestigationStartRequest(
        investigation_id="inv-exact-driver",
        question="What is true for this exact driver?",
        research_tier="deep",
        approved_run_ceiling_usd=2.0,
        selected_driver_role="synthesizer",
        selected_driver_provider=selected.provider,
        selected_driver_model=selected.model,
        selected_driver_pricing_fingerprint=selected.pricing_fingerprint,
    )
    quote = await _endpoint(isolated_app, "/investigations/quote", "POST")(
        command, request
    )
    started = await _endpoint(isolated_app, "/investigations", "POST")(
        command.model_copy(update={"research_quote_token": quote.quote_token}),
        request,
    )
    assert started.investigation_id == "inv-exact-driver"

    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority

    [start] = trajectory_authorized(
        InvestigationAuthority("alice", "inv-exact-driver", tmp_path / "events")
    )
    payload = start["payload"]
    assert payload["selected_driver_role"] == "synthesizer"
    assert payload["selected_driver_provider"] == selected.provider
    assert payload["selected_driver_model"] == selected.model
    assert payload["selected_driver_pricing_fingerprint"] == (
        selected.pricing_fingerprint
    )
    assert "research_quote_token" not in str(start)

    isolated_app.state.registered_providers = set()
    with pytest.raises(HTTPException) as unavailable:
        await _endpoint(isolated_app, "/investigations/quote", "POST")(
            command.model_copy(update={"investigation_id": "inv-unready"}),
            request,
        )
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_foreign_and_nonexistent_status_share_404_shape(isolated_app):
    alice_request = _request("alice")
    access = authority_from_request(alice_request, "owned")
    bind_new_investigation(access)
    endpoint = _endpoint(isolated_app, "/investigations/{investigation_id}", "GET")

    details = []
    for investigation_id in ("owned", "never-created"):
        with pytest.raises(HTTPException) as caught:
            await endpoint(investigation_id, _request("bob"))
        details.append((caught.value.status_code, caught.value.detail))
    assert details == [(404, "investigation not found")] * 2


@pytest.mark.asyncio
async def test_list_authenticates_before_absent_directory(isolated_app):
    endpoint = _endpoint(isolated_app, "/investigations", "GET")
    with pytest.raises(HTTPException) as caught:
        await endpoint(_request(None), limit=50, status_filter=None)
    assert caught.value.status_code == 401


@pytest.mark.asyncio
async def test_list_returns_only_callers_leased_streams(isolated_app):
    for user_id, investigation_id in (("alice", "inv-alice"), ("bob", "inv-bob")):
        request = _request(user_id)
        access = authority_from_request(request, investigation_id)
        bind_new_investigation(access)
        emit_typed_authorized(
            access.authority,
            InvestigationStartRequestedPayload(question=f"Question for {user_id}?"),
            role="authenticated_account",
            policy_id="auth/session_cookie",
        )
    endpoint = _endpoint(isolated_app, "/investigations", "GET")
    result = await endpoint(_request("alice"), limit=50, status_filter=None)
    assert result.count == 1
    assert [item.investigation_id for item in result.investigations] == ["inv-alice"]


@pytest.mark.asyncio
async def test_same_display_id_lists_only_callers_composite_rows(isolated_app):
    for user_id in ("alice", "bob"):
        request = _request(user_id)
        access = authority_from_request(request, "inv-shared")
        bind_new_investigation(access)
        emit_typed_authorized(
            access.authority,
            InvestigationStartRequestedPayload(question=f"Question for {user_id}?"),
            role="authenticated_account",
            policy_id="auth/session_cookie",
        )
    endpoint = _endpoint(isolated_app, "/investigations", "GET")
    alice = await endpoint(_request("alice"), limit=50, status_filter=None)
    bob = await endpoint(_request("bob"), limit=50, status_filter=None)
    assert [item.question for item in alice.investigations] == ["Question for alice?"]
    assert [item.question for item in bob.investigations] == ["Question for bob?"]


def test_middleware_authenticated_accounts_isolate_same_display_id_http(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "w3e-http-canary-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv(
        "ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test"
    )
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    configure_research_quote_authority(monkeypatch, tmp_path)
    app = create_app(
        broadcaster=EventBroadcaster(),
        cors_origins=[],
        register_wrestling=False,
        register_providers=False,
    )
    clients = {
        email: TestClient(app)
        for email in ("alice@example.test", "bob@example.test")
    }
    for email, client in clients.items():
        callback = client.get(
            f"/auth/callback?token={mint_magic_link_token(email)}",
            follow_redirects=False,
        )
        assert callback.status_code == 302

    for name, email in (
        ("alice", "alice@example.test"),
        ("bob", "bob@example.test"),
    ):
        response = post_signed_investigation(
            clients[email],
            {
                "investigation_id": "shared-display-id",
                "question": f"Private question for {name}?",
                "approved_run_ceiling_usd": 1.0,
            },
        )
        assert response.status_code == 202, response.text

    for name, email in (
        ("alice", "alice@example.test"),
        ("bob", "bob@example.test"),
    ):
        response = clients[email].get("/investigations")
        assert response.status_code == 200, response.text
        rows = response.json()["investigations"]
        assert [row["question"] for row in rows] == [f"Private question for {name}?"]


@pytest.mark.asyncio
async def test_watch_for_later_is_account_scoped_for_same_display_id(isolated_app):
    for user_id in ("alice", "bob"):
        access = authority_from_request(_request(user_id), "inv-shared")
        bind_new_investigation(access)
        emit_typed_authorized(
            access.authority,
            QuestionIdentifiedPayload(
                question_id=f"q-{user_id}",
                question_text=f"Parked for {user_id}?",
            ),
            document_id=f"doc-{user_id}",
            role="authenticated_account",
            policy_id="auth/session_cookie",
        )
    endpoint = _endpoint(isolated_app, "/watch-for-later", "GET")
    alice = await endpoint(_request("alice"), limit=100)
    bob = await endpoint(_request("bob"), limit=100)
    assert [entry.question_id for entry in alice.questions] == ["q-alice"]
    assert [entry.question_id for entry in bob.questions] == ["q-bob"]


@pytest.mark.asyncio
async def test_provider_ratio_rejects_authenticated_non_operator(isolated_app):
    endpoint = _endpoint(isolated_app, "/ops/provider-ratio", "GET")
    with pytest.raises(HTTPException) as caught:
        await endpoint(
            _request("alice"),
            window_minutes=15,
            openrouter_alert_threshold=0.1,
        )
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_billing_summary_rejects_foreign_authenticated_account(isolated_app):
    endpoint = _endpoint(
        isolated_app,
        "/billing/summary/{user_id}/{period}",
        "GET",
    )
    with pytest.raises(HTTPException) as caught:
        await endpoint("alice", "2026-07", _request("bob"))
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_suggestions_isolate_same_display_id_by_account(isolated_app):
    for user_id in ("alice", "bob"):
        access = authority_from_request(_request(user_id), "inv-shared")
        bind_new_investigation(access)
        log_event_authorized(
            access.authority,
            "evidence.retrieve.delivered",
            payload={
                "evidentiary_gaps": [
                    {
                        "gap_description": f"Gap visible only to {user_id}?",
                        "additional_retrieval_suggested": None,
                    }
                ]
            },
        )
    from interfaces.research.api.cascade_routes import suggestions

    alice = await suggestions(_request("alice"), limit=8)
    bob = await suggestions(_request("bob"), limit=8)
    assert [item.question for item in alice.suggestions] == [
        "Gap visible only to alice?"
    ]
    assert [item.question for item in bob.suggestions] == ["Gap visible only to bob?"]
