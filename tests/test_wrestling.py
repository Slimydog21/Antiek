"""Tests for the backend wrestling bridge.

What this file proves:

1. End-to-end happy path: a region is selected, a distillation is
   requested, the synthesizer dispatch returns structured JSON, and a
   ``distillation.delivered`` event with typed Claim[] lands on the
   trajectory.
2. The handler tolerates the LLM returning loose JSON (markdown fences,
   leading prose, trailing newlines).
3. Malformed-non-JSON responses surface as a single ``unknown``-
   confidence claim — the user sees something rather than nothing.
4. Missing provider doesn't crash the handler; a fallback claim is
   emitted with a ``wrestling-fallback/no-provider`` policy_id stamp.
5. The delivered event broadcasts to subscribed WebSocket clients.

Tests use httpx.AsyncClient + ASGITransport because the wrestling
handler runs as an asyncio background task; the TestClient's synchronous
interface returns before the handler completes. AsyncClient gives us
the same event loop the handler runs in, so ``wait_for_handlers``
deterministically waits for completion.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    DistillationDeliveredPayload,
    Event,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_events_and_providers(tmp_path, monkeypatch):
    """Pin every external-state resource at a tmp path: the event log
    JSONL store, the graph DuckDB file, and the embedding provider
    (forced to the deterministic hash fallback so tests don't load
    sentence-transformers)."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


class _StubSynthesizer:
    """Provider that returns a configured string. Used to control what
    the synthesizer ``dispatch`` call appears to have returned without
    actually hitting an LLM."""

    name = "stub-synthesis"

    def __init__(self, text: str, *, raise_on_call: bool = False):
        self._text = text
        self._raise = raise_on_call
        self.prompts: list[str] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.prompts.append(prompt)
        if self._raise:
            raise ProviderError("stub failure", provider=self.name, model=model, latency_ms=0)
        return RawProviderResponse(
            text=self._text,
            raw_usage={"input_tokens": 100, "output_tokens": 50},
            finish_reason="end_turn",
            latency_ms=10,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _wrestling_config(provider_name: str) -> DispatchConfig:
    """A DispatchConfig with a synthesis tier wired to ``provider_name``.
    Patched onto the dispatch router via monkeypatch in each test."""
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    synthesis = TierConfig(
        name="synthesis", provider=provider_name, model="stub-model",
        max_tokens=512, temperature=0.4, context_budget_tokens=64_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": synthesis},
    )


def _patch_dispatch_config(monkeypatch, config: DispatchConfig) -> None:
    """The wrestling handler calls dispatch() without an explicit config
    argument, so we monkeypatch DispatchConfig.from_yaml on the router
    to always return our test config."""
    import substrate.dispatch.router as router
    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: config),
    )


@pytest.fixture
def app_and_bus():
    bus = EventBroadcaster()
    app = create_app(broadcaster=bus, cors_origins=[])
    return app, bus


@pytest.fixture
async def async_client(app_and_bus):
    app, _ = app_and_bus
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _post_region(ac, *, investigation_id, document_id, region_id, text_excerpt):
    """Post a document.region_selected event with sensible defaults."""
    payload: dict[str, Any] = {
        "action_type": "document.region_selected",
        "region_id": region_id,
        "page": 1,
        "char_start": 0,
        "char_end": len(text_excerpt),
        "text_excerpt": text_excerpt,
    }
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": payload,
            "role": "user_agent",
        },
    )
    assert r.status_code == 201, r.text


async def _post_distillation_request(ac, *, investigation_id, document_id, region_id, user_prompt, target_tokens=256):
    payload: dict[str, Any] = {
        "action_type": "distillation.requested",
        "region_id": region_id,
        "user_prompt": user_prompt,
        "target_token_count": target_tokens,
    }
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": payload,
            "role": "user_agent",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["event_id"]


# ---------------------------------------------------------------------------
# 1. End-to-end happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_distillation_request_emits_delivered_with_structured_claims(
    monkeypatch, app_and_bus, async_client
):
    app, bus = app_and_bus
    register_provider(_StubSynthesizer(
        '{"rendered_text": "Two sentences summarizing the region.",'
        ' "claims": ['
        ' {"text": "X causes Y in case A.", "confidence": "moderate"},'
        ' {"text": "No causation has been shown in case B.", "confidence": "high"}'
        ']}'
    ))
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    inv = "inv-wrestle-1"
    doc = "doc-1"
    region = "r-1"

    await _post_region(
        async_client,
        investigation_id=inv, document_id=doc, region_id=region,
        text_excerpt="The source text about X and Y.",
    )
    await _post_distillation_request(
        async_client,
        investigation_id=inv, document_id=doc, region_id=region,
        user_prompt="Is X causally related to Y?",
    )

    # Wait for the wrestling handler to complete.
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory(inv)
    delivered = [r for r in rows if r["action_type"] == "distillation.delivered"]
    assert len(delivered) == 1, f"expected one delivered event, got {len(delivered)}"

    event = Event.model_validate(delivered[0])
    assert isinstance(event.payload, DistillationDeliveredPayload)
    p = event.payload
    assert p.rendered_text == "Two sentences summarizing the region."
    assert len(p.claims) == 2
    assert p.claims[0].text == "X causes Y in case A."
    assert p.claims[0].confidence == "moderate"
    assert p.claims[0].attribution_region_ids == [region]
    assert p.claims[1].confidence == "high"
    assert p.token_count == 50
    # The delivered event references the request via parent_event_id and
    # via the payload's request_event_id.
    assert p.request_event_id  # set
    assert event.parent_event_id == p.request_event_id
    assert event.role == "synthesizer"
    assert event.document_id == doc


@pytest.mark.asyncio
async def test_later_wrestling_prompt_receives_only_causal_same_investigation_memory(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    provider = _StubSynthesizer(
        '{"rendered_text": "ok", "claims": [{"text": "supported", '
        '"confidence": "moderate"}]}'
    )
    register_provider(provider)
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    async def post_memory(investigation_id: str, payload: dict[str, Any]) -> None:
        response = await async_client.post(
            "/events/typed",
            json={
                "investigation_id": investigation_id,
                "document_id": "doc-memory",
                "payload": payload,
                "role": "note_taker",
            },
        )
        assert response.status_code == 201, response.text

    await post_memory("inv-memory", {
        "action_type": "note.emerged",
        "note_id": "note-memory",
        "note_text": "Earlier insight to challenge, not source evidence.",
        "source_event_ids": ["source-event"],
        "confidence": "moderate",
        "node_id": None,
    })
    await post_memory("inv-memory", {
        "action_type": "question.identified",
        "question_id": "question-memory",
        "question_text": "Which mechanism remains unresolved?",
        "anchor_region_id": None,
    })
    await post_memory("inv-foreign", {
        "action_type": "note.emerged",
        "note_id": "note-foreign",
        "note_text": "FOREIGN MEMORY MUST NOT APPEAR",
        "source_event_ids": ["foreign-source"],
        "confidence": "high",
        "node_id": None,
    })
    await _post_region(
        async_client, investigation_id="inv-memory", document_id="doc-memory",
        region_id="region-memory", text_excerpt="Current authoritative source text.",
    )
    await _post_distillation_request(
        async_client, investigation_id="inv-memory", document_id="doc-memory",
        region_id="region-memory", user_prompt="What follows from this source?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert len(provider.prompts) == 1
    prompt = provider.prompts[0]
    assert "Earlier insight to challenge, not source evidence." in prompt
    assert "Which mechanism remains unresolved?" in prompt
    assert "FOREIGN MEMORY MUST NOT APPEAR" not in prompt
    assert prompt.index("## working_memory:") < prompt.index("## session:")
    assert prompt.index("Current authoritative source text.") < prompt.index(
        "What follows from this source?"
    )
    packs = [
        Event.model_validate(row)
        for row in trajectory("inv-memory")
        if row["action_type"] == "context_pack.assembled"
    ]
    memory_layers = [
        layer for layer in packs[-1].payload.layers if layer.kind == "working_memory"
    ]
    assert len(memory_layers) == 1
    assert memory_layers[0].source.startswith("investigation-memory:sha256:")
    assert memory_layers[0].source.endswith(":items=2")


@pytest.mark.asyncio
async def test_corrupt_working_memory_fails_visible_before_provider_dispatch(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    provider = _StubSynthesizer(
        '{"rendered_text": "must not run", "claims": []}'
    )
    register_provider(provider)
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))
    duplicate = {
        "action_type": "note.emerged",
        "note_id": "duplicate-note",
        "note_text": "same identity cannot be folded twice",
        "source_event_ids": ["source-event"],
        "confidence": "unknown",
        "node_id": None,
    }
    for _ in range(2):
        response = await async_client.post(
            "/events/typed",
            json={
                "investigation_id": "inv-corrupt-memory",
                "document_id": "doc-memory",
                "payload": duplicate,
                "role": "note_taker",
            },
        )
        assert response.status_code == 201, response.text
    await _post_region(
        async_client, investigation_id="inv-corrupt-memory", document_id="doc-memory",
        region_id="region-memory", text_excerpt="Current source.",
    )
    await _post_distillation_request(
        async_client, investigation_id="inv-corrupt-memory", document_id="doc-memory",
        region_id="region-memory", user_prompt="Question?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert provider.prompts == []
    delivered = [
        Event.model_validate(row)
        for row in trajectory("inv-corrupt-memory")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0].policy_id == "wrestling-fallback/memory-integrity"
    assert "No synthesizer call was made" in delivered[0].payload.rendered_text


@pytest.mark.asyncio
async def test_physical_trajectory_corruption_prevents_provider_dispatch(
    monkeypatch, app_and_bus, async_client
):
    from substrate.event_log import PhysicalTrajectoryError

    _, bus = app_and_bus
    provider = _StubSynthesizer('{"rendered_text": "must not run", "claims": []}')
    register_provider(provider)
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    def corrupt_physical_reader(*args, **kwargs):
        raise PhysicalTrajectoryError("conflicting duplicate event_id")

    monkeypatch.setattr(
        "interfaces.research.api.wrestling.iter_physical_events",
        corrupt_physical_reader,
    )
    await _post_distillation_request(
        async_client,
        investigation_id="inv-physical-corruption",
        document_id="doc-memory",
        region_id=None,
        user_prompt="Question?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert provider.prompts == []
    delivered = [
        Event.model_validate(row)
        for row in trajectory("inv-physical-corruption")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0].policy_id == "wrestling-fallback/memory-integrity"


# ---------------------------------------------------------------------------
# 2. Loose JSON (code fences, prose preamble)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_extracts_json_from_markdown_fence(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    register_provider(_StubSynthesizer(
        "Sure! Here's the JSON you asked for:\n\n```json\n"
        '{"rendered_text": "Summary.", "claims": ['
        ' {"text": "A claim.", "confidence": "low"}]}'
        "\n```\n"
    ))
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    inv = "inv-fence"
    await _post_region(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        text_excerpt="text",
    )
    await _post_distillation_request(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        user_prompt="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory(inv)
    delivered = [r for r in rows if r["action_type"] == "distillation.delivered"]
    assert delivered
    p = Event.model_validate(delivered[0]).payload
    assert len(p.claims) == 1
    assert p.claims[0].text == "A claim."
    assert p.claims[0].confidence == "low"


# ---------------------------------------------------------------------------
# 3. Malformed response — single unknown-confidence fallback claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_falls_back_to_single_unknown_claim_on_garbage_response(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    register_provider(_StubSynthesizer("this is not json and never will be"))
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    inv = "inv-garbage"
    await _post_region(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        text_excerpt="text",
    )
    await _post_distillation_request(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        user_prompt="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory(inv)
    delivered = [r for r in rows if r["action_type"] == "distillation.delivered"]
    assert delivered
    p = Event.model_validate(delivered[0]).payload
    assert len(p.claims) == 1
    assert p.claims[0].confidence == "unknown"
    assert "not json" in p.claims[0].text


# ---------------------------------------------------------------------------
# 4. Provider failure: handler still emits a delivered event (fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_emits_fallback_when_provider_raises(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    register_provider(_StubSynthesizer("never reached", raise_on_call=True))
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    inv = "inv-fail"
    await _post_region(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        text_excerpt="text",
    )
    await _post_distillation_request(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        user_prompt="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory(inv)
    delivered = [r for r in rows if r["action_type"] == "distillation.delivered"]
    assert delivered
    event = Event.model_validate(delivered[0])
    assert event.policy_id == "wrestling-fallback/no-provider"
    assert len(event.payload.claims) == 1
    assert "Could not dispatch" in event.payload.claims[0].text


@pytest.mark.asyncio
async def test_handler_does_not_crash_when_no_provider_registered(
    monkeypatch, app_and_bus, async_client
):
    """No provider in the registry → dispatch raises KeyError → the
    handler catches and falls through to the fallback claim path."""
    _, bus = app_and_bus
    # Note: NO register_provider call.
    _patch_dispatch_config(monkeypatch, _wrestling_config("not-registered"))

    inv = "inv-noprov"
    await _post_region(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        text_excerpt="t",
    )
    await _post_distillation_request(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        user_prompt="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory(inv)
    delivered = [r for r in rows if r["action_type"] == "distillation.delivered"]
    assert delivered, "fallback delivered event should land even with no provider"
    event = Event.model_validate(delivered[0])
    assert event.policy_id == "wrestling-fallback/no-provider"


# ---------------------------------------------------------------------------
# 5. Delivered event broadcasts to WS subscribers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delivered_event_broadcasts_to_subscribers(
    monkeypatch, app_and_bus, async_client
):
    """A subscribed WS-style listener should receive the delivered event
    fired by the handler (not just the request event that triggered it)."""
    _, bus = app_and_bus
    register_provider(_StubSynthesizer(
        '{"rendered_text": "ok", "claims": [{"text": "c", "confidence": "low"}]}'
    ))
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    # Capture broadcasts via a Python handler registered for
    # ``distillation.delivered``. Same mechanism as WS subscribers
    # internally use.
    seen: list[Event] = []

    async def capture(event):
        seen.append(event)

    bus.register_handler("distillation.delivered", capture)

    inv = "inv-bcast"
    await _post_region(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        text_excerpt="t",
    )
    await _post_distillation_request(
        async_client, investigation_id=inv, document_id="d", region_id="r",
        user_prompt="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert any(e.action_type == "distillation.delivered" for e in seen), (
        f"capture handler never saw the delivered broadcast; got: "
        f"{[str(e.action_type) for e in seen]}"
    )


# ---------------------------------------------------------------------------
# 6. Unit tests for the JSON extractor
# ---------------------------------------------------------------------------


def test_extract_json_object_handles_plain_json():
    from interfaces.research.api.wrestling import _extract_json_object
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_handles_code_fence():
    from interfaces.research.api.wrestling import _extract_json_object
    assert _extract_json_object('```json\n{"a": 2}\n```') == {"a": 2}


def test_extract_json_object_handles_prose_preamble():
    from interfaces.research.api.wrestling import _extract_json_object
    assert _extract_json_object("Sure thing!\n\n{\"a\": 3}") == {"a": 3}


def test_extract_json_object_returns_none_for_non_json():
    from interfaces.research.api.wrestling import _extract_json_object
    assert _extract_json_object("just plain text, no braces here") is None
    assert _extract_json_object("") is None


# ---------------------------------------------------------------------------
# 7. Confidence normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("high", "high"),
    ("HIGH", "high"),
    (" moderate ", "unknown"),  # whitespace not stripped intentionally
    ("medium", "unknown"),       # not in the schema enum
    (None, "unknown"),
    (0.9, "unknown"),
])
def test_normalize_confidence_coerces_unknown_values(raw, expected):
    from interfaces.research.api.wrestling import _normalize_confidence
    assert _normalize_confidence(raw) == expected


# ---------------------------------------------------------------------------
# Sprint 3 Day 2-3 — graph integration
# ---------------------------------------------------------------------------


def _read_graph_row(table: str, where: str, params: list) -> tuple | None:
    """Read one row from the test-isolated graph DB. Inline DuckDB
    connect so the test doesn't depend on import order."""
    import duckdb
    db_path = os.environ["ANTIEK_DUCKDB_PATH"]
    if not os.path.exists(db_path):
        return None
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchone()
    finally:
        con.close()


async def _post_document_loaded(ac, *, investigation_id, document_id, title=None, size_bytes=1000):
    payload: dict[str, Any] = {
        "action_type": "document.loaded",
        "media_type": "pdf",
        "content_hash": "sha256:test",
        "size_bytes": size_bytes,
        "title": title,
        "page_count": 12,
    }
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": payload,
            "role": "user_agent",
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_document_loaded_handler_inserts_documents_row(
    app_and_bus, async_client
):
    _, bus = app_and_bus
    await _post_document_loaded(
        async_client, investigation_id="inv-doc", document_id="doc-A",
        title="paper.pdf",
    )
    await bus.wait_for_handlers(timeout=5.0)

    row = _read_graph_row("documents", "document_id = ?", ["doc-A"])
    assert row is not None
    # Columns: document_id, source_uri, title, author, published_at,
    # acquired_at, source_tier, document_type, investigation_id, raw_text, metadata
    assert row[0] == "doc-A"
    assert row[2] == "paper.pdf"
    # Default tier when surface doesn't classify.
    assert row[6] == 4
    assert row[7] == "pdf"
    assert row[8] == "inv-doc"


@pytest.mark.asyncio
async def test_document_loaded_handler_is_idempotent(app_and_bus, async_client):
    _, bus = app_and_bus
    await _post_document_loaded(
        async_client, investigation_id="inv-idem", document_id="doc-A",
        title="first.pdf",
    )
    await bus.wait_for_handlers(timeout=5.0)
    # Re-fire with a different title — should be ignored by on_conflict='ignore'.
    await _post_document_loaded(
        async_client, investigation_id="inv-idem", document_id="doc-A",
        title="second.pdf",
    )
    await bus.wait_for_handlers(timeout=5.0)

    row = _read_graph_row("documents", "document_id = ?", ["doc-A"])
    assert row is not None
    assert row[2] == "first.pdf"  # original retained


@pytest.mark.asyncio
async def test_region_selected_handler_inserts_chunk_and_node(
    app_and_bus, async_client
):
    _, bus = app_and_bus
    # document.loaded first so the chunks FK resolves.
    await _post_document_loaded(
        async_client, investigation_id="inv-region", document_id="doc-R",
    )
    await _post_region(
        async_client,
        investigation_id="inv-region", document_id="doc-R", region_id="r-001-abc",
        text_excerpt="X causes Y in the photonic case.",
    )
    await bus.wait_for_handlers(timeout=5.0)

    # Chunk row landed with the deterministic id.
    chunk = _read_graph_row("chunks", "chunk_id = ?", ["chunk-001-abc"])
    assert chunk is not None
    assert chunk[1] == "doc-R"  # document_id
    assert chunk[4].startswith("X causes Y")  # text column
    # Embedding column has a float[384] from the hash fallback.
    assert chunk[5] is not None
    assert len(chunk[5]) == 384

    # GRAPH_NODE_INSERTED event landed via the ops emit_typed.
    rows = trajectory("inv-region")
    node_events = [r for r in rows if r["action_type"] == "graph.node.inserted"]
    assert len(node_events) == 1
    ev = Event.model_validate(node_events[0])
    assert ev.payload.canonical_label.startswith("X causes Y")
    assert ev.payload.node_type == "claim"
    assert ev.payload.graph_scope == "cross_domain"
    assert ev.payload.has_embedding is True


@pytest.mark.asyncio
async def test_region_selected_handler_is_idempotent(app_and_bus, async_client):
    """Same region_id → same chunk_id → no duplicate row, no duplicate
    GRAPH_NODE_INSERTED event."""
    _, bus = app_and_bus
    await _post_document_loaded(
        async_client, investigation_id="inv-region-idem", document_id="doc-RI",
    )
    for _ in range(3):
        await _post_region(
            async_client,
            investigation_id="inv-region-idem", document_id="doc-RI",
            region_id="r-dup-1",
            text_excerpt="same region selected three times",
        )
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory("inv-region-idem")
    node_events = [r for r in rows if r["action_type"] == "graph.node.inserted"]
    assert len(node_events) == 1, (
        f"expected 1 GRAPH_NODE_INSERTED across 3 region_selected posts, "
        f"got {len(node_events)}"
    )


@pytest.mark.asyncio
async def test_distillation_handler_prefers_chunk_text_from_graph(
    monkeypatch, app_and_bus, async_client
):
    """Sprint 3 fast path: when a region's text is in the chunks table,
    the distillation handler resolves it from there instead of walking
    the trajectory. Removing the trajectory entry shouldn't break the
    distillation lookup once the chunk row exists."""
    _, bus = app_and_bus
    register_provider(_StubSynthesizer(
        '{"rendered_text": "ok", "claims": [{"text": "c", "confidence": "low"}]}'
    ))
    _patch_dispatch_config(monkeypatch, _wrestling_config("stub-synthesis"))

    await _post_document_loaded(
        async_client, investigation_id="inv-from-graph", document_id="doc-G",
    )
    await _post_region(
        async_client,
        investigation_id="inv-from-graph", document_id="doc-G",
        region_id="r-fromgraph-1",
        text_excerpt="the source paragraph the model is supposed to read",
    )
    await bus.wait_for_handlers(timeout=5.0)

    await _post_distillation_request(
        async_client,
        investigation_id="inv-from-graph", document_id="doc-G",
        region_id="r-fromgraph-1",
        user_prompt="summarize",
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory("inv-from-graph")
        if r["action_type"] == "distillation.delivered"
    ]
    assert delivered, "distillation handler should still produce a delivered event"
    # The handler used the chunk text under the hood — direct test of
    # this is the _resolve_region_text_from_db unit test below; this
    # integration test confirms the end-to-end still works.


def test_resolve_region_text_from_db_returns_chunk_text(tmp_path):
    """Direct test: writing a chunk under the deterministic id makes
    _resolve_region_text_from_db return its text."""
    import os as _os
    db = str(tmp_path / "g.duckdb")
    _os.environ["ANTIEK_DUCKDB_PATH"] = db

    from interfaces.research.api.wrestling import (
        _region_to_chunk_id,
        _resolve_region_text_from_db,
    )
    from runtime.db_lock import connect_write
    from substrate.graph import (
        ensure_initialized,
        insert_chunk,
        insert_document,
    )

    ensure_initialized(db)
    con = connect_write(db, purpose="test_seed")
    try:
        insert_document(
            con, document_id="d", source_tier=4, document_type="pdf",
        )
        insert_chunk(
            con, chunk_id=_region_to_chunk_id("r-007"),
            document_id="d", chunk_index=0,
            text="the chunk-stored text", token_count=4,
        )
    finally:
        con.close()

    text = _resolve_region_text_from_db(db, "r-007")
    assert text == "the chunk-stored text"


def test_resolve_region_text_from_db_returns_none_when_missing(tmp_path):
    from interfaces.research.api.wrestling import _resolve_region_text_from_db
    from substrate.graph import ensure_initialized
    db = str(tmp_path / "g.duckdb")
    ensure_initialized(db)
    assert _resolve_region_text_from_db(db, "r-doesnt-exist") is None


def test_region_to_chunk_id_strips_r_prefix():
    from interfaces.research.api.wrestling import _region_to_chunk_id
    assert _region_to_chunk_id("r-abc-123") == "chunk-abc-123"
    # If the region_id doesn't have the prefix, the helper still
    # produces a chunk- id — defensive.
    assert _region_to_chunk_id("weird-id") == "chunk-weird-id"
