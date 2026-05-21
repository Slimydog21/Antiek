"""Advertiser onboarding state-machine tests (Sprint 23-24 phase 5)."""

from __future__ import annotations

import pytest

from substrate.ad_inventory import (
    AdvertiserOnboardingError,
    AdvertiserRegistry,
    AdvertiserStatus,
    activate_advertiser,
    approve_advertiser,
    churn_advertiser,
    is_serving,
    reject_advertiser,
    submit_application,
    suspend_advertiser,
)


def _new_registry() -> AdvertiserRegistry:
    return AdvertiserRegistry()


def test_submit_application_lands_in_pending_review():
    reg = _new_registry()
    rec = submit_application(
        reg,
        display_name="Acme Recruiting",
        contact_email="ops@acme.example",
        verticals=("recruiting", "saas"),
        audience_intents=("hiring_manager",),
        monthly_budget_usd_cents=500_00,
    )
    assert rec.status is AdvertiserStatus.PENDING_REVIEW
    assert rec.verticals == ("recruiting", "saas")
    assert rec.audience_intents == ("hiring_manager",)
    assert rec.monthly_budget_usd_cents == 500_00
    assert reg.latest(rec.advertiser_id) is rec


def test_submit_with_duplicate_id_refuses():
    reg = _new_registry()
    rec = submit_application(
        reg,
        display_name="A", contact_email="a@x", verticals=(),
        advertiser_id="adv-fixed-1",
    )
    with pytest.raises(AdvertiserOnboardingError):
        submit_application(
            reg,
            display_name="B", contact_email="b@x", verticals=(),
            advertiser_id="adv-fixed-1",
        )
    # The first record is still the latest.
    assert reg.latest("adv-fixed-1") is rec


def test_approve_then_activate_only_with_legal_gate():
    reg = _new_registry()
    rec = submit_application(
        reg, display_name="X", contact_email="x@y", verticals=("consulting",),
    )
    approved = approve_advertiser(
        reg, advertiser_id=rec.advertiser_id, operator_notes="vetted",
    )
    assert approved.status is AdvertiserStatus.APPROVED
    assert approved.operator_notes == "vetted"

    # Legal gate not passed → refuses to activate.
    with pytest.raises(AdvertiserOnboardingError) as ei:
        activate_advertiser(
            reg, advertiser_id=rec.advertiser_id, legal_gate_passed=False,
        )
    assert "legal gate" in str(ei.value).lower()

    # Legal gate passed → activates.
    active = activate_advertiser(
        reg, advertiser_id=rec.advertiser_id, legal_gate_passed=True,
    )
    assert active.status is AdvertiserStatus.ACTIVE
    assert is_serving(active) is True
    assert is_serving(approved) is False  # historical record unchanged


def test_reject_terminal():
    reg = _new_registry()
    rec = submit_application(
        reg, display_name="X", contact_email="x@y", verticals=(),
    )
    rejected = reject_advertiser(
        reg, advertiser_id=rec.advertiser_id, rejection_reason="off-brand",
    )
    assert rejected.status is AdvertiserStatus.REJECTED
    assert rejected.rejection_reason == "off-brand"
    # Cannot re-approve a rejected record.
    with pytest.raises(AdvertiserOnboardingError):
        approve_advertiser(reg, advertiser_id=rec.advertiser_id)


def test_approve_only_from_pending_review():
    reg = _new_registry()
    rec = submit_application(
        reg, display_name="X", contact_email="x@y", verticals=(),
    )
    approve_advertiser(reg, advertiser_id=rec.advertiser_id)
    # Already approved → second approve refused.
    with pytest.raises(AdvertiserOnboardingError):
        approve_advertiser(reg, advertiser_id=rec.advertiser_id)


def test_suspend_active_then_reactivate_requires_legal_gate():
    reg = _new_registry()
    rec = submit_application(
        reg, display_name="X", contact_email="x@y", verticals=(),
    )
    approve_advertiser(reg, advertiser_id=rec.advertiser_id)
    activate_advertiser(
        reg, advertiser_id=rec.advertiser_id, legal_gate_passed=True,
    )
    suspended = suspend_advertiser(
        reg, advertiser_id=rec.advertiser_id, reason="brand-safety review",
    )
    assert suspended.status is AdvertiserStatus.SUSPENDED
    assert "brand-safety review" in suspended.operator_notes
    assert is_serving(suspended) is False
    # SUSPENDED is not directly activatable — only APPROVED is.
    with pytest.raises(AdvertiserOnboardingError):
        activate_advertiser(
            reg, advertiser_id=rec.advertiser_id, legal_gate_passed=True,
        )


def test_churn_terminal_from_active_or_suspended():
    reg = _new_registry()
    rec = submit_application(
        reg, display_name="X", contact_email="x@y", verticals=(),
    )
    # Cannot churn PENDING_REVIEW.
    with pytest.raises(AdvertiserOnboardingError):
        churn_advertiser(reg, advertiser_id=rec.advertiser_id)
    approve_advertiser(reg, advertiser_id=rec.advertiser_id)
    activate_advertiser(
        reg, advertiser_id=rec.advertiser_id, legal_gate_passed=True,
    )
    churned = churn_advertiser(reg, advertiser_id=rec.advertiser_id)
    assert churned.status is AdvertiserStatus.CHURNED
    assert is_serving(churned) is False


def test_unknown_advertiser_id_raises():
    reg = _new_registry()
    for fn in (
        lambda: approve_advertiser(reg, advertiser_id="nope"),
        lambda: reject_advertiser(
            reg, advertiser_id="nope", rejection_reason="x",
        ),
        lambda: activate_advertiser(
            reg, advertiser_id="nope", legal_gate_passed=True,
        ),
        lambda: suspend_advertiser(
            reg, advertiser_id="nope", reason="x",
        ),
        lambda: churn_advertiser(reg, advertiser_id="nope"),
    ):
        with pytest.raises(AdvertiserOnboardingError):
            fn()


def test_all_serving_returns_only_active_records():
    reg = _new_registry()
    # One PENDING, one REJECTED, two ACTIVE.
    submit_application(
        reg, display_name="P", contact_email="p@x", verticals=(),
        advertiser_id="adv-p",
    )
    submit_application(
        reg, display_name="R", contact_email="r@x", verticals=(),
        advertiser_id="adv-r",
    )
    reject_advertiser(
        reg, advertiser_id="adv-r", rejection_reason="no",
    )
    for aid in ("adv-a", "adv-b"):
        submit_application(
            reg, display_name=aid, contact_email=f"{aid}@x", verticals=(),
            advertiser_id=aid,
        )
        approve_advertiser(reg, advertiser_id=aid)
        activate_advertiser(reg, advertiser_id=aid, legal_gate_passed=True)
    serving = reg.all_serving()
    assert [r.advertiser_id for r in serving] == ["adv-a", "adv-b"]


def test_audit_trail_preserved_across_transitions():
    reg = _new_registry()
    rec = submit_application(
        reg, display_name="X", contact_email="x@y", verticals=(),
    )
    approve_advertiser(reg, advertiser_id=rec.advertiser_id)
    activate_advertiser(
        reg, advertiser_id=rec.advertiser_id, legal_gate_passed=True,
    )
    suspend_advertiser(
        reg, advertiser_id=rec.advertiser_id, reason="paused",
    )
    # Every status transition should be visible in the registry log.
    statuses = [r.status for r in reg.records if r.advertiser_id == rec.advertiser_id]
    assert statuses == [
        AdvertiserStatus.PENDING_REVIEW,
        AdvertiserStatus.APPROVED,
        AdvertiserStatus.ACTIVE,
        AdvertiserStatus.SUSPENDED,
    ]
