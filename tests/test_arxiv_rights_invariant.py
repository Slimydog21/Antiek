"""SPR-02 M4 — the CI invariant test for the rights/serve boundary.

Two halves, both mechanically checkable:

1. **The tier-table invariant** — exhaustive over the ``RightsTier`` enum:
   ``body_servable(t) == (t is T1)`` and ``ads_allowed(t) == (t is T1)``
   for EVERY enum member (not a hand-picked subset), plus a sweep of
   unknown/garbage/empty license strings all resolving to T3 and being
   NOT-body-servable (deny-by-default), plus the synthetic-drift raise.

2. **The bypass-scanner invariant** — ``tools/lint/serve_guard_check.py`` is
   invoked PROGRAMMATICALLY here (not only as a CI shell step) and asserted to
   report ZERO violations on the current tree, so the boundary is enforced even
   under a pytest-only run. And — rigor #3 — we prove the scanner has TEETH by
   feeding it a synthetic tree containing a forbidden ``serve_full_text(`` call
   and asserting it flags exactly that line (a vacuous green scanner is worse
   than none).
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
from pathlib import Path

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
from tools.lint import serve_guard_check  # noqa: E402

# The body-servable ceiling and the ad ceiling, stated here as the literal
# invariant the test enforces against the implementation. If the implementation
# (``_BODY_SERVABLE_TIERS`` / ``_AD_ELIGIBLE_TIERS``) ever drifts from these, the
# exhaustive sweeps below go red — this file IS the spec made executable.
_EXPECTED_BODY_SERVABLE = {RightsTier.T1_REDISTRIBUTABLE}
_EXPECTED_AD_ELIGIBLE = {RightsTier.T1_REDISTRIBUTABLE}


# ── 1a. Exhaustive over the enum ────────────────────────────────────


def test_body_servable_is_exactly_t1_over_the_whole_enum():
    """EXHAUSTIVE: for EVERY RightsTier member, body_servable is True iff the
    tier is T1 — the {T1} body-serve ceiling on the current commercial surface.
    Iterating the enum (not a literal list) means a NEW tier added later is
    automatically covered — it must be explicitly classified. T2 (CC-BY-NC) is
    NOT body-servable here, coherent with acquisition.licenses_core gating
    CC-BY-NC."""
    for tier in RightsTier:
        assert body_servable(tier) is (tier is RightsTier.T1_REDISTRIBUTABLE), tier
        assert body_servable(tier) is (tier in _EXPECTED_BODY_SERVABLE), tier


def test_ads_allowed_is_exactly_t1_over_the_whole_enum():
    """EXHAUSTIVE: ads are T1-only across every enum member. The ad ceiling is
    strictly tighter than the body ceiling — that gap (T2 servable, not
    ad-eligible) is the whole NonCommercial point."""
    for tier in RightsTier:
        assert ads_allowed(tier) is (tier in _EXPECTED_AD_ELIGIBLE), tier


def test_ad_ceiling_is_a_subset_of_the_body_ceiling():
    """Coherence: anything ad-eligible must be body-servable (you cannot run ads
    on a body you may not even emit). On the current commercial surface the two
    ceilings COINCIDE at {T1} — the future gated->permissive flip
    ({T1}->{T1,T2}) is what would split them (a T2 body becomes display-servable
    while ads stay T1-only)."""
    body = {t for t in RightsTier if body_servable(t)}
    ads = {t for t in RightsTier if ads_allowed(t)}
    assert ads <= body  # subset (today: equal at {T1})
    assert ads == {RightsTier.T1_REDISTRIBUTABLE}
    assert body == {RightsTier.T1_REDISTRIBUTABLE}


# ── 1b. Garbage/unknown licenses → T3 → not body-servable ───────────

_GARBAGE_LICENSES = [
    None,
    "",
    "   ",
    "\t\n",
    "not-a-url",
    "http://example.com/made-up/license/1.0/",
    "all rights reserved",
    "creativecommons",  # bare host fragment, no license family
    "by-nc",  # a fragment, not a resolvable URI
    "\x00\x01garbage",
    "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",  # the arXiv default
]


@pytest.mark.parametrize("lic", _GARBAGE_LICENSES)
def test_unknown_or_garbage_license_resolves_t3_and_is_not_body_servable(lic):
    """Deny-by-default: anything not a recognised redistributable/NC license —
    including the absent case and raw garbage — resolves to T3 and is NOT
    body-servable. No input promotes itself out of the floor."""
    tier = resolve_tier(lic)
    assert tier is RightsTier.T3_DEFAULT_UNKNOWN
    assert body_servable(tier) is False
    assert ads_allowed(tier) is False


# ── 1c. The synthetic-drift raise at the predicate layer ────────────


def test_guard_servable_body_raises_on_every_non_servable_tier():
    """The enforcing wrapper raises for EXACTLY the non-body-servable tiers and
    passes the body through for the servable ones. Exhaustive over the enum."""
    body = "a body"
    for tier in RightsTier:
        if tier in _EXPECTED_BODY_SERVABLE:
            assert guard_servable_body(tier, body) == body
        else:
            with pytest.raises(T3BodyServeError):
                guard_servable_body(tier, body)


def test_drift_case_t3_uri_through_resolver_then_guard_raises():
    """End-to-end at the pure layer: a real arXiv-default URI resolves to T3 and
    a body routed through the guard for that tier raises. (The DB-level drift
    case lives in test_serve_guard.py.)"""
    tier = resolve_tier("http://arxiv.org/licenses/nonexclusive-distrib/1.0/")
    assert tier is RightsTier.T3_DEFAULT_UNKNOWN
    with pytest.raises(T3BodyServeError):
        guard_servable_body(tier, "leaked arXiv-default body")


# ── 2. The bypass scanner: clean on the tree + has teeth ────────────


def test_scanner_reports_zero_violations_on_the_current_tree():
    """The boundary is enforced even under a pytest-only run: invoke the scanner
    programmatically and assert ZERO violations. This is the same check the CI
    shell step runs, made resilient to a CI that forgets the step."""
    violations = serve_guard_check.find_violations()
    assert violations == [], "serve_full_text() called outside the guard:\n" + "\n".join(
        violations
    )


def test_scanner_catches_an_injected_bypass():
    """RIGOR #3 — prove the scanner is not vacuously green: point it at a
    synthetic tree containing a direct ``serve_full_text(`` call in a non-allowed
    module and assert it flags exactly that file:line. A scanner that cannot
    catch the violation it exists to catch is worse than no scanner."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # A non-allowed, non-test module that BYPASSES the guard.
        offender = root / "interfaces" / "research" / "api" / "rogue_endpoint.py"
        offender.parent.mkdir(parents=True)
        offender.write_text(
            textwrap.dedent(
                """\
                from substrate.books.serve import serve_full_text

                def handler(con, document_id):
                    return serve_full_text(con, document_id)
                """
            ),
            encoding="utf-8",
        )
        # The allowlisted files + a guarded call + a test file must NOT flag.
        # The guard's real home is substrate/books/serve_guard.py (allowlisted);
        # it legitimately calls the raw gate.
        guard = root / "substrate" / "books" / "serve_guard.py"
        guard.parent.mkdir(parents=True)
        guard.write_text(
            "def g(con, d):\n    return serve_full_text(con, d)\n", encoding="utf-8"
        )
        guarded_caller = root / "interfaces" / "research" / "api" / "books.py"
        guarded_caller.write_text(
            "def h(con, d):\n    return serve_full_text_guarded(con, d)\n",
            encoding="utf-8",
        )
        test_file = root / "tests" / "test_thing.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "def test_x(con, d):\n    serve_full_text(con, d)\n", encoding="utf-8"
        )

        violations = serve_guard_check.find_violations(root=root)

    assert len(violations) == 1, violations
    v = violations[0]
    assert v.startswith("interfaces/research/api/rogue_endpoint.py:")
    assert "serve_full_text(" in v
    # Only the rogue file is flagged. We check the FLAGGED path (the prefix
    # before ':') — not the message body, which legitimately names serve_guard.py
    # as the suggested fix.
    flagged_paths = {line.split(":", 1)[0] for line in violations}
    assert flagged_paths == {"interfaces/research/api/rogue_endpoint.py"}


def test_scanner_does_not_flag_the_guarded_call_form():
    """``serve_full_text_guarded(`` (the allowed wrapper) is NOT a violation even
    though its name has ``serve_full_text`` as a prefix — the scanner matches the
    exact callee name, not a substring."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = root / "interfaces" / "research" / "api" / "ok_endpoint.py"
        f.parent.mkdir(parents=True)
        f.write_text(
            "def h(con, d):\n    return serve_full_text_guarded(con, d)\n",
            encoding="utf-8",
        )
        assert serve_guard_check.find_violations(root=root) == []


def test_scanner_catches_an_aliased_import_bypass():
    """DEFECT-2 RIGOR: an ALIASED import is a real "grep proves no bypass" hole —
    ``from substrate.books.serve import serve_full_text as _sft`` makes the call
    node's callee name ``_sft``, not ``serve_full_text``. The scanner must walk
    the imports, bind ``_sft`` to the symbol, and flag the ``_sft(...)`` call. We
    construct exactly that module and assert it flags the call line (line 4)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        offender = root / "interfaces" / "research" / "api" / "aliased_bypass.py"
        offender.parent.mkdir(parents=True)
        offender.write_text(
            textwrap.dedent(
                """\
                from substrate.books.serve import serve_full_text as _sft


                def handler(con, document_id):
                    return _sft(con, document_id)
                """
            ),
            encoding="utf-8",
        )
        violations = serve_guard_check.find_violations(root=root)

    assert len(violations) == 1, violations
    v = violations[0]
    # The flagged line is the call site (the aliased call), not the import.
    assert v.startswith("interfaces/research/api/aliased_bypass.py:5:"), v
    flagged_paths = {line.split(":", 1)[0] for line in violations}
    assert flagged_paths == {"interfaces/research/api/aliased_bypass.py"}
