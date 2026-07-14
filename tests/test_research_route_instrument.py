"""Cycle 591 server-owned route preview and launch proof."""

from __future__ import annotations

import httpx
import pytest

from interfaces.research.api import EventBroadcaster, create_app
from substrate.dispatch.research_route import route_choices
from substrate.event_log import trajectory


@pytest.fixture
async def route_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    app = create_app(
        broadcaster=EventBroadcaster(),
        cors_origins=[],
        register_providers=False,
        # These contract tests assert the start event, not the nine-phase
        # orchestrator. Keeping handlers off prevents a successful POST from
        # making a real provider call in developer environments with keys.
        register_wrestling=False,
    )
    app.state.registered_providers = {"zai", "zai_reasoning"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.test_app = app  # type: ignore[attr-defined]
        yield client


@pytest.mark.asyncio
async def test_preview_is_closed_safe_and_cost_unknown(route_client):
    response = await route_client.post(
        "/research/routes/preview", json={"question": "Which thesis survives?"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["choice_id"] for row in body["candidates"]} == {
        row.choice_id for row in route_choices()
    }
    assert all(row["ready"] for row in body["candidates"])
    assert body["budget"]["authority"] == "advisory"
    assert body["budget"]["projected_cost_usd"] is None
    assert body["budget"]["would_exceed_budget"] is None
    serialized = response.text.lower()
    assert '"provider"' not in serialized
    assert "api_key" not in serialized


@pytest.mark.asyncio
async def test_launch_reresolves_and_persists_safe_provenance(route_client):
    question = "Which thesis survives the evidence?"
    preview = (await route_client.post(
        "/research/routes/preview", json={"question": question}
    )).json()
    deep = next(row for row in preview["candidates"] if row["display_name"] == "Deep lens")
    response = await route_client.post(
        "/investigations",
        json={
            "question": question,
            "investigation_id": "inv-route-proof",
            "route_choice_id": deep["choice_id"],
            "route_prompt_fingerprint": preview["prompt_fingerprint"],
            "route_policy_version": preview["policy_version"],
            "route_configuration_fingerprint": deep["configuration_fingerprint"],
        },
    )
    assert response.status_code == 202, response.text
    start = next(
        row for row in trajectory("inv-route-proof")
        if row["action_type"] == "investigation.start_requested"
    )["payload"]
    assert start["research_tier"] == "deep"
    assert start["research_route_choice_id"] == deep["choice_id"]
    assert start["research_route_prompt_fingerprint"] == preview["prompt_fingerprint"]
    assert "provider" not in start and "model" not in start


@pytest.mark.asyncio
async def test_launch_rejects_dual_input_and_prompt_replay(route_client):
    question = "Question used for the preview"
    preview = (await route_client.post(
        "/research/routes/preview", json={"question": question}
    )).json()
    choice = preview["candidates"][0]
    proof = {
        "route_choice_id": choice["choice_id"],
        "route_prompt_fingerprint": preview["prompt_fingerprint"],
        "route_policy_version": preview["policy_version"],
        "route_configuration_fingerprint": choice["configuration_fingerprint"],
    }
    dual = await route_client.post(
        "/investigations", json={"question": question, "research_tier": "fast", **proof}
    )
    assert dual.status_code == 422
    replay = await route_client.post(
        "/investigations", json={"question": "A changed question", **proof}
    )
    assert replay.status_code == 409


@pytest.mark.asyncio
async def test_launch_rechecks_readiness_and_emits_nothing(route_client):
    question = "Which evidence changes the conclusion?"
    preview = (await route_client.post(
        "/research/routes/preview", json={"question": question}
    )).json()
    choice = preview["candidates"][0]
    # Simulate the selected primary disappearing after preview. An explicit
    # reviewed route must not be disguised by the dispatch fallback chain.
    route_client.test_app.state.registered_providers = set()
    response = await route_client.post(
        "/investigations",
        json={
            "question": question,
            "investigation_id": "inv-route-unavailable",
            "route_choice_id": choice["choice_id"],
            "route_prompt_fingerprint": preview["prompt_fingerprint"],
            "route_policy_version": preview["policy_version"],
            "route_configuration_fingerprint": choice["configuration_fingerprint"],
        },
    )
    assert response.status_code == 409
    assert trajectory("inv-route-unavailable") == []


@pytest.mark.asyncio
async def test_launch_rejects_partial_and_stale_route_proofs(route_client):
    partial = await route_client.post(
        "/investigations",
        json={"question": "A valid question", "route_choice_id": "rr_partial"},
    )
    assert partial.status_code == 422

    question = "A second valid question"
    preview = (await route_client.post(
        "/research/routes/preview", json={"question": question}
    )).json()
    choice = preview["candidates"][0]
    stale = await route_client.post(
        "/investigations",
        json={
            "question": question,
            "route_choice_id": choice["choice_id"],
            "route_prompt_fingerprint": preview["prompt_fingerprint"],
            "route_policy_version": "research-route.stale",
            "route_configuration_fingerprint": choice["configuration_fingerprint"],
        },
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_legacy_tier_still_launches(route_client):
    response = await route_client.post(
        "/investigations",
        json={"question": "Legacy caller question", "research_tier": "fast"},
    )
    assert response.status_code == 202
