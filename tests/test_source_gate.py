"""Tests for the source-onboarding corpus-value kill-gate (reframe P3).

The gate's correctness must NOT depend on live data — it is the stop-rule that
decides whether a new source is worth onboarding — so it is exercised entirely
against hand-written censuses + threshold boundaries. Each test pins one real
behaviour: a clean pass, each gating dimension failing, the EXCLUSIVE/INCLUSIVE
boundary at every threshold, the arXiv reference-source exemption, the advisory-not-
gated status of t1_pct/open_pct, the empty-corpus deny-by-default, the missing-field
deny-by-default, JSON round-trip, and the CLI exit codes (incl. no-census-file)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.source_census import (
    DEDUP_OVERLAP_MAX,
    LINKBACK_RESOLVABLE_MIN,
    METADATA_COMPLETE_MIN,
    REFERENCE_SOURCE,
    SourceCensus,
    evaluate,
    gate_failures,
    load_censuses,
    save_censuses,
)


def _census(source="web", **over):
    """A census that PASSES every gate by default; override one field to fail it."""
    base = dict(
        source=source,
        total=1000,
        t1_pct=8.0,
        open_pct=12.0,
        metadata_complete_pct=99.0,
        dedup_overlap_pct=3.0,
        linkback_resolvable_pct=100.0,
    )
    base.update(over)
    return SourceCensus(**base)


def test_clean_source_passes():
    assert gate_failures(_census()) == []


def test_metadata_incomplete_fails():
    fails = gate_failures(_census(metadata_complete_pct=94.9))
    assert len(fails) == 1 and "metadata_complete_pct" in fails[0]


def test_linkback_unresolvable_fails():
    fails = gate_failures(_census(linkback_resolvable_pct=98.9))
    assert len(fails) == 1 and "linkback_resolvable_pct" in fails[0]


def test_dedup_overlap_fails():
    fails = gate_failures(_census(dedup_overlap_pct=25.0))
    assert len(fails) == 1 and "dedup_overlap_pct" in fails[0]


def test_multiple_failures_all_reported():
    fails = gate_failures(
        _census(metadata_complete_pct=10.0, linkback_resolvable_pct=10.0, dedup_overlap_pct=90.0)
    )
    assert len(fails) == 3


@pytest.mark.parametrize(
    "field,value,passes",
    [
        # metadata: >= MIN passes; just-below fails (inclusive bound).
        ("metadata_complete_pct", METADATA_COMPLETE_MIN, True),
        ("metadata_complete_pct", METADATA_COMPLETE_MIN - 0.01, False),
        # linkback: >= MIN passes; just-below fails (inclusive bound).
        ("linkback_resolvable_pct", LINKBACK_RESOLVABLE_MIN, True),
        ("linkback_resolvable_pct", LINKBACK_RESOLVABLE_MIN - 0.01, False),
        # dedup: < MAX passes; AT the bound fails (exclusive bound).
        ("dedup_overlap_pct", DEDUP_OVERLAP_MAX - 0.01, True),
        ("dedup_overlap_pct", DEDUP_OVERLAP_MAX, False),
    ],
)
def test_threshold_boundaries(field, value, passes):
    fails = gate_failures(_census(**{field: value}))
    assert (fails == []) is passes, f"{field}={value} expected passes={passes}, got {fails}"


def test_t1_and_open_pct_are_advisory_not_gated():
    """A source with ZERO redistributable-open share still PASSES if its corpus-
    value metrics are good — t1_pct/open_pct are reported, never gated (arXiv itself
    is mostly link-back-only yet is the flagship source)."""
    assert gate_failures(_census(t1_pct=0.0, open_pct=0.0)) == []


def test_empty_corpus_is_deny_by_default():
    """total<=0 is a failure, not a vacuous pass: an unmeasured source cannot be
    certified. (Mutation: returning [] for total==0 would let a phantom source
    through — this test fails under it.)"""
    fails = gate_failures(_census(total=0, metadata_complete_pct=100.0, linkback_resolvable_pct=100.0, dedup_overlap_pct=0.0))
    assert len(fails) == 1 and "total=0" in fails[0]


def test_evaluate_exempts_reference_from_thresholds_but_keeps_it_visible():
    """arXiv (the calibration baseline) is exempt from the THRESHOLDS; an identical-
    metrics non-arXiv source is blocked. Same numbers, opposite verdict — the
    exemption is real. But the reference is VISIBLE in the result (not silently
    dropped), so a malformed row mislabeled 'arxiv' cannot vanish unchecked."""
    awful = dict(total=1000, t1_pct=1.0, open_pct=1.0, metadata_complete_pct=1.0,
                 dedup_overlap_pct=99.0, linkback_resolvable_pct=1.0)
    results = evaluate([
        SourceCensus(source=REFERENCE_SOURCE, **awful),
        SourceCensus(source="web", **awful),
    ])
    assert results[REFERENCE_SOURCE] == []  # threshold-exempt, but PRESENT in results
    assert results["web"]  # same awful metrics, non-reference -> blocked


def test_reference_source_still_structurally_gated():
    """The exemption is THRESHOLD-only: even the baseline must have measured data, so
    an empty arXiv census fails (not a vacuous exempt pass) — closing the
    'mislabel as arxiv to vanish' hole for the empty/degenerate case."""
    results = evaluate([SourceCensus(
        source=REFERENCE_SOURCE, total=0, t1_pct=0.0, open_pct=0.0,
        metadata_complete_pct=0.0, dedup_overlap_pct=0.0, linkback_resolvable_pct=0.0,
    )])
    assert results[REFERENCE_SOURCE]  # total<=0 fails even for the reference


def test_duplicate_reference_rows_raise():
    """At most one reference row; a duplicate is a mislabel/evasion signal -> raise."""
    c = _census(source=REFERENCE_SOURCE)
    with pytest.raises(ValueError, match="must be unique"):
        evaluate([c, c])


def test_nan_gating_metric_fails_the_gate():
    """A directly-constructed census with a NaN gating metric FAILS at the predicate
    (defense-in-depth; from_dict also rejects it at parse). Without the finite check,
    nan<95 / nan>=99 / nan>=20 are all False and the source would silently pass."""
    import math as _m

    fails = gate_failures(_census(linkback_resolvable_pct=_m.nan))
    assert fails and "non-finite" in fails[0]


def test_from_dict_rejects_nan():
    d = _census().to_dict()
    d["metadata_complete_pct"] = float("nan")
    with pytest.raises(ValueError, match="not finite"):
        SourceCensus.from_dict(d)


def test_from_dict_rejects_out_of_range():
    d = _census().to_dict()
    d["linkback_resolvable_pct"] = 500.0
    with pytest.raises(ValueError, match="outside 0..100"):
        SourceCensus.from_dict(d)


def test_from_dict_rejects_non_object():
    with pytest.raises(ValueError, match="must be a JSON object"):
        SourceCensus.from_dict([1, 2, 3])


def test_from_dict_requires_every_gating_field():
    """A census missing a field raises rather than defaulting it to a passing value
    (a silent gate bypass). Deny-by-default at parse time."""
    partial = _census().to_dict()
    del partial["linkback_resolvable_pct"]
    with pytest.raises(ValueError, match="missing required field"):
        SourceCensus.from_dict(partial)


def test_json_round_trip(tmp_path):
    censuses = [_census(source="web"), _census(source="podcasts", dedup_overlap_pct=50.0)]
    path = tmp_path / "source_census.json"
    save_censuses(censuses, path)
    loaded = load_censuses(path)
    assert {c.source for c in loaded} == {"web", "podcasts"}
    assert loaded == sorted(censuses, key=lambda c: c.source)


# ── the CLI gate (tools/lint/source_gate.py) end-to-end ──────────────────────

_REPO = Path(__file__).resolve().parent.parent
_GATE = _REPO / "tools" / "lint" / "source_gate.py"


def _run_gate(census_path=None):
    """Run the real gate CLI, pointing it at a fixture census via argv so the test
    NEVER mutates the repo's reports/source_census.json."""
    cmd = [sys.executable, str(_GATE)]
    if census_path is not None:
        cmd.append(str(census_path))
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(_REPO))


def test_cli_passes_on_clean_census(tmp_path):
    p = tmp_path / "source_census.json"
    p.write_text(json.dumps([_census(source="web").to_dict()]) + "\n")
    r = _run_gate(p)
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_blocks_on_failing_census(tmp_path):
    p = tmp_path / "source_census.json"
    p.write_text(json.dumps([_census(source="web", dedup_overlap_pct=80.0).to_dict()]) + "\n")
    r = _run_gate(p)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "BLOCKED" in r.stdout


def test_cli_passes_when_no_census_file(tmp_path):
    """A non-existent census path → exit 0 (nothing onboarded to gate); must not crash."""
    r = _run_gate(tmp_path / "absent.json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no source census" in r.stdout
