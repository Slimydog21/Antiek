"""Export query-route safety and the full application's operator boundary.

Injected export metadata isolates adapter and renderer failures. Authentication
tests use the real app and resolver against the autouse scratch database.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import synthesis_artifact as mod
from services.html_projection.adapters.synthesis import Claim, SourceRef, SynthesisExport
from services.html_projection.gate import assert_script_free


def route_client() -> TestClient:
    app = FastAPI()
    mod.register_synthesis_artifact_routes(app)
    return TestClient(app)


@pytest.mark.parametrize("format_name", ["html", "antiek", "antiek_html"])
def test_query_export_refuses_restricted_metadata(
    monkeypatch: pytest.MonkeyPatch, format_name: str,
) -> None:
    export = SynthesisExport(
        synthesis_id="restricted", target_question="Q?", restricted=True,
        restriction_reason="owner withheld this synthesis",
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid: export)
    response = route_client().get(
        f"/api/syntheses/restricted/artifact?format={format_name}",
    )
    assert response.status_code == 403
    assert response.json() == {
        "error": "export_refused", "reason": "owner withheld this synthesis",
        "synthesis_id": "restricted",
    }


def test_html_query_export_withholds_restricted_source_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [
        SourceRef(document_id="public", document_title="Public paper",
                  content_class="public_domain", ip_holder_id=None,
                  locator="/read/public", chunk_text="PUBLIC EXCERPT"),
        SourceRef(document_id="personal", document_title="Private paper",
                  content_class="personal_reading", ip_holder_id="publisher",
                  locator="/read/personal", chunk_text="WITHHELD EXCERPT"),
    ]
    export = SynthesisExport(
        synthesis_id="mixed", target_question="Q?", claims=[Claim("Claim", sources)],
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid: export)
    response = route_client().get("/api/syntheses/mixed/artifact?format=html")
    assert response.status_code == 200
    assert "PUBLIC EXCERPT" in response.text
    assert "WITHHELD EXCERPT" not in response.text
    assert "cite-only" in response.text
    assert "attachment" in response.headers["content-disposition"]
    assert_script_free(response.text)


def test_html_query_export_rejects_poisoned_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = SynthesisExport(synthesis_id="poison", target_question="Q?")
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid: export)
    monkeypatch.setattr(mod, "render", lambda model, context: "<script>poison()</script>")
    response = route_client().get("/api/syntheses/poison/artifact?format=html")
    assert response.status_code == 500
    assert response.json()["detail"] == "artifact failed the zero-script gate; refused"
    assert "poison()" not in response.text


@pytest.mark.parametrize("suffix", ["artifact.html", "artifact?format=html"])
def test_full_app_requires_operator_auth_before_export_resolution(
    monkeypatch: pytest.MonkeyPatch, suffix: str,
) -> None:
    from interfaces.research.api.app import create_app

    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "export-test-operator")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    url = f"/api/syntheses/absent/{suffix}"
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        response = client.get(url, headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "operator_auth_required"
    authorized = client.get(url, headers={"Authorization": "Bearer export-test-operator"})
    assert authorized.status_code == 404
    assert "not found" in authorized.json()["detail"]


def test_full_app_export_checks_signed_cookie_and_operator_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from secrets import token_urlsafe

    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie

    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@example.test")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", token_urlsafe(32))
    client = TestClient(create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    ))
    url = "/api/syntheses/absent/artifact?format=html"
    for cookie in (
        "invalid",
        mint_session_cookie(user_id="other", email="other@example.test"),
    ):
        client.cookies.set("ANTIEK_SESSION", cookie)
        assert client.get(url).status_code == 401
    client.cookies.set("ANTIEK_SESSION", mint_session_cookie(
        user_id="__operator__", email="operator@example.test",
    ))
    response = client.get(url)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
