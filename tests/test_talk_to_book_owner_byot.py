"""Exact owner-selected BYOT execution for Talk-to-Book."""

from __future__ import annotations

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
        "user_agent__fallback", "house", "house-model", 200, 0.1, 1000, pricing,
    )
    tier = TierConfig(
        "pro", "house", "house-model", 200, 0.1, 1000, pricing, fallback,
    )
    return DispatchConfig({"user_agent": "pro"}, {"pro": tier})


def _authority_fixture(monkeypatch: pytest.MonkeyPatch):
    record = models_admin.UserModelRecord(
        id="user-owner-model",
        owner_user_id="owner-a",
        provider_kind="openai_compat",
        provider_catalog_id="deepseek",
        model_id="deepseek-chat",
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
    assert result.cost_usd == pytest.approx((2 * 0.28 + 3 * 0.42) / 1_000_000)
    assert ledger.key_usage(record.id, "owner-a").used_cents == 1


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
            "model": {"model_id": "deepseek-reasoner"},
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
