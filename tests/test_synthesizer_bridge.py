"""Tests for the synthesizer bridge (Sprint 7 day 5).

The synthesizer bridge is unique in Loop 1: it's the only bridge
that drives the Sprint 7 day 3 constraint loop. These tests cover
the loop-wiring carefully.

Coverage:

1. Happy path with NO constraints — single dispatch, single_pass
   terminus, Delivered carries the thesis verbatim.
2. With constraints satisfied first-try — single_pass, no revision.
3. With constraints failing first-try, fixed on revision —
   passed (iteration 2), Delivered carries the REVISED thesis.
4. With constraints unfixable — max_iterations_reached.
5. First-dispatch provider failure → fallback Delivered with
   ``insufficient_evidence``, no loop ran.
6. First-dispatch parse failure → fallback Delivered, dispatch
   policy_id preserved.
7. Constraint loop status surfaces on the Delivered payload's
   ``constraint_loop_status`` + ``constraint_loop_iterations``.
"""

from __future__ import annotations

import json
import os
import sys

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
    ActionType,
    Event,
    SynthesizeDeliveredPayload,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


class _StubSynthesizer:
    """Provider returning a queue of canned text responses (one per
    call). Each dispatch consumes the next item; if exhausted the
    last item is returned indefinitely (so a loop running past the
    queue doesn't crash — it just gets the same answer back, which
    is what 'no progress' looks like in production)."""

    name = "stub-synthesizer"

    def __init__(self, texts: list[str], *, raise_on_call: bool = False):
        self._texts = texts
        self._raise = raise_on_call
        self.call_count = 0

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        if self._raise:
            raise ProviderError(
                "stub failure", provider=self.name, model=model, latency_ms=0,
            )
        idx = min(self.call_count, len(self._texts) - 1)
        text = self._texts[idx]
        self.call_count += 1
        return RawProviderResponse(
            text=text,
            raw_usage={"input_tokens": 200, "output_tokens": 200},
            finish_reason="end_turn", latency_ms=10,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _synth_config(provider_name: str) -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    synthesis = TierConfig(
        name="synthesis", provider=provider_name, model="stub-synth-model",
        max_tokens=8192, temperature=0.2, context_budget_tokens=256_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": synthesis},
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


async def _post_synthesize(
    ac, *, investigation_id, constraints=None,
):
    payload = {
        "action_type": "synthesize.requested",
        "question": "Is X causally linked to Y?",
        "decomposition_block": "[decomposition]",
        "evidence_block": json.dumps([
            {
                "supporting_claims": [
                    {
                        "claim": "X correlates with Y in primary evidence.",
                        "chunk_ids": ["chunk-1"],
                    },
                ],
            },
        ]),
        "parameters_block": "[parameters]",
        "substrate_block": json.dumps({
            "paths": [
                {
                    "path_node_ids": ["n-1", "n-2"],
                    "path_edge_ids": ["e-1"],
                },
            ],
        }),
        "constraints": constraints or [],
    }
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "payload": payload,
            "role": "orchestrator",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _good_thesis(*, attributed: bool = True, summary: str = "X is causally linked to Y.") -> dict:
    """A well-formed thesis. ``attributed=False`` removes
    supporting_chunk_ids on the only component, which the
    ``must_attribute`` constraint will catch."""
    chunks = ["chunk-1"] if attributed else []
    return {
        "thesis_summary": summary,
        "implicit_recommendation": "proceed",
        "thesis_components": [{
            "claim": "X correlates with Y in primary evidence.",
            "confidence": "moderate",
            "confidence_basis": "one filing + one analyst report",
            "supporting_chunk_ids": chunks,
            "supporting_path_indices": [0],
            "effective_source_tier": 2,
            "hedging_required": False,
        }],
        "falsification_conditions": [{
            "condition": "Correlation breaks below 0.5",
            "specific_observable": "Q4 dataset r-value",
        }],
        "execution_risks": [{
            "risk": "Sample size insufficient",
            "severity_if_manifested": "moderate",
        }],
        "constraint_compliance": {
            "hard_constraints_satisfied": True,
            "soft_constraints_violated": [],
            "violations_justified": [],
        },
        "reasoning_paths_used": [{
            "path_node_ids": ["n-1", "n-2"],
            "path_edge_ids": ["e-1"],
            "support_summary": "Path traces from X's measurement to Y's outcome.",
        }],
        "conviction_level": 0.7,
    }


def _must_attribute_spec(*, strictness: str = "hard") -> dict:
    return {
        "constraint_id": "c-attr",
        "strictness": strictness,
        "kind": "must_attribute",
        "description": "every claim must cite at least one chunk",
        "config": {},
    }


# ---------------------------------------------------------------------------
# 1. Happy path, no constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_constraints_single_pass(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-synth-noc"
    register_provider(_StubSynthesizer([json.dumps(_good_thesis())]))
    _patch_dispatch_config(monkeypatch, _synth_config("stub-synthesizer"))

    await _post_synthesize(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.SYNTHESIZE_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    assert isinstance(p, SynthesizeDeliveredPayload)
    assert p.implicit_recommendation == "proceed"
    assert p.constraint_loop_status == "single_pass"
    assert p.constraint_loop_iterations == 1
    assert len(p.thesis_components) == 1
    assert p.thesis_summary == "X is causally linked to Y."
    assert e.role == "synthesizer"


# ---------------------------------------------------------------------------
# 2. With constraints — first pass satisfies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_constraints_satisfied_first_try(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-synth-clean"
    # Attributed thesis → must_attribute constraint passes immediately.
    register_provider(_StubSynthesizer([json.dumps(_good_thesis(attributed=True))]))
    _patch_dispatch_config(monkeypatch, _synth_config("stub-synthesizer"))

    await _post_synthesize(
        async_client, investigation_id=inv,
        constraints=[_must_attribute_spec()],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.SYNTHESIZE_DELIVERED.value
    ]
    assert len(delivered) == 1
    p = Event.model_validate(delivered[0]).payload
    # Loop ran one iteration with constraints → single_pass.
    assert p.constraint_loop_status == "single_pass"
    assert p.constraint_loop_iterations == 1


# ---------------------------------------------------------------------------
# 3. With constraints — fails first, fixed on revision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_constraint_failure_triggers_revision_then_passes(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-synth-revise"
    # First dispatch returns un-attributed thesis (must_attribute will
    # fail). Second dispatch (loop's re-invoke) returns attributed
    # thesis with a different summary so we can tell the FINAL Delivered
    # carried the REVISED output, not the first one.
    register_provider(_StubSynthesizer([
        json.dumps(_good_thesis(attributed=False, summary="FIRST_PASS")),
        json.dumps(_good_thesis(attributed=True, summary="REVISED_PASS")),
    ]))
    _patch_dispatch_config(monkeypatch, _synth_config("stub-synthesizer"))

    await _post_synthesize(
        async_client, investigation_id=inv,
        constraints=[_must_attribute_spec()],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.SYNTHESIZE_DELIVERED.value
    ]
    assert len(delivered) == 1
    p = Event.model_validate(delivered[0]).payload
    assert p.constraint_loop_status == "passed"
    assert p.constraint_loop_iterations == 2
    # Delivered carries the REVISED thesis, not the first.
    assert p.thesis_summary == "REVISED_PASS"

    # Loop machinery emitted its own events.
    violations = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONSTRAINT_VIOLATION_FOUND.value
    ]
    assert len(violations) >= 1
    revisions = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONSTRAINT_REVISION_TRIGGERED.value
    ]
    assert len(revisions) == 1
    resolved = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value
    ]
    assert len(resolved) == 1


# ---------------------------------------------------------------------------
# 4. Unfixable → max_iterations_reached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_constraint_unfixable_max_iterations(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-synth-maxiter"
    # Every dispatch returns an un-attributed thesis → constraint
    # never clears → max_iterations_reached.
    register_provider(_StubSynthesizer([
        json.dumps(_good_thesis(attributed=False, summary=f"PASS_{i}"))
        for i in range(5)
    ]))
    _patch_dispatch_config(monkeypatch, _synth_config("stub-synthesizer"))

    await _post_synthesize(
        async_client, investigation_id=inv,
        constraints=[_must_attribute_spec()],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.SYNTHESIZE_DELIVERED.value
    ]
    assert len(delivered) == 1
    p = Event.model_validate(delivered[0]).payload
    assert p.constraint_loop_status == "max_iterations_reached"
    assert p.constraint_loop_iterations == 3  # CONSTRAINT_MAX_ITERATIONS


# ---------------------------------------------------------------------------
# 5. First-dispatch provider failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_dispatch_provider_unavailable_fallback(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-synth-noprov"
    _patch_dispatch_config(monkeypatch, _synth_config("stub-synthesizer"))

    await _post_synthesize(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.SYNTHESIZE_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    assert p.implicit_recommendation == "insufficient_evidence"
    assert p.thesis_components == []
    assert p.constraint_compliance.hard_constraints_satisfied is False
    assert e.policy_id == "synthesizer-fallback/no-provider"
    # No constraint loop ran.
    resolved = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value
    ]
    assert resolved == []


# ---------------------------------------------------------------------------
# 6. First-dispatch parse failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_dispatch_parse_failure_fallback(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-synth-badparse"
    register_provider(_StubSynthesizer(["definitely not JSON"]))
    _patch_dispatch_config(monkeypatch, _synth_config("stub-synthesizer"))

    await _post_synthesize(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.SYNTHESIZE_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    assert p.implicit_recommendation == "insufficient_evidence"
    assert p.thesis_components == []
    # Dispatch succeeded — parse failed; policy_id reflects the model.
    assert e.policy_id == "stub-synthesizer/stub-synth-model"


# ---------------------------------------------------------------------------
# 7. Loop status surfaced on Delivered (single source of truth)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_status_and_iterations_on_delivered(
    monkeypatch, app_and_bus, async_client,
):
    """Downstream consumers should NOT need to read both
    SYNTHESIZE_DELIVERED and CONSTRAINT_LOOP_RESOLVED to know how the
    loop terminated. The Delivered payload exposes the verdict."""
    _, bus = app_and_bus
    inv = "inv-synth-loop-surface"
    register_provider(_StubSynthesizer([
        json.dumps(_good_thesis(attributed=False)),
        json.dumps(_good_thesis(attributed=True)),
    ]))
    _patch_dispatch_config(monkeypatch, _synth_config("stub-synthesizer"))

    await _post_synthesize(
        async_client, investigation_id=inv,
        constraints=[_must_attribute_spec()],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered_row = next(
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.SYNTHESIZE_DELIVERED.value
    )
    p = Event.model_validate(delivered_row).payload

    # Compare against the loop's resolved event — they MUST agree.
    resolved_row = next(
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value
    )
    resolved_p = Event.model_validate(resolved_row).payload
    assert p.constraint_loop_status == resolved_p.final_status
    assert p.constraint_loop_iterations == resolved_p.total_iterations
