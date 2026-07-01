"""Tests for the RLM-backed long-document wrestling route."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from interfaces.research.api.rlm_wrestling import maybe_handle_rlm_distillation
from interfaces.research.api.wrestling import (
    _parse_claims_response,
    _resolve_document_text_from_db,
    _resolve_region_text,
    _sha256_prefix,
)
from runtime.db_lock import connect_write
from substrate.dispatch import (
    DispatchConfig,
    NormalizedUsage,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory
from substrate.graph import ensure_initialized, insert_chunk, insert_document
from substrate.schemas import (
    ActionType,
    DistillationDeliveredPayload,
    DistillationRequestedPayload,
    Event,
)


@pytest.fixture(autouse=True)
def _provider_registry_clean():
    reset_provider_registry()
    yield
    reset_provider_registry()


class _RecordingBroadcaster:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def broadcast(self, event: Event) -> None:
        self.events.append(event)


class _CodeProvider:
    name = "rlm-code-stub"

    def __init__(self, code: str) -> None:
        self.code = code

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        return RawProviderResponse(
            text=self.code,
            raw_usage={"input_tokens": 100, "output_tokens": 50},
            finish_reason="end_turn",
            latency_ms=10,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _dispatch_config() -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    tier = TierConfig(
        name="synthesis",
        provider="rlm-code-stub",
        model="stub-model",
        max_tokens=512,
        temperature=0.0,
        context_budget_tokens=64_000,
        pricing=pricing,
        fallback=None,
    )
    return DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": tier},
    )


def _cost_cap_dispatch_config() -> DispatchConfig:
    tier = TierConfig(
        name="synthesis",
        provider="rlm-code-stub",
        model="stub-model",
        max_tokens=512,
        temperature=0.0,
        context_budget_tokens=64_000,
        pricing=TierPricing(input_per_mtok=0.0, output_per_mtok=200_000.0),
        fallback=None,
    )
    return DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": tier},
    )


def _event(*, investigation_id: str, document_id: str) -> Event:
    payload = DistillationRequestedPayload(
        user_prompt="What is the load-bearing constraint?",
        target_token_count=256,
    )
    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:8]}",
        investigation_id=investigation_id,
        action_type=ActionType.DISTILLATION_REQUESTED,
        payload=payload,
        param_version="test-v0",
        emitted_at=datetime.now(UTC),
        document_id=document_id,
    )


def test_rlm_wrestling_emits_lifecycle_and_delivered(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setattr(
        "substrate.dispatch.router.DispatchConfig.from_yaml",
        classmethod(lambda cls, path: _dispatch_config()),
    )
    code = (
        "answer['content'] = '{"
        "\"rendered_text\": \"RLM result\", "
        "\"claims\": [{\"text\": \"Constraint found.\", \"confidence\": \"high\"}]"
        "}'\n"
        "answer['ready'] = True"
    )
    register_provider(_CodeProvider(code))

    ensure_initialized(db)
    con = connect_write(db, purpose="test_seed")
    try:
        insert_document(
            con,
            document_id="doc-long",
            source_tier=4,
            document_type="pdf",
        )
        insert_chunk(
            con,
            document_id="doc-long",
            chunk_index=0,
            text="A" * 270_000,
        )
    finally:
        con.close()

    bus = _RecordingBroadcaster()
    event = _event(investigation_id="inv-rlm-wrestle", document_id="doc-long")

    handled = asyncio.run(
        maybe_handle_rlm_distillation(
            event=event,
            request=event.payload,
            broadcaster=bus,
            db_path=db,
            resolve_document_text=_resolve_document_text_from_db,
            resolve_region_text=_resolve_region_text,
            parse_claims_response=_parse_claims_response,
            sha256_prefix=_sha256_prefix,
        )
    )

    assert handled is True
    assert [e.payload.action_type for e in bus.events] == [
        "rlm.session_started",
        "rlm.iteration",
        "rlm.session_completed",
        "distillation.delivered",
    ]

    delivered_rows = [
        row
        for row in trajectory("inv-rlm-wrestle")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered_rows) == 1
    delivered = Event.model_validate(delivered_rows[0])
    assert isinstance(delivered.payload, DistillationDeliveredPayload)
    assert delivered.policy_id == "rlm-wrestling/evented-loop"
    assert delivered.payload.rendered_text == "RLM result"
    assert delivered.payload.claims[0].text == "Constraint found."


def test_rlm_wrestling_emits_sub_call_for_llm_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setattr(
        "substrate.dispatch.router.DispatchConfig.from_yaml",
        classmethod(lambda cls, path: _dispatch_config()),
    )
    code = (
        "partials = llm_batch(['a', 'b', 'c', 'd', 'e'])\n"
        "answer['content'] = '{"
        "\"rendered_text\": \"RLM batch result\", "
        "\"claims\": [{\"text\": \"Batch constraint found.\", "
        "\"confidence\": \"moderate\"}]"
        "}'\n"
        "answer['ready'] = True"
    )
    register_provider(_CodeProvider(code))

    ensure_initialized(db)
    con = connect_write(db, purpose="test_seed")
    try:
        insert_document(
            con,
            document_id="doc-long-batch",
            source_tier=4,
            document_type="pdf",
        )
        insert_chunk(
            con,
            document_id="doc-long-batch",
            chunk_index=0,
            text="B" * 270_000,
        )
    finally:
        con.close()

    bus = _RecordingBroadcaster()
    event = _event(
        investigation_id="inv-rlm-wrestle-batch",
        document_id="doc-long-batch",
    )

    handled = asyncio.run(
        maybe_handle_rlm_distillation(
            event=event,
            request=event.payload,
            broadcaster=bus,
            db_path=db,
            resolve_document_text=_resolve_document_text_from_db,
            resolve_region_text=_resolve_region_text,
            parse_claims_response=_parse_claims_response,
            sha256_prefix=_sha256_prefix,
        )
    )

    assert handled is True
    assert [e.payload.action_type for e in bus.events] == [
        "rlm.session_started",
        "rlm.sub_call_dispatched",
        "rlm.iteration",
        "rlm.session_completed",
        "distillation.delivered",
    ]
    sub_call = bus.events[1].payload
    assert sub_call.prompt_count == 5
    assert sub_call.target_role == "synthesizer"
    assert sub_call.parent_event_id == event.event_id
    dispatch_calls = [
        row
        for row in trajectory("inv-rlm-wrestle-batch")
        if row["action_type"] == "dispatch.call"
    ]
    assert len(dispatch_calls) == 6  # one codegen call + five llm_batch calls
    assert all(row["parent_event_id"] == event.event_id for row in dispatch_calls)


def test_rlm_wrestling_cost_cap_delivers_hedged_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setattr(
        "substrate.dispatch.router.DispatchConfig.from_yaml",
        classmethod(lambda cls, path: _cost_cap_dispatch_config()),
    )
    code = (
        "answer['content'] = '{"
        "\"rendered_text\": \"expensive partial\", "
        "\"claims\": [{\"text\": \"partial\", \"confidence\": \"low\"}]"
        "}'\n"
        "answer['ready'] = True"
    )
    register_provider(_CodeProvider(code))

    ensure_initialized(db)
    con = connect_write(db, purpose="test_seed")
    try:
        insert_document(
            con,
            document_id="doc-long-cost",
            source_tier=4,
            document_type="pdf",
        )
        insert_chunk(
            con,
            document_id="doc-long-cost",
            chunk_index=0,
            text="C" * 270_000,
        )
    finally:
        con.close()

    bus = _RecordingBroadcaster()
    event = _event(
        investigation_id="inv-rlm-wrestle-cost",
        document_id="doc-long-cost",
    )

    handled = asyncio.run(
        maybe_handle_rlm_distillation(
            event=event,
            request=event.payload,
            broadcaster=bus,
            db_path=db,
            resolve_document_text=_resolve_document_text_from_db,
            resolve_region_text=_resolve_region_text,
            parse_claims_response=_parse_claims_response,
            sha256_prefix=_sha256_prefix,
        )
    )

    assert handled is True
    assert [e.payload.action_type for e in bus.events] == [
        "rlm.session_started",
        "rlm.session_completed",
        "distillation.delivered",
    ]
    completed = bus.events[1].payload
    assert completed.status == "cost_capped"
    assert completed.cost_usd_accumulated == 0.0

    delivered_rows = [
        row
        for row in trajectory("inv-rlm-wrestle-cost")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered_rows) == 1
    delivered = Event.model_validate(delivered_rows[0])
    assert "cost cap" in delivered.payload.rendered_text
    assert delivered.payload.claims[0].confidence == "unknown"
    assert "configured cost cap" in delivered.payload.claims[0].text


def test_rlm_wrestling_timeout_emits_failure_without_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setattr(
        "substrate.dispatch.router.DispatchConfig.from_yaml",
        classmethod(lambda cls, path: _dispatch_config()),
    )
    code = "x = 0\nwhile x < 1000000:\n    x += 1"
    register_provider(_CodeProvider(code))

    ensure_initialized(db)
    con = connect_write(db, purpose="test_seed")
    try:
        insert_document(
            con,
            document_id="doc-long-timeout",
            source_tier=4,
            document_type="pdf",
        )
        insert_chunk(
            con,
            document_id="doc-long-timeout",
            chunk_index=0,
            text="T" * 270_000,
        )
    finally:
        con.close()

    bus = _RecordingBroadcaster()
    event = _event(
        investigation_id="inv-rlm-wrestle-timeout",
        document_id="doc-long-timeout",
    )

    handled = asyncio.run(
        maybe_handle_rlm_distillation(
            event=event,
            request=event.payload,
            broadcaster=bus,
            db_path=db,
            resolve_document_text=_resolve_document_text_from_db,
            resolve_region_text=_resolve_region_text,
            parse_claims_response=_parse_claims_response,
            sha256_prefix=_sha256_prefix,
            timeout_s=0.000001,
        )
    )

    assert handled is True
    assert [e.payload.action_type for e in bus.events] == [
        "rlm.session_started",
        "rlm.session_failed",
    ]
    failed = bus.events[1].payload
    assert failed.error_type == "TimeoutError"
    assert [
        row
        for row in trajectory("inv-rlm-wrestle-timeout")
        if row["action_type"] == "distillation.delivered"
    ] == []


def test_rlm_wrestling_exposes_search_graph_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setattr(
        "substrate.dispatch.router.DispatchConfig.from_yaml",
        classmethod(lambda cls, path: _dispatch_config()),
    )
    monkeypatch.setattr(
        "interfaces.research.api.rlm_wrestling.search_graph",
        lambda query, top_k=5: f"tool result for {query} top_k={top_k}",
    )
    code = (
        "evidence = search_graph('constraint', top_k=3)\n"
        "answer['content'] = '{"
        "\"rendered_text\": \"' + evidence + '\", "
        "\"claims\": [{\"text\": \"Graph evidence was available.\", "
        "\"confidence\": \"moderate\"}]"
        "}'\n"
        "answer['ready'] = True"
    )
    register_provider(_CodeProvider(code))

    ensure_initialized(db)
    con = connect_write(db, purpose="test_seed")
    try:
        insert_document(
            con,
            document_id="doc-long-search",
            source_tier=4,
            document_type="pdf",
        )
        insert_chunk(
            con,
            document_id="doc-long-search",
            chunk_index=0,
            text="S" * 270_000,
        )
    finally:
        con.close()

    bus = _RecordingBroadcaster()
    event = _event(
        investigation_id="inv-rlm-wrestle-search",
        document_id="doc-long-search",
    )

    handled = asyncio.run(
        maybe_handle_rlm_distillation(
            event=event,
            request=event.payload,
            broadcaster=bus,
            db_path=db,
            resolve_document_text=_resolve_document_text_from_db,
            resolve_region_text=_resolve_region_text,
            parse_claims_response=_parse_claims_response,
            sha256_prefix=_sha256_prefix,
        )
    )

    assert handled is True
    delivered_rows = [
        row
        for row in trajectory("inv-rlm-wrestle-search")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered_rows) == 1
    delivered = Event.model_validate(delivered_rows[0])
    assert delivered.payload.rendered_text == "tool result for constraint top_k=3"
    assert delivered.payload.claims[0].text == "Graph evidence was available."
