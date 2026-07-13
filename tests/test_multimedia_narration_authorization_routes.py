from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes as multimedia_routes_module
from interfaces.research.api.multimedia_narration_authorization_routes import (
    MultimediaNarrationAuthorizationRuntime,
    get_multimedia_narration_authorization_runtime,
    multimedia_narration_authorization_router,
    multimedia_narration_authorization_runtime_from_environment,
)
from substrate.multimedia.execution_authorization_issuer import ExecutionAuthorizationIssuer
from substrate.multimedia.narration_authorization import TrustedNarrationTerms
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _setup(tmp_path: Path, owner: str = "owner-1") -> tuple[TestClient, str, str]:
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Authorized narration",
            target_minutes=15,
            mode="video",
            route_policy="balanced",
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    terms = TrustedNarrationTerms(
        provider="trusted-tts",
        model="voice-1",
        endpoint_capability="text-to-speech",
        catalog_version="catalog-1",
        catalog_digest="a" * 64,
        quote_id="quote-1",
        quote_ttl_seconds=600,
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest="b" * 64,
        maximum_ceiling_microdollars=500_000,
    )
    runtime = MultimediaNarrationAuthorizationRuntime(
        store=store,
        issuer=ExecutionAuthorizationIssuer(
            db_path=str(tmp_path / "authorization.duckdb"), signing_key=b"s" * 32
        ),
        terms_resolver=lambda _record, _chapter: terms,
        clock=lambda: NOW,
    )
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = owner
        return await call_next(request)

    app.include_router(multimedia_narration_authorization_router, prefix="/api/multimedia")
    app.dependency_overrides[get_multimedia_narration_authorization_runtime] = lambda: runtime
    return TestClient(app), ready.asset.asset_id, ready.plan.chapters[0].chapter_id


def _body(chapter_id: str, **changes) -> dict[str, object]:
    body: dict[str, object] = {
        "request_id": "request-1",
        "expected_revision_id": "rev-1",
        "chapter_id": chapter_id,
        "approved_ceiling_microdollars": 250_000,
        "operator_acknowledged_spend": True,
    }
    body.update(changes)
    return body


def test_route_returns_server_derived_v2_authority_and_exact_replay(tmp_path: Path) -> None:
    client, asset_id, chapter_id = _setup(tmp_path)
    url = f"/api/multimedia/assets/{asset_id}/narration-authorizations"
    first = client.post(url, json=_body(chapter_id))
    assert first.status_code == 200
    payload = first.json()
    assert payload["chapter_id"] == chapter_id
    assert payload["authorization"]["request_body_digest"] == payload["request_body_digest"]
    assert payload["authorization"]["provider"] == "trusted-tts"
    serialized = first.text
    assert '"text"' not in serialized and '"body_json"' not in serialized
    assert client.post(url, json=_body(chapter_id)).json() == payload

    conflict = client.post(url, json=_body(chapter_id, speed=1.1))
    assert conflict.status_code == 409


def test_foreign_owner_and_unacknowledged_spend_fail(tmp_path: Path) -> None:
    foreign, asset_id, chapter_id = _setup(tmp_path, owner="owner-2")
    response = foreign.post(
        f"/api/multimedia/assets/{asset_id}/narration-authorizations",
        json=_body(chapter_id),
    )
    assert response.status_code == 404
    owner, asset_id, chapter_id = _setup(tmp_path / "owner")
    denied = owner.post(
        f"/api/multimedia/assets/{asset_id}/narration-authorizations",
        json=_body(chapter_id, operator_acknowledged_spend=False),
    )
    assert denied.status_code == 409


def test_environment_configuration_is_all_or_nothing(tmp_path: Path) -> None:
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    assert multimedia_narration_authorization_runtime_from_environment(store=store, environ={}) is None
    values = {
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_ENABLED": "true",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_DB_PATH": str(tmp_path / "auth.duckdb"),
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_SIGNING_KEY_HEX": "11" * 32,
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_PROVIDER": "trusted-tts",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_MODEL": "voice-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_CATALOG_VERSION": "catalog-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_CATALOG_DIGEST": "aa" * 32,
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_QUOTE_ID": "quote-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_QUOTE_TTL_SECONDS": "600",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_RECOVERY_AUTHORITY_ID": "recovery-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_RECOVERY_VERIFICATION_KEY_DIGEST": "bb" * 32,
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_MAXIMUM_CEILING_MICRODOLLARS": "500000",
    }
    assert multimedia_narration_authorization_runtime_from_environment(
        store=store, environ=values
    ) is not None
    values.pop("ANTIEK_MULTIMEDIA_NARRATION_AUTH_MODEL")
    try:
        multimedia_narration_authorization_runtime_from_environment(store=store, environ=values)
    except RuntimeError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("partial narration authorization configuration must fail")


def test_route_forbids_client_control_of_trusted_terms(tmp_path: Path) -> None:
    client, asset_id, chapter_id = _setup(tmp_path)
    response = client.post(
        f"/api/multimedia/assets/{asset_id}/narration-authorizations",
        json=_body(chapter_id, provider="attacker", request_body_digest="0" * 64),
    )
    assert response.status_code == 422


def test_route_maps_issuer_infrastructure_failure_to_unavailable(tmp_path: Path) -> None:
    client, asset_id, chapter_id = _setup(tmp_path)
    runtime = client.app.dependency_overrides[
        get_multimedia_narration_authorization_runtime
    ]()

    class FailingIssuer:
        def issue_async(self, *_args, **_kwargs):
            raise RuntimeError("database path leaked")

    client.app.dependency_overrides[get_multimedia_narration_authorization_runtime] = lambda: (
        MultimediaNarrationAuthorizationRuntime(
            store=runtime.store,
            issuer=FailingIssuer(),  # type: ignore[arg-type]
            terms_resolver=runtime.terms_resolver,
            clock=runtime.clock,
        )
    )
    response = client.post(
        f"/api/multimedia/assets/{asset_id}/narration-authorizations",
        json=_body(chapter_id),
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "multimedia narration authorization is unavailable"


def test_app_registration_composes_narration_runtime(tmp_path: Path, monkeypatch) -> None:
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    runtime = MultimediaNarrationAuthorizationRuntime(
        store=store,
        issuer=ExecutionAuthorizationIssuer(
            db_path=str(tmp_path / "authorization.duckdb"), signing_key=b"s" * 32
        ),
        terms_resolver=lambda _record, _chapter: TrustedNarrationTerms(
            provider="trusted-tts",
            model="voice-1",
            endpoint_capability="text-to-speech",
            catalog_version="catalog-1",
            catalog_digest="a" * 64,
            quote_id="quote-1",
            quote_ttl_seconds=600,
            recovery_authority_id="recovery-1",
            recovery_verification_key_digest="b" * 64,
            maximum_ceiling_microdollars=500_000,
        ),
        clock=lambda: NOW,
    )
    monkeypatch.setattr(multimedia_routes_module, "_STORE", store)
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_reconciliation_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_knowledge_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_playback_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_narration_authorization_runtime_from_environment",
        lambda *, store: runtime,
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    configured = app.dependency_overrides[
        get_multimedia_narration_authorization_runtime
    ]()
    assert configured is runtime


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ANTIEK_MULTIMEDIA_NARRATION_AUTH_CATALOG_DIGEST", "z" * 64),
        ("ANTIEK_MULTIMEDIA_NARRATION_AUTH_RECOVERY_VERIFICATION_KEY_DIGEST", "z" * 64),
        (
            "ANTIEK_MULTIMEDIA_NARRATION_AUTH_MAXIMUM_CEILING_MICRODOLLARS",
            str(9_223_372_036_854_775_808),
        ),
    ],
)
def test_environment_rejects_malformed_trusted_terms(
    tmp_path: Path, field: str, value: str
) -> None:
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    values = {
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_ENABLED": "true",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_DB_PATH": str(tmp_path / "auth.duckdb"),
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_SIGNING_KEY_HEX": "11" * 32,
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_PROVIDER": "trusted-tts",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_MODEL": "voice-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_CATALOG_VERSION": "catalog-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_CATALOG_DIGEST": "aa" * 32,
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_QUOTE_ID": "quote-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_QUOTE_TTL_SECONDS": "600",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_RECOVERY_AUTHORITY_ID": "recovery-1",
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_RECOVERY_VERIFICATION_KEY_DIGEST": "bb" * 32,
        "ANTIEK_MULTIMEDIA_NARRATION_AUTH_MAXIMUM_CEILING_MICRODOLLARS": "500000",
    }
    values[field] = value
    with pytest.raises(RuntimeError, match="invalid"):
        multimedia_narration_authorization_runtime_from_environment(
            store=store, environ=values
        )
