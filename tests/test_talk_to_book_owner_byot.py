"""Exact owner-selected BYOT execution for Talk-to-Book."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from interfaces.research.api import settings_models_admin as models_admin
from interfaces.research.api.owner_byot_dispatch import (
    OwnerByotDispatchUnavailable,
    OwnerByotOutcomeUnknown,
    dispatch_talk_to_book_byot,
)
from runtime.byok.store import CredentialMetadata
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    register_provider,
    reset_provider_registry,
)
from substrate.dispatch.router import DispatchConfig, TierConfig, TierPricing


class _Provider:
    def __init__(self, name: str, fingerprint: str) -> None:
        self.name = name
        self._user_model_authority_fingerprint = fingerprint
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return RawProviderResponse(
            text="owner answer",
            raw_usage={"input_tokens": 2, "output_tokens": 3},
            finish_reason="stop",
            latency_ms=1,
            request_id="owner-byot",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage["input_tokens"]),
            output_tokens=int(raw_usage["output_tokens"]),
        )


@pytest.fixture(autouse=True)
def _registry() -> None:
    reset_provider_registry()
    yield
    reset_provider_registry()


def _config() -> DispatchConfig:
    pricing = TierPricing()
    fallback = TierConfig(
        "thought_partner__fallback", "house", "house-model", 200, 0.1, 1000, pricing,
    )
    tier = TierConfig(
        "pro", "house", "house-model", 200, 0.1, 1000, pricing, fallback,
    )
    return DispatchConfig({"thought_partner": "pro"}, {"pro": tier})


def _authority_fixture(monkeypatch: pytest.MonkeyPatch, model_id: str = "deepseek-flash"):
    record = models_admin.UserModelRecord(
        id="user-owner-model",
        owner_user_id="owner-a",
        provider_kind="openai_compat",
        provider_catalog_id="deepseek",
        model_id=model_id,
        display_name="Owner model",
        base_url="https://api.deepseek.com",
        cred_ref="cred-owner",
        cred_fingerprint="a" * 64,
    )
    metadata = CredentialMetadata(
        cred_id="cred-owner",
        account_handle=record.id,
        pipeline_kind="model_provider",
        binding_version=3,
        artifact_fingerprint="a" * 64,
        owner_user_id="owner-a",
    )
    app = FastAPI()

    @app.middleware("http")
    async def _test_identity(request, call_next):
        request.state.user_id = "owner-a"
        request.state.user_email = "operator-under-test@example.com"
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    fingerprint = models_admin._record_fingerprint(record)
    app.state.user_model_registration_fingerprints = {record.id: fingerprint}
    provider = _Provider(record.id, fingerprint)
    house = _Provider("house", "house")
    register_provider(provider)
    register_provider(house)
    monkeypatch.setattr(models_admin, "_load_registry", lambda: {record.id: record})
    monkeypatch.setattr(models_admin, "_credential_metadata", lambda: {metadata.cred_id: metadata})
    return app, record, metadata, provider, house


def test_exact_owner_model_executes_one_rung_without_house_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    app, record, _, provider, house = _authority_fixture(monkeypatch)
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    result, authority = dispatch_talk_to_book_byot(
        app=app,
        request_owner_user_id="owner-a",
        resource_owner_user_id="owner-a",
        document_id="doc-a",
        choice=models_admin.UserModelChoice(
            authority="user_model", provider_id=record.id, model_id=record.model_id,
        ),
        prompt="private book prompt",
        investigation_id="read-doc-a",
        logical_operation_id="turn-1",
        config=_config(),
        usage_ledger=ledger,
    )

    assert result.text == "owner answer"
    assert (result.provider, result.model) == (record.id, record.model_id)
    assert len(authority.fallback_manifest) == 1
    assert authority.payer_policy.value == "byot_only"
    assert authority.owner_user_id == "owner-a"
    assert authority.resource_id == "doc-a"
    assert len(authority.digest()) == 64
    assert provider.calls[0]["prompt"] == "private book prompt"
    assert house.calls == []
    # deepseek-flash peak cache-miss rates: $0.30 in / $1.20 out per 1M tokens.
    assert result.cost_usd == pytest.approx((2 * 0.30 + 3 * 1.20) / 1_000_000)
    assert ledger.key_usage(record.id, "owner-a").used_cents == 1


@pytest.mark.parametrize(("stored", "sent"), [
    ("deepseek-chat", "deepseek-flash-nothink"),
    ("deepseek-reasoner", "deepseek-flash"),
    ("deepseek-v4-flash", "deepseek-flash"),
])
def test_record_saved_under_a_retired_name_keeps_its_mode_and_price(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stored: str, sent: str,
) -> None:
    """A key registered before DeepSeek retired deepseek-chat/deepseek-reasoner
    must not fail at the provider: it is priced, bound and dispatched as the
    current variant with the same mode, at Flash rates, and a remembered
    choice under the old name still resolves."""
    app, record, _, provider, house = _authority_fixture(monkeypatch, model_id=stored)
    result, authority = dispatch_talk_to_book_byot(
        app=app,
        request_owner_user_id="owner-a",
        resource_owner_user_id="owner-a",
        document_id="doc-a",
        choice=models_admin.UserModelChoice(
            authority="user_model", provider_id=record.id, model_id=stored,
        ),
        prompt="private book prompt",
        investigation_id="read-doc-a",
        logical_operation_id="turn-legacy",
        config=_config(),
        usage_ledger=ByotUsageLedger(tmp_path / "usage.sqlite3"),
    )
    assert provider.calls[0]["model"] == sent
    assert (result.provider, result.model) == (record.id, sent)
    # Flash peak cache-miss rates, never Pro's $1.32 / $3.96.
    assert result.cost_usd == pytest.approx((2 * 0.30 + 3 * 1.20) / 1_000_000)
    assert house.calls == []


@pytest.mark.parametrize(("stored", "thinking"), [
    ("deepseek-chat", "disabled"),
    ("deepseek-reasoner", "enabled"),
    ("deepseek-v4-flash", "enabled"),
])
def test_persisted_legacy_record_sends_its_mode_on_the_wire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stored: str, thinking: str,
) -> None:
    """End to end from disk: a registry row saved under a retired DeepSeek
    name, reloaded at boot, dispatched through the real registered adapter.
    The request DeepSeek receives names a live model and keeps the old mode."""
    import httpx
    from fastapi.testclient import TestClient

    from interfaces.research.api.settings_budget import register_settings_budget_routes
    from substrate.dispatch.router import get_provider

    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    registry_path = tmp_path / "settings" / "user_models.json"
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(registry_path))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "byok" / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "byok" / "master.key"))

    def _app() -> FastAPI:
        app = FastAPI()

        @app.middleware("http")
        async def _test_identity(request, call_next):
            request.state.user_id = "__operator__"
            request.state.user_email = "operator-under-test@example.com"
            request.state.auth_method = "antiek_session_cookie"
            return await call_next(request)

        register_settings_budget_routes(app)
        return app

    with TestClient(_app()) as first:
        created = first.post("/settings/models/user", json={
            "provider_kind": "openai_compat",
            "provider_catalog_id": "deepseek",
            "model_id": "deepseek-flash",
            "display_name": "Old DeepSeek",
            "api_key": "sk-test-only-legacy-key-abcdefghijklmnopqrstuvwxyz",
        })
        assert created.status_code == 201
    provider_id = created.json()["id"]
    # Rewrite the row as a pre-rename registration would have saved it.
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry[provider_id]["model_id"] = stored
    registry[provider_id]["model_ids"] = [stored]
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    owner = registry[provider_id]["owner_user_id"]

    reset_provider_registry()
    sent: list[httpx.Request] = []

    def deepseek(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, request=request, json={
            "id": "chatcmpl-legacy",
            "object": "chat.completion",
            "model": "deepseek-flash",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "owner answer"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        })

    with TestClient(_app()) as reborn:
        adapter = get_provider(provider_id)
        adapter._client = httpx.Client(transport=httpx.MockTransport(deepseek))  # noqa: SLF001
        adapter._owns_client = True  # noqa: SLF001
        result, _ = dispatch_talk_to_book_byot(
            app=reborn.app,
            request_owner_user_id=owner,
            resource_owner_user_id=owner,
            document_id="doc-a",
            choice=models_admin.UserModelChoice(
                authority="user_model", provider_id=provider_id, model_id=stored,
            ),
            prompt="private book prompt",
            investigation_id="read-doc-a",
            logical_operation_id="turn-wire",
            config=_config(),
            usage_ledger=ByotUsageLedger(tmp_path / "usage.sqlite3"),
        )
    reset_provider_registry()

    assert result.text == "owner answer"
    assert len(sent) == 1
    assert str(sent[0].url) == "https://api.deepseek.com/chat/completions"
    body = json.loads(sent[0].content)
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": thinking}
    assert body["messages"] == [{"role": "user", "content": "private book prompt"}]
    assert result.cost_usd == pytest.approx((2 * 0.30 + 3 * 1.20) / 1_000_000)


@pytest.mark.parametrize("resource_owner", ["owner-b", "__operator__"])
def test_resource_owner_mismatch_refuses_before_provider_io(
    monkeypatch: pytest.MonkeyPatch, resource_owner: str, tmp_path: Path,
) -> None:
    app, record, _, provider, house = _authority_fixture(monkeypatch)
    with pytest.raises(OwnerByotDispatchUnavailable) as caught:
        dispatch_talk_to_book_byot(
            app=app,
            request_owner_user_id="owner-a",
            resource_owner_user_id=resource_owner,
            document_id="doc-a",
            choice=models_admin.UserModelChoice(
                authority="user_model", provider_id=record.id, model_id=record.model_id,
            ),
            prompt="secret marker",
            investigation_id="read-doc-a",
            logical_operation_id="turn-1",
            config=_config(),
            usage_ledger=ByotUsageLedger(tmp_path / "usage.sqlite3"),
        )
    assert str(caught.value) == "owner_byot_dispatch_unavailable"
    assert provider.calls == [] and house.calls == []


def test_stale_v3_fingerprint_refuses_value_free_without_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    app, record, metadata, provider, house = _authority_fixture(monkeypatch)
    stale = CredentialMetadata(
        cred_id=metadata.cred_id,
        account_handle=metadata.account_handle,
        pipeline_kind=metadata.pipeline_kind,
        binding_version=3,
        artifact_fingerprint="b" * 64,
        owner_user_id=metadata.owner_user_id,
    )
    monkeypatch.setattr(models_admin, "_credential_metadata", lambda: {stale.cred_id: stale})
    with pytest.raises(OwnerByotDispatchUnavailable) as caught:
        dispatch_talk_to_book_byot(
            app=app,
            request_owner_user_id="owner-a",
            resource_owner_user_id="owner-a",
            document_id="doc-a",
            choice=models_admin.UserModelChoice(
                authority="user_model", provider_id=record.id, model_id=record.model_id,
            ),
            prompt="secret marker",
            investigation_id="read-doc-a",
            logical_operation_id="turn-1",
            config=_config(),
            usage_ledger=ByotUsageLedger(tmp_path / "usage.sqlite3"),
        )
    assert str(caught.value) == "owner_byot_dispatch_unavailable"
    assert "secret marker" not in str(caught.value)
    assert provider.calls == [] and house.calls == []


@pytest.mark.parametrize("mutation", ["model", "endpoint", "fingerprint"])
def test_call_time_route_mutation_refuses_before_provider_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str,
) -> None:
    app, record, _, provider, house = _authority_fixture(monkeypatch)
    original_load = models_admin._load_registry
    calls = 0

    def changing_registry():
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_load()
        changes = {
            "model": {"model_id": "deepseek-v4-pro"},
            "endpoint": {"base_url": "https://example.invalid/v1"},
            "fingerprint": {"cred_fingerprint": "b" * 64},
        }[mutation]
        return {record.id: record.model_copy(update=changes)}

    monkeypatch.setattr(models_admin, "_load_registry", changing_registry)
    with pytest.raises(OwnerByotDispatchUnavailable):
        dispatch_talk_to_book_byot(
            app=app, request_owner_user_id="owner-a", resource_owner_user_id="owner-a",
            document_id="doc-a", choice=models_admin.UserModelChoice(
                authority="user_model", provider_id=record.id, model_id=record.model_id,
            ), prompt="private", investigation_id="read-doc-a",
            logical_operation_id=f"mutation-{mutation}", config=_config(),
            usage_ledger=ByotUsageLedger(tmp_path / "usage.sqlite3"),
        )
    assert provider.calls == [] and house.calls == []


def test_exhausted_owner_limit_refuses_without_io_or_settlement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    app, record, _, provider, house = _authority_fixture(monkeypatch)
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_limit(record.id, "owner-a", 0)
    with pytest.raises(OwnerByotDispatchUnavailable):
        dispatch_talk_to_book_byot(
            app=app,
            request_owner_user_id="owner-a",
            resource_owner_user_id="owner-a",
            document_id="doc-a",
            choice=models_admin.UserModelChoice(
                authority="user_model", provider_id=record.id, model_id=record.model_id,
            ),
            prompt="private book prompt",
            investigation_id="read-doc-a",
            logical_operation_id="turn-limit",
            config=_config(),
            usage_ledger=ledger,
        )
    assert provider.calls == [] and house.calls == []
    assert ledger.key_usage(record.id, "owner-a").used_cents == 0


def test_provider_failure_is_unknown_and_operation_cannot_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    app, record, _, provider, _ = _authority_fixture(monkeypatch)
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    monkeypatch.setattr(
        "interfaces.research.api.owner_byot_dispatch.dispatch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("secret provider failure")),
    )
    kwargs = dict(
        app=app, request_owner_user_id="owner-a", resource_owner_user_id="owner-a",
        document_id="doc-a", choice=models_admin.UserModelChoice(
            authority="user_model", provider_id=record.id, model_id=record.model_id,
        ), prompt="private prompt", investigation_id="read-doc-a",
        logical_operation_id="op-unknown", config=_config(), usage_ledger=ledger,
    )
    with pytest.raises(OwnerByotOutcomeUnknown, match="^owner_byot_outcome_unknown$"):
        dispatch_talk_to_book_byot(**kwargs)
    assert ledger.operation("owner-a", "op-unknown").state == "unknown"  # type: ignore[union-attr]
    with pytest.raises(OwnerByotDispatchUnavailable):
        dispatch_talk_to_book_byot(**kwargs)
    assert provider.calls == []


def test_settlement_fault_leaves_sent_reservation_and_refuses_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    app, record, _, provider, _ = _authority_fixture(monkeypatch)
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    original = ledger.settle_operation
    monkeypatch.setattr(ledger, "settle_operation", lambda *args: (_ for _ in ()).throw(OSError()))
    kwargs = dict(
        app=app, request_owner_user_id="owner-a", resource_owner_user_id="owner-a",
        document_id="doc-a", choice=models_admin.UserModelChoice(
            authority="user_model", provider_id=record.id, model_id=record.model_id,
        ), prompt="private prompt", investigation_id="read-doc-a",
        logical_operation_id="op-settle-fault", config=_config(), usage_ledger=ledger,
    )
    with pytest.raises(OwnerByotOutcomeUnknown):
        dispatch_talk_to_book_byot(**kwargs)
    pending = ledger.operation("owner-a", "op-settle-fault")
    assert pending is not None and pending.state == "settlement_pending"
    assert (pending.provider_id, pending.model_id) == (record.id, record.model_id)
    assert pending.dispatch_event_id is not None and pending.dispatch_event_id.startswith("evt-")
    monkeypatch.setattr(ledger, "settle_operation", original)
    reconciled = ledger.reconcile_operation("owner-a", "op-settle-fault")
    assert reconciled.state == "settled"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("boundary", ["resource_changed", "mark_sent_failed"])
def test_provably_unsent_boundary_releases_prepared_reservation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, boundary: str,
) -> None:
    app, record, _, provider, _ = _authority_fixture(monkeypatch)
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_limit(record.id, "owner-a", 100)
    if boundary == "mark_sent_failed":
        monkeypatch.setattr(
            ledger, "mark_operation_sent",
            lambda *args: (_ for _ in ()).throw(OSError("unsent")),
        )
    with pytest.raises(OwnerByotDispatchUnavailable):
        dispatch_talk_to_book_byot(
            app=app, request_owner_user_id="owner-a", resource_owner_user_id="owner-a",
            document_id="doc-a", choice=models_admin.UserModelChoice(
                authority="user_model", provider_id=record.id, model_id=record.model_id,
            ), prompt="private", investigation_id="read-doc-a",
            logical_operation_id=f"boundary-{boundary}", resource_authority_digest="a" * 64,
            resource_authority_revalidator=(
                (lambda: "b" * 64) if boundary == "resource_changed" else (lambda: "a" * 64)
            ), config=_config(), usage_ledger=ledger,
        )
    operation = ledger.operation("owner-a", f"boundary-{boundary}")
    assert operation is not None and operation.state == "cancelled"
    assert ledger.key_usage(record.id, "owner-a").held_cents == 0  # type: ignore[union-attr]
    assert provider.calls == []


def test_operator_lineup_never_reroutes_an_owner_paid_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Audit wave 4, finding 1 (#3400).

    The operator's AI Role Lineup assigns the ``thought_partner`` action to the
    house provider. An owner-paid rung must still execute on the owner's key:
    the payer decides the provider. Before the fix the seam called ``dispatch``
    with no override, the router consulted the lineup (precedence 2), swapped
    the exact tier's primary for ``house``, the house adapter answered and was
    paid, and the post-call identity guard turned the owner's reservation into
    ``unknown`` for a call that never touched the owner's key.
    """
    from substrate.dispatch import lineup_override

    app, record, _, provider, house = _authority_fixture(monkeypatch)
    lineup = tmp_path / "lineup.json"
    lineup.write_text(json.dumps({
        "owners": {"__operator__": {
            "general": {},
            "advanced": {"thought_partner": {"provider_id": "house", "model_id": "house-model"}},
        }},
    }), encoding="utf-8")
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(lineup))
    lineup_override._registry_cache.clear()
    # Control: the registry really resolves this role to the house provider, so a
    # pass below is the seam declining the lineup, not the lineup being absent.
    resolved = lineup_override.effective_override_for_dispatch_role("thought_partner")
    assert resolved is not None and resolved.provider_id == "house"

    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    result, authority = dispatch_talk_to_book_byot(
        app=app,
        request_owner_user_id="owner-a",
        resource_owner_user_id="owner-a",
        document_id="doc-a",
        choice=models_admin.UserModelChoice(
            authority="user_model", provider_id=record.id, model_id=record.model_id,
        ),
        prompt="private book prompt",
        investigation_id="read-doc-a",
        logical_operation_id="turn-lineup",
        config=_config(),
        usage_ledger=ledger,
    )

    assert house.calls == [], "the house provider was called and paid on an owner-paid dispatch"
    assert len(provider.calls) == 1
    assert (result.provider, result.model) == (record.id, record.model_id)
    assert authority.payer_policy.value == "byot_only"
    operation = ledger.operation("owner-a", "turn-lineup")
    assert operation is not None and operation.state == "settled"
    assert operation.provider_id == record.id

