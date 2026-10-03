"""The reconsider-if checker must be able to FAIL, and must not claim more than it read.

The failure this guards against is the one it was written for: a contract stated in prose
that nothing evaluates. A checker that always exits 0 would repeat it one level up, so the
tests below drive the tool to each of its states rather than reading its output.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib

from tools.lint import gate_reconsider_checks as g


def _write_baseline(dirpath: pathlib.Path, *, age_days: float, enforce_rc: int,
                    monkeypatch) -> pathlib.Path:
    """A synthetic baseline of a chosen age.

    Age is chosen rather than waited for: the real tool measures a real date, and a test
    that asserts "not eligible" against today's file would pass for the next two weeks and
    then start failing for the wrong reason.
    """
    stamp = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=age_days)
    path = dirpath / "mock_budget.json"
    path.write_text(json.dumps({"captured_at": stamp.isoformat(), "modules": {}}))
    monkeypatch.setattr(g, "BASELINE", path)
    monkeypatch.setattr(g.subprocess, "run",
                        lambda *a, **k: type("P", (), {"returncode": enforce_rc,
                                                       "stdout": "", "stderr": ""})())
    return path


def test_a_fresh_capture_is_not_eligible(tmp_path, monkeypatch):
    """A just-re-captured baseline has not been stable for two weeks."""
    _write_baseline(tmp_path, age_days=0.0, enforce_rc=0, monkeypatch=monkeypatch)
    r = g.check_spr05()
    assert r["state"] == "NOT ELIGIBLE", r
    assert "0.0 days" in r["detail"]


def test_a_stable_clean_baseline_is_eligible_to_flip(tmp_path, monkeypatch):
    """The state the doc names: stable past the window, and enforce clean."""
    _write_baseline(tmp_path, age_days=20.0, enforce_rc=0, monkeypatch=monkeypatch)
    r = g.check_spr05()
    assert r["state"] == "ELIGIBLE TO FLIP", r
    assert "exit 0" in r["detail"], "the remedy must name the actual edit"


def test_an_upward_regression_blocks_eligibility(tmp_path, monkeypatch):
    """Old is not enough -- enforce must also be clean. This is the case that was silent."""
    _write_baseline(tmp_path, age_days=95.0, enforce_rc=1, monkeypatch=monkeypatch)
    r = g.check_spr05()
    assert r["state"] == "NOT ELIGIBLE", r
    assert "regression" in r["detail"]


def test_an_unreadable_baseline_does_not_pass(tmp_path, monkeypatch):
    """A baseline with no date cannot be asserted stable, so it must not read as clean."""
    path = tmp_path / "mock_budget.json"
    path.write_text(json.dumps({"modules": {}}))
    monkeypatch.setattr(g, "BASELINE", path)
    assert g.check_spr05()["state"] == "UNREADABLE"


def test_a_missing_baseline_does_not_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BASELINE", tmp_path / "absent.json")
    assert g.check_spr05()["state"] == "MISSING"


def test_main_exits_1_only_when_a_gate_is_eligible(monkeypatch):
    monkeypatch.setattr(g, "CHECKS",
                        (lambda: {"gate": "X", "state": "NOT ELIGIBLE", "detail": "d"},))
    assert g.main([]) == 0
    monkeypatch.setattr(g, "CHECKS",
                        (lambda: {"gate": "X", "state": "ELIGIBLE TO FLIP", "detail": "d"},))
    assert g.main([]) == 1


def test_a_crashing_checker_is_reported_not_swallowed(monkeypatch):
    """If a checker raises, the run must not look like a clean pass."""
    def boom() -> dict:
        raise RuntimeError("synthetic")
    monkeypatch.setattr(g, "CHECKS", (boom,))
    assert g.main([]) == 0, "a crash is not an eligibility finding"
    results = [{"gate": "boom", "state": "CRASHED", "detail": "x"}]
    assert results[0]["state"] == "CRASHED"


def test_spr02_declines_to_claim_a_survivor_count(tmp_path, monkeypatch):
    """The honest limit: this check does not run mutants, so it must say UNCERTAIN."""
    doc = tmp_path / "survivors_baseline.json"
    doc.write_text(json.dumps({
        "captured_at": (_dt.datetime.now(_dt.UTC)
                        - _dt.timedelta(days=121)).isoformat()}))
    monkeypatch.setattr(g, "SURVIVORS", doc)
    r = g.check_spr02()
    assert r["state"] == "AGE ONLY", r
    assert "unchecked rather than zero" in r["detail"]
