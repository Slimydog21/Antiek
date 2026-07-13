"""Tests for the Midnight Oil scope-adherence axis (ask #13).

The NEGATIVE complement to goal_delivery #1938 (positive coverage). Exercises:
on_scope/drifted/fully_off_scope/unknown verdicts, on_scope_ratio, off-scope
finding listing, all-glue exclusion, min_goal_overlap, custom threshold,
purity/immutability, validation. Fixtures use BARE NONSENSE TOKENS.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.mo_scope_adherence import (
    FindingScope,
    ScopeAdherenceError,
    ScopeAdherenceReport,
    measure_scope_adherence,
)

# --- on_scope (control held) ----------------------------------------------


def test_on_scope_all_findings_within_goals() -> None:
    goals = ["alpha beta", "gamma delta"]
    findings = ["alpha found", "gamma result", "beta and gamma"]
    r = measure_scope_adherence(goals, findings)
    assert r.verdict == "on_scope"
    assert r.on_scope_count == 3
    assert r.off_scope_count == 0
    assert r.on_scope_ratio == 1.0
    assert r.off_scope_findings == ()
    assert r.authority == "advisory"


def test_on_scope_at_threshold() -> None:
    # 5 findings, 4 on-scope (80%); default threshold 85% -> drifted.
    # Use 4/4 on-scope instead -> 100% -> on_scope.
    goals = ["alpha"]
    findings = ["alpha one", "alpha two", "alpha three", "alpha four"]
    r = measure_scope_adherence(goals, findings)
    assert r.on_scope_ratio == 1.0
    assert r.verdict == "on_scope"


# --- drifted (partial control failure) ------------------------------------


def test_drifted_some_findings_off_scope() -> None:
    goals = ["alpha beta"]
    # 5 findings: 3 on-scope (share alpha/beta), 2 off-scope (zzz only).
    # on_scope_ratio = 3/5 = 0.60 < 0.85 -> drifted.
    findings = ["alpha x", "beta y", "alpha beta", "zzz one", "zzz two"]
    r = measure_scope_adherence(goals, findings)
    assert r.on_scope_ratio == pytest.approx(0.60)
    assert r.verdict == "drifted"
    assert r.off_scope_count == 2
    assert len(r.off_scope_findings) == 2
    assert r.off_scope_findings == ("zzz one", "zzz two")


def test_drifted_off_scope_findings_listed_for_review() -> None:
    goals = ["alpha"]
    findings = ["alpha one", "zzz drift", "alpha two", "yyy drift"]
    r = measure_scope_adherence(goals, findings)
    assert r.verdict == "drifted"
    assert r.off_scope_findings == ("zzz drift", "yyy drift")


# --- fully_off_scope (total runaway) --------------------------------------


def test_fully_off_scope_no_finding_addresses_any_goal() -> None:
    goals = ["alpha beta"]
    findings = ["zzz one", "yyy two", "xxx three"]
    r = measure_scope_adherence(goals, findings)
    assert r.on_scope_ratio == 0.0
    assert r.verdict == "fully_off_scope"
    assert r.off_scope_count == 3
    assert r.on_scope_count == 0


# --- unknown (defer, never fabricated) ------------------------------------


def test_unknown_when_no_measurable_findings() -> None:
    goals = ["alpha beta"]
    findings = ["the and of", "is was be"]  # all-glue
    r = measure_scope_adherence(goals, findings)
    assert r.unmeasurable_count == 2
    assert r.on_scope_ratio is None
    assert r.verdict == "unknown"


def test_unknown_when_no_findings() -> None:
    goals = ["alpha beta"]
    r = measure_scope_adherence(goals, [])
    assert r.on_scope_ratio is None
    assert r.verdict == "unknown"


# --- all-glue exclusion ---------------------------------------------------


def test_all_glue_excluded_from_ratio() -> None:
    # 1 on-scope + 1 all-glue; ratio = 1/1 = 1.0 (the glue finding is unmeasurable).
    goals = ["alpha"]
    findings = ["alpha found", "the and of"]
    r = measure_scope_adherence(goals, findings)
    assert r.on_scope_ratio == 1.0
    assert r.unmeasurable_count == 1
    assert r.on_scope_count == 1
    assert r.verdict == "on_scope"


# --- goal pool construction -----------------------------------------------


def test_goal_pool_unions_all_goals() -> None:
    # goal1 = {alpha, beta}, goal2 = {gamma, delta}; pool = 4 terms.
    # finding "alpha gamma" on-scope (2 in pool); "zzz" off-scope.
    goals = ["alpha beta", "gamma delta"]
    findings = ["alpha gamma", "zzz yyy"]
    r = measure_scope_adherence(goals, findings)
    assert r.goal_pool_size == 4
    assert r.on_scope_count == 1
    assert r.off_scope_count == 1


# --- min_goal_overlap -----------------------------------------------------


def test_min_goal_overlap_raises_on_zero() -> None:
    with pytest.raises(ScopeAdherenceError, match="min_goal_overlap"):
        measure_scope_adherence(["alpha"], ["alpha"], min_goal_overlap=0)


def test_custom_min_goal_overlap() -> None:
    # finding "alpha zzz" shares 1 term with goal "alpha beta gamma".
    # min_overlap=1 -> on_scope; min_overlap=2 -> off_scope.
    goals = ["alpha beta gamma"]
    findings = ["alpha zzz"]
    loose = measure_scope_adherence(goals, findings, min_goal_overlap=1)
    assert loose.on_scope_count == 1
    strict = measure_scope_adherence(goals, findings, min_goal_overlap=2)
    assert strict.off_scope_count == 1


# --- custom adherence threshold -------------------------------------------


def test_custom_adherence_threshold() -> None:
    # 3 on-scope / 5 total = 0.60.
    goals = ["alpha"]
    findings = ["alpha one", "alpha two", "alpha three", "zzz one", "zzz two"]
    loose = measure_scope_adherence(goals, findings, adherence_threshold=0.50)
    assert loose.verdict == "on_scope"  # 0.60 >= 0.50
    strict = measure_scope_adherence(goals, findings, adherence_threshold=0.70)
    assert strict.verdict == "drifted"  # 0.60 < 0.70


# --- per-finding evidence -------------------------------------------------


def test_per_finding_scope_recorded() -> None:
    goals = ["alpha beta"]
    findings = ["alpha one", "zzz two"]
    r = measure_scope_adherence(goals, findings)
    by_finding = {f.finding: f for f in r.finding_scopes}
    assert by_finding["alpha one"].verdict == "on_scope"
    assert by_finding["alpha one"].goal_overlap_count == 1
    assert by_finding["zzz two"].verdict == "off_scope"
    assert by_finding["zzz two"].goal_overlap_count == 0


# --- validation -----------------------------------------------------------


def test_empty_goals_raises() -> None:
    with pytest.raises(ScopeAdherenceError, match="at least one goal"):
        measure_scope_adherence([], ["alpha"])


def test_empty_goal_string_raises() -> None:
    with pytest.raises(ScopeAdherenceError, match="non-empty"):
        measure_scope_adherence(["  "], ["alpha"])


def test_empty_finding_string_raises() -> None:
    with pytest.raises(ScopeAdherenceError, match="non-empty"):
        measure_scope_adherence(["alpha"], [""])


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_bad_threshold_raises(bad: float) -> None:
    with pytest.raises(ScopeAdherenceError, match="adherence_threshold"):
        measure_scope_adherence(["alpha"], ["alpha"], adherence_threshold=bad)


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_deterministic() -> None:
    goals = ["alpha beta"]
    findings = ["alpha one", "zzz two"]
    r1 = measure_scope_adherence(goals, findings)
    r2 = measure_scope_adherence(goals, findings)
    assert dataclasses.is_dataclass(r1)
    assert isinstance(r1.finding_scopes, tuple)
    assert all(isinstance(f, FindingScope) for f in r1.finding_scopes)
    assert r1 == r2  # deterministic
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.verdict = "tampered"  # type: ignore[misc]
    assert isinstance(r1, ScopeAdherenceReport)


def test_notes_are_non_empty_and_auditable() -> None:
    r = measure_scope_adherence(["alpha"], ["alpha one"])
    assert isinstance(r.notes, tuple)
    assert len(r.notes) >= 5
    assert all(isinstance(n, str) and n for n in r.notes)
