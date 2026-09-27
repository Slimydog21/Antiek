"""Quick Ask spends at most one owner-selected rung for one operation."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import owner_byot_dispatch, quick_ask
from interfaces.research.api import settings_models_admin as models_admin
from runtime.byok.store import CredentialMetadata
from runtime.research_runner.byot_provider_catalog import (
    ByotModelVariant,
    ByotProviderPreset,
)
from runtime.research_runner.cost_projection import UnitRate
from runtime.research_runner.protocol import BillingUnit
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    register_provider,
    reset_provider_registry,
)

_MODEL = "deepseek-v4-pro"
_OWNER = "owner-a"


class RecordingProvider:
    def __init__(self, fingerprint: str) -> None:
        self.name = "user-owner-model"
        self._user_model_authority_fingerprint = fingerprint
        self.calls: list[dict[str, Any]] = []
        self.raw_usage: dict[str, int] = {"input_tokens": 7, "output_tokens": 11}
        self.fail = False
        self.finish_reason = "stop"

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model, "prompt": prompt, "max_tokens": max_tokens})
        if self.fail:
            raise RuntimeError("private provider error")
        return RawProviderResponse(
            text="one answer", raw_usage=self.raw_usage,
            finish_reason=self.finish_reason, latency_ms=1, request_id="fake-one",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=raw_usage.get("input_tokens", 0),
            output_tokens=raw_usage.get("output_tokens", 0),
            reported=bool(raw_usage),
        )


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def route(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    snapshot = datetime.now(UTC).date().isoformat()
    variant = ByotModelVariant(
        _MODEL, "DeepSeek V4 Pro",
        (
            UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0.00000055")),
            UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal("0.00000219")),
        ),
        f"deepseek-v4-pro-{snapshot}",
    )
    preset = ByotProviderPreset(
        "deepseek", "DeepSeek", "openai_compat", "https://api.deepseek.com",
        "/chat/completions", (variant,), "https://api-docs.deepseek.com/pricing",
    )
    preset_box = [preset]
    monkeypatch.setattr(quick_ask, "get_provider_preset", lambda _: preset_box[0])
    monkeypatch.setattr(owner_byot_dispatch, "get_provider_preset", lambda _: preset_box[0])

    record_box = [models_admin.UserModelRecord(
        id="user-owner-model", owner_user_id=_OWNER,
        provider_kind="openai_compat", provider_catalog_id="deepseek",
        model_id=_MODEL, display_name="Owner V4 Pro",
        base_url="https://api.deepseek.com", cred_ref="cred-owner",
        cred_fingerprint="a" * 64,
    )]
    metadata = CredentialMetadata(
        cred_id="cred-owner", account_handle=record_box[0].id,
        pipeline_kind="model_provider", binding_version=3,
        artifact_fingerprint="a" * 64, owner_user_id=_OWNER,
    )
    monkeypatch.setattr(models_admin, "_load_registry", lambda: {record_box[0].id: record_box[0]})
    monkeypatch.setattr(models_admin, "_credential_metadata", lambda: {metadata.cred_id: metadata})

    identity = {"owner": _OWNER, "method": "antiek_session_cookie"}
    app = FastAPI()

    @app.middleware("http")
    async def _identity(request: Request, call_next):
        request.state.user_id = identity["owner"]
        request.state.auth_method = identity["method"]
        request.state.user_email = "owner@example.test"
        return await call_next(request)

    fingerprint = models_admin._record_fingerprint(record_box[0])
    app.state.user_model_registration_fingerprints = {record_box[0].id: fingerprint}
    provider = RecordingProvider(fingerprint)
    register_provider(provider)
    ledger = ByotUsageLedger(tmp_path / "quick-ask.sqlite3")
    ledger.set_limit(record_box[0].id, _OWNER, 100)
    app.state.quick_ask_usage_ledger = ledger
    app.include_router(quick_ask.quick_ask_router)
    with TestClient(app) as client:
        yield client, provider, ledger, preset_box, record_box, identity, app


def _body(operation_id: str | None = None, question: str = "What changed?") -> dict[str, Any]:
    return {
        "operation_id": operation_id or str(uuid4()),
        "question": question,
        "model_choice": {
            "authority": "user_model", "provider_id": "user-owner-model", "model_id": _MODEL,
        },
    }


def _quote(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/research/quick-ask/quote", json=body)
    assert response.status_code == 200, response.json()
    return response.json()


def test_model_inventory_uses_same_owner_and_current_price_predicate(route) -> None:
    client, provider, _, preset_box, record_box, identity, app = route
    listed = client.get("/research/quick-ask/models")
    assert listed.status_code == 200
    assert [(row["provider_id"], row["model_id"]) for row in listed.json()["models"]] == [
        ("user-owner-model", _MODEL),
    ]
    assert provider.calls == []
    flash = ByotModelVariant(
        "deepseek-flash", "DeepSeek V4.1 Flash",
        preset_box[0].models[0].rates,
        preset_box[0].models[0].snapshot.replace("v4-pro", "v4-flash"),
    )
    preset_box[0] = replace(preset_box[0], models=(*preset_box[0].models, flash))
    record_box[0] = record_box[0].model_copy(update={
        "model_ids": [_MODEL, "deepseek-flash"],
    })
    fingerprint = models_admin._record_fingerprint(record_box[0])
    app.state.user_model_registration_fingerprints = {record_box[0].id: fingerprint}
    provider._user_model_authority_fingerprint = fingerprint
    listed = client.get("/research/quick-ask/models")
    assert [row["model_id"] for row in listed.json()["models"]] == [
        _MODEL, "deepseek-flash",
    ]

    stale_flash = replace(flash, snapshot="deepseek-flash-2026-08-12")
    preset_box[0] = replace(preset_box[0], models=(preset_box[0].models[0], stale_flash))
    assert [row["model_id"] for row in client.get(
        "/research/quick-ask/models"
    ).json()["models"]] == [_MODEL]
    identity["owner"] = "owner-b"
    assert client.get("/research/quick-ask/models").json() == {"models": [], "count": 0}
    assert provider.calls == []


def test_equal_operation_ids_have_distinct_owner_event_scopes() -> None:
    operation = uuid4()
    assert quick_ask._event_scope("owner-a", operation) != quick_ask._event_scope(
        "owner-b", operation,
    )


def test_quote_is_free_and_confirmed_send_is_one_exact_request(route) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body(question="A full private question ☂")
    quote = _quote(client, body)
    assert provider.calls == []
    assert quote["max_output_tokens"] == 1024
    assert quote["estimate_usd"] != "0"
    assert "not a provider cap" in quote["warning"]
    response = client.post("/research/quick-ask", json={**body, "quote_digest": quote["quote_digest"]})
    assert response.status_code == 200, response.json()
    assert response.json()["usage_basis"] == "provider_reported_tokens_priced_locally"
    assert response.json()["answer"] == "one answer"
    assert provider.calls == [{
        "model": _MODEL, "prompt": body["question"], "max_tokens": 1024,
    }]
    assert ledger.operation(_OWNER, f"quick-ask:{body['operation_id']}").state == "settled"


def test_one_request_excludes_shadow_selector_even_when_enabled(
    route, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from substrate.dispatch import notdiamond_shadow

    client, provider, _, _, _, _, _ = route
    monkeypatch.setenv("ANTIEK_NOTDIAMOND_MODE", "shadow")
    monkeypatch.setenv("ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE", "true")
    selector_calls: list[object] = []

    def unexpected_selector(**kwargs: object) -> None:
        selector_calls.append(kwargs)
        raise AssertionError("Quick Ask must not call the shadow model selector")

    monkeypatch.setattr(notdiamond_shadow, "_select_with_deadline", unexpected_selector)
    body = _body()
    quote = _quote(client, body)
    assert selector_calls == []
    response = client.post(
        "/research/quick-ask", json={**body, "quote_digest": quote["quote_digest"]},
    )
    assert response.status_code == 200, response.json()
    assert len(provider.calls) == 1
    assert selector_calls == []


def test_quote_qualifies_the_resolved_variant_for_a_legacy_choice(
    route, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider, _, _, _, _, _ = route
    freeze = quick_ask._freeze_current_authority

    def canonicalizing_freeze(**kwargs: Any):
        choice = kwargs["choice"]
        if choice.model_id == "deepseek-reasoner":
            kwargs["choice"] = choice.model_copy(update={"model_id": _MODEL})
        return freeze(**kwargs)

    monkeypatch.setattr(quick_ask, "_freeze_current_authority", canonicalizing_freeze)
    body = _body()
    body["model_choice"]["model_id"] = "deepseek-reasoner"
    response = client.post("/research/quick-ask/quote", json=body)
    assert response.status_code == 200, response.json()
    assert response.json()["model_id"] == _MODEL
    assert provider.calls == []


def test_legacy_choice_replays_its_canonical_stored_answer_without_resending(route) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    body["model_choice"]["model_id"] = "deepseek-reasoner"
    payload = {**body, "quote_digest": "b" * 64}
    operation = f"quick-ask:{body['operation_id']}"
    request_digest = quick_ask._request_digest(
        _OWNER, operation, quick_ask.QuickAskExecute.model_validate(payload),
    )
    ledger.prepare_operation(
        "user-owner-model", _OWNER, operation, 1, "a" * 64,
        request_digest=request_digest, quote_estimate_usd="0.004",
    )
    ledger.mark_operation_sent(_OWNER, operation)
    ledger.record_operation_result(
        _OWNER, operation, actual_cents=1, evidence_sha256="e" * 64,
        dispatch_event_id="canonical-send", provider_id="user-owner-model",
        model_id=_MODEL, result_text="canonical stored answer",
        cost_usd_estimate="0.003",
    )
    ledger.settle_operation(_OWNER, operation, 1, "e" * 64)

    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 200, replay.json()
    assert replay.json()["answer"] == "canonical stored answer"
    assert replay.json()["model_id"] == _MODEL
    assert replay.json()["replayed"] is True
    changed = {**payload, "model_choice": {**payload["model_choice"], "model_id": "deepseek-chat"}}
    assert client.post("/research/quick-ask", json=changed).status_code == 409
    assert provider.calls == []


def test_settled_replay_returns_prior_receipt_without_new_send_or_false_zero_usage(route) -> None:
    client, provider, _, _, _, identity, _ = route
    body = _body()
    quoted = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    first = client.post("/research/quick-ask", json=quoted)
    replay = client.post("/research/quick-ask", json=quoted)
    assert first.status_code == replay.status_code == 200
    assert replay.json()["answer"] == first.json()["answer"]
    assert replay.json()["usage_basis"] == "prior_receipt"
    assert first.json()["estimated_cost_usd"] == replay.json()["estimated_cost_usd"]
    assert 0 < replay.json()["estimated_cost_usd"] < 0.01
    assert replay.json()["input_tokens"] is None
    assert replay.json()["output_tokens"] is None
    assert len(provider.calls) == 1
    identity["owner"] = "owner-b"
    foreign = client.post("/research/quick-ask", json=quoted)
    assert foreign.status_code == 409
    assert "one answer" not in foreign.text
    assert len(provider.calls) == 1


def test_settled_replay_survives_revoked_key_and_stale_price_without_io(
    route, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider, ledger, preset_box, _, _, _ = route
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    assert client.post("/research/quick-ask", json=payload).status_code == 200
    row = ledger.operation(_OWNER, f"quick-ask:{body['operation_id']}")
    assert row is not None and row.request_digest is not None
    old = preset_box[0]
    preset_box[0] = replace(old, models=(
        replace(old.models[0], snapshot="deepseek-v4-pro-2026-08-12"),
    ))
    monkeypatch.setattr(models_admin, "_credential_metadata", lambda: {})
    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 200
    assert replay.json()["answer"] == "one answer"
    assert replay.json()["replayed"] is True
    assert replay.json()["usage_basis"] == "prior_receipt"
    assert replay.json()["input_tokens"] is None
    assert len(provider.calls) == 1
    preset_box[0] = replace(old, models=())
    retired_replay = client.post("/research/quick-ask", json=payload)
    assert retired_replay.status_code == 200
    assert retired_replay.json()["answer"] == "one answer"
    changed = {**payload, "question": "Different bytes"}
    conflict = client.post("/research/quick-ask", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "quick_ask_operation_conflict"
    assert "one answer" not in conflict.text
    altered_quote = {**payload, "quote_digest": "0" * 64}
    assert client.post("/research/quick-ask", json=altered_quote).json()["detail"] == (
        "quick_ask_operation_conflict"
    )
    assert len(provider.calls) == 1


def test_length_finish_is_incomplete_on_first_answer_and_replay(route, monkeypatch) -> None:
    client, provider, _, _, _, _, _ = route
    provider.finish_reason = "length"
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    first = client.post("/research/quick-ask", json=payload)
    assert first.status_code == 200
    assert first.json()["incomplete"] is True
    monkeypatch.setattr(models_admin, "_credential_metadata", lambda: {})
    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 200
    assert replay.json()["incomplete"] is True
    assert len(provider.calls) == 1


def test_racing_helper_replay_uses_stored_finish_reason(route, monkeypatch) -> None:
    client, provider, ledger, _, _, _, _ = route
    provider.finish_reason = "length"
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    assert client.post("/research/quick-ask", json=payload).status_code == 200
    original_operation = ledger.operation
    reads = 0

    def hide_first_read(owner: str, operation_id: str):
        nonlocal reads
        reads += 1
        return None if reads == 1 else original_operation(owner, operation_id)

    monkeypatch.setattr(ledger, "operation", hide_first_read)
    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 200
    assert replay.json()["incomplete"] is True
    assert replay.json()["usage_basis"] == "prior_receipt"
    assert len(provider.calls) == 1


def test_legacy_operation_without_request_digest_refuses_terminal_replay(route) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    quote = _quote(client, body)
    op = f"quick-ask:{body['operation_id']}"
    ledger.prepare_operation("user-owner-model", _OWNER, op, 1, quote["quote_digest"])
    response = client.post(
        "/research/quick-ask", json={**body, "quote_digest": quote["quote_digest"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "quick_ask_operation_conflict"
    assert provider.calls == []


def test_old_settled_row_without_precise_receipt_fails_closed(route) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    first = client.post("/research/quick-ask", json=payload)
    assert first.status_code == 200
    with sqlite3.connect(ledger._db_path) as con:
        con.execute(
            "UPDATE byot_operation_journal SET quote_estimate_usd = NULL,"
            " cost_usd_estimate = NULL WHERE owner_user_id = ? AND operation_id = ?",
            (_OWNER, f"quick-ask:{body['operation_id']}"),
        )
    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 409
    assert replay.json()["detail"] == "charge_unknown"
    assert "one answer" not in replay.text
    assert len(provider.calls) == 1


def test_incomplete_helper_receipt_configuration_refuses_before_io(route) -> None:
    _, provider, ledger, _, record_box, _, app = route
    with pytest.raises(owner_byot_dispatch.OwnerByotDispatchUnavailable):
        owner_byot_dispatch.dispatch_talk_to_book_byot(
            app=app, request_owner_user_id=_OWNER, resource_owner_user_id=_OWNER,
            document_id="quick-ask:test", choice=models_admin.UserModelChoice(
                authority="user_model", provider_id=record_box[0].id,
                model_id=record_box[0].model_id,
            ),
            prompt="question", investigation_id="quick-ask-test",
            logical_operation_id="quick-ask:test", usage_ledger=ledger,
            require_reported_usage=True,
        )
    assert provider.calls == []


def test_terminal_recheck_recovers_a_result_written_during_quote_failure(
    route, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    quote = _quote(client, body)
    payload = {**body, "quote_digest": quote["quote_digest"]}
    parsed = quick_ask.QuickAskExecute.model_validate(payload)
    operation_id = f"quick-ask:{body['operation_id']}"
    request_digest = quick_ask._request_digest(_OWNER, operation_id, parsed)

    def complete_then_fail_quote(*_args, **_kwargs):
        ledger.prepare_operation(
            "user-owner-model", _OWNER, operation_id, 1, quote["quote_digest"],
            request_digest=request_digest,
            quote_estimate_usd=quote["estimate_usd"],
        )
        ledger.mark_operation_sent(_OWNER, operation_id)
        ledger.record_unknown_result(
            _OWNER, operation_id, result_text="answer from first request",
            dispatch_event_id=None, provider_id="user-owner-model", model_id=_MODEL,
        )
        raise RuntimeError("catalog changed while sibling completed")

    monkeypatch.setattr(quick_ask, "_quote", complete_then_fail_quote)
    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 200
    assert replay.json()["answer"] == "answer from first request"
    assert replay.json()["usage_basis"] == "charge_unknown"
    assert len(provider.calls) == 0


def test_concurrent_twins_cannot_send_twice(route) -> None:
    client, provider, _, _, _, _, _ = route
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(
            lambda _: client.post("/research/quick-ask", json=payload), range(4),
        ))
    assert all(response.status_code in {200, 409} for response in responses)
    assert any(response.status_code == 200 for response in responses)
    assert len(provider.calls) == 1


def test_changed_question_model_and_quote_are_refused_before_io(route) -> None:
    client, provider, _, _, _, _, _ = route
    body = _body()
    quote = _quote(client, body)
    changes = (
        {**body, "question": "A different question", "quote_digest": quote["quote_digest"]},
        {**body, "model_choice": {**body["model_choice"], "model_id": "mimo-v2.5-pro"},
         "quote_digest": quote["quote_digest"]},
        {**body, "quote_digest": "0" * 64},
    )
    for changed in changes:
        response = client.post("/research/quick-ask", json=changed)
        assert response.status_code == 409
    missing = client.post("/research/quick-ask", json=body)
    assert missing.status_code == 422
    assert provider.calls == []


def test_price_drift_within_same_rounded_cent_invalidates_quote(route) -> None:
    client, provider, _, preset_box, _, _, _ = route
    body = _body()
    quote = _quote(client, body)
    old = preset_box[0]
    old_variant = old.models[0]
    new_variant = replace(old_variant, rates=(
        UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0.00000056")),
        old_variant.rates[1],
    ))
    preset_box[0] = replace(old, models=(new_variant,))
    new_quote = _quote(client, body)
    assert new_quote["reserved_cents"] == quote["reserved_cents"]
    assert new_quote["quote_digest"] != quote["quote_digest"]
    response = client.post("/research/quick-ask", json={**body, "quote_digest": quote["quote_digest"]})
    assert response.status_code == 409
    assert response.json()["detail"] == "quick_ask_quote_changed"
    assert provider.calls == []


def test_reported_usage_above_quote_is_disclosed_without_claiming_hard_cap(route) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    quote = _quote(client, body)
    provider.raw_usage = {"input_tokens": 100_000, "output_tokens": 10}
    response = client.post(
        "/research/quick-ask", json={**body, "quote_digest": quote["quote_digest"]},
    )
    assert response.status_code == 200
    assert response.json()["reported_usage_estimate_exceeds_quote"] is True
    assert response.json()["estimated_cost_usd"] > float(quote["estimate_usd"])
    row = ledger.operation(_OWNER, f"quick-ask:{body['operation_id']}")
    assert row is not None and row.state == "settled"
    assert row.actual_cents is not None and row.actual_cents > quote["reserved_cents"]
    assert row.cost_usd_estimate == str(response.json()["estimated_cost_usd"])
    assert row.quote_estimate_usd == quote["estimate_usd"]
    replay = client.post(
        "/research/quick-ask", json={**body, "quote_digest": quote["quote_digest"]},
    )
    assert replay.status_code == 200
    assert replay.json()["reported_usage_estimate_exceeds_quote"] is True
    assert replay.json()["estimated_cost_usd"] == response.json()["estimated_cost_usd"]
    assert len(provider.calls) == 1


def test_unreported_usage_and_transport_failure_keep_unknown_hold(route) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    provider.raw_usage = {}
    response = client.post("/research/quick-ask", json=payload)
    assert response.status_code == 200
    assert response.json()["answer"] == "one answer"
    assert response.json()["usage_basis"] == "charge_unknown"
    assert response.json()["estimated_cost_usd"] is None
    assert response.json()["input_tokens"] is None
    row = ledger.operation(_OWNER, f"quick-ask:{body['operation_id']}")
    assert row is not None and row.state == "unknown" and row.actual_cents is None
    assert ledger.key_usage("user-owner-model", _OWNER).held_cents > 0
    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 200
    assert replay.json()["answer"] == "one answer"
    assert replay.json()["usage_basis"] == "charge_unknown"
    assert replay.json()["replayed"] is True
    assert len(provider.calls) == 1

    second = _body()
    second_payload = {**second, "quote_digest": _quote(client, second)["quote_digest"]}
    provider.fail = True
    response = client.post("/research/quick-ask", json=second_payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "charge_unknown"
    assert len(provider.calls) == 2


def test_unknown_answer_replay_survives_revocation_but_no_answer_stays_unknown(
    route, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    provider.raw_usage = {}
    assert client.post("/research/quick-ask", json=payload).json()["answer"] == "one answer"
    no_answer = _body()
    failed_payload = {
        **no_answer, "quote_digest": _quote(client, no_answer)["quote_digest"],
    }
    provider.fail = True
    failure = client.post("/research/quick-ask", json=failed_payload)
    assert failure.status_code == 409 and failure.json()["detail"] == "charge_unknown"
    row = ledger.operation(_OWNER, f"quick-ask:{no_answer['operation_id']}")
    assert row is not None and row.state == "unknown" and row.result_text is None
    monkeypatch.setattr(models_admin, "_credential_metadata", lambda: {})
    replay = client.post("/research/quick-ask", json=payload)
    assert replay.status_code == 200
    assert replay.json()["usage_basis"] == "charge_unknown"
    assert replay.json()["answer"] == "one answer"
    refused = client.post("/research/quick-ask", json=failed_payload)
    assert refused.status_code == 409 and refused.json()["detail"] == "charge_unknown"
    assert len(provider.calls) == 2


def test_unknown_length_answer_stays_incomplete_on_replay(route) -> None:
    client, provider, _, _, _, _, _ = route
    provider.raw_usage = {}
    provider.finish_reason = "length"
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    first = client.post("/research/quick-ask", json=payload)
    replay = client.post("/research/quick-ask", json=payload)
    assert first.status_code == replay.status_code == 200
    assert first.json()["incomplete"] is True
    assert replay.json()["incomplete"] is True
    assert replay.json()["usage_basis"] == "charge_unknown"
    assert len(provider.calls) == 1


def test_content_filter_answer_stays_incomplete_on_replay(route) -> None:
    client, provider, _, _, _, _, _ = route
    provider.finish_reason = "content_filter"
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    first = client.post("/research/quick-ask", json=payload)
    replay = client.post("/research/quick-ask", json=payload)
    assert first.status_code == replay.status_code == 200
    assert first.json()["answer"] == "one answer"
    assert first.json()["incomplete"] is True
    assert replay.json()["incomplete"] is True
    assert len(provider.calls) == 1


def test_answer_survives_nonfatal_local_event_failure(
    route, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider, ledger, _, _, _, _ = route
    monkeypatch.setattr("substrate.dispatch.router._emit_dispatch_call", lambda **_: None)
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    response = client.post("/research/quick-ask", json=payload)
    assert response.status_code == 200
    assert response.json()["answer"] == "one answer"
    assert response.json()["usage_basis"] == "charge_unknown"
    assert response.json()["estimated_cost_usd"] is None
    row = ledger.operation(_OWNER, f"quick-ask:{body['operation_id']}")
    assert row is not None and row.state == "unknown" and row.dispatch_event_id is None
    assert len(provider.calls) == 1


def test_owner_key_endpoint_and_retired_model_gates(route) -> None:
    client, provider, _, _, record_box, identity, app = route
    body = _body()
    identity["owner"] = "owner-b"
    assert client.post("/research/quick-ask/quote", json=body).status_code == 409
    identity["owner"] = _OWNER
    identity["method"] = "unauthenticated_local"
    assert client.post("/research/quick-ask/quote", json=body).status_code == 401
    identity["method"] = "antiek_session_cookie"
    record_box[0] = record_box[0].model_copy(update={"base_url": "https://custom.example"})
    app.state.user_model_registration_fingerprints = {
        record_box[0].id: models_admin._record_fingerprint(record_box[0]),
    }
    provider._user_model_authority_fingerprint = app.state.user_model_registration_fingerprints[
        record_box[0].id
    ]
    assert client.post("/research/quick-ask/quote", json=body).status_code == 409
    retired = _body()
    retired["model_choice"]["model_id"] = "mimo-v2.5-pro"
    assert client.post("/research/quick-ask/quote", json=retired).status_code == 409
    assert provider.calls == []


def test_revoked_key_and_old_price_snapshot_refuse_quote(route, monkeypatch) -> None:
    client, provider, _, preset_box, _, _, _ = route
    body = _body()
    valid_quote = _quote(client, body)
    old = preset_box[0]
    preset_box[0] = replace(old, models=(
        replace(old.models[0], snapshot="deepseek-v4-pro-2026-08-12"),
    ))
    response = client.post("/research/quick-ask/quote", json=body)
    assert response.status_code == 409
    assert response.json()["detail"] == "quick_ask_model_unavailable"
    preset_box[0] = old
    monkeypatch.setattr(models_admin, "_credential_metadata", lambda: {})
    response = client.post("/research/quick-ask/quote", json=body)
    assert response.status_code == 409
    send = client.post(
        "/research/quick-ask", json={**body, "quote_digest": valid_quote["quote_digest"]},
    )
    assert send.status_code == 409
    assert provider.calls == []


def test_paid_endpoint_refuses_simple_form_content_type(route) -> None:
    client, provider, _, _, _, _, _ = route
    response = client.post(
        "/research/quick-ask",
        content='{"question":"spend","operation_id":"00000000-0000-4000-8000-000000000000"}',
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 415
    assert response.json()["detail"] == "quick_ask_json_required"
    assert provider.calls == []


def test_recent_receipts_recover_answers_without_model_or_provider_io(
    route, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider, ledger, _, _, identity, _ = route
    settled = _body(question="private settled question")
    settled_payload = {
        **settled, "quote_digest": _quote(client, settled)["quote_digest"],
    }
    provider.finish_reason = "length"
    provider.raw_usage = {"input_tokens": 100_000, "output_tokens": 10}
    first = client.post("/research/quick-ask", json=settled_payload)
    assert first.status_code == 200 and first.json()[
        "reported_usage_estimate_exceeds_quote"
    ] is True
    unknown = _body(question="private unknown question")
    unknown_payload = {
        **unknown, "quote_digest": _quote(client, unknown)["quote_digest"],
    }
    provider.raw_usage = {}
    second = client.post("/research/quick-ask", json=unknown_payload)
    assert second.status_code == 200 and second.json()["usage_basis"] == "charge_unknown"
    sent_id = str(uuid4())
    pending_id = str(uuid4())
    prepared_id = str(uuid4())
    for operation_id in (sent_id, pending_id, prepared_id):
        ledger.prepare_operation(
            "user-owner-model", _OWNER, f"quick-ask:{operation_id}", 1,
            "a" * 64, request_digest="b" * 64, quote_estimate_usd="0.001",
        )
    ledger.mark_operation_sent(_OWNER, f"quick-ask:{sent_id}")
    ledger.mark_operation_sent(_OWNER, f"quick-ask:{pending_id}")
    ledger.record_operation_result(
        _OWNER, f"quick-ask:{pending_id}", actual_cents=1,
        evidence_sha256="e" * 64, dispatch_event_id="event-pending",
        provider_id="user-owner-model", model_id=_MODEL,
        result_text="pending answer must stay hidden", cost_usd_estimate="0.001",
    )
    # Equal UUIDs in distinct owner partitions must remain distinct.
    ledger.prepare_operation(
        "foreign-key", "owner-b", f"quick-ask:{settled['operation_id']}", 1,
        "c" * 64, request_digest="d" * 64, quote_estimate_usd="0.001",
    )
    ledger.mark_operation_sent("owner-b", f"quick-ask:{settled['operation_id']}")
    before = {
        operation_id: ledger.operation(_OWNER, f"quick-ask:{operation_id}")
        for operation_id in (settled["operation_id"], unknown["operation_id"], sent_id,
                             pending_id, prepared_id)
    }
    held_before = ledger.key_usage("user-owner-model", _OWNER)
    assert held_before is not None

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("receipt recovery must not resolve or call a model")

    monkeypatch.setattr(quick_ask, "_quote", unexpected)
    monkeypatch.setattr(quick_ask, "dispatch_talk_to_book_byot", unexpected)
    monkeypatch.setattr(models_admin, "_load_registry", unexpected)
    monkeypatch.setattr(models_admin, "_credential_metadata", unexpected)
    response = client.get("/research/quick-ask/recent")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    operations = response.json()["operations"]
    by_id = {item["operation_id"]: item for item in operations}
    assert set(by_id) == {settled["operation_id"], unknown["operation_id"],
                          sent_id, pending_id}
    assert [item["created_at"] for item in operations] == sorted(
        (item["created_at"] for item in operations), reverse=True,
    )
    recovered = by_id[settled["operation_id"]]
    assert recovered["status"] == "answered"
    assert recovered["result"] == {
        **first.json(), "usage_basis": "prior_receipt", "input_tokens": None,
        "output_tokens": None, "replayed": True,
    }
    assert by_id[unknown["operation_id"]]["status"] == "answered"
    assert by_id[unknown["operation_id"]]["result"]["usage_basis"] == "charge_unknown"
    assert by_id[unknown["operation_id"]]["result"]["estimated_cost_usd"] is None
    for operation_id in (sent_id, pending_id):
        assert by_id[operation_id]["status"] == "charge_unknown"
        assert by_id[operation_id]["result"] is None
    assert "private settled question" not in response.text
    assert "private unknown question" not in response.text
    assert "pending answer must stay hidden" not in response.text
    assert "event-pending" not in response.text
    for row in before.values():
        assert row is not None
        assert row.authority_digest not in response.text
        assert row.request_digest not in response.text
    assert "foreign-key" not in response.text
    assert len(provider.calls) == 2
    assert before == {
        operation_id: ledger.operation(_OWNER, f"quick-ask:{operation_id}")
        for operation_id in before
    }
    assert ledger.key_usage("user-owner-model", _OWNER) == held_before

    identity["owner"] = "owner-b"
    other = client.get("/research/quick-ask/recent")
    assert other.status_code == 200
    assert other.json()["operations"] == [{
        "operation_id": settled["operation_id"],
        "created_at": ledger.operation(
            "owner-b", f"quick-ask:{settled['operation_id']}"
        ).created_at,
        "status": "charge_unknown",
        "result": None,
    }]
    assert "one answer" not in other.text
    identity["method"] = "unauthenticated_local"
    assert client.get("/research/quick-ask/recent").status_code == 401


def test_recent_receipts_reject_caller_owner_override(route) -> None:
    client, provider, _, _, _, _, _ = route
    response = client.get("/research/quick-ask/recent?owner_user_id=owner-b")
    assert response.status_code == 400
    assert provider.calls == []


def test_recent_receipts_fail_closed_on_malformed_historical_rows(route) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    assert client.post("/research/quick-ask", json=payload).status_code == 200
    malformed_id = str(uuid4())
    ledger.prepare_operation(
        "user-owner-model", _OWNER, f"quick-ask:{malformed_id}", 1,
        "a" * 64, request_digest="b" * 64, quote_estimate_usd="0.01",
    )
    ledger.mark_operation_sent(_OWNER, f"quick-ask:{malformed_id}")
    ledger.prepare_operation(
        "user-owner-model", _OWNER, "quick-ask:not-a-uuid", 1,
        "a" * 64, request_digest="b" * 64, quote_estimate_usd="0.01",
    )
    ledger.mark_operation_sent(_OWNER, "quick-ask:not-a-uuid")
    with sqlite3.connect(ledger._db_path) as con:
        con.execute(
            "UPDATE byot_operation_journal SET cost_usd_estimate = 'NaN'"
            " WHERE owner_user_id = ? AND operation_id = ?",
            (_OWNER, f"quick-ask:{body['operation_id']}"),
        )
        con.execute(
            "UPDATE byot_operation_journal SET created_at = 'not a date'"
            " WHERE owner_user_id = ? AND operation_id = ?",
            (_OWNER, f"quick-ask:{malformed_id}"),
        )
    response = client.get("/research/quick-ask/recent")
    assert response.status_code == 200, response.text
    assert response.json() == {"operations": [{
        "operation_id": body["operation_id"],
        "created_at": ledger.operation(
            _OWNER, f"quick-ask:{body['operation_id']}"
        ).created_at,
        "status": "charge_unknown",
        "result": None,
    }]}
    assert "one answer" not in response.text
    assert len(provider.calls) == 1


def test_recent_receipts_page_past_newer_malformed_rows(route, monkeypatch) -> None:
    client, provider, ledger, _, _, _, _ = route
    body = _body()
    payload = {**body, "quote_digest": _quote(client, body)["quote_digest"]}
    first = client.post("/research/quick-ask", json=payload)
    assert first.status_code == 200
    with sqlite3.connect(ledger._db_path) as con:
        con.execute(
            "UPDATE byot_operation_journal SET created_at = ?"
            " WHERE owner_user_id = ? AND operation_id = ?",
            ("2026-09-26T00:00:00+00:00", _OWNER,
             f"quick-ask:{body['operation_id']}"),
        )
        for index in range(35):
            con.execute(
                "INSERT INTO byot_operation_journal"
                " (api_key_id, owner_user_id, operation_id, state, reserved_cents,"
                " authority_digest, created_at, updated_at, request_digest,"
                " quote_estimate_usd) VALUES (?, ?, ?, 'sent', 1, ?, ?, ?, ?, ?)",
                ("user-owner-model", _OWNER, f"quick-ask:invalid-{index:02d}",
                 "a" * 64, "2026-09-27T00:00:00+00:00",
                 "2026-09-27T00:00:00+00:00", "b" * 64, "0.01"),
            )

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("receipt recovery must not call the model path")

    monkeypatch.setattr(quick_ask, "_quote", unexpected)
    monkeypatch.setattr(quick_ask, "dispatch_talk_to_book_byot", unexpected)
    response = client.get("/research/quick-ask/recent")
    assert response.status_code == 200, response.text
    assert response.json()["operations"] == [{
        "operation_id": body["operation_id"],
        "created_at": "2026-09-26T00:00:00+00:00",
        "status": "answered",
        "result": {
            **first.json(), "usage_basis": "prior_receipt",
            "input_tokens": None, "output_tokens": None, "replayed": True,
        },
    }]
    assert len(provider.calls) == 1


def test_recent_receipts_do_not_create_missing_ledger(
    route, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    client, provider, _, _, _, _, app = route
    del app.state.quick_ask_usage_ledger
    missing_path = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(missing_path))
    response = client.get("/research/quick-ask/recent")
    assert response.status_code == 503
    assert response.json() == {"detail": "quick_ask_receipts_unavailable"}
    assert response.headers["cache-control"] == "private, no-store"
    assert not missing_path.exists()
    assert provider.calls == []
