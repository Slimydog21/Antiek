"""AGH SPR-06 — injected-failure traces at silent-swallow sites.

Each test drives a verified swallow site with the guarded operation forced to
raise, and asserts BOTH halves of the contract:
  (a) the failure now leaves a trace (previously silent), and
  (b) the isolation posture is preserved — the loop/operation continues and
      the caller's result shape is unchanged.

Red-proof: with the source trace removed, (a) fails while (b) still passes —
proving the assertion is about the NEW trace, not incidental behavior.

This module intentionally covers the two cleanest-to-inject sites (one stderr
idiom, one logging idiom). The remaining sites' injection recipes are recorded
in the SPR-06 handoff; their direct tests are a documented follow-up.
"""

from __future__ import annotations

import logging

import pytest


# ---------------------------------------------------------------------------
# Site 5 — postconditions._events_of_type: malformed trajectory row skipped.
# Idiom: `phase_runner:`-prefixed stderr (matches runner.py). Injection:
# monkeypatch the module's `trajectory` to yield a row that fails
# Event.model_validate.
# ---------------------------------------------------------------------------


def test_postconditions_malformed_row_is_traced_and_skipped(monkeypatch, capsys):
    from orchestration.phase_runner import postconditions
    from substrate.schemas.events import ActionType

    at = ActionType.AUTO_PATCH_APPLIED
    good_then_bad = [
        {"action_type": at.value, "not_a_valid": "event", "missing": "fields"},
    ]
    monkeypatch.setattr(postconditions, "trajectory", lambda _iid: good_then_bad)

    out = postconditions._events_of_type("inv-tz-1", at)

    # (b) isolation: the malformed row is skipped, function returns cleanly.
    assert out == []
    # (a) trace: the skip is no longer silent.
    err = capsys.readouterr().err
    assert "phase_runner: malformed event row skipped for inv-tz-1" in err
    assert "action_type=" in err


# ---------------------------------------------------------------------------
# Site 2 — remote_exec runner._teardown: provider.teardown failure traced.
# Idiom: logging.getLogger("antiek.remote_exec"). Injection: a provider whose
# teardown raises; drive cancel() (unconditional teardown). A leaked paid
# sandbox must not be invisible.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remote_teardown_failure_is_traced(monkeypatch, caplog):
    pytest.importorskip("pytest_asyncio")
    from runtime.remote_exec import runner as runner_mod

    class _Sandbox:
        sandbox_id = "sbx-leak-1"

    class _Plan:
        investigation_id = "inv-teardown-1"

    class _State:
        sandbox = _Sandbox()
        plan = _Plan()
        torn_down = False

    class _BoomProvider:
        async def teardown(self, sandbox):  # noqa: ANN001, ANN202
            raise RuntimeError("provider teardown boom")

    r = runner_mod.RemoteResearchRunner.__new__(runner_mod.RemoteResearchRunner)
    r._provider = _BoomProvider()  # type: ignore[attr-defined]
    st = _State()

    with caplog.at_level(logging.WARNING, logger="antiek.remote_exec"):
        # _teardown must swallow the provider error (isolation) ...
        await r._teardown(st)  # type: ignore[attr-defined]

    # (b) isolation: st marked torn_down, no exception propagated.
    assert st.torn_down is True
    # (a) trace: the leaked-sandbox failure is now recorded.
    assert any(
        "sandbox teardown failed" in rec.message and "sbx-leak-1" in rec.message
        for rec in caplog.records
    )
