"""Cycle 590: persisted depth steers upstream bridges, never synthesis."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import (  # noqa: E402
    connector,
    decomposer,
    evidence_retriever,
    parameter_extractor,
    research_tier_routing,
    synthesizer,
)


@pytest.mark.parametrize(
    ("recorded", "expected"),
    [
        ("fast", ("zai", "glm-5.2")),
        ("deep", ("zai_reasoning", "glm-5.2")),
        (None, (None, None)),
        ("legacy-provider-name", (None, None)),
    ],
)
def test_persisted_tier_is_the_only_source_of_override(monkeypatch, recorded, expected):
    payload = {} if recorded is None else {"research_tier": recorded}
    monkeypatch.setattr(
        research_tier_routing,
        "trajectory",
        lambda _id: [
            {"action_type": "question.identified", "payload": {"research_tier": "fast"}},
            {"action_type": "investigation.start_requested", "payload": payload},
            {"action_type": "investigation.start_requested", "payload": {"research_tier": "fast"}},
        ],
    )
    research_tier_routing.clear_research_tier_override_cache()
    assert research_tier_routing.persisted_research_tier_override("inv") == expected


def test_persisted_tier_lookup_is_cached_per_investigation(monkeypatch):
    calls = 0

    def fake_trajectory(_id):
        nonlocal calls
        calls += 1
        return [
            {
                "action_type": "investigation.start_requested",
                "payload": {"research_tier": "deep"},
            },
        ]

    monkeypatch.setattr(research_tier_routing, "trajectory", fake_trajectory)
    research_tier_routing.clear_research_tier_override_cache()
    assert research_tier_routing.persisted_research_tier_override("inv-cache") == (
        "zai_reasoning",
        "glm-5.2",
    )
    assert research_tier_routing.persisted_research_tier_override("inv-cache") == (
        "zai_reasoning",
        "glm-5.2",
    )
    assert calls == 1


def test_transient_missing_start_is_not_negative_cached(monkeypatch):
    rows = []
    monkeypatch.setattr(research_tier_routing, "trajectory", lambda _id: list(rows))
    research_tier_routing.clear_research_tier_override_cache()
    assert research_tier_routing.persisted_research_tier_override("inv-late") == (
        None,
        None,
    )
    rows.append(
        {
            "action_type": "investigation.start_requested",
            "payload": {"research_tier": "fast"},
        },
    )
    assert research_tier_routing.persisted_research_tier_override("inv-late") == (
        "zai",
        "glm-5.2",
    )


@pytest.mark.parametrize(
    ("module", "call"),
    [
        (decomposer, lambda m, e: m._dispatch_and_parse("p", e, label="initial")),
        (
            evidence_retriever,
            lambda m, e: m._dispatch_and_parse("p", e, sub_question="q"),
        ),
        (parameter_extractor, lambda m, e: m._dispatch_and_parse("p", e)),
        (connector, lambda m, e: m._dispatch_and_parse("p", e)),
    ],
)
def test_all_four_upstream_bridges_pass_only_server_resolved_override(
    monkeypatch, module, call,
):
    captured = {}
    monkeypatch.setattr(
        module,
        "persisted_research_tier_override",
        lambda _id: ("server-provider", "server-model"),
    )

    def fake_dispatch(*args, **kwargs):
        captured.update(kwargs)
        raise KeyError("stop after routing assertion")

    monkeypatch.setattr(module, "dispatch", fake_dispatch)
    event = SimpleNamespace(investigation_id="inv", event_id="parent")
    call(module, event)
    assert captured["provider_override"] == "server-provider"
    assert captured["model_override"] == "server-model"


def test_synthesizer_stays_pinned_for_every_persisted_tier(monkeypatch):
    for tier in ("fast", "deep"):
        monkeypatch.setattr(
            synthesizer,
            "trajectory",
            lambda _id, tier=tier: [
                {
                    "action_type": "investigation.start_requested",
                    "payload": {"research_tier": tier},
                },
            ],
        )
        assert synthesizer._research_tier_override("inv") == (None, None)
