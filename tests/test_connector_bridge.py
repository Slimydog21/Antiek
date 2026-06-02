"""Tests for the connector bridge (Sprint 7 day 4).

End-to-end: seed a small graph, POST connector.requested with seed
pairs + pre-resolved keyword mappings, assert Delivered carries the
traversed paths AND the role's NL renderings.

Coverage:

1. Happy path — bridge runs top_n_paths against the seeded graph,
   dispatches role with rendered blocks, Delivered carries both
   structured paths AND NL relationships.
2. Provider unavailable → fallback Delivered preserves the
   traversed paths so the operator sees what the graph could
   surface, but NL relationships stay empty + algorithm echoes
   what the bridge ran + policy stamped fallback.
3. Parse failure → fallback Delivered, dispatch policy_id preserved,
   paths from traversal preserved.
4. Empty seed_pairs → bridge skips traversal, paths are empty,
   role still dispatched (it confirms mappings even with no paths).
5. Graph layer raises (corrupt db_path) → empty paths, dispatch
   still happens, Delivered emits with empty paths block.
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
from runtime.db_lock import connect_write  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.graph import ensure_initialized, insert_edge, insert_node  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    ConnectorDeliveredPayload,
    Event,
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


class _StubConnector:
    name = "stub-connector"

    def __init__(self, text: str):
        self._text = text

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        return RawProviderResponse(
            text=self._text,
            raw_usage={"input_tokens": 100, "output_tokens": 80},
            finish_reason="end_turn", latency_ms=5,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _connector_config(provider_name: str) -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    pro = TierConfig(
        name="pro", provider=provider_name, model="stub-pro-model",
        max_tokens=4096, temperature=0.0, context_budget_tokens=128_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"connector": "pro"},
        tiers={"pro": pro},
    )


def _patch_dispatch_config(monkeypatch, config: DispatchConfig) -> None:
    import substrate.dispatch.router as router
    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: config),
    )


@pytest.fixture
def db_path(tmp_path) -> str:
    p = str(tmp_path / "graph.duckdb")
    ensure_initialized(p)
    return p


def _seed_two_node_path(db_path: str) -> tuple[str, str, str]:
    """Seed a minimal 2-node, 1-edge graph and return (src, tgt, edge)."""
    con = connect_write(db_path, purpose="test-seed")
    try:
        src = insert_node(
            con, canonical_label="TSMC", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-seed",
        )
        tgt = insert_node(
            con, canonical_label="ASML", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-seed",
        )
        eid = insert_edge(
            con, source_node_id=src, target_node_id=tgt,
            relation="sources_from", source_tier=1,
            extraction_confidence=0.95,
            graph_scope="cross_domain", investigation_id="inv-seed",
        )
    finally:
        con.close()
    return src, tgt, eid


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


async def _post_request(ac, *, investigation_id, seed_pairs, keyword_mappings=None):
    payload = {
        "action_type": "connector.requested",
        "keyword_mappings": keyword_mappings or [],
        "seed_pairs": seed_pairs,
        "algorithm": "top_n_shortest_paths",
        "max_paths_per_pair": 5,
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


def _good_response(*, with_paths: bool = True) -> dict:
    paths_list = [{
        "path_nodes": ["n-tsmc", "n-asml"],
        "node_labels": ["TSMC", "ASML"],
        "path_relations": ["sources_from"],
        "depth": 1,
        "avg_confidence": 0.95,
        "edge_ids": ["e-1"],
    }] if with_paths else []
    nl_list = [{
        "text": "TSMC sources EUV lithography systems from ASML.",
        "source_path_index": 0,
    }] if with_paths else []
    return {
        "keyword_mappings": [{
            "keyword": "TSMC", "matched_node_id": "n-tsmc",
            "matched_node_label": "TSMC", "matched_node_type": "entity",
            "similarity": 0.95, "low_confidence": False,
        }],
        "selected_algorithm": "top_n_shortest_paths",
        "algorithm_rationale": "Enumerating mechanisms.",
        "paths": paths_list,
        "natural_language_relationships": nl_list,
    }


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connector_happy_path(monkeypatch, app_and_bus, async_client, db_path):
    _, bus = app_and_bus
    inv = "inv-conn-happy"

    src, tgt, _ = _seed_two_node_path(db_path)

    register_provider(_StubConnector(json.dumps(_good_response())))
    _patch_dispatch_config(monkeypatch, _connector_config("stub-connector"))

    await _post_request(
        async_client, investigation_id=inv,
        seed_pairs=[{"source_node_id": src, "target_node_id": tgt}],
        keyword_mappings=[{
            "keyword": "TSMC",
            "matched_node_id": src,
            "matched_node_label": "TSMC",
            "matched_node_type": "entity",
            "similarity": 0.92,
            "low_confidence": False,
        }],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONNECTOR_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    assert isinstance(p, ConnectorDeliveredPayload)
    assert p.selected_algorithm == "top_n_shortest_paths"
    assert len(p.keyword_mappings) == 1
    assert len(p.paths) >= 1
    assert len(p.natural_language_relationships) >= 1
    assert e.role == "connector"
    assert e.policy_id == "stub-connector/stub-pro-model"


# ---------------------------------------------------------------------------
# 2. Provider unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_unavailable_preserves_traversed_paths(
    monkeypatch, app_and_bus, async_client, db_path,
):
    _, bus = app_and_bus
    inv = "inv-conn-noprov"
    src, tgt, _ = _seed_two_node_path(db_path)

    # No provider registered.
    _patch_dispatch_config(monkeypatch, _connector_config("stub-connector"))

    await _post_request(
        async_client, investigation_id=inv,
        seed_pairs=[{"source_node_id": src, "target_node_id": tgt}],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONNECTOR_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    # Bridge ran the traversal — paths preserved even without LLM.
    assert len(p.paths) >= 1
    # No NL renderings without the role.
    assert p.natural_language_relationships == []
    # Algorithm echoes the request (no role to correct).
    assert p.selected_algorithm == "top_n_shortest_paths"
    assert e.policy_id == "connector-fallback/no-provider"


# ---------------------------------------------------------------------------
# 3. Parse failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_failure_preserves_paths_and_dispatch_stamp(
    monkeypatch, app_and_bus, async_client, db_path,
):
    _, bus = app_and_bus
    inv = "inv-conn-badparse"
    src, tgt, _ = _seed_two_node_path(db_path)

    register_provider(_StubConnector("not parseable JSON at all"))
    _patch_dispatch_config(monkeypatch, _connector_config("stub-connector"))

    await _post_request(
        async_client, investigation_id=inv,
        seed_pairs=[{"source_node_id": src, "target_node_id": tgt}],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONNECTOR_DELIVERED.value
    ]
    assert len(delivered) == 1
    e = Event.model_validate(delivered[0])
    p = e.payload
    # Paths preserved from traversal even though LLM parse failed.
    assert len(p.paths) >= 1
    assert p.natural_language_relationships == []
    # Dispatch succeeded — the model failed. Policy reflects the model.
    assert e.policy_id == "stub-connector/stub-pro-model"


# ---------------------------------------------------------------------------
# 4. Empty seed_pairs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_seed_pairs_still_dispatches(
    monkeypatch, app_and_bus, async_client, db_path,
):
    """Even with zero seed pairs, the role still gets a chance to
    confirm any pre-resolved mappings the request supplied."""
    _, bus = app_and_bus
    inv = "inv-conn-empty"

    register_provider(_StubConnector(json.dumps(_good_response(with_paths=False))))
    _patch_dispatch_config(monkeypatch, _connector_config("stub-connector"))

    await _post_request(
        async_client, investigation_id=inv, seed_pairs=[],
        keyword_mappings=[{
            "keyword": "Quantum", "matched_node_id": "n-q",
            "matched_node_label": "Quantum", "matched_node_type": "concept",
            "similarity": 0.91, "low_confidence": False,
        }],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONNECTOR_DELIVERED.value
    ]
    assert len(delivered) == 1
    p = Event.model_validate(delivered[0]).payload
    assert p.paths == []
    assert p.natural_language_relationships == []
    # Mapping confirmation still landed.
    assert len(p.keyword_mappings) == 1


# ---------------------------------------------------------------------------
# 5. Disconnected graph (traversal returns no paths)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnected_seed_pair_produces_empty_paths(
    monkeypatch, app_and_bus, async_client, db_path,
):
    """Two isolated nodes with no edge between them → traversal
    returns []. Role dispatched anyway; Delivered carries empty
    paths."""
    _, bus = app_and_bus
    inv = "inv-conn-disc"

    # Seed two unconnected nodes (no edge between them).
    con = connect_write(db_path, purpose="test-disc")
    try:
        src = insert_node(
            con, canonical_label="Alpha", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-disc",
        )
        tgt = insert_node(
            con, canonical_label="Beta", node_type="entity",
            graph_scope="cross_domain", investigation_id="inv-disc",
        )
    finally:
        con.close()

    register_provider(_StubConnector(json.dumps(_good_response(with_paths=False))))
    _patch_dispatch_config(monkeypatch, _connector_config("stub-connector"))

    await _post_request(
        async_client, investigation_id=inv,
        seed_pairs=[{"source_node_id": src, "target_node_id": tgt}],
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.CONNECTOR_DELIVERED.value
    ]
    assert len(delivered) == 1
    p = Event.model_validate(delivered[0]).payload
    assert p.paths == []  # graph layer returned nothing
    # Role still emitted its (empty-paths) response shape.
