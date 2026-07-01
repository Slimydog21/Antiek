"""ANT-ND SPR-02 — DispatchCallPayload nd_* attribution fields (schema v28).

Proves the additive contract:

* the seven ``nd_*`` fields exist with the spec'd defaults,
* a fully-populated payload round-trips,
* a pre-v28 row (no ``nd_*`` keys) deserializes to the defaults (schema-on-read),
* the bypass partial-update path works,
* ``nd_decision_latency_ms`` rejects negatives,
* ``record_nd_decision`` stages into a ContextVar and ``consume_nd_decision``
  drains it exactly once (single-writer preserved — record writes no event),
* SPR-02 adds **zero** callers of ``record_nd_decision`` in the dispatch/runtime
  hot path (SPR-03 adds the only caller),
* ``EVENT_SCHEMA_VERSION`` was bumped to 28.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from substrate.dispatch.nd_attribution import (
    clear_nd_decision,
    consume_nd_decision,
    peek_nd_decision,
    record_nd_decision,
)
from substrate.schemas.events import EVENT_SCHEMA_VERSION, DispatchCallPayload

_REPO = Path(__file__).resolve().parent.parent

_ND_FIELDS = (
    "nd_session_id",
    "nd_recommended_provider",
    "nd_recommended_model",
    "nd_tradeoff",
    "nd_decision_latency_ms",
    "nd_bypassed",
    "nd_bypass_reason",
)


def _base(**over):
    kw = dict(
        provider="anthropic",
        model="claude-opus-4-7",
        tier="synthesis",
        target_role="synthesize",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0,
        latency_ms=12,
        prompt_hash="deadbeef",
    )
    kw.update(over)
    return kw


@pytest.fixture(autouse=True)
def _isolate_ctx():
    """Ensure no staged decision leaks across tests."""
    clear_nd_decision()
    yield
    clear_nd_decision()


# --- schema shape ---------------------------------------------------------


def test_schema_version_bumped_to_28():
    assert EVENT_SCHEMA_VERSION == 28


def test_all_seven_nd_fields_present_with_defaults():
    p = DispatchCallPayload(**_base())
    for f in _ND_FIELDS:
        assert f in DispatchCallPayload.model_fields, f"missing field {f}"
    assert p.nd_bypassed is False
    assert p.nd_session_id is None
    assert p.nd_recommended_provider is None
    assert p.nd_recommended_model is None
    assert p.nd_tradeoff is None
    assert p.nd_decision_latency_ms is None
    assert p.nd_bypass_reason is None


def test_round_trip_with_nd_populated():
    p = DispatchCallPayload(
        **_base(
            nd_session_id="s1",
            nd_recommended_provider="anthropic",
            nd_recommended_model="claude-opus-4-7",
            nd_tradeoff="quality",
            nd_decision_latency_ms=42,
            nd_bypassed=False,
            nd_bypass_reason=None,
        )
    )
    again = DispatchCallPayload.model_validate(p.model_dump())
    assert again == p
    assert again.nd_session_id == "s1"
    assert again.nd_decision_latency_ms == 42


def test_schema_on_read_pre_v28_row_defaults():
    """A pre-v28 DispatchCall dict — no nd_* keys at all — must validate with
    the defaults applied (schema-on-read), NOT raise despite extra='forbid'.
    extra='forbid' rejects unknown keys, never missing ones."""
    pre_v28 = _base()  # deliberately contains none of the nd_* keys
    p = DispatchCallPayload.model_validate(pre_v28)
    assert p.nd_bypassed is False
    assert p.nd_session_id is None


def test_bypass_partial_update():
    p = DispatchCallPayload(**_base(nd_bypassed=True, nd_bypass_reason="timeout"))
    assert p.nd_bypassed is True
    assert p.nd_bypass_reason == "timeout"
    assert p.nd_session_id is None  # partial: no recommendation recorded


def test_decision_latency_ms_rejects_negative():
    with pytest.raises(ValueError):
        DispatchCallPayload(**_base(nd_decision_latency_ms=-1))


def test_extra_unknown_field_still_forbidden():
    """The additive fields must not have loosened extra='forbid'."""
    with pytest.raises(ValueError):
        DispatchCallPayload(**_base(nd_not_a_real_field="x"))


# --- staging / drain (single-writer) --------------------------------------


def test_record_and_consume_staging():
    record_nd_decision(
        nd_session_id="sess",
        nd_recommended_provider="anthropic",
        nd_recommended_model="claude-opus-4-7",
        nd_tradeoff="cost",
        nd_decision_latency_ms=12,
    )
    staged = consume_nd_decision()
    assert staged["nd_session_id"] == "sess"
    assert staged["nd_recommended_provider"] == "anthropic"
    assert staged["nd_bypassed"] is False
    # Drained: a second consume yields the defaults (one decision → one event).
    assert consume_nd_decision()["nd_session_id"] is None


def test_consume_default_when_nothing_staged():
    d = consume_nd_decision()
    assert d == {
        "nd_session_id": None,
        "nd_recommended_provider": None,
        "nd_recommended_model": None,
        "nd_tradeoff": None,
        "nd_decision_latency_ms": None,
        "nd_bypassed": False,
        "nd_bypass_reason": None,
    }


def test_staged_decision_spreads_onto_payload():
    """The emitter drains with **consume_nd_decision() and spreads onto the
    payload; simulate that here to prove the keys line up exactly."""
    record_nd_decision(nd_session_id="s9", nd_bypassed=True, nd_bypass_reason="shadow")
    p = DispatchCallPayload(**_base(), **consume_nd_decision())
    assert p.nd_session_id == "s9"
    assert p.nd_bypassed is True
    assert p.nd_bypass_reason == "shadow"


def test_record_writes_nothing_and_returns_none():
    assert record_nd_decision(nd_bypassed=True, nd_bypass_reason="disabled") is None
    assert peek_nd_decision()["nd_bypassed"] is True  # staged, not emitted


def test_remote_exec_emitter_also_drains_nd(monkeypatch):
    """The remote-exec fan-out (runtime/remote_exec/cost.py:record_remote_dispatch)
    is the SECOND DispatchCall emitter, and ND's DRW scope routes through it.
    It must drain + clear the same ND attribution ContextVar (verifier-critic
    finding, 2026-07-01). Duck-typed event/budget + a captured emit avoid pulling
    the remote infra."""
    import runtime.remote_exec.cost as costmod

    captured: dict = {}

    def _fake_emit(inv, payload, **kw):
        captured["payload"] = payload
        return "evt-remote-1"

    monkeypatch.setattr(costmod, "emit_typed", _fake_emit)

    class _FakeEvent:
        provider = "daytona"
        model = "research-leaf"
        cost_usd = 0.01
        tokens = 5
        data: dict = {}

    class _FakeBudget:
        def charge(self, *a, **k):
            return None

    record_nd_decision(nd_session_id="remote-sess", nd_tradeoff="cost")
    costmod.record_remote_dispatch(
        investigation_id="inv-1", event=_FakeEvent(), budget=_FakeBudget()
    )
    assert captured["payload"].nd_session_id == "remote-sess"
    assert captured["payload"].nd_tradeoff == "cost"
    # Cleared after drain — no leak onto a later call.
    assert peek_nd_decision() is None


def test_no_callers_of_record_nd_decision_in_hot_path():
    """SPR-02 adds ZERO callers of record_nd_decision; SPR-03 is the only one.
    The sole emitter drains via consume_nd_decision, never record_nd_decision.

    Match actual CALL sites only (``record_nd_decision(``) in .py files, skip
    binaries, and exclude the definition module (whose ``def`` line matches)."""
    out = subprocess.run(
        [
            "grep",
            "-rInE",
            "--include=*.py",
            r"record_nd_decision\(",
            str(_REPO / "substrate" / "dispatch"),
            str(_REPO / "runtime"),
        ],
        capture_output=True,
        text=True,
    )
    offending = [
        ln
        for ln in out.stdout.splitlines()
        if "nd_attribution.py" not in ln  # the `def record_nd_decision(` definition
    ]
    assert offending == [], f"unexpected record_nd_decision caller(s): {offending}"
