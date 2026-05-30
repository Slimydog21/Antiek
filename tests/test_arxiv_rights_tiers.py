"""Tests for the authoritative arXiv rights-tier resolver (SPR-02 M1).

The tier table is the audit artifact the whole payout case rides on, so the
acceptance bar is EXHAUSTIVE: every distinct ``<license>`` string the SPR-02
diligence pre-pass enumerated (http/https, 4.0/3.0 ports, CC0, PDM, the
arXiv-default, and the absent case) gets an explicit, non-vacuous assertion,
PLUS null / empty / whitespace / garbage all resolve (never raise) and land in
T3 by deny-by-default. The load-bearing negative — on the current commercial
surface a body may be emitted from Antiek storage for T1 ONLY; a T2 (CC-BY-NC)
body may NOT (body-serve ceiling = {T1}, coherent with
``acquisition.licenses_core`` gating CC-BY-NC as commercial-use-forbidden), and
neither may a T3 body — is tested directly. The ad gate is the same {T1}
ceiling. Finally the reconciliation contract:
``substrate.schemas.documents.classify_tier`` returns IDENTICAL verdicts via
delegation (one source of truth, not a fork).
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.rights import (  # noqa: E402
    RightsTier,
    T3BodyServeError,
    ads_allowed,
    body_servable,
    guard_servable_body,
    resolve_tier,
)
from substrate.schemas.documents import classify_tier  # noqa: E402


# ---------------------------------------------------------------------------
# The EXHAUSTIVE diligence table. Every (license_string, expected_tier) the
# SPR-02 diligence pre-pass observed/enumerated, plus the absent case. The
# `(absent / empty)` census bucket is represented by None / "" / "   ".
# ---------------------------------------------------------------------------

# T1 — redistributable open (CC0 / CC-BY / CC-BY-SA). http+https, 4.0+3.0.
_T1_URIS = [
    "http://creativecommons.org/licenses/by/4.0/",
    "https://creativecommons.org/licenses/by/4.0/",
    "http://creativecommons.org/licenses/by/3.0/",
    "https://creativecommons.org/licenses/by/3.0/",
    "http://creativecommons.org/licenses/by-sa/4.0/",
    "https://creativecommons.org/licenses/by-sa/4.0/",
    "http://creativecommons.org/publicdomain/zero/1.0/",
    "https://creativecommons.org/publicdomain/zero/1.0/",
]

# T2 — CC-BY-NC* (non-commercial). NonCommercial forbids ad-funded serving.
_T2_URIS = [
    "http://creativecommons.org/licenses/by-nc/4.0/",
    "https://creativecommons.org/licenses/by-nc/4.0/",
    "http://creativecommons.org/licenses/by-nc-sa/4.0/",
    "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    # by-nc-nd is also a NonCommercial license -> T2 (the NC bar dominates the
    # ND bar for the ad/commercial question this taxonomy partitions on).
    "http://creativecommons.org/licenses/by-nc-nd/4.0/",
    "https://creativecommons.org/licenses/by-nc-nd/4.0/",
]

# T3 — arXiv-default / unrecognised / restricted (NOT NonCommercial, NOT
# redistributable). ND (no-derivatives, but commercial-OK) is NOT T2: it is
# not a NonCommercial license, so it falls to the deny-by-default floor.
_T3_PRESENT_URIS = [
    "http://creativecommons.org/licenses/by-nd/4.0/",
    "https://creativecommons.org/licenses/by-nd/4.0/",
    "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
    "https://arxiv.org/licenses/nonexclusive-distrib/1.0/",
    "All rights reserved",
    "http://example.com/some-novel-license/9.9/",
    "totally-unknown-garbage",
    # CC Public-Domain Mark is in the diligence enumeration, but arXiv does NOT
    # emit it in its <license> element (documented set: CC0 / CC-BY / CC-BY-SA /
    # CC-BY-NC-SA / CC-BY-NC-ND / nonexclusive-distrib). The arXiv license table
    # therefore does not match PDM, so the authoritative resolver treats it as
    # unrecognised -> T3 by deny-by-default. Biasing an unmatched license to T3
    # (never optimistically to T1) is exactly honesty bar 1 — we do NOT invent a
    # PDM->T1 right the arXiv serving layer would not actually grant.
    "http://creativecommons.org/publicdomain/mark/1.0/",
    "https://creativecommons.org/publicdomain/mark/1.0/",
]

# T3 — the absent/empty deny-by-default bucket. These MUST resolve, not raise.
_T3_ABSENT_URIS = [None, "", "   ", "\t\n"]


@pytest.mark.parametrize("uri", _T1_URIS)
def test_t1_redistributable_open(uri):
    assert resolve_tier(uri) is RightsTier.T1_REDISTRIBUTABLE


@pytest.mark.parametrize("uri", _T2_URIS)
def test_t2_non_commercial(uri):
    """CC-BY-NC* -> T2. The structured NC signal, never the display name."""
    assert resolve_tier(uri) is RightsTier.T2_NON_COMMERCIAL


@pytest.mark.parametrize("uri", _T3_PRESENT_URIS)
def test_t3_present_but_not_redistributable(uri):
    assert resolve_tier(uri) is RightsTier.T3_DEFAULT_UNKNOWN


@pytest.mark.parametrize("uri", _T3_ABSENT_URIS)
def test_t3_absent_is_deny_by_default(uri):
    """LOAD-BEARING: an absent / empty / whitespace license RESOLVES (never
    raises) and lands in T3 — never silently dropped, never promoted to T1."""
    assert resolve_tier(uri) is RightsTier.T3_DEFAULT_UNKNOWN


def test_exhaustive_table_partitions_every_input():
    """Belt-and-suspenders over the whole diligence table: every enumerated
    input resolves to exactly one of the three tiers, and the partition is
    non-trivial (all three tiers are actually exercised)."""
    seen: set[RightsTier] = set()
    for uri in _T1_URIS + _T2_URIS + _T3_PRESENT_URIS + _T3_ABSENT_URIS:
        tier = resolve_tier(uri)
        assert tier in {
            RightsTier.T1_REDISTRIBUTABLE,
            RightsTier.T2_NON_COMMERCIAL,
            RightsTier.T3_DEFAULT_UNKNOWN,
        }
        seen.add(tier)
    assert seen == {
        RightsTier.T1_REDISTRIBUTABLE,
        RightsTier.T2_NON_COMMERCIAL,
        RightsTier.T3_DEFAULT_UNKNOWN,
    }


def test_no_t3_or_t2_input_is_ever_promoted_to_t1():
    """The cardinal-sin guard: NOTHING in the T2/T3 input sets resolves to T1.
    A wrong T3->T1 promotion is a redistribution violation."""
    for uri in _T2_URIS + _T3_PRESENT_URIS + _T3_ABSENT_URIS:
        assert resolve_tier(uri) is not RightsTier.T1_REDISTRIBUTABLE


# ---------------------------------------------------------------------------
# The reconciliation contract: classify_tier DELEGATES, returning identical
# verdicts. One source of truth, not a fork.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri", _T1_URIS + _T2_URIS + _T3_PRESENT_URIS + _T3_ABSENT_URIS
)
def test_classify_tier_delegates_identically(uri):
    """``substrate.schemas.documents.classify_tier`` must return EXACTLY what
    the authoritative resolver returns for every diligence input — proving it
    delegates and has no forked second mapping."""
    assert classify_tier(uri) is resolve_tier(uri)


def test_classify_tier_no_longer_imports_resolve_license_directly():
    """Reconciliation is structural, not just behavioural: classify_tier's
    source now delegates to substrate.rights.resolve_tier and no longer carries
    its own NC/redistributable branch (which keyed off the display name)."""
    import inspect

    from substrate.schemas import documents

    src = inspect.getsource(documents.classify_tier)
    assert "resolve_tier" in src, "classify_tier should delegate to resolve_tier"
    # The old forked branch substring-matched the display name. It must be gone.
    assert "license_name" not in src
    assert 'if "NC" in' not in src


# ---------------------------------------------------------------------------
# The NEGATIVE: on the current commercial surface a body may be emitted from
# Antiek storage for T1 ONLY. A T2 (CC-BY-NC) body may NOT — a commercial
# ad-funded platform emitting an NC body contradicts acquisition.licenses_core,
# which gates CC-BY-NC (redistributable=False, "ad-funded serving is
# commercial"). A T3 body may not either. The ad gate is the same {T1} ceiling.
# ---------------------------------------------------------------------------


def test_body_servable_predicate_t1_only():
    """The body-EMISSION ceiling on the current commercial surface is {T1}: only
    T1 (redistributable open) permits a body to leave storage. T2 (CC-BY-NC
    non-commercial-display) and T3 (and any unknown tier) are NOT body-servable
    here — deny-by-default, coherent with acquisition.licenses_core gating
    CC-BY-NC."""
    assert body_servable(RightsTier.T1_REDISTRIBUTABLE) is True
    assert body_servable(RightsTier.T2_NON_COMMERCIAL) is False
    assert body_servable(RightsTier.T3_DEFAULT_UNKNOWN) is False


def test_guard_passes_t1_body_through():
    body = "the full redistributable paper text"
    assert guard_servable_body(RightsTier.T1_REDISTRIBUTABLE, body) == body


def test_guard_refuses_t2_body():
    """T2 (CC-BY-NC*) is non-commercial-DISPLAY-ONLY. On Antiek's current
    commercial (ad-funded) surface a T2 body may NOT be emitted from storage —
    that would contradict acquisition.licenses_core, which gates CC-BY-NC as
    commercial-use-forbidden. So the body-emission guard RAISES on a T2 body
    (and body_servable(T2) is False). Promoting T2 to body-servable is the
    future state contingent on a non-commercial serving mode + §9.0/counsel."""
    assert body_servable(RightsTier.T2_NON_COMMERCIAL) is False
    with pytest.raises(T3BodyServeError):
        guard_servable_body(RightsTier.T2_NON_COMMERCIAL, "leaked T2 NC body")


def test_guard_refuses_t3_body():
    """LOAD-BEARING NEGATIVE: routing a T3 body through the guard RAISES rather
    than emitting it. T3 is link-back-only; a T3 body never leaves storage."""
    with pytest.raises(T3BodyServeError):
        guard_servable_body(RightsTier.T3_DEFAULT_UNKNOWN, "leaked T3 body")


def test_t2_is_neither_body_servable_nor_ad_eligible():
    """T2 (CC-BY-NC) is NEITHER body-servable NOR ad-eligible on the current
    commercial surface: a commercial ad-funded platform may neither emit an NC
    body nor run ads on it, both flowing from the same NonCommercial bar that
    acquisition.licenses_core enforces. Both predicates are False — conflating
    T2 into the body-servable set is the bug this asserts against."""
    assert body_servable(RightsTier.T2_NON_COMMERCIAL) is False
    assert ads_allowed(RightsTier.T2_NON_COMMERCIAL) is False


def test_guard_refuses_t3_body_even_when_resolved_from_a_real_t3_uri():
    """End-to-end negative: take an actual arXiv-default URI through the
    resolver, then attempt to serve its body — the chokepoint refuses."""
    tier = resolve_tier("http://arxiv.org/licenses/nonexclusive-distrib/1.0/")
    assert tier is RightsTier.T3_DEFAULT_UNKNOWN
    with pytest.raises(T3BodyServeError):
        guard_servable_body(tier, "arXiv-default paper body — link back only")


def test_resolve_tier_is_pure_no_exceptions_on_any_string():
    """Defensive sweep: no string input — however malformed — makes the
    resolver raise. Everything resolves to a tier (deny-by-default to T3)."""
    for uri in ["", " ", "://", "creativecommons", "by-nc", "BY/4.0", "\x00"]:
        assert isinstance(resolve_tier(uri), RightsTier)


def test_t1_tiers_are_the_ad_eligible_ones():
    """Cross-module coherence: the body-servable tier (T1) is exactly the
    ad-eligible tier. (Detail asserted in test_ad_eligibility.py.)"""
    assert body_servable(RightsTier.T1_REDISTRIBUTABLE) is True
    assert ads_allowed(RightsTier.T1_REDISTRIBUTABLE) is True
