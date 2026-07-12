"""Tests for substrate/budget/usage_ledger.py — per-key actuals (ask #8)."""

from __future__ import annotations

import pytest

from substrate.budget.usage_ledger import (
    KeyCap,
    UsageEvent,
    UsageLedgerError,
    ledger_state,
    project_key_after_event,
    to_budget_state,
)

# ---------------------------------------------------------------------------
# ledger_state — basic aggregation
# ---------------------------------------------------------------------------


def test_single_key_sums_events():
    events = [
        UsageEvent(key_id="k1", cost_usd=0.12),
        UsageEvent(key_id="k1", cost_usd=0.08),
    ]
    out = ledger_state(events, [KeyCap(key_id="k1", cap_usd=1.0)])
    assert len(out) == 1
    assert out[0].key_id == "k1"
    assert out[0].spent_usd == pytest.approx(0.20)
    assert out[0].event_count == 2


def test_keys_separated():
    events = [
        UsageEvent(key_id="k1", cost_usd=0.5),
        UsageEvent(key_id="k2", cost_usd=0.3),
        UsageEvent(key_id="k1", cost_usd=0.2),
    ]
    out = ledger_state(events, {})
    by = {u.key_id: u for u in out}
    assert by["k1"].spent_usd == pytest.approx(0.7)
    assert by["k2"].spent_usd == pytest.approx(0.3)


def test_empty_events_and_caps_returns_empty():
    assert ledger_state([], []) == []


# ---------------------------------------------------------------------------
# cap statuses — the core honesty property
# ---------------------------------------------------------------------------


def test_status_under():
    out = ledger_state([UsageEvent("k", 0.2)], [KeyCap("k", 1.0)])[0]
    assert out.status == "under"
    assert out.remaining_usd == pytest.approx(0.8)
    assert out.usage_pct == pytest.approx(20.0)
    assert out.cap_known is True


def test_status_at_cap():
    out = ledger_state([UsageEvent("k", 1.0)], [KeyCap("k", 1.0)])[0]
    assert out.status == "at_cap"
    assert out.remaining_usd == pytest.approx(0.0)
    assert out.usage_pct == pytest.approx(100.0)


def test_status_over_remaining_negative():
    out = ledger_state([UsageEvent("k", 1.5)], [KeyCap("k", 1.0)])[0]
    assert out.status == "over"
    assert out.remaining_usd == pytest.approx(-0.5)
    assert out.usage_pct == pytest.approx(150.0)


def test_no_cap_yields_none_fields():
    out = ledger_state([UsageEvent("k", 5.0)], [KeyCap("k", None)])[0]
    assert out.status == "no_cap"
    assert out.cap_usd is None
    assert out.cap_known is False
    assert out.remaining_usd is None
    assert out.usage_pct is None
    assert out.spent_usd == pytest.approx(5.0)


def test_key_with_events_but_no_cap_entry():
    out = ledger_state([UsageEvent("k", 5.0)], {})[0]
    assert out.status == "no_cap"
    assert out.cap_known is False
    assert out.remaining_usd is None


def test_cap_but_no_events_appears_under():
    out = ledger_state([], [KeyCap("k", 1.0)])[0]
    assert out.spent_usd == 0.0
    assert out.status == "under"
    assert out.event_count == 0
    assert out.remaining_usd == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# impossible inputs are rejected, never coerced
# ---------------------------------------------------------------------------


def test_negative_cost_rejected():
    with pytest.raises(UsageLedgerError):
        ledger_state([UsageEvent("k", -0.1)], {})


def test_negative_cap_rejected():
    with pytest.raises(UsageLedgerError):
        ledger_state([], [KeyCap("k", -1.0)])


def test_project_negative_cost_rejected():
    cur = ledger_state([UsageEvent("k", 0.1)], [KeyCap("k", 1.0)])[0]
    with pytest.raises(UsageLedgerError):
        project_key_after_event(cur, UsageEvent("k", -0.5))


def test_zero_cost_allowed():
    out = ledger_state([UsageEvent("k", 0.0)], [KeyCap("k", 1.0)])[0]
    assert out.spent_usd == 0.0
    assert out.status == "under"


# ---------------------------------------------------------------------------
# by_model attribution honesty
# ---------------------------------------------------------------------------


def test_by_model_attributes_named_models():
    events = [
        UsageEvent("k", 0.3, model="gpt"),
        UsageEvent("k", 0.2, model="claude"),
        UsageEvent("k", 0.1, model="gpt"),
    ]
    out = ledger_state(events, {})[0]
    assert out.by_model == {"gpt": pytest.approx(0.4), "claude": pytest.approx(0.2)}
    assert out.spent_usd == pytest.approx(0.6)


def test_unmodeled_events_excluded_from_by_model():
    events = [
        UsageEvent("k", 0.3, model="gpt"),
        UsageEvent("k", 0.2),  # model=None
    ]
    out = ledger_state(events, {})[0]
    assert out.by_model == {"gpt": pytest.approx(0.3)}
    # total still includes the unattributed spend
    assert out.spent_usd == pytest.approx(0.5)
    assert out.event_count == 2


# ---------------------------------------------------------------------------
# determinism + input shapes
# ---------------------------------------------------------------------------


def test_output_sorted_by_key_id():
    events = [
        UsageEvent("zeta", 0.1),
        UsageEvent("alpha", 0.2),
        UsageEvent("mid", 0.3),
    ]
    out = ledger_state(events, {})
    assert [u.key_id for u in out] == ["alpha", "mid", "zeta"]


def test_caps_as_mapping_or_iterable_equivalent():
    events = [UsageEvent("k1", 0.1), UsageEvent("k2", 0.2)]
    via_iter = ledger_state(events, [KeyCap("k1", 1.0), KeyCap("k2", 2.0)])
    via_map = ledger_state(events, {"k1": KeyCap("k1", 1.0), "k2": KeyCap("k2", 2.0)})
    assert via_iter == via_map


def test_ledger_state_is_pure_idempotent():
    events = [UsageEvent("k", 0.3, model="gpt")]
    caps = [KeyCap("k", 1.0)]
    assert ledger_state(events, caps) == ledger_state(events, caps)


# ---------------------------------------------------------------------------
# project_key_after_event — forward check on actuals
# ---------------------------------------------------------------------------


def test_project_advances_spend_and_status():
    cur = ledger_state([UsageEvent("k", 0.7)], [KeyCap("k", 1.0)])[0]
    nxt = project_key_after_event(cur, UsageEvent("k", 0.4))
    assert nxt.spent_usd == pytest.approx(1.1)
    assert nxt.status == "over"
    assert nxt.event_count == 2
    assert cur.event_count == 1  # current unchanged (pure)


def test_project_transitions_under_to_at_cap():
    cur = ledger_state([UsageEvent("k", 0.7)], [KeyCap("k", 1.0)])[0]
    nxt = project_key_after_event(cur, UsageEvent("k", 0.3))
    assert nxt.status == "at_cap"
    assert nxt.remaining_usd == pytest.approx(0.0)


def test_project_no_cap_stays_no_cap():
    cur = ledger_state([UsageEvent("k", 0.5)], {})[0]
    nxt = project_key_after_event(cur, UsageEvent("k", 0.9))
    assert nxt.status == "no_cap"
    assert nxt.remaining_usd is None
    assert nxt.spent_usd == pytest.approx(1.4)


def test_project_updates_by_model():
    cur = ledger_state([UsageEvent("k", 0.3, model="gpt")], {})[0]
    nxt = project_key_after_event(cur, UsageEvent("k", 0.2, model="gpt"))
    assert nxt.by_model == {"gpt": pytest.approx(0.5)}


def test_project_key_id_mismatch_rejected():
    cur = ledger_state([UsageEvent("k1", 0.1)], {})[0]
    with pytest.raises(UsageLedgerError):
        project_key_after_event(cur, UsageEvent("k2", 0.1))


# ---------------------------------------------------------------------------
# adapter to #1838 BudgetState
# ---------------------------------------------------------------------------


def test_to_budget_state_fields():
    u = ledger_state([UsageEvent("k", 0.3)], [KeyCap("k", 1.0)])[0]
    assert to_budget_state(u) == (1.0, 0.3, True, True)


def test_to_budget_state_no_cap():
    u = ledger_state([UsageEvent("k", 0.3)], {})[0]
    assert to_budget_state(u) == (None, 0.3, False, True)


# ---------------------------------------------------------------------------
# usage_pct edge: zero cap with zero spend
# ---------------------------------------------------------------------------


def test_zero_cap_zero_spend_is_at_cap():
    out = ledger_state([UsageEvent("k", 0.0)], [KeyCap("k", 0.0)])[0]
    assert out.status == "at_cap"
    assert out.remaining_usd == 0.0
    assert out.usage_pct == pytest.approx(0.0)
