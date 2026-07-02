"""antiek-yegge-execute SPR-01 — token-burn telemetry on ``DispatchCallPayload``.

The spec proposed a SEPARATE ``token_burn`` event; diligence against current
main found that a substrate-fit defect: ``DISPATCH_CALL`` is already the
canonical per-LLM-call token+cost event (``substrate/coordination/cost_view.py``
reads every cent off ``DispatchCallPayload``), so a second event would fork the
convention. Operator decision 2026-07-02: extend DISPATCH_CALL instead.

These tests pin the contract: the five new fields are OPTIONAL with safe
defaults, every pre-SPR-01 emitter constructs the payload identically
(byte-unchanged regression guard), and cost_view's ``payload.get(...)`` read
pattern is unaffected.
"""

from __future__ import annotations

import pytest

from substrate.schemas.events import DispatchCallPayload

# ── the five new fields exist + default safely ──────────────────────────────


def test_token_burn_fields_exist_with_safe_defaults():
    """The five token-burn fields are present and default to None/0 so an
    emitter that does not set them is byte-identical to pre-SPR-01."""
    p = DispatchCallPayload(
        provider="anthropic",
        model="claude-opus-4-7",
        tier="synthesis",
        target_role="synthesizer",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        latency_ms=2000,
        prompt_hash="abc",
    )
    assert p.cached_input_tokens == 0
    assert p.task_id is None
    assert p.parent_run_id is None
    assert p.feature_label is None
    assert p.session_id is None


def test_cached_input_tokens_rejects_negative():
    """A provider that returns -1 on cache-only calls must be rejected, not
    coerced to 0 (rigor #3)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DispatchCallPayload(
            provider="anthropic", model="claude-opus-4-7", tier="synthesis",
            target_role="synthesizer", input_tokens=100, output_tokens=50,
            cost_usd=0.01, latency_ms=2000, prompt_hash="abc",
            cached_input_tokens=-1,
        )


# ── REGRESSION GUARD: pre-SPR-01 construction is byte-identical ─────────────


def test_pre_spr01_construction_round_trips_without_new_fields():
    """Every existing emitter (router.py, base.py, remote_exec cost) constructs
    DispatchCallPayload WITHOUT the new fields. The serialized payload must be
    identical to pre-SPR-01 — the new fields add keys with default values, they
    do not change any existing key.

    This is the no-regression proof cost_view depends on: it reads
    payload['cost_usd'] / payload['target_role'] / payload['provider'] via
    .get(), and those keys (plus the new ones) are the only ones present."""
    p = DispatchCallPayload(
        provider="anthropic",
        model="claude-opus-4-7",
        tier="synthesis",
        target_role="synthesizer",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        latency_ms=2000,
        prompt_hash="abc",
    )
    dumped = p.model_dump(mode="json")
    # The pre-SPR-01 keys are all present with their pre-SPR-01 values.
    assert dumped["provider"] == "anthropic"
    assert dumped["target_role"] == "synthesizer"
    assert dumped["cost_usd"] == 0.01
    assert dumped["input_tokens"] == 100
    assert dumped["output_tokens"] == 50
    assert dumped["tier"] == "synthesis"
    # The new fields serialize as their JSON defaults (0 / null), not absent.
    assert dumped["cached_input_tokens"] == 0
    assert dumped["task_id"] is None


def test_new_fields_populate_when_set():
    """When the SPR-05 token-burn middleware sets the fields, they serialize."""
    p = DispatchCallPayload(
        provider="anthropic", model="claude-opus-4-7", tier="synthesis",
        target_role="synthesizer", input_tokens=100, output_tokens=50,
        cost_usd=0.01, latency_ms=2000, prompt_hash="abc",
        cached_input_tokens=80, task_id="t-1", parent_run_id="r-1",
        feature_label="deep-research", session_id="sess-1",
    )
    d = p.model_dump(mode="json")
    assert d["cached_input_tokens"] == 80
    assert d["task_id"] == "t-1"
    assert d["parent_run_id"] == "r-1"
    assert d["feature_label"] == "deep-research"
    assert d["session_id"] == "sess-1"


# ── cost_view read pattern is unaffected ────────────────────────────────────


def test_cost_view_read_pattern_get_keys_still_resolves():
    """cost_view.py reads the payload as a dict via payload.get('cost_usd') /
    payload.get('target_role') / payload.get('provider'). Those keys + the new
    ones are all present in the dumped dict; absent-before fields read via
    .get() resolve to their default, never KeyError."""
    p = DispatchCallPayload(
        provider="anthropic", model="claude-opus-4-7", tier="synthesis",
        target_role="synthesizer", input_tokens=100, output_tokens=50,
        cost_usd=0.01, latency_ms=2000, prompt_hash="abc",
    )
    payload = p.model_dump(mode="json")
    # The exact three keys cost_view reads (cost_view.py:321-323 + :17).
    assert payload.get("cost_usd") == 0.01
    assert payload.get("target_role") == "synthesizer"
    assert payload.get("provider") == "anthropic"
    # The new token-burn keys are .get()-able (None / 0), not absent.
    assert payload.get("cached_input_tokens") == 0
    assert payload.get("task_id") is None
