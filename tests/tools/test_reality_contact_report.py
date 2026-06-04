"""Tests for the reality-contact EVIDENCE report (SPR-03).

The report is the auditable face of the RCR: it must cite every theater claim and
every indeterminate file by `file:line`, render deterministically (so a PR that
adds one theater test shows exactly one new line), and never disagree with the
scoreboard (its RCR comes from the SAME ``compute_metric``). These tests pin all
of that:

  * COMPLETENESS — a fixture ledger built WITH theater (the real tree has 0, so a
    fixture is the only way to make this test bite) yields exactly the cited
    entries, every one carrying a `file:line` + the mocked core symbol.
  * DETERMINISM — two renders of the same ledger are byte-identical.
  * CROSS-CHECK — the summary's headline RCR string equals what ``compute_metric``
    produces on the same ledger (report and scoreboard can never diverge).
  * COMMITTED == RENDER — the on-disk ``reports/reality_contact_evidence.md``
    equals a fresh render of the live ledger (no hand-edits can soften a finding).
  * INDETERMINATE CITED — the real indeterminate file appears with its `file:line`.
  * BLIND-SPOT TEXT — the ledger's ``known_blind_spots`` text appears in the report
    (theater=0 is never presented as a clean bill).

By the classifier's own definition this file is ``reality``/``n-a``: it imports the
real report + metric modules and mocks nothing on a core path.
"""

from __future__ import annotations

import json
from typing import Any

from tools.reality_contact import LEDGER_PATH
from tools.reality_contact.metric import compute_metric
from tools.reality_contact.report import (
    REPORT_PATH,
    _fmt_rcr,
    _indeterminate_entries,
    _theater_entries,
    render_report,
)

# Two real CORE subsystem names so the fixture mirrors the live ledger's keys.
A = "substrate.graph.ops"
B = "substrate.dispatch.router"


def _file(
    path: str,
    verdict: str,
    labels: dict[str, str],
    core_mock_evidence: list[dict[str, Any]] | None = None,
    unresolved_on_core: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A ledger file entry shaped exactly like ``ledger.py`` emits."""
    return {
        "path": path,
        "verdict": verdict,
        "subsystem_labels": labels,
        "core_mock_evidence": core_mock_evidence or [],
        "unresolved_on_core": unresolved_on_core or [],
    }


def _theater_ev(subsystem: str, lineno: int, target: str) -> dict[str, Any]:
    return {
        "subsystem": subsystem,
        "target": target,
        "form": "patch.object",
        "lineno": lineno,
        "raw": f"patch.object({target})",
    }


def _fixture_ledger() -> dict[str, Any]:
    """A hand-built ledger WITH theater so the completeness test actually bites.

    Theater claims (3 total, across 2 subsystems):
      * f_theat1 mocks A at line 12 and A again at line 40  -> 2 A-claims
      * f_theat2 mocks B at line 7                          -> 1 B-claim
    One indeterminate file with 2 unresolved sites. Plus reality + n-a files so
    the RCR denominator is non-trivial. Counts (per-subsystem, (file,subsystem)):
      A: f_real1 reality, f_theat1 theater  -> claiming 2, reality 1, theater 1
      B: f_real1 reality, f_theat2 theater, f_indet indeterminate
                                            -> claiming 3, reality 1, theater 1, indet 1
    """
    return {
        "boundaries_hash": "sha256:FIXTURE",
        "file_count": 6,
        "core_modules": [A, B],
        "known_blind_spots": {
            "provider_mocks_are_boundary": "PROVIDER-IS-BOUNDARY-SENTINEL",
            "provider_boundary_mock_file_count": 0,
            "static_analysis_limits": "STATIC-LIMITS-SENTINEL",
        },
        "files": [
            _file("tests/f_real1.py", "reality", {A: "reality", B: "reality"}),
            _file(
                "tests/f_theat1.py",
                "theater",
                {A: "theater"},
                core_mock_evidence=[
                    _theater_ev(A, 40, f"{A}.upsert_node"),
                    _theater_ev(A, 12, f"{A}.delete_node"),
                ],
            ),
            _file(
                "tests/f_theat2.py",
                "theater",
                {B: "theater"},
                core_mock_evidence=[_theater_ev(B, 7, f"{B}.route")],
            ),
            _file(
                "tests/f_indet.py",
                "indeterminate",
                {B: "indeterminate"},
                unresolved_on_core=[
                    {
                        "form": "monkeypatch",
                        "lineno": 99,
                        "raw": "monkeypatch.setattr(<unresolved-obj>, 'X')",
                    },
                    {
                        "form": "monkeypatch",
                        "lineno": 50,
                        "raw": "monkeypatch.setattr(<unresolved-obj>, 'Y')",
                    },
                ],
            ),
            _file("tests/f_na.py", "n-a", {}),
            _file("tests/f_real2.py", "reality", {A: "reality"}),
        ],
    }


# --- COMPLETENESS -----------------------------------------------------------


def test_every_theater_claim_is_cited_exactly_once() -> None:
    """N theater claims in the ledger -> exactly N cited `file:line` entries, each
    with its mocked core symbol. The real tree has 0 theater, so this fixture is
    the only thing that makes the completeness guarantee bite."""
    ledger = _fixture_ledger()
    report = render_report(ledger)

    # The fixture has 3 theater claims (2 under A, 1 under B).
    rows = _theater_entries(ledger)
    assert len(rows) == 3

    # Each theater claim is cited with file:line + the mocked symbol.
    expected = [
        ("tests/f_theat1.py:12", f"{A}.delete_node"),
        ("tests/f_theat1.py:40", f"{A}.upsert_node"),
        ("tests/f_theat2.py:7", f"{B}.route"),
    ]
    for fileline, symbol in expected:
        assert f"`{fileline}`" in report, f"missing citation {fileline}"
        assert f"`{symbol}`" in report, f"missing mocked symbol {symbol}"

    # Grouped under each subsystem it is theater for; both headers present.
    assert f"### `{A}`" in report
    assert f"### `{B}`" in report

    # Exactly as many cited theater file:line rows as theater claims — no
    # duplication, no omission. Count table rows that cite a theater file.
    cited = sum(
        1
        for line in report.splitlines()
        if line.startswith("| `tests/f_theat")
    )
    assert cited == 3


def test_no_theater_entry_lacks_a_citation() -> None:
    """Every theater row carries a non-empty path, a positive line, a target, and
    a form — an entry without a citable line is a defect."""
    rows = _theater_entries(_fixture_ledger())
    assert rows  # guard: the fixture must actually have theater
    for r in rows:
        assert r["path"]
        assert r["lineno"] > 0
        assert r["target"]
        assert r["form"]


# --- DETERMINISM ------------------------------------------------------------


def test_render_is_deterministic() -> None:
    """Two renders of the same ledger are byte-identical (no wall-clock leaked)."""
    ledger = _fixture_ledger()
    assert render_report(ledger) == render_report(ledger)


def test_no_wall_clock_timestamp_leaked() -> None:
    """The report stamps the boundaries hash, never a date/time — a wall-clock
    would reshuffle the diff on every run and hide regressions in noise."""
    report = render_report(_fixture_ledger())
    assert "sha256:FIXTURE" in report  # the hash IS stamped
    # No ISO-8601-ish timestamp or 'generated at <time>' wording.
    lowered = report.lower()
    assert "utc" not in lowered
    assert "t00:00:00" not in lowered
    # Years like 2026-06-04 must not appear (the determinism hazard).
    import re

    assert re.search(r"\b20\d\d-\d\d-\d\d\b", report) is None


def test_sort_order_is_stable_under_input_shuffle() -> None:
    """Reversing the ledger's file list changes nothing — the renderer sorts by
    (subsystem, path, line), so the committed report can't reshuffle on rebuild."""
    ledger = _fixture_ledger()
    shuffled = dict(ledger)
    shuffled["files"] = list(reversed(ledger["files"]))
    assert render_report(ledger) == render_report(shuffled)


# --- CROSS-CHECK WITH THE METRIC -------------------------------------------


def test_summary_rcr_equals_compute_metric() -> None:
    """The headline RCR string in the report equals ``compute_metric``'s RCR on the
    same ledger — the report and the scoreboard read the same arithmetic, so they
    can never disagree."""
    ledger = _fixture_ledger()
    metric = compute_metric(ledger)
    report = render_report(ledger)
    expected = _fmt_rcr(metric.headline_rcr)
    assert f"**RCR (claiming-weighted) = {expected}**" in report
    # The per-subsystem rows match too.
    for row in metric.per_subsystem:
        cell = f"| `{row.subsystem}` | {row.claiming} | {row.reality} | {row.theater} | {row.indeterminate} | {_fmt_rcr(row.rcr)} |"
        assert cell in report, f"per-subsystem row mismatch for {row.subsystem}"


def test_summary_rcr_matches_metric_on_live_ledger() -> None:
    """Same cross-check against the REAL committed ledger (the 97.62% headline)."""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    metric = compute_metric(ledger)
    report = render_report(ledger)
    assert f"**RCR (claiming-weighted) = {_fmt_rcr(metric.headline_rcr)}**" in report


# --- COMMITTED == RENDER ----------------------------------------------------


def test_committed_report_equals_fresh_render() -> None:
    """The on-disk ``reports/reality_contact_evidence.md`` equals a fresh render of
    the live ledger. A hand-edited report is a lie waiting to happen; this test is
    the guard that makes the committed file trustworthy."""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    fresh = render_report(ledger)
    committed = REPORT_PATH.read_text(encoding="utf-8")
    assert committed == fresh, (
        "reports/reality_contact_evidence.md is out of date — "
        "regenerate with `python -m tools.reality_contact.report`"
    )


# --- HONESTY: INDETERMINATE + BLIND-SPOT ------------------------------------


def test_indeterminate_file_is_cited_with_file_line() -> None:
    """The real indeterminate file appears in the report with each of its
    `file:line` mock sites — never silently dropped (rigor #1)."""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    report = render_report(ledger)
    assert "tests/test_book_qa_meta_reading.py" in report
    # Each unresolved site is cited with its exact file:line.
    indet = _indeterminate_entries(ledger)
    assert len(indet) == 1
    target = indet[0]
    assert target["path"] == "tests/test_book_qa_meta_reading.py"
    assert target["sites"], "indeterminate file must carry its mock sites"
    for site in target["sites"]:
        assert f"`{target['path']}:{site['lineno']}`" in report


def test_indeterminate_is_not_dropped_in_fixture() -> None:
    """The fixture's indeterminate file is cited with both its unresolved sites,
    in sorted (line) order."""
    ledger = _fixture_ledger()
    report = render_report(ledger)
    assert "tests/f_indet.py" in report
    assert "`tests/f_indet.py:50`" in report
    assert "`tests/f_indet.py:99`" in report
    # Sorted by line: 50 appears before 99.
    assert report.index("f_indet.py:50") < report.index("f_indet.py:99")


def test_known_blind_spots_text_appears() -> None:
    """The ledger's ``known_blind_spots`` text is carried into the report verbatim —
    the caveat travels with the number; theater=0 is never a clean bill."""
    ledger = _fixture_ledger()
    report = render_report(ledger)
    for value in ledger["known_blind_spots"].values():
        assert str(value) in report


def test_live_blind_spots_text_appears() -> None:
    """The REAL ledger's blind-spot prose (DI-fakes / provider-is-boundary) appears
    in the committed report — a reader can never read 0 theater as 'all good'."""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    report = render_report(ledger)
    blind = ledger["known_blind_spots"]
    assert str(blind["provider_mocks_are_boundary"]) in report
    assert str(blind["static_analysis_limits"]) in report
    # The honest framing for theater=0 is present.
    assert "NOT a clean bill of health" in report


def test_theater_zero_is_not_presented_as_clean() -> None:
    """With theater=0 the report explicitly refuses the 'clean bill' reading."""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    report = render_report(ledger)
    assert "0 theater claims under the current contract" in report
    assert "NOT a clean bill of health" in report
