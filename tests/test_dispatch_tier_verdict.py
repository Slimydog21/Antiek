"""Dispatch tier-differentiation verdict analyzer (G5)."""

from __future__ import annotations

from datetime import datetime, timezone

from tools.dispatch_tier_verdict.analyzer import (
    PASS_RATE_GAP_THRESHOLD_PP,
    analyse_events,
    render_verdict_markdown,
)


def _ev(
    *,
    action: str,
    inv: str = "inv-1",
    ts: str = "2026-05-20T12:00:00Z",
    **payload,
) -> dict:
    return {
        "action_type": action,
        "investigation_id": inv,
        "created_at": ts,
        "payload": {"action_type": action, **payload},
    }


def _dispatch_synthesis(
    provider: str,
    model: str,
    *,
    inv: str = "inv-1",
    cost_usd: float = 0.01,
    ts: str = "2026-05-20T12:00:00Z",
) -> dict:
    return _ev(
        action="dispatch.call",
        inv=inv,
        ts=ts,
        tier="synthesis",
        provider=provider,
        model=model,
        target_role="synthesizer",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=cost_usd,
        latency_ms=200,
        prompt_hash="h",
    )


def _verify_score(score: float, *, inv: str = "inv-1", ts: str = "2026-05-20T12:01:00Z") -> dict:
    return _ev(
        action="rubric.scored",
        inv=inv,
        ts=ts,
        rubric_id="r-synth",
        final_score=score,
    )


# ── Analyzer ─────────────────────────────────────────────────────────


def test_empty_events_insufficient_data():
    v = analyse_events(events=[])
    assert v.decision == "insufficient_data"
    assert v.scores == []


def test_opus_only_traffic_insufficient_data():
    """When only one provider has run, no comparison possible."""
    events: list[dict] = []
    for i in range(15):
        inv = f"inv-{i}"
        events.append(_dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv=inv))
        events.append(_verify_score(0.8, inv=inv))
    v = analyse_events(events=events)
    assert v.decision == "insufficient_data"
    assert v.opus_score is not None
    assert v.opus_score.passed_count == 15


def test_small_gap_flips_to_hermes():
    """Within 5pp tolerance → flip to Hermes for cost."""
    events: list[dict] = []
    # Opus: 15 verified, 12 pass (80%)
    for i in range(15):
        inv = f"opus-inv-{i}"
        events.append(_dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv=inv, cost_usd=0.05))
        events.append(_verify_score(0.8 if i < 12 else 0.3, inv=inv))
    # Hermes: 15 verified, 11 pass (~73%) — 7pp gap. ABOVE threshold
    # Let me re-do so gap is within 5pp:
    # Opus 80% pass, Hermes 76% pass → 4pp gap, within threshold
    for i in range(15):
        inv = f"hermes-inv-{i}"
        events.append(_dispatch_synthesis("hermes", "grok-4.3", inv=inv, cost_usd=0.005))
        # 11/15 = 73.3%; let me do 12/15 = 80% to make gap zero
        # Actually let me set 11 passes for hermes → 11/15 = 73.3%
        # Opus 12/15 = 80%; gap = 6.7pp ABOVE threshold
        events.append(_verify_score(0.8 if i < 12 else 0.3, inv=inv))
    v = analyse_events(events=events)
    # 12/15 vs 12/15 = 0pp gap, within threshold → flip to hermes
    assert v.decision == "flip_to_hermes_primary"
    assert v.gap_pp is not None
    assert abs(v.gap_pp) <= PASS_RATE_GAP_THRESHOLD_PP
    assert v.opus_score is not None
    assert v.hermes_score is not None


def test_large_gap_keeps_opus():
    """Outside 5pp tolerance → keep Opus."""
    events: list[dict] = []
    # Opus: 15 syntheses, all pass
    for i in range(15):
        inv = f"opus-{i}"
        events.append(_dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv=inv))
        events.append(_verify_score(0.85, inv=inv))
    # Hermes: 15 syntheses, half fail (~50%)
    for i in range(15):
        inv = f"hermes-{i}"
        events.append(_dispatch_synthesis("hermes", "grok-4.3", inv=inv))
        events.append(_verify_score(0.85 if i < 7 else 0.2, inv=inv))
    v = analyse_events(events=events)
    assert v.decision == "keep_opus_primary"
    assert v.gap_pp is not None
    assert v.gap_pp > PASS_RATE_GAP_THRESHOLD_PP


def test_cost_per_passed_synthesis_computed():
    events = [
        _dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv="i-1", cost_usd=0.10),
        _verify_score(0.9, inv="i-1"),
        _dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv="i-2", cost_usd=0.10),
        _verify_score(0.9, inv="i-2"),
    ]
    v = analyse_events(events=events)
    opus = v.opus_score
    assert opus is not None
    assert opus.passed_count == 2
    assert opus.cost_per_passed_synthesis == 0.10  # 0.20 total / 2 passes


def test_provider_alias_normalisation():
    """'hermes' and 'hermes-grok' map to the same bucket."""
    events = [
        _dispatch_synthesis("hermes", "grok-4.3", inv="i-1"),
        _verify_score(0.9, inv="i-1"),
        _dispatch_synthesis("grok", "grok-4.3", inv="i-2"),
        _verify_score(0.9, inv="i-2"),
    ]
    v = analyse_events(events=events)
    # Both should land in the hermes-grok bucket
    hermes_scores = [s for s in v.scores if s.provider == "hermes-grok"]
    assert len(hermes_scores) == 1
    assert hermes_scores[0].synthesis_count == 2


def test_unverified_synthesis_counts_as_unpassed():
    """Conservative metric: synthesis with no verifier evidence ≠ pass."""
    events = [
        _dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv="i-1"),
        # no verify event for i-1
        _dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv="i-2"),
        _verify_score(0.9, inv="i-2"),
    ]
    v = analyse_events(events=events)
    opus = v.opus_score
    assert opus is not None
    assert opus.synthesis_count == 2
    assert opus.verified_count == 1
    assert opus.passed_count == 1
    assert opus.pass_rate_overall == 0.5


def test_window_filters_out_old_events():
    early = _dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv="i-1", ts="2026-04-01T00:00:00Z")
    late = _dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv="i-2", ts="2026-05-20T00:00:00Z")
    since = datetime(2026, 5, 1, tzinfo=timezone.utc)
    v = analyse_events(events=[early, late], since=since)
    assert v.opus_score is not None
    assert v.opus_score.synthesis_count == 1  # only the late one


def test_accepts_emitted_at_field():
    """Production event log uses `emitted_at`, not `created_at`."""
    ev = {
        "event_id": "evt-1",
        "investigation_id": "inv-1",
        "emitted_at": "2026-05-20T12:00:00Z",
        "action_type": "dispatch.call",
        "payload": {
            "action_type": "dispatch.call",
            "tier": "synthesis",
            "provider": "hermes",
            "model": "grok-4.3",
            "cost_usd": 0.005,
        },
    }
    v = analyse_events(events=[ev])
    assert v.hermes_score is not None
    assert v.hermes_score.synthesis_count == 1


# ── G5 follow-up: synthesizer self-grade fallback ────────────────────


def _synthesize_delivered(
    *,
    inv: str = "inv-1",
    recommendation: str = "buy",
    conviction: float = 0.7,
    ts: str = "2026-05-20T12:01:00Z",
) -> dict:
    return {
        "event_id": f"evt-syn-{inv}",
        "investigation_id": inv,
        "emitted_at": ts,
        "action_type": "synthesize.delivered",
        "payload": {
            "action_type": "synthesize.delivered",
            "implicit_recommendation": recommendation,
            "conviction_level": conviction,
        },
    }


def test_self_grade_fallback_when_no_rubric_scored():
    """When the rubric chain isn't firing in production (the G5
    finding), the analyzer falls back to synthesize.delivered's
    own implicit_recommendation + conviction_level."""
    events = [
        _dispatch_synthesis("hermes", "grok-4.3", inv="inv-1"),
        _synthesize_delivered(inv="inv-1", recommendation="buy", conviction=0.8),
    ]
    v = analyse_events(events=events)
    assert v.hermes_score is not None
    assert v.hermes_score.verified_count == 1  # self-graded counts as verified
    assert v.hermes_score.passed_count == 1    # conviction 0.8 ≥ 0.5 → pass


def test_self_grade_insufficient_evidence_counts_as_fail():
    """A synthesis that declined (insufficient_evidence) counts
    against the provider — the synthesizer self-reported failure."""
    events = [
        _dispatch_synthesis("hermes", "grok-4.3", inv="inv-1"),
        _synthesize_delivered(
            inv="inv-1",
            recommendation="insufficient_evidence",
            conviction=0.05,
        ),
    ]
    v = analyse_events(events=events)
    assert v.hermes_score is not None
    assert v.hermes_score.verified_count == 1
    assert v.hermes_score.passed_count == 0  # insufficient_evidence = fail


def test_rubric_scored_overrides_self_grade():
    """When both rubric.scored and self-grade exist, the explicit
    rubric wins. Self-grade is a fallback, not a co-signal."""
    events = [
        _dispatch_synthesis("hermes", "grok-4.3", inv="inv-1"),
        # Synthesizer self-grades 0.9
        _synthesize_delivered(inv="inv-1", recommendation="buy", conviction=0.9),
        # But the verifier rubric explicitly scored 0.3 → fail
        _verify_score(0.3, inv="inv-1"),
    ]
    v = analyse_events(events=events)
    assert v.hermes_score is not None
    assert v.hermes_score.verified_count == 1
    assert v.hermes_score.passed_count == 0  # rubric.scored 0.3 wins over self-grade


# ── Markdown renderer ────────────────────────────────────────────────


def test_renders_markdown_with_decision_and_table():
    events = []
    for i in range(15):
        inv = f"opus-{i}"
        events.append(_dispatch_synthesis("openrouter-opus", "claude-opus-4-7", inv=inv, cost_usd=0.05))
        events.append(_verify_score(0.85, inv=inv))
    for i in range(15):
        inv = f"hermes-{i}"
        events.append(_dispatch_synthesis("hermes", "grok-4.3", inv=inv, cost_usd=0.005))
        events.append(_verify_score(0.85, inv=inv))
    v = analyse_events(events=events)
    md = render_verdict_markdown(v)
    assert "# Dispatch tier-differentiation verdict (§14.4)" in md
    assert "openrouter-opus" in md
    assert "hermes-grok" in md
    assert "## Per-provider scores" in md
    assert "## Next steps" in md
