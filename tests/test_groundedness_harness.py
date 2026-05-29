"""Offline groundedness harness (Foundation v2 SPR-02, M3) — gate G5.

The harness must (a) run the scorer over a hand-labeled set and report a
separation statistic, (b) run over real on-disk Phase-6 traces and
produce a distribution, and (c) ERROR when the labeled set has no
hallucinations (non-vacuity — Rigor card 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.eval.groundedness.harness import (
    FAITHFUL,
    HALLUCINATED,
    LabeledSetError,
    load_labeled,
    main as harness_main,
    score_labeled_set,
    score_traces,
)

_LABELED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "groundedness_labeled.jsonl"
)


def test_groundedness_harness_labeled_set_separates():
    """The checked-in labeled set separates faithful from hallucinated:
    faithful mean clearly above hallucinated mean, AUC well above 0.5."""
    cases = load_labeled(str(_LABELED_FIXTURE))
    report, rows = score_labeled_set(cases)
    assert report.n_faithful >= 1
    assert report.n_hallucinated >= 1  # the set contains real hallucinations
    assert report.faithful_mean > report.hallucinated_mean
    assert report.mean_gap > 0.2
    assert report.auc > 0.5
    # The densely-cited lie (Rigor card 2 steelman-then-break) must be
    # caught: it is in the fixture and must score below threshold.
    dense_lie = next(c for c, _s, _ok in rows if c.case_id == "hallu-densely-cited-lie")
    dense_lie_score = next(s for c, s, _ok in rows if c is dense_lie)
    assert dense_lie_score < report.threshold


def test_groundedness_harness_labeled_set_has_a_real_hallucination():
    """Rigor card 3: the labeled set genuinely contains >=1 hallucination
    that the scorer is required to catch."""
    cases = load_labeled(str(_LABELED_FIXTURE))
    hallu = [c for c in cases if c.label == HALLUCINATED]
    assert len(hallu) >= 1
    # And the scorer actually scores at least one of them as unsupported.
    _report, rows = score_labeled_set(cases)
    caught = [c for c, _s, supported in rows
              if c.label == HALLUCINATED and not supported]
    assert len(caught) >= 1


def test_groundedness_harness_errors_without_negatives(tmp_path):
    """Non-vacuity gate: a labeled set with no hallucinations is rejected —
    a separation statistic over faithful-only claims is meaningless."""
    faithful_only = tmp_path / "faithful_only.jsonl"
    faithful_only.write_text(
        json.dumps({
            "id": "f1", "label": FAITHFUL, "claim": "x is y",
            "cited_chunk_ids": ["c"], "chunk_texts": {"c": "x is y"},
        }) + "\n",
        encoding="utf-8",
    )
    cases = load_labeled(str(faithful_only))
    with pytest.raises(LabeledSetError):
        score_labeled_set(cases)


def test_groundedness_harness_runs_over_real_traces(tmp_path):
    """G5: the harness runs over on-disk Phase-6 traces and produces a
    per-synthesis distribution. We write a real synthesize.delivered
    trace through the event log, then score it offline."""
    import os

    events_dir = tmp_path / "events"
    events_dir.mkdir()
    os.environ_backup = dict(os.environ)
    # Emit a real synthesize.delivered event to disk.
    from substrate.event_log import emit_typed
    from substrate.schemas.events import (
        ConstraintCompliance,
        SynthesizeDeliveredPayload,
        ThesisComponent,
    )

    payload = SynthesizeDeliveredPayload(
        thesis_summary="The radar achieves 24 dB of gain.",
        implicit_recommendation="proceed",  # type: ignore[arg-type]
        thesis_components=[
            ThesisComponent(
                claim="The radar achieves 24 dB of gain.",
                confidence="high",
                supporting_chunk_ids=["chunk-radar-1"],
            ),
        ],
        constraint_compliance=ConstraintCompliance(hard_constraints_satisfied=True),
        conviction_level=0.8,
    )
    emit_typed(
        "inv-trace-1", payload, phase=6, role="synthesizer",
        events_dir=str(events_dir),
    )

    rows = score_traces(str(events_dir))
    assert len(rows) == 1
    row = rows[0]
    assert row["investigation_id"] == "inv-trace-1"
    assert row["total_claims"] == 1
    # No DB + no inline text → the claim is honestly ungrounded (0.0),
    # which is the correct offline behaviour, and the harness still
    # produces a distribution row.
    assert 0.0 <= row["groundedness_score"] <= 1.0


def test_groundedness_harness_main_smoke(capsys):
    """The CLI entry runs end-to-end over the checked-in labeled set and
    prints a separation report (exit 0)."""
    rc = harness_main(["--labeled", str(_LABELED_FIXTURE)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "separation" in out.lower()
    assert "rank-AUC" in out
