"""Tests for the parameter_extractor bridge (Sprint 7 day 2).

Coverage:

1. Happy path — Delivered carries both raw parameters AND derived
   constraints; constraint kinds match the parameter shapes.
2. Provider unavailable → fallback Delivered with both lists empty +
   ``parameter-extractor-fallback/no-provider`` policy_id.
3. Parse failure → fallback Delivered, dispatch policy_id preserved.
4. Mixed parameter shapes (scalar + range + categorical + qualitative)
   produce the right mix of constraint kinds in one Delivered event.
5. Scalar without unit gets parsed BUT the converter drops it — the
   payload's parameters list contains it, constraints list does not.
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
    ParameterExtractDeliveredPayload,
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


class _StubParameterExtractor:
    name = "stub-pe"

    def __init__(self, text: str, *, raise_on_call: bool = False):
        self._text = text
        self._raise = raise_on_call

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        if self._raise:
            raise ProviderError(
                "stub failure", provider=self.name, model=model, latency_ms=0,
            )
        return RawProviderResponse(
            text=self._text,
            raw_usage={"input_tokens": 100, "output_tokens": 80},
            finish_reason="end_turn",
            latency_ms=5,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _pe_config(provider_name: str) -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    flash = TierConfig(
        name="flash", provider=provider_name, model="stub-flash-model",
        max_tokens=4096, temperature=0.0, context_budget_tokens=32_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"parameter_extractor": "flash"},
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


def _evidence_block(*chunk_ids: str) -> str:
    ids = list(chunk_ids) or ["chunk-1", "chunk-2"]
    return json.dumps([
        {
            "subquestion_id": "sq-1",
            "supporting_claims": [
                {
                    "claim": "synthetic evidence",
                    "chunk_ids": ids,
                },
            ],
        },
    ])


async def _post_request(ac, *, investigation_id, evidence_block=None):
    payload = {
        "action_type": "parameter_extract.requested",
        "evidence_block": evidence_block or _evidence_block(),
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


def _scalar_param() -> dict:
    return {
        "semantic_anchor": "training_compute",
        "metric_value": {"value_type": "scalar", "value": 1e25, "unit": "FLOP"},
        "qualitative_descriptor": None,
        "evidence_status": "observed",
        "source_chunk_ids": ["chunk-1"],
        "constraint_strictness": "hard",
    }


def _qual_param() -> dict:
    return {
        "semantic_anchor": "regulatory_uncertainty",
        "metric_value": {"value_type": "null"},
        "qualitative_descriptor": "Pending rulemaking",
        "evidence_status": "imputed",
        "source_chunk_ids": ["chunk-2"],
        "constraint_strictness": "soft",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_emits_delivered_with_parameters_and_constraints(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-pe-happy"
    response = {"parameters": [_scalar_param(), _qual_param()]}
    register_provider(_StubParameterExtractor(json.dumps(response)))
    _patch_dispatch_config(monkeypatch, _pe_config("stub-pe"))

    await _post_request(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.PARAMETER_EXTRACT_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    assert isinstance(p, ParameterExtractDeliveredPayload)
    assert len(p.parameters) == 2
    assert len(p.constraints) == 2  # scalar with unit + qualitative
    kinds = {c.kind for c in p.constraints}
    assert kinds == {"numeric_range", "must_attribute"}
    assert e.role == "parameter_extractor"
    assert e.policy_id == "stub-pe/stub-flash-model"


@pytest.mark.asyncio
async def test_provider_unavailable_falls_back(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-pe-noprov"
    _patch_dispatch_config(monkeypatch, _pe_config("stub-pe"))

    await _post_request(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.PARAMETER_EXTRACT_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    assert p.parameters == []
    assert p.constraints == []
    assert e.policy_id == "parameter-extractor-fallback/no-provider"


@pytest.mark.asyncio
async def test_parse_failure_falls_back_preserving_dispatch_policy_id(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-pe-bad"
    register_provider(_StubParameterExtractor("not even close to JSON"))
    _patch_dispatch_config(monkeypatch, _pe_config("stub-pe"))

    await _post_request(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.PARAMETER_EXTRACT_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    assert p.parameters == []
    assert p.constraints == []
    # Dispatch succeeded — parse failed. Provider stamp preserved.
    assert e.policy_id == "stub-pe/stub-flash-model"


@pytest.mark.asyncio
async def test_mixed_shapes_produce_mixed_constraint_kinds(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-pe-mixed"

    range_param = _scalar_param()
    range_param["metric_value"] = {
        "value_type": "range", "value": [10.0, 20.0], "unit": "%",
    }
    range_param["semantic_anchor"] = "gross_margin"

    cat_param = _scalar_param()
    cat_param["metric_value"] = {
        "value_type": "categorical", "value": ["us", "canada"],
    }
    cat_param["semantic_anchor"] = "geography"

    response = {
        "parameters": [
            _scalar_param(),  # numeric_range (degenerate)
            range_param,       # numeric_range
            cat_param,         # must_include_term x2
            _qual_param(),     # must_attribute
        ],
    }
    register_provider(_StubParameterExtractor(json.dumps(response)))
    _patch_dispatch_config(monkeypatch, _pe_config("stub-pe"))

    await _post_request(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = Event.model_validate(
        next(r for r in trajectory(inv)
             if r["action_type"] == ActionType.PARAMETER_EXTRACT_DELIVERED.value),
    )
    constraints = delivered.payload.constraints
    # scalar(numeric_range) + range(numeric_range) + 2x cat + 1x qual = 5
    assert len(constraints) == 5
    by_kind: dict[str, int] = {}
    for c in constraints:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    assert by_kind == {
        "numeric_range": 2,
        "must_include_term": 2,
        "must_attribute": 1,
    }


@pytest.mark.asyncio
async def test_scalar_without_unit_in_parameters_but_not_constraints(
    monkeypatch, app_and_bus, async_client,
):
    """Parser accepts a scalar with unit absent; converter drops it."""
    _, bus = app_and_bus
    inv = "inv-pe-noun"

    unitless = _scalar_param()
    unitless["metric_value"] = {"value_type": "scalar", "value": 100.0}
    # The payload's parameter still shows up; constraint does not.

    response = {"parameters": [unitless]}
    register_provider(_StubParameterExtractor(json.dumps(response)))
    _patch_dispatch_config(monkeypatch, _pe_config("stub-pe"))

    await _post_request(async_client, investigation_id=inv)
    await bus.wait_for_handlers(timeout=5.0)

    delivered = Event.model_validate(
        next(r for r in trajectory(inv)
             if r["action_type"] == ActionType.PARAMETER_EXTRACT_DELIVERED.value),
    )
    p = delivered.payload
    assert len(p.parameters) == 1
    assert p.parameters[0].metric_value.unit is None
    assert p.constraints == []  # converter dropped it
