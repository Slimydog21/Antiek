"""Tests for the ad-eligibility predicate (SPR-02 M3).

Acceptance: ``ads_allowed(tier) == (tier == T1)``. True ONLY for T1; T2 and T3
are both False. The fairness steelman ("serve NC with ads + attribution") is
refuted in the module docstring; the test pins the refusal as code: a T2 (NC)
tier is NOT ad-eligible.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.rights import RightsTier, ads_allowed  # noqa: E402


def test_t1_is_ad_eligible():
    assert ads_allowed(RightsTier.T1_REDISTRIBUTABLE) is True


def test_t2_non_commercial_is_not_ad_eligible():
    """The refuted steelman, pinned: NC forbids commercial reuse; ad-funded
    serving is commercial; attribution does not cure it. T2 -> no ads."""
    assert ads_allowed(RightsTier.T2_NON_COMMERCIAL) is False


def test_t3_default_unknown_is_not_ad_eligible():
    assert ads_allowed(RightsTier.T3_DEFAULT_UNKNOWN) is False


def test_ads_allowed_equals_tier_is_t1():
    """The acceptance criterion verbatim, over EVERY tier: ads_allowed(t) iff
    t is T1. Exhaustive over the closed RightsTier enum so a future fourth tier
    cannot be silently ad-eligible without this test being updated."""
    for tier in RightsTier:
        assert ads_allowed(tier) == (tier is RightsTier.T1_REDISTRIBUTABLE)


def test_exactly_one_tier_is_ad_eligible():
    """Defensibility: the ad-eligible set is exactly {T1} — not empty, not two
    tiers. Counted, not asserted by inspection."""
    eligible = [t for t in RightsTier if ads_allowed(t)]
    assert eligible == [RightsTier.T1_REDISTRIBUTABLE]
