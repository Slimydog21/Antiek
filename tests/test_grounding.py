"""Tests for the backend grounder bridge (Sprint 3 day 3-4).

End-to-end: a region is selected (wrestling bridge populates the
graph), a claim is challenged (grounder runs search + dispatches),
the verdict event lands.

Cases:

1. Happy path — grounder returns "grounded" with a chunk_id from the
   search results → ``claim.grounding_check_passed`` lands with the
   located_region_id (chunk → region reverse mapping verified).
2. Not grounded — grounder returns "grounded=false" with one of the 4
   reason Literals → ``claim.grounding_check_failed`` lands.
3. Hallucinated chunk_id — grounder claims grounded but cites a
   chunk_id not in our search results → treated as ambiguous failure
   (defends against the LLM picking an id it made up).
4. Provider unavailable — no provider registered → fallback failed
   event with ``grounding-fallback/no-provider`` policy_id.
5. Malformed JSON — handler still emits a single ambiguous-failed
   event (conservative posture from the role prompt).
6. The challenge handler doesn't fire on non-challenge events
   (sanity for action_type routing).
7. ``_chunk_to_region_id`` is the inverse of ``_region_to_chunk_id``.
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
from interfaces.research.api.grounding import (  # noqa: E402
    _chunk_to_region_id,
    _parse_grounder_response,
)
from interfaces.research.api.wrestling import _region_to_chunk_id  # noqa: E402
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
    ClaimGroundingCheckFailedPayload,
    ClaimGroundingCheckPassedPayload,
    Event,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Same isolation as test_wrestling.py — events dir, graph DB,
    embedding provider all pinned to the tmp path."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


class _StubGrounder:
    """Provider that returns a configured response string. Same shape
    as the wrestling _StubSynthesizer but registered under a different
    name so the grounder dispatch routes to it."""

    name = "stub-grounder"

    def __init__(self, text: str, *, raise_on_call: bool = False):
        self._text = text
        self._raise = raise_on_call

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        if self._raise:
            raise ProviderError(
                "stub failure", provider=self.name, model=model, latency_ms=0
            )
        return RawProviderResponse(
            text=self._text,
            raw_usage={"input_tokens": 50, "output_tokens": 20},
            finish_reason="end_turn",
            latency_ms=5,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _grounder_config(provider_name: str) -> DispatchConfig:
    """A DispatchConfig with a flash tier wired to ``provider_name``
    (grounder defaults to flash tier per substrate.constants)."""
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    flash = TierConfig(
        name="flash", provider=provider_name, model="stub-flash-model",
        max_tokens=512, temperature=0.1, context_budget_tokens=32_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"grounder": "flash"},
        tiers={"flash": flash},
    )


def _patch_dispatch_config(monkeypatch, config: DispatchConfig) -> None:
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


# ---------------------------------------------------------------------------
# Helpers: drive the wrestling bridge to populate the graph, then post a challenge
# ---------------------------------------------------------------------------


async def _post_document_loaded(ac, *, investigation_id, document_id):
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": {
                "action_type": "document.loaded",
                "media_type": "pdf",
                "content_hash": "sha256:t",
                "size_bytes": 1000,
            },
            "role": "user_agent",
        },
    )
    assert r.status_code == 201, r.text


async def _post_region(ac, *, investigation_id, document_id, region_id, text_excerpt):
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


async def _post_challenge(
    ac, *, investigation_id, document_id, claim_id, claim_text, user_question,
    anchor_region_id=None,
):
    payload: dict[str, Any] = {
        "action_type": "claim.challenge_raised",
        "challenged_claim_id": claim_id,
        "claim_text": claim_text,
        "anchor_region_id": anchor_region_id,
        "user_question": user_question,
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


async def _seed_document_with_region(
    ac, *, investigation_id, document_id, region_id, text_excerpt,
):
    """Drive document.loaded + document.region_selected so the graph
    has a chunk the grounder can search against."""
    await _post_document_loaded(
        ac, investigation_id=investigation_id, document_id=document_id,
    )
    await _post_region(
        ac, investigation_id=investigation_id, document_id=document_id,
        region_id=region_id, text_excerpt=text_excerpt,
    )


# ---------------------------------------------------------------------------
# 1. Happy path — grounded passes with located region
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grounder_returns_passed_with_located_region(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus

    inv = "inv-grounded"
    doc = "doc-G1"
    region = "r-test-1"
    region_text = "PsiQuantum uses photonic qubits with measurement-based gates."
    chunk_id = _region_to_chunk_id(region)

    # Seed the graph with the region the grounder will find.
    await _seed_document_with_region(
        async_client, investigation_id=inv, document_id=doc,
        region_id=region, text_excerpt=region_text,
    )
    await bus.wait_for_handlers(timeout=5.0)

    # Stub grounder: returns grounded=true citing the chunk_id we just
    # seeded.
    register_provider(_StubGrounder(
        f'{{"grounded": true, "located_chunk_id": "{chunk_id}", "confidence": 0.92}}'
    ))
    _patch_dispatch_config(monkeypatch, _grounder_config("stub-grounder"))

    await _post_challenge(
        async_client, investigation_id=inv, document_id=doc,
        claim_id="c-42", claim_text="PsiQuantum uses photonic qubits",
        user_question="Is this supported in the source?",
        anchor_region_id=region,
    )
    await bus.wait_for_handlers(timeout=5.0)

    passed = [
        r for r in trajectory(inv)
        if r["action_type"] == "claim.grounding_check_passed"
    ]
    assert len(passed) == 1
    ev = Event.model_validate(passed[0])
    assert isinstance(ev.payload, ClaimGroundingCheckPassedPayload)
    p = ev.payload
    assert p.claim_id == "c-42"
    assert p.claim_text == "PsiQuantum uses photonic qubits"
    assert p.located_region_id == region  # reverse map worked
    assert p.confidence == pytest.approx(0.92)
    assert ev.policy_id == "stub-grounder/stub-flash-model"
    assert ev.document_id == doc


# ---------------------------------------------------------------------------
# 2. Not grounded — failed event with reason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grounder_returns_failed_with_reason(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-ungrounded"
    doc = "doc-G2"

    await _seed_document_with_region(
        async_client, investigation_id=inv, document_id=doc,
        region_id="r-2", text_excerpt="The weather report mentions sunny skies.",
    )
    await bus.wait_for_handlers(timeout=5.0)

    # Claim has nothing to do with the source.
    register_provider(_StubGrounder(
        '{"grounded": false, "reason": "absent_from_source"}'
    ))
    _patch_dispatch_config(monkeypatch, _grounder_config("stub-grounder"))

    await _post_challenge(
        async_client, investigation_id=inv, document_id=doc,
        claim_id="c-99", claim_text="The document contains a quantum algorithm",
        user_question="Where?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    failed = [
        r for r in trajectory(inv)
        if r["action_type"] == "claim.grounding_check_failed"
    ]
    assert len(failed) == 1
    ev = Event.model_validate(failed[0])
    assert isinstance(ev.payload, ClaimGroundingCheckFailedPayload)
    assert ev.payload.reason == "absent_from_source"
    assert ev.payload.claim_id == "c-99"
    # searched_regions records what the search returned for the
    # operator-facing trajectory audit.
    assert ev.payload.searched_regions == ["r-2"]


@pytest.mark.parametrize("reason", [
    "absent_from_source", "paraphrased_not_stated", "out_of_scope", "ambiguous",
])
@pytest.mark.asyncio
async def test_grounder_accepts_every_failure_reason(
    monkeypatch, app_and_bus, async_client, reason,
):
    """Every Literal value from ClaimGroundingCheckFailedPayload.reason
    must be a valid grounder output."""
    _, bus = app_and_bus
    inv = f"inv-reason-{reason}"
    await _seed_document_with_region(
        async_client, investigation_id=inv, document_id="d",
        region_id="r", text_excerpt="some text",
    )
    await bus.wait_for_handlers(timeout=5.0)

    register_provider(_StubGrounder(
        f'{{"grounded": false, "reason": "{reason}"}}'
    ))
    _patch_dispatch_config(monkeypatch, _grounder_config("stub-grounder"))

    await _post_challenge(
        async_client, investigation_id=inv, document_id="d",
        claim_id="c", claim_text="any claim", user_question="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    failed = [r for r in trajectory(inv) if r["action_type"] == "claim.grounding_check_failed"]
    assert failed and Event.model_validate(failed[0]).payload.reason == reason


# ---------------------------------------------------------------------------
# 3. Hallucinated chunk_id → ambiguous failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grounder_hallucinated_chunk_id_becomes_ambiguous_failure(
    monkeypatch, app_and_bus, async_client
):
    """If the grounder claims grounded=true but cites a chunk_id NOT in
    the search results, the handler treats it as ambiguous failure
    (defends against confabulated id citations)."""
    _, bus = app_and_bus
    inv = "inv-hallucinated"
    doc = "doc-H"
    await _seed_document_with_region(
        async_client, investigation_id=inv, document_id=doc,
        region_id="r-h-1", text_excerpt="some real chunk text",
    )
    await bus.wait_for_handlers(timeout=5.0)

    register_provider(_StubGrounder(
        '{"grounded": true, "located_chunk_id": "chunk-MADEUP-DOES-NOT-EXIST", "confidence": 0.95}'
    ))
    _patch_dispatch_config(monkeypatch, _grounder_config("stub-grounder"))

    await _post_challenge(
        async_client, investigation_id=inv, document_id=doc,
        claim_id="c", claim_text="any claim", user_question="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory(inv)
    failed = [r for r in rows if r["action_type"] == "claim.grounding_check_failed"]
    passed = [r for r in rows if r["action_type"] == "claim.grounding_check_passed"]
    assert len(failed) == 1
    assert not passed
    assert Event.model_validate(failed[0]).payload.reason == "ambiguous"


# ---------------------------------------------------------------------------
# 4. Provider unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grounder_no_provider_emits_fallback_failed(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-noprov"
    await _seed_document_with_region(
        async_client, investigation_id=inv, document_id="d",
        region_id="r", text_excerpt="some text",
    )
    await bus.wait_for_handlers(timeout=5.0)

    # Note: NO register_provider call.
    _patch_dispatch_config(monkeypatch, _grounder_config("not-registered"))

    await _post_challenge(
        async_client, investigation_id=inv, document_id="d",
        claim_id="c", claim_text="any claim", user_question="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    failed = [
        r for r in trajectory(inv)
        if r["action_type"] == "claim.grounding_check_failed"
    ]
    assert failed
    ev = Event.model_validate(failed[0])
    assert ev.policy_id == "grounding-fallback/no-provider"
    assert ev.payload.reason == "ambiguous"


@pytest.mark.asyncio
async def test_grounder_provider_raises_emits_fallback_failed(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-raise"
    await _seed_document_with_region(
        async_client, investigation_id=inv, document_id="d",
        region_id="r", text_excerpt="text",
    )
    await bus.wait_for_handlers(timeout=5.0)

    register_provider(_StubGrounder("never reached", raise_on_call=True))
    _patch_dispatch_config(monkeypatch, _grounder_config("stub-grounder"))

    await _post_challenge(
        async_client, investigation_id=inv, document_id="d",
        claim_id="c", claim_text="claim", user_question="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    failed = [r for r in trajectory(inv) if r["action_type"] == "claim.grounding_check_failed"]
    assert failed
    assert Event.model_validate(failed[0]).policy_id == "grounding-fallback/no-provider"


# ---------------------------------------------------------------------------
# 5. Malformed JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grounder_malformed_json_emits_single_ambiguous_failed(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-malformed"
    await _seed_document_with_region(
        async_client, investigation_id=inv, document_id="d",
        region_id="r", text_excerpt="text",
    )
    await bus.wait_for_handlers(timeout=5.0)

    register_provider(_StubGrounder("I cannot determine this — total prose response"))
    _patch_dispatch_config(monkeypatch, _grounder_config("stub-grounder"))

    await _post_challenge(
        async_client, investigation_id=inv, document_id="d",
        claim_id="c", claim_text="claim", user_question="?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    rows = trajectory(inv)
    failed = [r for r in rows if r["action_type"] == "claim.grounding_check_failed"]
    passed = [r for r in rows if r["action_type"] == "claim.grounding_check_passed"]
    assert len(failed) == 1
    assert not passed
    assert Event.model_validate(failed[0]).payload.reason == "ambiguous"


# ---------------------------------------------------------------------------
# 6. Pure-helper tests
# ---------------------------------------------------------------------------


def test_chunk_to_region_id_strips_chunk_prefix():
    assert _chunk_to_region_id("chunk-abc-123") == "r-abc-123"
    # Defensive: unprefixed input.
    assert _chunk_to_region_id("weird-id") == "r-weird-id"


def test_chunk_to_region_is_inverse_of_region_to_chunk():
    """The handler relies on this round-trip: the region_id the surface
    posts must equal the region_id the located result reports."""
    for rid in ("r-abc-1", "r-defgh-2", "r-0000-3"):
        assert _chunk_to_region_id(_region_to_chunk_id(rid)) == rid


def test_parse_grounder_response_extracts_clean_json():
    grounded, cid, conf, reason = _parse_grounder_response(
        '{"grounded": true, "located_chunk_id": "chunk-1", "confidence": 0.8}'
    )
    assert grounded is True
    assert cid == "chunk-1"
    assert conf == pytest.approx(0.8)
    assert reason is None


def test_parse_grounder_response_extracts_failed():
    grounded, cid, conf, reason = _parse_grounder_response(
        '{"grounded": false, "reason": "paraphrased_not_stated"}'
    )
    assert grounded is False
    assert cid is None
    assert conf == 0.0
    assert reason == "paraphrased_not_stated"


def test_parse_grounder_response_clamps_confidence_to_unit_range():
    _, _, conf, _ = _parse_grounder_response(
        '{"grounded": true, "located_chunk_id": "c", "confidence": 1.5}'
    )
    assert conf == 1.0
    _, _, conf2, _ = _parse_grounder_response(
        '{"grounded": true, "located_chunk_id": "c", "confidence": -0.1}'
    )
    assert conf2 == 0.0


def test_parse_grounder_response_defaults_to_ambiguous_on_garbage():
    assert _parse_grounder_response("not json") == (False, None, 0.0, "ambiguous")
    assert _parse_grounder_response("") == (False, None, 0.0, "ambiguous")


def test_parse_grounder_response_rejects_unknown_reason():
    """If the model returns a non-Literal reason, we coerce to
    ambiguous rather than letting it through and failing the Pydantic
    validator downstream."""
    grounded, _, _, reason = _parse_grounder_response(
        '{"grounded": false, "reason": "i_made_this_up"}'
    )
    assert grounded is False
    assert reason == "ambiguous"
