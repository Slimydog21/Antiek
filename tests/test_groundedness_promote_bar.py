"""Groundedness promote-to-gate bar check (Groundedness Gate SPR-01, M3).

This is the MECHANICAL gate-criterion check that PROMOTE_TO_GATE.md specifies.
It runs the offline harness over the checked-in labeled set and asserts the
four-part promote-to-gate bar from a pure function of the harness JSON — no
judgment call, no hand-typed "0.87 looks fine". A reader can decide met/not-met
from the four comparisons alone, exactly as PROMOTE_TO_GATE.md "How to
mechanically check it" specifies.

Scope discipline: this check enforces the BAR (criterion 1 + 2 + the labeled-set
half of criterion 3). It is NOT a live-gate flip — it does not block a merge on
live Phase-6 groundedness, and it does not touch the scorer backend. The live
merge-blocking gate is SPR-03 territory, behind the activation flag and
criterion 4 (2 weeks of live <1%-failure traces). This check only asserts: IF
we claim the labeled-set bar is met, the harness numbers back it.

The thresholds below are NAMED CONSTANTS matching PROMOTE_TO_GATE.md verbatim —
not magic numbers. If the document's bar changes, these constants change with
it; nothing else in this file does.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.eval.groundedness.harness import (
    load_labeled,
    score_labeled_set,
)
from substrate.eval.groundedness.harness import main as harness_main

# --- The promote-to-gate bar (PROMOTE_TO_GATE.md, criterion 1 + 2) ------------
# Criterion 1: minimum labeled-set size.
MIN_TOTAL_CASES = 40
MIN_HALLUCINATED = 15
MIN_FAITHFUL = 15  # PROMOTE_TO_GATE.md criterion 1: "at least 15 faithful"
# Criterion 2: separation. rank-AUC + the two secondary guards.
MIN_AUC = 0.85
MIN_MEAN_GAP = 0.30
MIN_THRESHOLD_ACCURACY = 0.85

# Criterion 3: the densely-cited-hallucination class must be present. The
# fixture tags each densely-cited case in its `note` field with the literal
# marker below so a maintainer can confirm the class is genuinely represented
# (not just N-hallucinations padded with easy ones).
DENSELY_CITED_MARKER = "DENSELY-CITED-HALLUCINATION"
MIN_DENSELY_CITED = 5  # PROMOTE_TO_GATE.md criterion 3: >=5 of the class

_LABELED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "groundedness_labeled.jsonl"
)


def _bar_report():
    """Run the harness over the checked-in labeled set and return its
    SeparationReport-as-dict. Single source of truth for every check below."""
    cases = load_labeled(str(_LABELED_FIXTURE))
    report, _rows = score_labeled_set(cases)
    return report, cases


def test_promote_bar_criterion1_minimum_set_size():
    """PROMOTE_TO_GATE.md criterion 1: N >= 40 total, >= 15 hallucinations,
    >= 15 faithful. The separation statistic must not be computed on a toy set."""
    report, _ = _bar_report()
    total = report.n_faithful + report.n_hallucinated
    assert total >= MIN_TOTAL_CASES, (
        f"criterion 1 FAILED: total labeled cases {total} < {MIN_TOTAL_CASES}. "
        "Expand tests/fixtures/groundedness_labeled.jsonl."
    )
    assert report.n_hallucinated >= MIN_HALLUCINATED, (
        f"criterion 1 FAILED: n_hallucinated {report.n_hallucinated} "
        f"< {MIN_HALLUCINATED}."
    )
    assert report.n_faithful >= MIN_FAITHFUL, (
        f"criterion 1 FAILED: n_faithful {report.n_faithful} < {MIN_FAITHFUL}."
    )


def test_promote_bar_criterion2_separation_threshold():
    """PROMOTE_TO_GATE.md criterion 2: rank-AUC >= 0.85 AND mean_gap >= 0.30
    AND threshold_accuracy >= 0.85.

    NOTE FOR MAINTAINERS (the SPR-01 finding): as of the SPR-01 expansion the
    LEXICAL backend clears auc and mean_gap but FAILS threshold_accuracy on the
    hard set (the densely-cited-hallucination class slips past threshold). This
    test currently expects the bar to be MET once SPR-02 ships a real entailment
    backend. Until then, this assertion is marked xfail(strict) BELOW so the
    failure mode is VISIBLE and TRACKED, not silently green. See the dedicated
    test_promote_bar_lexical_finds_the_gap for the documented gap.
    """
    report, _ = _bar_report()
    # auc + mean_gap must hold even on the lexical backend — these are the
    # separation statistics, not the classification accuracy.
    assert report.auc >= MIN_AUC, (
        f"criterion 2 FAILED: rank-AUC {report.auc:.4f} < {MIN_AUC}."
    )
    assert report.mean_gap >= MIN_MEAN_GAP, (
        f"criterion 2 FAILED: mean_gap {report.mean_gap:.4f} < {MIN_MEAN_GAP}."
    )


@pytest.mark.xfail(
    reason=(
        "SPR-01 documented finding: the lexical backend's threshold_accuracy "
        "on the expanded hard set is below the 0.85 bar (the densely-cited-"
        "hallucination class slips past threshold). This is the load-bearing "
        "justification for SPR-02 (a real entailment backend). The xfail flips "
        "to xpass when SPR-02 lands. See test_promote_bar_lexical_finds_the_gap."
    ),
    strict=True,
    raises=AssertionError,
)
def test_promote_bar_criterion2_threshold_accuracy():
    """The threshold_accuracy leg of criterion 2. EXPECTED TO FAIL on the
    lexical backend (strict xfail) — that failure IS the SPR-01 finding."""
    report, _ = _bar_report()
    assert report.threshold_accuracy >= MIN_THRESHOLD_ACCURACY, (
        f"criterion 2 (threshold_accuracy) FAILED: {report.threshold_accuracy:.4f} "
        f"< {MIN_THRESHOLD_ACCURACY} on the lexical backend — this is the "
        "documented SPR-01 gap; SPR-02's entailment backend closes it."
    )


def test_promote_bar_criterion3_densely_cited_class_present():
    """PROMOTE_TO_GATE.md criterion 3: the labeled set includes the
    densely-cited-hallucination class — a high-citation-density claim that
    fails entailment. Verified by counting cases whose note carries the
    DENSELY-CITED marker; a maintainer must confirm each is genuinely
    high-overlap + hallucinated (the marker documents which cases assert it)."""
    _report, cases = _bar_report()
    tagged = [c for c in cases if DENSELY_CITED_MARKER in c.note.upper()]
    assert len(tagged) >= MIN_DENSELY_CITED, (
        f"criterion 3 FAILED: only {len(tagged)} densely-cited-hallucination "
        f"cases tagged (need >= {MIN_DENSELY_CITED}). Each must be a "
        "high-claim<->chunk-overlap hallucination that a citation-density "
        "gate would get wrong."
    )
    # And every tagged case must actually be labeled hallucinated — a tagged
    # faithful case would be a documentation bug, not a valid member of the class.
    mislabeled = [c for c in tagged if c.label != "hallucinated"]
    assert not mislabeled, (
        "criterion 3 FAILED: cases tagged densely-cited-hallucination but "
        f"labeled faithful: {[c.case_id for c in mislabeled]}"
    )


def test_promote_bar_lexical_finds_the_gap():
    """The SPR-01 load-bearing finding, asserted as a regression guard.

    On the expanded hard set the lexical backend's threshold_accuracy is
    BELOW the promote bar — the densely-cited-hallucination class systematically
    slips past threshold. This test PASSES while that gap exists and FAILS if
    the gap closes WITHOUT a real entailment backend landing (which would mean
    someone weakened the hard set to make lexical look good — the exact
    fake-green PROMOTE_TO_GATE.md forbids).

    If SPR-02's entailment backend closes the gap for real, this test will
    fail at that point and should be replaced with a positive assertion that
    the new backend clears the bar.
    """
    report, _ = _bar_report()
    assert report.threshold_accuracy < MIN_THRESHOLD_ACCURACY, (
        f"SPR-01 finding regression: lexical threshold_accuracy "
        f"{report.threshold_accuracy:.4f} now CLEARS the {MIN_THRESHOLD_ACCURACY} "
        "bar. If a real entailment backend landed (SPR-02), update this test. "
        "If not, the hard set was likely weakened to make the cheap backend "
        "look good — restore the densely-cited-hallucination class."
    )


def test_promote_bar_harness_json_exposes_all_four_metrics():
    """The bar must be mechanically decidable from the harness --json output
    alone (PROMOTE_TO_GATE.md "How to mechanically check it"). Guards against
    a future harness refactor that drops a metric and silently makes the bar
    undecidable."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="r", suffix=".out", delete=False) as tf:
        capture_path = tf.name
    try:
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = harness_main(["--labeled", str(_LABELED_FIXTURE), "--json"])
        assert rc == 0
        out = buf.getvalue()
        payload = json.loads(out)
        labeled = payload["labeled"]
        for key in (
            "n_faithful",
            "n_hallucinated",
            "auc",
            "mean_gap",
            "threshold_accuracy",
        ):
            assert key in labeled, (
                f"harness --json dropped metric '{key}' — the promote bar is "
                "no longer mechanically decidable from harness output."
            )
    finally:
        Path(capture_path).unlink(missing_ok=True)
