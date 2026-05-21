"""WebSocket end-to-end tests for the v4/v5 typed payloads.

Confirms the new payloads (RLM bridge, quality gate, cross-graph
citation, payout, DP preference, skill rule promotion) flow through
the typed event POST → broadcaster → WS subscriber path cleanly
and arrive at the subscriber with their discriminator preserved.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app(register_wrestling=False))


def _post_typed(client: TestClient, payload: dict, *, inv_id: str = "inv-WS"):
    return client.post(
        "/events/typed",
        json={"investigation_id": inv_id, "payload": payload},
    )


# ── RLM bridge ──────────────────────────────────────────────────────


def test_ws_receives_rlm_bridge_event(client):
    with client.websocket_connect("/ws/events?investigation_id=inv-WS") as ws:
        resp = _post_typed(client, {
            "action_type": "rlm.bridge.decided",
            "document_id_ref": "doc-1",
            "estimated_tokens": 128_000,
            "threshold_tokens": 64_000,
            "above_threshold": True,
            "ratified": False,
            "escalated": False,
            "reason": "deferred_pending_ratification",
        })
        assert resp.status_code == 201
        frame = ws.receive_json()
        assert frame["payload"]["action_type"] == "rlm.bridge.decided"
        assert frame["payload"]["reason"] == "deferred_pending_ratification"


# ── Quality gate ──────────────────────────────────────────────────


def test_ws_receives_quality_gate_event(client):
    with client.websocket_connect("/ws/events?investigation_id=inv-WS") as ws:
        resp = _post_typed(client, {
            "action_type": "quality_gate.evaluated",
            "target_kind": "notebook",
            "target_id": "nb-42",
            "accepted": True,
            "verification_passed": True,
            "voice_style_passed": True,
            "source_tier_passed": True,
            "em_dash_density": 0.5,
            "padding_phrase_count": 0,
            "sector_vocab_overlap": 0.7,
            "min_tier_cited": 1,
            "pct_tier_1_or_2": 1.0,
            "reasons": [],
        })
        assert resp.status_code == 201
        frame = ws.receive_json()
        assert frame["payload"]["action_type"] == "quality_gate.evaluated"
        assert frame["payload"]["target_id"] == "nb-42"


# ── Cross-graph citation ──────────────────────────────────────────


def test_ws_receives_cross_graph_citation_event(client):
    with client.websocket_connect("/ws/events?investigation_id=inv-WS") as ws:
        resp = _post_typed(client, {
            "action_type": "cross_graph.citation.recorded",
            "reference_id": "xref-1",
            "referencing_user_id": "user-B",
            "referencing_investigation_id": "inv-WS",
            "referenced_user_id": "user-A",
            "referenced_note_id": "note-1",
        })
        assert resp.status_code == 201
        frame = ws.receive_json()
        assert frame["payload"]["action_type"] == "cross_graph.citation.recorded"
        assert frame["payload"]["referenced_user_id"] == "user-A"


# ── Rev share ─────────────────────────────────────────────────────


def test_ws_receives_rev_share_event(client):
    with client.websocket_connect("/ws/events?investigation_id=inv-WS") as ws:
        resp = _post_typed(client, {
            "action_type": "rev_share.decided",
            "decision_id": "rs-1",
            "impression_id": "imp-1",
            "kind": "creator",
            "recipient_ref": "user-X",
            "amount_usd_cents": 700,
            "document_id_ref": "doc-A",
            "requires_escrow": False,
            "capped_to_daily_limit": False,
        })
        assert resp.status_code == 201
        frame = ws.receive_json()
        assert frame["payload"]["action_type"] == "rev_share.decided"
        assert frame["payload"]["amount_usd_cents"] == 700


# ── DP preference observation ──────────────────────────────────────


def test_ws_receives_preference_observation_event(client):
    with client.websocket_connect("/ws/events?investigation_id=inv-WS") as ws:
        resp = _post_typed(client, {
            "action_type": "preference.observation.recorded",
            "category": "dispatch_followed_suggestion",
            "noisy_value": True,
            "per_obs_epsilon": 0.01,
            "cumulative_epsilon_spent": 0.05,
            "category_budget": 4.0,
            "user_id": "__operator__",
        })
        assert resp.status_code == 201
        frame = ws.receive_json()
        assert frame["payload"]["action_type"] == "preference.observation.recorded"
        assert frame["payload"]["category"] == "dispatch_followed_suggestion"


# ── Skill rule promotion (v5) ──────────────────────────────────────


def test_ws_receives_skill_rule_promoted_event(client):
    with client.websocket_connect("/ws/events?investigation_id=inv-WS") as ws:
        resp = _post_typed(client, {
            "action_type": "skill_rule.promoted",
            "rule_id": "skill-abc",
            "rule_text": "Lukin lab papers are tier 1",
            "rule_kind": "source_tier_rule",
            "domain": "quantum",
            "distinct_user_count": 4,
            "total_epsilon_consumed": 0.05,
            "confidence": "moderate",
            "contributing_user_ids": ["u1", "u2", "u3", "u4"],
        })
        assert resp.status_code == 201
        frame = ws.receive_json()
        assert frame["payload"]["action_type"] == "skill_rule.promoted"
        assert frame["payload"]["confidence"] == "moderate"


# ── Cross-payload investigation filter ─────────────────────────────


def test_ws_filter_holds_across_v4_v5_payloads(client):
    """A WS subscriber to investigation inv-X must not receive a v4/v5
    event emitted under inv-Y."""
    with client.websocket_connect("/ws/events?investigation_id=inv-X") as ws:
        # Emit one for inv-Y (filtered out) and one for inv-X.
        _post_typed(client, {
            "action_type": "quality_gate.evaluated",
            "target_kind": "notebook",
            "target_id": "nb-Y",
            "accepted": True,
            "verification_passed": True,
            "voice_style_passed": True,
            "source_tier_passed": True,
            "em_dash_density": 0.0,
            "padding_phrase_count": 0,
            "sector_vocab_overlap": 1.0,
            "min_tier_cited": 1,
            "pct_tier_1_or_2": 1.0,
            "reasons": [],
        }, inv_id="inv-Y")
        target = _post_typed(client, {
            "action_type": "quality_gate.evaluated",
            "target_kind": "notebook",
            "target_id": "nb-X",
            "accepted": True,
            "verification_passed": True,
            "voice_style_passed": True,
            "source_tier_passed": True,
            "em_dash_density": 0.0,
            "padding_phrase_count": 0,
            "sector_vocab_overlap": 1.0,
            "min_tier_cited": 1,
            "pct_tier_1_or_2": 1.0,
            "reasons": [],
        }, inv_id="inv-X")
        target_id = target.json()["event_id"]

        frame = ws.receive_json()
        # The first frame must be the inv-X event — inv-Y was filtered.
        assert frame["event_id"] == target_id
        assert frame["investigation_id"] == "inv-X"
