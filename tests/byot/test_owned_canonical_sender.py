"""The owned sender uses one real journal attempt and a private mock exchange."""

from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from interfaces.research.api import owner_byot_dispatch as sender
from interfaces.research.api import settings_models_admin as models
from runtime.byok.store import delete_credential, store_credential_with_metadata
from substrate.byot_usage.actions import OwnerActionDecision
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch import canonical_http
from substrate.dispatch.router import (
    DispatchConfig,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory

_SECRET = "sk-fixture-owned-canonical-key-123456789"
_PROMPT = "Read this exact fixture passage and answer privately."
_SOURCE = hashlib.sha256(b"fixture-current-body").hexdigest()
_ROLE = "synthesizer"
_PACK = "pack-fixture-canonical"
_PARENT = "request-fixture-canonical"


class _Case:
    def __init__(self, app, ledger, provider, choice, config, record, responses, source):
        self.app = app
        self.ledger = ledger
        self.provider = provider
        self.choice = choice
        self.config = config
        self.record = record
        self.responses = responses
        self.source = source

    @contextmanager
    def source_guard(self):
        yield self.source[0]

    def call(self, *, owner: str = "owner-a", operation: str = "canonical-one"):
        action = self.ledger.action("owner-a", "action-a")
        assert action is not None
        return sender.dispatch_talk_to_book_byot(
            app=self.app, request_owner_user_id=owner,
            resource_owner_user_id="owner-a", document_id="book-a",
            choice=self.choice, prompt=_PROMPT, investigation_id="inv-canonical-test",
            logical_operation_id=operation, resource_authority_digest=_SOURCE,
            resource_authority_guard=self.source_guard, config=self.config,
            usage_ledger=self.ledger, role=_ROLE, action="wrestling.distillation",
            owner_action=action.ref, context_pack_event_id=_PACK,
            parent_event_id=_PARENT,
        )


@pytest.fixture(autouse=True)
def isolated_registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def make_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def make(protocol: str) -> _Case:
        root = tmp_path / protocol
        root.mkdir()
        monkeypatch.setenv("ANTIEK_HOME", str(root))
        monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(root / "models.json"))
        monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(root / "credentials.enc"))
        monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(root / "master.key"))
        monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(root / "events"))
        if protocol == "deepseek":
            model_id = "deepseek-flash-nothink"
            kind = "openai_compat"
            base_url = "https://api.deepseek.com"
        else:
            model_id = "claude-haiku-4-5-20251001"
            kind = "anthropic"
            base_url = "https://api.anthropic.com"
        record_id = models._owner_id_prefix("owner-a") + protocol
        credential = store_credential_with_metadata(
            record_id, _SECRET, pipeline_kind="model_provider", owner_user_id="owner-a",
        )
        record = models.UserModelRecord(
            id=record_id, owner_user_id="owner-a", provider_kind=kind,
            provider_catalog_id=protocol, model_id=model_id,
            display_name="Fixture owner model", base_url=base_url,
            cred_ref=credential.cred_id,
            cred_fingerprint=credential.artifact_fingerprint,
        )
        with models._registry_guard(exclusive=True):
            models._write_registry_unlocked({record.id: record})
        provider = models._make_provider(record)
        register_provider(provider)
        app = FastAPI()
        app.state.registered_providers = {record.id}
        app.state.user_model_registration_fingerprints = {
            record.id: models._record_fingerprint(record),
        }
        choice = models.UserModelChoice(
            authority="user_model", provider_id=record.id, model_id=model_id,
        )
        ledger = ByotUsageLedger(root / "money.sqlite3")
        route = sender.approved_owner_action_route(app, choice, owner_user_id="owner-a")
        ledger.begin_action(OwnerActionDecision(
            "owner-a", "action-a", "long_document_wrestling", 10_000,
            _SOURCE, hashlib.sha256(b"owner-approved-fixture").hexdigest(), (route,),
        ))
        config = DispatchConfig(
            {_ROLE: "synthesis"},
            {"synthesis": TierConfig(
                "synthesis", None, None, 64, 0.2, 4096, TierPricing(),
            )},
        )
        responses: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            responses.append(request)
            if protocol == "deepseek":
                return httpx.Response(200, json={
                    "id": "upstream-openai-fixture", "object": "chat.completion",
                    "model": "deepseek-flash", "choices": [{
                        "index": 0, "message": {"role": "assistant", "content": "Private answer"},
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 9,
                              "total_tokens": 17},
                })
            return httpx.Response(200, json={
                "id": "upstream-anthropic-fixture", "type": "message",
                "role": "assistant", "model": model_id,
                "content": [{"type": "text", "text": "Private answer"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 8, "output_tokens": 9},
            })

        monkeypatch.setattr(canonical_http, "_new_inner_transport",
                            lambda: httpx.MockTransport(respond))
        return _Case(app, ledger, provider, choice, config, record,
                     responses, [_SOURCE])

    return make


@pytest.mark.parametrize("protocol", ["deepseek", "anthropic"])
def test_two_protocols_claim_one_wire_exchange_and_exact_replay(make_case, protocol):
    case = make_case(protocol)
    result, _ = case.call()
    assert result.text == "Private answer"
    assert result.usage.input_tokens == 8 and result.usage.output_tokens == 9
    assert len(case.responses) == 1
    row = case.ledger.action_attempt("owner-a", "canonical-one")
    assert row is not None and row.operation.state == "settled"
    assert row.request_digest is not None and len(row.request_digest) == 64
    assert row.claim_nonce_digest is not None and len(row.claim_nonce_digest) == 64
    assert case.ledger.canonical_input_binding("owner-a", "canonical-one") is not None
    events = [event for event in trajectory("inv-canonical-test")
              if event["action_type"] == "dispatch.call"]
    assert len(events) == 1
    assert events[0]["event_id"] == result.event_id
    assert events[0]["parent_event_id"] == _PARENT
    assert events[0]["payload"]["context_pack_event_id"] == _PACK
    assert events[0]["payload"]["model"] == case.record.model_id
    assert case.ledger.close_action("owner-a", "action-a", expected_epoch=0).state == "closed"
    replay, _ = case.call()
    assert replay.text == result.text and replay.finish_reason == "replayed"
    assert replay.event_id == result.event_id
    assert len(case.responses) == 1
    assert case.ledger.action_attempt("owner-a", "canonical-one").operation.state == "settled"


def test_foreign_owner_and_unsupported_variant_do_not_send(make_case):
    case = make_case("deepseek")
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        case.call(owner="owner-b")
    assert case.responses == []
    unsupported = models.UserModelChoice(
        authority="user_model", provider_id=case.record.id,
        model_id="deepseek-flash",
    )
    case.choice = unsupported
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        case.call(operation="unsupported")
    assert case.responses == []


@pytest.mark.parametrize("protocol", ["deepseek", "anthropic"])
def test_current_provider_reload_replays_without_rebinding_old_wire(make_case, protocol):
    case = make_case(protocol)
    first, _ = case.call()
    before = case.ledger.action_attempt("owner-a", "canonical-one")
    binding = case.ledger.canonical_input_binding("owner-a", "canonical-one")
    register_provider(models._make_provider(case.record))
    replay, _ = case.call()
    after = case.ledger.action_attempt("owner-a", "canonical-one")
    assert replay.text == first.text and replay.finish_reason == "replayed"
    assert replay.event_id == first.event_id
    assert after == before
    assert case.ledger.canonical_input_binding("owner-a", "canonical-one") == binding
    assert len(case.responses) == 1
    case.source[0] = hashlib.sha256(b"no-longer-the-approved-body").hexdigest()
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        case.call()
    assert len(case.responses) == 1


@pytest.mark.parametrize("changed", ["source", "registry", "credential", "generation"])
def test_current_authority_change_during_builder_refuses_before_claim(
    make_case, monkeypatch, changed,
):
    case = make_case("deepseek")
    builder = case.provider.build_request

    def changed_builder(**kwargs):
        if changed == "source":
            case.source[0] = hashlib.sha256(b"changed-body").hexdigest()
        elif changed == "registry":
            with models._registry_guard(exclusive=True):
                models._write_registry_unlocked({})
        elif changed == "credential":
            assert delete_credential(case.record.cred_ref)
        else:
            reset_provider_registry()
        return builder(**kwargs)

    monkeypatch.setattr(case.provider, "build_request", changed_builder)
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        case.call()
    assert case.responses == []
    attempt = case.ledger.action_attempt("owner-a", "canonical-one")
    assert attempt is not None and attempt.operation.state == "cancelled"


def test_cancel_before_claim_and_possible_send_unknown_never_resend(make_case, monkeypatch):
    case = make_case("deepseek")
    builder = case.provider.build_request

    def cancel_during_build(**kwargs):
        case.ledger.close_action("owner-a", "action-a", expected_epoch=0)
        return builder(**kwargs)

    monkeypatch.setattr(case.provider, "build_request", cancel_during_build)
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        case.call()
    assert case.responses == []
    assert case.ledger.action_attempt("owner-a", "canonical-one").operation.state == "cancelled"

    other = make_case("anthropic")
    def lost_response(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("fixture lost response")

    monkeypatch.setattr(canonical_http, "_new_inner_transport",
                        lambda: httpx.MockTransport(lost_response))
    with pytest.raises(sender.OwnerByotOutcomeUnknown):
        other.call()
    attempt = other.ledger.action_attempt("owner-a", "canonical-one")
    assert attempt is not None and attempt.operation.state == "unknown"
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        other.call()
    assert len(other.responses) == 0


def test_lost_claim_return_recovers_own_nonce_without_second_send(make_case, monkeypatch):
    case = make_case("deepseek")
    claim = case.ledger.claim_action_attempt
    lost = False

    def committed_then_lost(*args, **kwargs):
        nonlocal lost
        result = claim(*args, **kwargs)
        if not lost:
            lost = True
            raise RuntimeError("fixture lost SQLite return")
        return result

    monkeypatch.setattr(case.ledger, "claim_action_attempt", committed_then_lost)
    result, _ = case.call()
    assert lost and result.text == "Private answer"
    assert len(case.responses) == 1
    assert case.ledger.action_attempt("owner-a", "canonical-one").operation.state == "settled"


def test_settlement_pending_recovery_never_resends(make_case, monkeypatch):
    case = make_case("deepseek")
    settle = case.ledger.settle_action_attempt

    def interrupted_settlement(*args, **kwargs):
        raise RuntimeError("fixture interrupted before settlement")

    monkeypatch.setattr(case.ledger, "settle_action_attempt", interrupted_settlement)
    with pytest.raises(sender.OwnerByotOutcomeUnknown):
        case.call()
    attempt = case.ledger.action_attempt("owner-a", "canonical-one")
    assert attempt is not None and attempt.operation.state == "settlement_pending"
    monkeypatch.setattr(case.ledger, "settle_action_attempt", settle)
    replay, _ = case.call()
    assert replay.finish_reason == "replayed"
    assert len(case.responses) == 1
    assert case.ledger.action_attempt("owner-a", "canonical-one").operation.state == "settled"


def test_unobserved_claim_return_retains_sent_without_sending_or_retry(make_case, monkeypatch):
    case = make_case("deepseek")
    claim = case.ledger.claim_action_attempt
    observe = case.ledger.action_attempt
    committed = False

    def lost_claim(*args, **kwargs):
        nonlocal committed
        claim(*args, **kwargs)
        committed = True
        raise RuntimeError("fixture lost committed claim return")

    def unreadable_claim(*args, **kwargs):
        if committed:
            raise RuntimeError("fixture journal temporarily unreadable")
        return observe(*args, **kwargs)

    monkeypatch.setattr(case.ledger, "claim_action_attempt", lost_claim)
    monkeypatch.setattr(case.ledger, "action_attempt", unreadable_claim)
    with pytest.raises(sender.OwnerByotOutcomeUnknown):
        case.call()
    monkeypatch.setattr(case.ledger, "action_attempt", observe)
    row = observe("owner-a", "canonical-one")
    assert row is not None and row.operation.state == "sent"
    assert row.claim_nonce_digest is not None
    assert row.operation.actual_cents is None
    assert case.responses == []
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        case.call()
    assert observe("owner-a", "canonical-one") == row
    assert case.responses == []


@pytest.mark.parametrize("protocol", ["deepseek", "anthropic"])
def test_historical_settled_escaped_answer_refuses_replay_without_resend(
    make_case, monkeypatch, protocol,
):
    case = make_case(protocol)
    escaped = "".join(f"\\u{ord(char):04x}" for char in _SECRET)
    text = '{"rendered_text":"' + escaped + '","claims":[]}'
    def historical_response(request):
        case.responses.append(request)
        if protocol == "deepseek":
            payload = {"id": "historical-fixture", "object": "chat.completion",
                "model": "deepseek-flash", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 9, "total_tokens": 17}}
        else:
            payload = {"id": "historical-fixture", "type": "message", "role": "assistant",
                "model": case.record.model_id, "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 8, "output_tokens": 9}}
        return httpx.Response(200, json=payload)
    monkeypatch.setattr(canonical_http, "_new_inner_transport",
                        lambda: httpx.MockTransport(historical_response))
    validate = canonical_http.validate_owned_response_text
    # Recreate the former text check while retaining the real private wire,
    # claim, usage validation and journal settlement for this synthetic row.
    monkeypatch.setattr(canonical_http, "validate_owned_response_text", lambda *_: None)
    first, _ = case.call()
    assert first.text == text and len(case.responses) == 1
    before = case.ledger.action_attempt("owner-a", "canonical-one")
    assert before is not None and before.operation.state == "settled"
    monkeypatch.setattr(canonical_http, "validate_owned_response_text", validate)
    with pytest.raises(sender.OwnerByotDispatchUnavailable):
        case.call()
    assert case.ledger.action_attempt("owner-a", "canonical-one") == before
    assert len(case.responses) == 1


def test_live_duplicate_observes_winner_without_marking_unknown(make_case, monkeypatch):
    case = make_case("deepseek")
    entered = threading.Event()
    release = threading.Event()

    def held_response(request: httpx.Request) -> httpx.Response:
        entered.set()
        assert release.wait(10)
        return httpx.Response(200, json={
            "id": "held-fixture", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Private answer"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 9, "total_tokens": 17},
        })

    monkeypatch.setattr(canonical_http, "_new_inner_transport",
                        lambda: httpx.MockTransport(held_response))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(case.call)
        try:
            assert entered.wait(10)
            with pytest.raises(sender.OwnerByotDispatchUnavailable):
                case.call()
            assert case.ledger.action_attempt("owner-a", "canonical-one").operation.state == "sent"
        finally:
            release.set()
        result, _ = future.result(timeout=10)
    assert result.text == "Private answer"
    assert case.ledger.action_attempt("owner-a", "canonical-one").operation.state == "settled"


def test_verified_usage_overrun_settles_actual_and_quarantines(make_case, monkeypatch):
    case = make_case("deepseek")

    def overrun(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "overrun-fixture", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Private answer"},
                         "finish_reason": "length"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 100_000,
                      "total_tokens": 100_008},
        })

    monkeypatch.setattr(canonical_http, "_new_inner_transport",
                        lambda: httpx.MockTransport(overrun))
    result, _ = case.call()
    attempt = case.ledger.action_attempt("owner-a", "canonical-one")
    assert result.usage.output_tokens == 100_000
    assert attempt is not None and attempt.operation.state == "settled"
    assert attempt.operation.actual_cents > attempt.proposal.reserved_cents
    assert case.ledger.action("owner-a", "action-a").quarantined
