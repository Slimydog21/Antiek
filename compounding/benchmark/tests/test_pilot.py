"""AFF SPR-09 PILOT — propose_parameters derives the bar from observed CV.

``propose_parameters`` is a PURE function; these tests pin its derivation so the
operator ratifies a number with a known rationale (§0.2). The live pilot RUN is
exercised lightly (it drives the mock harness) and marked slow.
"""

from __future__ import annotations

import pytest

from compounding.benchmark.pilot import (
    MAX_PROPOSED_N,
    MIN_PROPOSED_N,
    propose_parameters,
)


def test_zero_cv_clamps_n_and_flags_degenerate():
    """A zero-variance (mock-path) pilot clamps n to the minimum and says so in
    the derivation — the operator must not mistake it for a powered run."""
    p = propose_parameters({"token_cost_usd": 0.0}, cold_means={"token_cost_usd": 0.0})
    assert p.n == MIN_PROPOSED_N
    assert p.material_floor == 0.0
    assert p.control_tolerance == 0.0
    assert "zero-variance" in p.derivation or "CV is 0" in p.derivation


def test_n_grows_with_cv():
    """Higher observed CV demands more runs for the same target half-width."""
    low = propose_parameters({"token_cost_usd": 0.10}, cold_means={"token_cost_usd": 0.50})
    high = propose_parameters({"token_cost_usd": 0.40}, cold_means={"token_cost_usd": 0.50})
    assert high.n > low.n
    assert MIN_PROPOSED_N <= low.n <= MAX_PROPOSED_N
    assert MIN_PROPOSED_N <= high.n <= MAX_PROPOSED_N


def test_floor_outside_noise_band_and_tolerance_tighter():
    """The material floor sits strictly outside the cold-arm noise band (2·CV·
    cold_mean) and the control tolerance is tighter than the floor (§2)."""
    p = propose_parameters({"token_cost_usd": 0.20}, cold_means={"token_cost_usd": 1.00})
    # 2 * 0.20 * 1.00 = 0.40
    assert abs(p.material_floor - 0.40) < 1e-9
    assert p.control_tolerance < p.material_floor
    assert abs(p.control_tolerance - 0.20) < 1e-9


def test_n_derivation_formula():
    """n = ceil((z·CV/target)²) with z=1.96, target=0.10 → for CV=0.20,
    (1.96·0.2/0.1)² = 3.92² ≈ 15.37 → 16."""
    p = propose_parameters({"token_cost_usd": 0.20}, cold_means={"token_cost_usd": 1.00})
    assert p.n == 16


@pytest.mark.slow
def test_run_pilot_drives_harness(tmp_path):
    """The pilot RUN drives the real mock harness and reports CV. Slow (multiple
    arm runs); excluded from the fast CI suite via the ``slow`` marker."""
    import os

    from compounding.benchmark.pilot import run_pilot
    from compounding.benchmark.question_set import load_question_set

    qs = load_question_set()
    rep = [qs.headline_questions()[0]] + qs.control_questions()[:1]
    report = run_pilot(
        rep,
        events_dir=os.path.join(tmp_path, "ev"),
        graphs_dir=os.path.join(tmp_path, "gr"),
        runs_per_cell=2,
    )
    assert set(report.cv) == {"token_cost_usd", "sources_fetched", "wall_ms"}
    # mock path: no dispatch cost → token cost CV is 0.
    assert report.cv["token_cost_usd"] == 0.0


# ── ACV SPR-06 — the pilot-report artifact is persisted (M4 / B3) ─────────────


def test_write_pilot_report_persists_artifact(tmp_path):
    """``write_pilot_report`` persists the observed CV + derived params + a
    content-addressed pilot_report_id that --ratified later references."""
    import json

    from compounding.benchmark.pilot import ProposedParameters
    from compounding.benchmark.run import write_pilot_report

    class _Rep:
        cv = {"token_cost_usd": 0.0, "sources_fetched": 0.0, "wall_ms": 0.26}
        cold_means = {"token_cost_usd": 0.0, "sources_fetched": 0.0, "wall_ms": 0.25}
        cell_stats: list = []
        questions = ["Q-HI-E1", "Q-ZC-01"]
        runs_per_cell = 5

    proposal = ProposedParameters(n=5, material_floor=0.0, control_tolerance=0.0, derivation="d")
    path = str(tmp_path / "pilot_report.json")
    pid = write_pilot_report(_Rep(), proposal, path=path, frozen_sha="sha256:abc", git_sha="deadbee")

    assert pid.startswith("pilot:")
    data = json.loads((tmp_path / "pilot_report.json").read_text())
    assert data["kind"] == "pilot_report"
    assert data["observed_cv"]["wall_ms"] == 0.26
    assert data["proposed_parameters"]["n"] == 5
    assert data["pilot_report_id"] == pid
    assert data["ratified"] is False  # the operator flips this by RUNNING --ratified


def test_pilot_report_id_is_content_addressed(tmp_path):
    """Same inputs → same pilot_report_id (so --ratification-ref is stable);
    different CV → different id (a re-run with new variance is a new report)."""
    from compounding.benchmark.pilot import ProposedParameters
    from compounding.benchmark.run import write_pilot_report

    class _Rep:
        cv = {"token_cost_usd": 0.0}
        cold_means = {"token_cost_usd": 0.0}
        cell_stats: list = []
        questions = ["Q-HI-E1"]
        runs_per_cell = 5

    prop = ProposedParameters(n=5, material_floor=0.0, control_tolerance=0.0, derivation="d")
    a = write_pilot_report(_Rep(), prop, path=str(tmp_path / "a.json"), frozen_sha="s", git_sha="g")
    b = write_pilot_report(_Rep(), prop, path=str(tmp_path / "b.json"), frozen_sha="s", git_sha="g2")
    assert a == b, "same frozen_sha + cv + proposal → same id (git_sha excluded from the digest)"

    class _Rep2(_Rep):
        cv = {"token_cost_usd": 0.5}

    c = write_pilot_report(_Rep2(), prop, path=str(tmp_path / "c.json"), frozen_sha="s", git_sha="g")
    assert c != a, "different observed CV → different id"
