"""Deferral docs for Autoresearch/Prime must match shipped substrate."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFERRALS = ROOT / "docs" / "engineering_deferrals.md"


def test_d2_autoresearch_wedge3_tracks_shipped_sweep_substrate() -> None:
    text = DEFERRALS.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert "## D2 — Autoresearch Wedge 3: config sweeps" in text
    assert "Substrate shipped; activation deferred" in text
    assert "Wedge 3 not started" not in text
    assert "substrate/autoresearch/wedge3_sweep.py" in text
    assert "tests/test_autoresearch_wedge3.py" in text
    assert "cohort_too_small" in text
    assert "operator verdict/proposal ledger" in compact
    assert "≥500 graded outcomes" in text
    assert "G6 Wedge 1 ratification" in text


def test_d5_prime_items_track_shipped_gepa_and_env_substrate() -> None:
    text = DEFERRALS.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert "## D5 — Prime Intellect items A and B" in text
    assert "Substrate shipped; activation deferred" in text
    assert "Items A + B not started" not in text
    assert "tools/gepa/optimizer.py" in text
    assert "interfaces/research/environments/parameter_extractor_env.py" in text
    assert "tools/eval/antiek_rubric_to_verifiers.py" in text
    assert "tests/test_gepa.py" in text
    assert "tests/test_parameter_extractor_env.py" in text
    assert "40 passed" in text
    assert "G8 remains the activation/training gate" in compact
    assert "No hosted `prime rl run`" in text
