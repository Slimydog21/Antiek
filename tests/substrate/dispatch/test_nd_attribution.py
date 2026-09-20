from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from substrate.dispatch.nd_attribution import (
    clear_nd_decision,
    consume_nd_decision,
    peek_nd_decision,
    push_nd_decision,
    record_nd_decision,
    reset_nd_decision,
)
from substrate.schemas.events import EVENT_SCHEMA_VERSION, DispatchCallPayload

_REPO = Path(__file__).resolve().parents[3]

_ND_FIELDS = (
    "nd_session_id",
    "nd_recommended_provider",
    "nd_recommended_model",
    "nd_tradeoff",
    "nd_decision_latency_ms",
    "nd_bypassed",
    "nd_bypass_reason",
)


def _base(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "tier": "synthesis",
        "target_role": "synthesize",
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.0,
        "latency_ms": 12,
        "prompt_hash": "deadbeef",
    }
    values.update(overrides)
    return values


@pytest.fixture(autouse=True)
def _isolate_ctx() -> Iterator[None]:
    clear_nd_decision()
    yield
    clear_nd_decision()


def test_schema_version_includes_post_nd_bumps() -> None:
    assert EVENT_SCHEMA_VERSION == 40


def test_all_seven_nd_fields_present_with_defaults() -> None:
    p = DispatchCallPayload.model_validate(_base())
    for field in _ND_FIELDS:
        assert field in DispatchCallPayload.model_fields
    assert p.nd_session_id is None
    assert p.nd_recommended_provider is None
    assert p.nd_recommended_model is None
    assert p.nd_tradeoff is None
    assert p.nd_decision_latency_ms is None
    assert p.nd_bypassed is False
    assert p.nd_bypass_reason is None


def test_round_trip_with_nd_populated() -> None:
    p = DispatchCallPayload.model_validate(
        _base(
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


def test_schema_on_read_pre_nd_row_defaults() -> None:
    p = DispatchCallPayload.model_validate(_base())
    assert p.nd_session_id is None
    assert p.nd_bypassed is False


def test_bypass_partial_update() -> None:
    p = DispatchCallPayload.model_validate(
        _base(nd_bypassed=True, nd_bypass_reason="timeout")
    )
    assert p.nd_bypassed is True
    assert p.nd_bypass_reason == "timeout"
    assert p.nd_session_id is None


def test_decision_latency_ms_rejects_negative() -> None:
    with pytest.raises(ValueError):
        DispatchCallPayload.model_validate(_base(nd_decision_latency_ms=-1))


def test_record_and_consume_staging() -> None:
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
    assert consume_nd_decision()["nd_session_id"] is None


def test_consume_default_when_nothing_staged() -> None:
    assert consume_nd_decision() == {
        "nd_session_id": None,
        "nd_recommended_provider": None,
        "nd_recommended_model": None,
        "nd_tradeoff": None,
        "nd_decision_latency_ms": None,
        "nd_bypassed": False,
        "nd_bypass_reason": None,
    }


def test_record_writes_nothing_and_returns_none() -> None:
    record_nd_decision(nd_bypassed=True, nd_bypass_reason="disabled")
    staged = peek_nd_decision()
    assert staged is not None
    assert staged["nd_bypassed"] is True


def test_scoped_attribution_ignores_unrelated_emitter_and_remains_available() -> None:
    scope = object()
    decision = {
        "nd_session_id": "scoped",
        "nd_recommended_provider": "zai",
        "nd_recommended_model": "glm-5.2",
        "nd_tradeoff": "quality",
        "nd_decision_latency_ms": 4,
        "nd_bypassed": True,
        "nd_bypass_reason": "shadow",
    }
    tokens = push_nd_decision(decision, scope=scope)
    try:
        assert consume_nd_decision()["nd_session_id"] is None
        assert consume_nd_decision(scope=object())["nd_session_id"] is None
        assert consume_nd_decision(scope=scope)["nd_session_id"] == "scoped"
        assert consume_nd_decision(scope=scope)["nd_session_id"] == "scoped"
    finally:
        reset_nd_decision(tokens)


def test_remote_exec_emitter_also_drains_nd(monkeypatch: pytest.MonkeyPatch) -> None:
    import runtime.remote_exec.cost as costmod

    captured: dict[str, object] = {}

    def _fake_emit(*args: object, **kwargs: object) -> str:
        captured["payload"] = args[1]
        return "evt-remote-1"

    monkeypatch.setattr(costmod, "emit_typed", _fake_emit)

    class _FakeEvent:
        provider = "daytona"
        model = "research-leaf"
        cost_usd = 0.01
        tokens = 5
        data: dict[str, object] = {}

    class _FakeBudget:
        def charge(self, *args: object, **kwargs: object) -> None:
            return None

    record_nd_decision(nd_session_id="remote-sess", nd_tradeoff="cost")
    costmod.record_remote_dispatch(
        investigation_id="inv-1",
        event=cast(Any, _FakeEvent()),
        budget=cast(Any, _FakeBudget()),
    )
    payload = captured["payload"]
    assert isinstance(payload, DispatchCallPayload)
    assert payload.nd_session_id == "remote-sess"
    assert payload.nd_tradeoff == "cost"
    assert peek_nd_decision() is None


def test_shadow_uses_only_the_scoped_push_in_hot_path() -> None:
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
        check=False,
    )
    record_callers = [
        line
        for line in out.stdout.splitlines()
        if "nd_attribution.py" not in line
    ]
    assert record_callers == []
    push = subprocess.run(
        [
            "grep",
            "-rInE",
            "--include=*.py",
            r"push_nd_decision\(",
            str(_REPO / "substrate" / "dispatch"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    push_callers = [line for line in push.stdout.splitlines() if "nd_attribution.py" not in line]
    assert len(push_callers) == 1
    assert "substrate/dispatch/router.py" in push_callers[0]
