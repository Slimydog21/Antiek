"""Tests for substrate/budget/execution_gate.py — the price-ceiling-approval gate."""

from __future__ import annotations

import pytest

from substrate.budget.execution_gate import (
    AuthorizationDecision,
    BudgetHeadroom,
    CostCeiling,
    ExecutionGateError,
    OperatorConsent,
    authorize_execution,
)


def _consent(
    granted: bool = True,
    approved: float | None = 1.0,
    expired: bool = False,
    revoked: bool = False,
) -> OperatorConsent:
    return OperatorConsent(
        granted=granted,
        approved_ceiling_usd=approved,
        is_expired=expired,
        revoked=revoked,
    )


def _ceiling(usd: float | None = 0.5, known: bool = True) -> CostCeiling:
    return CostCeiling(ceiling_usd=usd, pricing_known=known)


def _headroom(remaining: float | None = 1.0, known: bool = True) -> BudgetHeadroom:
    return BudgetHeadroom(remaining_usd=remaining, headroom_known=known)


# ---------------------------------------------------------------------------
# the happy path — every gate passes
# ---------------------------------------------------------------------------


def test_authorized_when_all_gates_pass():
    d = authorize_execution(_ceiling(0.5), _consent(approved=1.0), _headroom(1.0))
    assert d.authorized is True
    assert d.reason == "all gates passed"
    assert d.notes  # non-empty provenance


def test_authorized_at_exact_bounds():
    # ceiling == approved == remaining: still fits (<=)
    d = authorize_execution(_ceiling(1.0), _consent(approved=1.0), _headroom(1.0))
    assert d.authorized is True


# ---------------------------------------------------------------------------
# Gate 1 — consent (the operator's price-ceiling approval)
# ---------------------------------------------------------------------------


def test_deny_no_consent():
    d = authorize_execution(_ceiling(0.5), _consent(granted=False), _headroom(1.0))
    assert d.authorized is False
    assert d.reason == "no operator consent"


def test_deny_consent_revoked():
    d = authorize_execution(_ceiling(0.5), _consent(revoked=True), _headroom(1.0))
    assert d.authorized is False
    assert d.reason == "operator consent revoked"


def test_deny_consent_expired():
    d = authorize_execution(_ceiling(0.5), _consent(expired=True), _headroom(1.0))
    assert d.authorized is False
    assert d.reason == "operator consent expired"


def test_deny_no_approved_ceiling_is_not_blanket_consent():
    d = authorize_execution(_ceiling(0.5), _consent(approved=None), _headroom(1.0))
    assert d.authorized is False
    assert "no price ceiling" in d.reason
    assert any("blanket" in n for n in d.notes)


# ---------------------------------------------------------------------------
# Gate 2 — bounded pricing
# ---------------------------------------------------------------------------


def test_deny_pricing_unknown_flag():
    d = authorize_execution(_ceiling(0.5, known=False), _consent(), _headroom(1.0))
    assert d.authorized is False
    assert d.reason == "pricing unknown; spend unbounded"


def test_deny_ceiling_none():
    d = authorize_execution(_ceiling(None, known=True), _consent(), _headroom(1.0))
    assert d.authorized is False
    assert "unbounded" in d.reason


# ---------------------------------------------------------------------------
# Gate 3 — run fits what the operator approved
# ---------------------------------------------------------------------------


def test_deny_run_exceeds_approved_ceiling():
    d = authorize_execution(_ceiling(1.5), _consent(approved=1.0), _headroom(5.0))
    assert d.authorized is False
    assert d.reason == "run ceiling exceeds approved ceiling"
    assert any("re-approval" in n for n in d.notes)


def test_authorized_when_run_under_approved_but_over_half_headroom_ok():
    # approved 2.0, run 1.5, headroom 5.0 -> fits approved, fits headroom
    d = authorize_execution(_ceiling(1.5), _consent(approved=2.0), _headroom(5.0))
    assert d.authorized is True


# ---------------------------------------------------------------------------
# Gate 4 — known headroom
# ---------------------------------------------------------------------------


def test_deny_headroom_unknown_flag():
    d = authorize_execution(_ceiling(0.5), _consent(), _headroom(1.0, known=False))
    assert d.authorized is False
    assert d.reason == "budget headroom unknown"


def test_deny_headroom_none():
    d = authorize_execution(_ceiling(0.5), _consent(), _headroom(None, known=True))
    assert d.authorized is False
    assert d.reason == "budget headroom unknown"


# ---------------------------------------------------------------------------
# Gate 5 — run fits remaining budget
# ---------------------------------------------------------------------------


def test_deny_run_exceeds_remaining_budget():
    d = authorize_execution(_ceiling(1.5), _consent(approved=5.0), _headroom(1.0))
    assert d.authorized is False
    assert d.reason == "run ceiling exceeds remaining budget"


def test_deny_run_exceeds_remaining_even_if_under_approved():
    # approved 5.0 (operator is generous), run 1.5, but only 1.0 left
    d = authorize_execution(_ceiling(1.5), _consent(approved=5.0), _headroom(1.0))
    assert d.authorized is False


# ---------------------------------------------------------------------------
# gate ordering — cheapest check denies first
# ---------------------------------------------------------------------------


def test_consent_checked_before_pricing():
    # no consent AND pricing unknown -> reason is consent (gate 1 first)
    d = authorize_execution(_ceiling(None, known=False), _consent(granted=False), _headroom(1.0))
    assert d.reason == "no operator consent"


def test_pricing_checked_before_headroom():
    # pricing unknown AND headroom unknown -> reason is pricing (gate before headroom)
    d = authorize_execution(_ceiling(None, known=False), _consent(), _headroom(None, known=False))
    assert "unbounded" in d.reason


def test_approved_ceiling_checked_before_headroom():
    # approved None (gate 2) and headroom None (gate 4) -> reason is approved
    d = authorize_execution(_ceiling(0.5), _consent(approved=None), _headroom(None, known=False))
    assert "no price ceiling" in d.reason


# ---------------------------------------------------------------------------
# impossible inputs rejected, never coerced
# ---------------------------------------------------------------------------


def test_negative_ceiling_rejected():
    with pytest.raises(ExecutionGateError):
        authorize_execution(_ceiling(-0.1), _consent(), _headroom(1.0))


def test_negative_approved_ceiling_rejected():
    with pytest.raises(ExecutionGateError):
        authorize_execution(_ceiling(0.5), _consent(approved=-1.0), _headroom(1.0))


def test_negative_headroom_rejected():
    with pytest.raises(ExecutionGateError):
        authorize_execution(_ceiling(0.5), _consent(), _headroom(-1.0))


def test_zero_ceiling_authorized_if_consent_and_headroom_hold():
    d = authorize_execution(_ceiling(0.0), _consent(approved=1.0), _headroom(1.0))
    assert d.authorized is True


# ---------------------------------------------------------------------------
# purity — decision is a value, no side effects
# ---------------------------------------------------------------------------


def test_decision_is_frozen_value():
    d = authorize_execution(_ceiling(0.5), _consent(), _headroom(1.0))
    assert isinstance(d, AuthorizationDecision)
    assert d.authorized is True
    # notes is a tuple (immutable)
    assert isinstance(d.notes, tuple)


def test_authorize_execution_is_pure_idempotent():
    args = (_ceiling(0.5), _consent(), _headroom(1.0))
    assert authorize_execution(*args) == authorize_execution(*args)
