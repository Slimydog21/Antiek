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
