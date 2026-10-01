"""Signed operator sessions remain separate through owner-paid dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from interfaces.research.api.account_memory_identity import derive_owner_from_verified_email
from interfaces.research.api.app import create_app
from interfaces.research.api.owner_byot_dispatch import (
    OwnerByotDispatchUnavailable,
    authenticated_distinct_owner,
    dispatch_talk_to_book_byot,
)
from interfaces.research.api.settings_models_admin import (
    UserModelChoice,
    _UserOpenAICompatProvider,
)
from substrate.auth.magic_link import mint_session_cookie
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch.base import RawProviderResponse
from substrate.dispatch.router import reset_provider_registry


def test_signed_operator_can_spend_only_own_registered_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    emails = {name: f"{name}@example.test" for name in ("alice", "bob")}
    owners = {name: derive_owner_from_verified_email(email) for name, email in emails.items()}
    assert owners["alice"] and owners["bob"] and owners["alice"] != owners["bob"]
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "test-only-auth-secret-at-least-32-bytes")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", ",".join(emails.values()))
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    cookies = {
        name: {"ANTIEK_SESSION": mint_session_cookie(user_id="__operator__", email=email)}
        for name, email in emails.items()
    }
    secrets = {name: f"sk-test-only-{name}-abcdefghijklmnopqrstuvwxyz" for name in emails}
    sends: list[tuple[str, str, str]] = []

    def offline_call(
        self: _UserOpenAICompatProvider, *, model: str, prompt: str,
        max_tokens: int, temperature: float,
    ) -> RawProviderResponse:
        sends.append((self.name, model, self._resolve_api_key()))
        return RawProviderResponse(
            text="offline answer", raw_usage={"prompt_tokens": 1000, "completion_tokens": 1000},
            finish_reason="stop", latency_ms=1,
        )

    monkeypatch.setattr(_UserOpenAICompatProvider, "call", offline_call)
    reset_provider_registry()
    app = create_app(register_wrestling=False, register_providers=False)

    @app.post("/__test__/owner-paid")
    def paid(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        owner = authenticated_distinct_owner(request)
        try:
            result, authority = dispatch_talk_to_book_byot(
                app=request.app,
                request_owner_user_id=owner,
                resource_owner_user_id=owner,
                document_id="test-document",
                choice=UserModelChoice.model_validate(payload["choice"]),
                prompt="offline paid prompt",
                investigation_id="inv-signed-owner-paid",
                logical_operation_id=payload["operation_id"],
                usage_ledger=ledger,
            )
        except OwnerByotDispatchUnavailable:
            raise HTTPException(status_code=409, detail="owner_model_unavailable") from None
        return {
            "owner": owner, "provider": result.provider, "model": result.model,
            "text": result.text, "rungs": len(authority.fallback_manifest),
            "payer_policy": authority.payer_policy,
            "fallback": result.fallback_chain_index,
        }

    try:
        with TestClient(app) as client:
            created = {}
            for name in emails:
                response = client.post(
                    "/settings/models/user",
                    json={
                        "provider_kind": "openai_compat",
                        "provider_catalog_id": "deepseek",
                        "model_id": "deepseek-flash-nothink",
                        "display_name": "My DeepSeek",
                        "api_key": secrets[name],
                    },
                    cookies=cookies[name],
                )
                assert response.status_code == 201, response.text
                created[name] = response.json()["id"]
            assert created["alice"] != created["bob"]
            def choice(name: str) -> dict[str, str]:
                return {
                    "authority": "user_model", "provider_id": created[name],
                    "model_id": "deepseek-flash-nothink",
                }

            ledger.record_settlement(created["bob"], owners["bob"], 125, "b" * 64)
            bob_before = ledger.snapshot(owners["bob"])

            # A signed operator cannot route through the other operator's key.
            denied = client.post(
                "/__test__/owner-paid",
                json={"choice": choice("bob"), "operation_id": "denied-bob"},
                cookies=cookies["alice"],
            )
            assert denied.status_code == 409
            assert sends == []
            assert ledger.snapshot(owners["alice"]) == []
            assert ledger.snapshot(owners["bob"]) == bob_before
            assert ledger.operation(owners["bob"], "denied-bob") is None

            allowed = client.post(
                "/__test__/owner-paid",
                json={"choice": choice("alice"), "operation_id": "alice-paid"},
                cookies=cookies["alice"],
            )
            assert allowed.status_code == 200, allowed.text
            assert allowed.json() == {
                "owner": owners["alice"], "provider": created["alice"],
                "model": "deepseek-flash-nothink", "text": "offline answer",
                "rungs": 1, "payer_policy": "byot_only", "fallback": 0,
            }
            assert sends == [(created["alice"], "deepseek-flash-nothink", secrets["alice"])]
            settled = ledger.operation(owners["alice"], "alice-paid")
            assert settled is not None and settled.state == "settled"
            assert settled.api_key_id == created["alice"]
            assert settled.actual_cents is not None and settled.actual_cents > 0
            usage = ledger.key_usage(created["alice"], owners["alice"])
            assert usage is not None and usage.used_cents == settled.actual_cents
            assert ledger.snapshot(owners["bob"]) == bob_before
    finally:
        reset_provider_registry()
