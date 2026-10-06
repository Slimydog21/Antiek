"""Owner-bound wrestling admission and its existing canonical consumer."""

from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from interfaces.research.api import owned_wrestling as subject
from interfaces.research.api import settings_models_admin as models_admin
from interfaces.research.api.owner_byot_dispatch import (
    approved_owner_action_route,
    dispatch_talk_to_book_byot,
)
from interfaces.research.api.settings_models_admin import UserModelChoice
from runtime.byok.store import store_credential_with_metadata
from substrate.books import owned_wrestling_sources as sources
from substrate.byot_usage.actions import ApprovedOwnerRoute, OwnerActionDecision
from substrate.byot_usage.ledger import ByotUsageLedger, OperationConflict
from substrate.constants import ANTIEK_PARAM_VERSION
from substrate.dispatch import canonical_http, register_provider, reset_provider_registry
from substrate.dispatch.router import DispatchConfig, TierConfig, TierPricing
from substrate.event_log import trajectory
from substrate.schemas import DistillationRequestedPayload, Event


def _decision() -> OwnerActionDecision:
    return OwnerActionDecision(
        "owner-a", "action-a", "long_document_wrestling", 100,
        "b" * 64, "d" * 64,
        (ApprovedOwnerRoute("record", "provider", "model", "a" * 64),),
    )


def _admit(ledger: ByotUsageLedger):
    return ledger.admit_owned_wrestling(
        _decision(), investigation_id="ownw-test", document_id="book-a",
        source_reference="source-a", source_digest="c" * 64,
        request_event_id="owreq-test", delivered_event_id="owdel-test",
        request_payload_digest=subject._payload_digest(DistillationRequestedPayload(
            user_prompt="What follows?", target_token_count=100, region_id=None,
        )),
    )


def _request(job) -> Event:
    return Event(
        event_id=job.request_event_id, investigation_id=job.investigation_id,
        action_type="distillation.requested",
        payload=DistillationRequestedPayload(
            user_prompt="What follows?", target_token_count=100, region_id=None,
        ),
        parent_event_id=None, policy_id=subject.OWNED_POLICY,
        param_version=ANTIEK_PARAM_VERSION, emitted_at=datetime.now(UTC),
        document_id=job.document_id, role="operator",
    )


def _artifact() -> dict[str, Any]:
    return {
        "material": {"body": "Exact owned book body", "document_id": "book-a"},
        "work": {
            "user_prompt": "What follows?", "target_token_count": 100,
            "approve_canonical_fallback_if_prime_unavailable": True,
            "canonical_model": {
                "authority": "user_model", "provider_id": "record", "model_id": "model",
            },
        },
    }


def test_admission_replay_is_exact_and_transaction_has_no_orphan_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    first = _admit(ledger)
    assert _admit(ledger) == first
    with pytest.raises(OperationConflict, match="cannot be rebound"):
        ledger.admit_owned_wrestling(
            _decision(), investigation_id="ownw-test", document_id="book-a",
            source_reference="source-a", source_digest="e" * 64,
            request_event_id="owreq-test", delivered_event_id="owdel-test",
            request_payload_digest=first.request_payload_digest,
        )
    with sqlite3.connect(tmp_path / "usage.sqlite3") as con:
        assert con.execute("SELECT COUNT(*) FROM byot_action_journal").fetchone() == (1,)
        assert con.execute("SELECT COUNT(*) FROM byot_owned_wrestling_job").fetchone() == (1,)
        assert con.execute("SELECT COUNT(*) FROM byot_owned_wrestling_outbox").fetchone() == (1,)

    other = ByotUsageLedger(tmp_path / "rollback.sqlite3")
    original = other._insert_action

    def crash_after_money_row(con, decision):
        original(con, decision)
        raise RuntimeError("crash before job and request outbox")

    monkeypatch.setattr(other, "_insert_action", crash_after_money_row)
    with pytest.raises(RuntimeError, match="crash"):
        _admit(other)
    assert other.action("owner-a", "action-a") is None
    assert other.owned_wrestling_job("owner-a", "action-a") is None
    with sqlite3.connect(tmp_path / "rollback.sqlite3") as con:
        assert con.execute("SELECT COUNT(*) FROM byot_owned_wrestling_outbox").fetchone() == (0,)


def test_original_v5_owned_job_layout_upgrades_and_admits_new_work(tmp_path: Path) -> None:
    path = tmp_path / "original-v5.sqlite3"
    first_ledger = ByotUsageLedger(path)
    first = _admit(first_ledger)
    with sqlite3.connect(path) as con:
        before = con.execute(
            "SELECT updated_at FROM byot_owned_wrestling_job WHERE action_id='action-a'"
        ).fetchone()[0]
        con.execute("ALTER TABLE byot_owned_wrestling_job DROP COLUMN execution_token")
        assert [row[1] for row in con.execute(
            "PRAGMA table_info(byot_owned_wrestling_job)"
        ).fetchall()][-1] == "updated_at"
        assert con.execute(
            "SELECT value FROM byot_usage_meta WHERE key='schema_version'"
        ).fetchone() == ("6",)

    upgraded = ByotUsageLedger(path)
    assert upgraded.owned_wrestling_job("owner-a", "action-a") == first
    second = upgraded.admit_owned_wrestling(
        replace(_decision(), action_id="action-b"),
        investigation_id="ownw-second", document_id="book-a",
        source_reference="source-b", source_digest="e" * 64,
        request_event_id="owreq-second", delivered_event_id="owdel-second",
        request_payload_digest=first.request_payload_digest,
    )
    assert second.state == "queued"
    elected = upgraded.claim_owned_wrestling_execution(
        "owner-a", "action-b", token="worker-b", operation_id="owcanon-second",
    )
    assert elected is not None and elected.execution_token == "worker-b"
    with sqlite3.connect(path) as con:
        old_row = con.execute(
            "SELECT updated_at,execution_token FROM byot_owned_wrestling_job"
            " WHERE action_id='action-a'"
        ).fetchone()
        new_row = con.execute(
            "SELECT updated_at,execution_token FROM byot_owned_wrestling_job"
            " WHERE action_id='action-b'"
        ).fetchone()
    assert old_row == (before, None)
    assert isinstance(new_row[0], str) and new_row[0]
    assert new_row[1] == "worker-b"


def test_owned_book_submission_binds_actual_source_and_approved_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    choice = {"authority": "user_model", "provider_id": "record", "model_id": "model"}
    work = subject.OwnedWrestlingRequest.model_validate({
        "action_id": "action-a", "user_prompt": "What follows?", "target_token_count": 100,
        "total_budget_cents": 100, "canonical_model": choice, "prime_model": choice,
        "approve_canonical_source_processing": True,
        "approve_prime_source_processing": True,
        "approve_canonical_fallback_if_prime_unavailable": True,
    })
    material = {
        "schema": "antiek.owned-wrestling-source.v1", "owner_user_id": "owner-a",
        "document_id": "book-a", "content_class": "personal_reading",
        "taken_down": False, "body": "The exact book body", "chunks": [],
        "body_span": {"char_start": 0, "char_end": 19},
    }
    route = ApprovedOwnerRoute("record", "provider", "model", "a" * 64)
    monkeypatch.setattr(subject, "authority_handoff_guard", lambda *_a, **_kw: nullcontext())
    monkeypatch.setattr(subject, "current_book_material", lambda *_a, **_kw: material)
    monkeypatch.setattr(subject, "approved_owner_action_route", lambda *_a, **_kw: route)
    monkeypatch.setattr(subject, "_event_rows", lambda _id: [])
    job = subject._submit_sync(SimpleNamespace(), "unused", "owner-a", "book-a", work, ledger)
    assert job.state == "queued"
    assert job.investigation_id.startswith("ownw-")
    assert ledger.action("owner-a", "action-a").decision.body_authority_digest == sources.source_digest(material)
    artifact = subject._source_artifact(job, ledger)
    assert artifact["material"] == material
    assert artifact["work"]["approve_canonical_fallback_if_prime_unavailable"] is True
    assert ledger.owned_wrestling_for_request(job.request_event_id) == job


def test_actual_book_material_binds_owner_rights_body_and_exact_chunk_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = {
        "owner": "owner-a", "body": "Alpha unique sentence. Beta unique sentence.",
        "taken_down": False, "chunk": "Beta unique sentence.",
    }

    class FakeConnection:
        def execute(self, sql: str, _params: list[str]):
            if "FROM documents d" in sql:
                return SimpleNamespace(fetchone=lambda: (
                    facts["owner"], "personal_reading", "{}", facts["taken_down"],
                ))
            return SimpleNamespace(fetchall=lambda: [
                ("chunk-a", 1, "section 1", facts["chunk"], 4),
            ])

        def close(self):
            pass

    monkeypatch.setattr(sources, "connect_read", lambda _: FakeConnection())
    monkeypatch.setattr(sources, "serve_full_text_guarded", lambda *_args, **_kw: SimpleNamespace(
        full_text=None if facts["taken_down"] else facts["body"], content_format="text",
        tier=None, license=None, canonical_url=None,
    ))
    original = sources.current_book_material("unused", owner="owner-a", document_id="book-a")
    assert original["chunks"][0]["char_start"] == original["body"].index(facts["chunk"])
    assert original["chunks"][0]["char_end"] == len(original["body"])
    digest = sources.source_digest(original)

    facts["body"] = "Alpha changed. Beta unique sentence."
    assert sources.source_digest(sources.current_book_material(
        "unused", owner="owner-a", document_id="book-a",
    )) != digest
    facts["chunk"] = "Alpha changed."
    assert sources.source_digest(sources.current_book_material(
        "unused", owner="owner-a", document_id="book-a",
    )) != digest
    facts["owner"] = "foreign"
    with pytest.raises(sources.OwnedSourceUnavailable, match="owner"):
        sources.current_book_material("unused", owner="owner-a", document_id="book-a")
    facts["owner"] = "owner-a"
    facts["taken_down"] = True
    with pytest.raises(sources.OwnedSourceUnavailable, match="rights"):
        sources.current_book_material("unused", owner="owner-a", document_id="book-a")


def test_missing_approval_budget_and_route_are_refused_before_admission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    choice = {"authority": "user_model", "provider_id": "record", "model_id": "model"}
    base = {
        "action_id": "action-a", "user_prompt": "Question?", "target_token_count": 100,
        "total_budget_cents": 10, "canonical_model": choice, "prime_model": choice,
        "approve_canonical_source_processing": True,
        "approve_prime_source_processing": True,
        "approve_canonical_fallback_if_prime_unavailable": False,
    }
    with pytest.raises(ValidationError):
        subject.OwnedWrestlingRequest.model_validate({
            key: value for key, value in base.items()
            if key != "approve_prime_source_processing"
        })
    with pytest.raises(ValidationError):
        subject.OwnedWrestlingRequest.model_validate(dict(base, total_budget_cents=0))
    with pytest.raises(ValidationError):
        subject.OwnedWrestlingRequest.model_validate(dict(
            base, approve_prime_source_processing="yes",
        ))
    with pytest.raises(ValidationError):
        subject.OwnedWrestlingRequest.model_validate(dict(base, region_id="unowned-region"))
    with pytest.raises(ValidationError):
        subject.OwnedWrestlingRequest.model_validate(dict(base, investigation_id="foreign"))
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    work = subject.OwnedWrestlingRequest.model_validate(dict(
        base, approve_canonical_source_processing=False,
    ))
    with pytest.raises(sources.OwnedSourceUnavailable, match="approval"):
        subject._submit_sync(SimpleNamespace(), "unused", "owner-a", "book-a", work, ledger)
    monkeypatch.setattr(subject, "approved_owner_action_route", lambda *_a, **_kw: (
        (_ for _ in ()).throw(subject.OwnerByotDispatchUnavailable("no current route"))
    ))
    with pytest.raises(subject.OwnerByotDispatchUnavailable):
        subject._submit_sync(SimpleNamespace(), "unused", "owner-a", "book-a",
                             subject.OwnedWrestlingRequest.model_validate(base), ledger)
    assert ledger.action("owner-a", "action-a") is None


def test_same_id_contradictory_request_and_delivery_refuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    job = _admit(ByotUsageLedger(tmp_path / "usage.sqlite3"))
    event = _request(job)
    wrong = event.model_dump(mode="json")
    wrong["payload"]["user_prompt"] = "Different question"
    monkeypatch.setattr(subject, "_event_rows", lambda _id: [wrong])
    with pytest.raises(sources.OwnedSourceUnavailable, match="contradictory"):
        subject._matching_persisted_event(
            job, job.request_event_id, event.payload, parent_event_id=None,
            role="operator", policy_id=subject.OWNED_POLICY,
        )
    delivered = subject.DistillationDeliveredPayload(
        request_event_id=job.request_event_id, claims=[], rendered_text="answer",
        rendered_text_hash=subject._sha256_prefix("answer"), token_count=1,
    )
    wrong["event_id"] = job.delivered_event_id
    wrong["action_type"] = "distillation.delivered"
    wrong["payload"] = delivered.model_dump(mode="json")
    wrong["payload"]["rendered_text"] = "contradiction"
    wrong["parent_event_id"] = job.request_event_id
    wrong["role"] = "synthesizer"
    wrong["policy_id"] = subject.OWNED_POLICY + "/canonical-fallback"
    with pytest.raises(sources.OwnedSourceUnavailable, match="contradictory"):
        subject._matching_persisted_event(
            job, job.delivered_event_id, delivered,
            parent_event_id=job.request_event_id, role="synthesizer",
            policy_id=subject.OWNED_POLICY + "/canonical-fallback",
        )


@pytest.mark.asyncio
async def test_delivery_publication_replay_keeps_one_event_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    job = _admit(ledger)
    seen: list[Event] = []

    class Broadcaster:
        async def broadcast(self, event: Event) -> None:
            seen.append(event)

    request = _request(job).payload
    await subject._publish(job, request, kind="requested",
                           broadcaster=Broadcaster(), ledger=ledger)
    ledger.transition_owned_wrestling("owner-a", "action-a", expected="queued", state="running")
    delivered = subject.DistillationDeliveredPayload(
        request_event_id=job.request_event_id, claims=[], rendered_text="answer",
        rendered_text_hash=subject._sha256_prefix("answer"), token_count=3,
    )
    job = ledger.transition_owned_wrestling(
        "owner-a", "action-a", expected="running", state="ready",
        result_reference="result-a", result_digest="e" * 64,
        publication_payload_digest=subject._payload_digest(delivered),
    )
    await subject._publish(job, delivered, kind="delivered",
                           broadcaster=Broadcaster(), ledger=ledger)
    await subject._publish(job, delivered, kind="delivered",
                           broadcaster=Broadcaster(), ledger=ledger)
    rows = trajectory(job.investigation_id)
    assert [row["event_id"] for row in rows] == [job.request_event_id, job.delivered_event_id]
    assert len(seen) == 3  # at-least-once broadcast; the durable event is unique


@pytest.mark.asyncio
async def test_missing_binding_and_prior_injected_memory_never_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    job = _admit(ledger)
    event = _request(job)
    monkeypatch.setattr(subject, "ByotUsageLedger", lambda: ledger)
    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", lambda **_kw: pytest.fail("paid send"))
    forged = event.model_copy(update={"event_id": "owreq-unbound"})
    with pytest.raises(sources.OwnedSourceUnavailable, match="no server-owned binding"):
        await subject.consume(forged, broadcaster=SimpleNamespace())

    monkeypatch.setattr(subject, "_source_artifact", lambda *_args: _artifact())
    monkeypatch.setattr(subject, "_require_current_source", lambda *_args: "b" * 64)
    injected = {"event_id": "note-unowned", "investigation_id": job.investigation_id,
                "action_type": "note.emerged", "payload": {"note_text": "foreign data"}}
    monkeypatch.setattr(subject, "_event_rows", lambda _id: [injected, event.model_dump(mode="json")])
    with pytest.raises(sources.OwnedSourceUnavailable, match="unverifiable prior events"):
        await subject.consume(event, broadcaster=SimpleNamespace())
    assert ledger.owned_wrestling_job("owner-a", "action-a").state == "refused"


@pytest.mark.asyncio
async def test_changed_current_source_refuses_before_canonical_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    job = _admit(ledger)
    monkeypatch.setattr(subject, "ByotUsageLedger", lambda: ledger)
    monkeypatch.setattr(subject, "_source_artifact", lambda *_args: _artifact())
    monkeypatch.setattr(subject, "_current_source_digest", lambda *_args: "e" * 64)
    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", lambda **_kw: pytest.fail("paid send"))
    with pytest.raises(sources.OwnedSourceUnavailable, match="body, chunks, ownership or rights"):
        await subject.consume(_request(job), broadcaster=SimpleNamespace())
    assert ledger.owned_wrestling_job("owner-a", "action-a").state == "refused"
    assert ledger.action("owner-a", "action-a").state == "closed"


@pytest.mark.asyncio
async def test_missing_canonical_fallback_approval_never_calls_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    job = _admit(ledger)
    event = _request(job)
    artifact = _artifact()
    artifact["work"]["approve_canonical_fallback_if_prime_unavailable"] = False
    monkeypatch.setattr(subject, "ByotUsageLedger", lambda: ledger)
    monkeypatch.setattr(subject, "_source_artifact", lambda *_args: artifact)
    monkeypatch.setattr(subject, "_require_current_source", lambda *_args: "b" * 64)
    monkeypatch.setattr(subject, "_event_rows", lambda _id: [event.model_dump(mode="json")])
    monkeypatch.setattr(subject, "assemble_context_pack", lambda **_kw: SimpleNamespace(
        text="exact pack", event_id="context-pack", budget_overrun=False,
    ))
    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", lambda **_kw: pytest.fail("paid send"))
    await subject.consume(event, broadcaster=SimpleNamespace())
    assert ledger.owned_wrestling_job("owner-a", "action-a").state == "refused"
    assert ledger.action("owner-a", "action-a").state == "closed"


@pytest.mark.asyncio
async def test_canonical_fallback_consumes_exact_body_and_publishes_one_typed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    job = _admit(ledger)
    event = _request(job)
    calls: list[dict[str, Any]] = []
    publications: list[tuple[str, Any]] = []
    monkeypatch.setattr(subject, "ByotUsageLedger", lambda: ledger)
    monkeypatch.setattr(subject, "_source_artifact", lambda *_args: _artifact())
    monkeypatch.setattr(subject, "_require_current_source", lambda *_args: "b" * 64)
    monkeypatch.setattr(subject, "_event_rows", lambda _id: [event.model_dump(mode="json")])
    monkeypatch.setattr(subject, "_artifact_dir", lambda _ledger: tmp_path / "artifacts")
    monkeypatch.setattr(subject, "assemble_context_pack", lambda **kw: (
        calls.append({"pack": kw}) or SimpleNamespace(
            text="PACK: " + kw["layers"][-1].content, event_id="context-pack-a",
            budget_overrun=False,
        )
    ))

    def fake_dispatch(**kwargs):
        calls.append({"dispatch": kwargs})
        return (SimpleNamespace(
            text='{"rendered_text":"Owned answer","claims":[{"text":"Supported claim","confidence":"high"}]}',
            usage=SimpleNamespace(output_tokens=7), finish_reason="stop",
        ), SimpleNamespace())

    async def fake_publish(_job, payload, *, kind, **_kwargs):
        publications.append((kind, payload))
        return Event(
            event_id=_job.delivered_event_id, investigation_id=_job.investigation_id,
            action_type="distillation.delivered", payload=payload,
            parent_event_id=_job.request_event_id,
            policy_id=subject.OWNED_POLICY + "/canonical-fallback",
            param_version=ANTIEK_PARAM_VERSION, emitted_at=datetime.now(UTC),
            document_id=_job.document_id, role="synthesizer",
        )

    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", fake_dispatch)
    monkeypatch.setattr(subject, "_publish", fake_publish)
    broadcaster = SimpleNamespace(_owner_model_app=SimpleNamespace())
    await subject.consume(event, broadcaster=broadcaster)
    assert len(calls) == 2
    dispatched = calls[1]["dispatch"]
    assert dispatched["role"] == "synthesizer"
    assert dispatched["owner_action"].action_id == job.action_id
    assert dispatched["context_pack_event_id"] == "context-pack-a"
    assert dispatched["parent_event_id"] == event.event_id
    selected_tier = dispatched["config"].role_tiers["synthesizer"]
    assert dispatched["config"].tiers[selected_tier].max_tokens == 100
    assert "Exact owned book body" in dispatched["prompt"]
    assert len(publications) == 1 and publications[0][0] == "delivered"
    delivered = publications[0][1]
    assert delivered.request_event_id == event.event_id
    assert delivered.claims[0].text == "Supported claim"
    assert delivered.token_count == 7
    assert ledger.owned_wrestling_job("owner-a", "action-a").state == "delivered"
    assert ledger.action("owner-a", "action-a").state == "closed"
    finished = ledger.owned_wrestling_job("owner-a", "action-a")
    assert finished is not None
    assert finished.canonical_input_reference and finished.canonical_input_digest
    stored = sources.read_immutable_artifact(
        tmp_path / "artifacts", finished.canonical_input_reference,
        finished.canonical_input_digest,
    )
    assert stored["prompt"] == dispatched["prompt"]


@pytest.mark.asyncio
async def test_running_worker_is_only_observed_by_duplicate_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    job = _admit(ledger)
    ledger.transition_owned_wrestling("owner-a", "action-a", expected="queued", state="running")
    monkeypatch.setattr(subject, "ByotUsageLedger", lambda: ledger)
    monkeypatch.setattr(subject, "_source_artifact", lambda *_args: _artifact())
    monkeypatch.setattr(subject, "_require_current_source", lambda *_args: "b" * 64)
    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", lambda **_kw: pytest.fail("resent"))
    await subject.consume(_request(job), broadcaster=SimpleNamespace())
    assert ledger.owned_wrestling_job("owner-a", "action-a").state == "running"


def test_actual_canonical_dispatch_event_links_pack_and_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The owner dispatcher forwards both links to the real dispatch event."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credential.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    reset_provider_registry()
    record_id = models_admin._owner_id_prefix("owner-a") + "real-dispatch-fixture"
    metadata = store_credential_with_metadata(
        record_id, "synthetic-real-dispatch-key", pipeline_kind="model_provider",
        owner_user_id="owner-a",
    )
    record = models_admin.UserModelRecord(
        id=record_id, owner_user_id="owner-a",
        provider_kind="openai_compat", provider_catalog_id="deepseek",
        model_id="deepseek-flash-nothink", display_name="Owner model",
        base_url="https://api.deepseek.com", cred_ref=metadata.cred_id,
        cred_fingerprint=metadata.artifact_fingerprint,
    )
    with models_admin._registry_guard(exclusive=True):
        models_admin._write_registry_unlocked({record.id: record})
    fingerprint = models_admin._record_fingerprint(record)
    app = FastAPI()
    app.state.user_model_registration_fingerprints = {record.id: fingerprint}
    app.state.registered_providers = {record.id}

    register_provider(models_admin._UserOpenAICompatProvider(record))
    monkeypatch.setattr(canonical_http, "_new_inner_transport", lambda: httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "id": "owned-wrestling-test", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "canonical text"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }),
    ))
    choice = UserModelChoice(
        authority="user_model", provider_id=record.id, model_id=record.model_id,
    )
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    action = ledger.begin_action(OwnerActionDecision(
        owner_user_id="owner-a", action_id="wrestle-real-dispatch",
        action_kind="long_document_wrestling", budget_cents=100,
        body_authority_digest="b" * 64, owner_decision_digest="d" * 64,
        approved_routes=(approved_owner_action_route(app, choice, owner_user_id="owner-a"),),
    ))
    tier = TierConfig("pro", "house", "house-model", 200, 0.1, 1000, TierPricing())
    config = DispatchConfig({"synthesizer": "pro"}, {"pro": tier})
    try:
        result, _ = dispatch_talk_to_book_byot(
            app=app, request_owner_user_id="owner-a", resource_owner_user_id="owner-a",
            document_id="book-a", choice=choice, prompt="actual pack text",
            investigation_id="ownw-real", logical_operation_id="owcanon-real",
            resource_authority_digest="b" * 64,
            resource_authority_revalidator=lambda: "b" * 64,
            resource_authority_guard=lambda: nullcontext("b" * 64),
            config=config, usage_ledger=ledger, role="synthesizer",
            action="wrestling.distillation", owner_action=action.ref,
            context_pack_event_id="context-pack-real", parent_event_id="owreq-real",
        )
        rows = [row for row in trajectory("ownw-real")
                if row.get("event_id") == result.event_id]
        assert len(rows) == 1
        assert rows[0]["action_type"] == "dispatch.call"
        assert rows[0]["parent_event_id"] == "owreq-real"
        assert rows[0]["payload"]["context_pack_event_id"] == "context-pack-real"
        assert rows[0]["payload"]["target_role"] == "synthesizer"
    finally:
        reset_provider_registry()
