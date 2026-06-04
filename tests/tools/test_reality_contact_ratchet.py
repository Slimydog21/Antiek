"""Tests for the one-way reality-contact ratchet (SPR-04).

Every direction is pinned to HAND-BUILT fixture ledger + baseline pairs, NOT the
live numbers — a ratchet tested against the real RCR would rot the moment the real
suite changes, and the point of this gate is to be a stable contract. The six
directions, each demonstrated to BITE (the assertion is on the specific
regression, so deleting the rule under test flips the test red):

  (1) a NEW un-exempted theater test            -> FAIL, naming the offender
  (2) an improvement (theater cleared / +reality) -> PASS, reported as progress
  (3) exact-equal (current == baseline)         -> PASS (gate blocks regression, not stasis)
  (4) a RECORDED exemption for that theater test -> PASS
  (5) bare --accept WITHOUT --reason            -> REJECTED, no baseline change
  (6) adding an INDETERMINATE test              -> PASS (the false-alarm a naive
                                                   RCR floor would raise, which the
                                                   theater-count floor must NOT)

By the classifier's own definition this file is ``reality``/``n-a``: it imports the
real ratchet module and mocks nothing on a core path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tools.reality_contact.ratchet as ratchet_mod
from tools.reality_contact.ratchet import (
    EXIT_OK,
    EXIT_REGRESSION,
    EXIT_USAGE,
    Baseline,
    evaluate,
    load_baseline,
    run_accept,
    run_check,
)

# Two real CORE subsystem names so fixtures mirror the live ledger's keys.
OPS = "substrate.graph.ops"
ROUTER = "substrate.dispatch.router"


# --------------------------------------------------------------------------- #
# Fixture builders.
# --------------------------------------------------------------------------- #
def _file(
    path: str,
    labels: dict[str, str],
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal ledger file entry — only the fields the ratchet consumes."""
    return {
        "path": path,
        "verdict": "n-a",
        "subsystem_labels": labels,
        "core_mock_evidence": evidence or [],
    }


def _theater_evidence(subsystem: str, target: str, lineno: int = 10) -> dict[str, Any]:
    return {
        "subsystem": subsystem,
        "target": target,
        "form": "patch-str",
        "lineno": lineno,
        "raw": f'mock.patch("{target}")',
    }


def _baseline_dict(
    theater: list[dict[str, str]],
    exemptions: list[dict[str, str]],
    subsystems: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """A committed-baseline-shaped dict for the fixtures."""
    return {
        "schema_version": 1,
        "gate": "reality_contact_ratchet",
        "provenance": {"boundaries_hash": "sha256:fixture", "ledger_content_hash": "sha256:fixture"},
        "subsystems": subsystems
        or {
            OPS: {"claiming": 2, "reality": 2, "theater": 0, "indeterminate": 0},
            ROUTER: {"claiming": 1, "reality": 1, "theater": 0, "indeterminate": 0},
        },
        "theater": theater,
        "exemptions": exemptions,
    }


def _clean_baseline_ledger() -> tuple[Baseline, dict[str, Any]]:
    """A baseline with an EMPTY theater set (mirrors the real frozen state) and a
    ledger that matches it: two real ops claims, one real router claim, no theater.
    """
    baseline = Baseline.from_json(_baseline_dict(theater=[], exemptions=[]))
    ledger = {
        "core_modules": [OPS, ROUTER],
        "files": [
            _file("tests/test_ops_a.py", {OPS: "reality"}),
            _file("tests/test_ops_b.py", {OPS: "reality"}),
            _file("tests/test_router_a.py", {ROUTER: "reality"}),
        ],
    }
    return baseline, ledger


# --------------------------------------------------------------------------- #
# (1) NEW un-exempted theater test -> FAIL, naming the offender.
# --------------------------------------------------------------------------- #
def test_new_unexempted_theater_fails_naming_offender() -> None:
    baseline, ledger = _clean_baseline_ledger()
    # A brand-new test mocks a CORE symbol of graph.ops at line 42.
    ledger["files"].append(
        _file(
            "tests/test_ops_evil.py",
            {OPS: "theater"},
            evidence=[_theater_evidence(OPS, "substrate.graph.ops.upsert_node", lineno=42)],
        )
    )

    result = evaluate(ledger, baseline)

    assert result.exit_code == EXIT_REGRESSION
    # The offender is named to file:line:symbol — the load-bearing diff.
    assert len(result.new_theater) == 1
    offender = result.new_theater[0]
    assert offender.key.path == "tests/test_ops_evil.py"
    assert offender.lineno == 42
    assert offender.key.target == "substrate.graph.ops.upsert_node"
    assert "tests/test_ops_evil.py:42:substrate.graph.ops.upsert_node" in result.report
    # BITE: if the primary gate were removed, new_theater would be empty and this
    # would not be a regression. The assertion above is exactly that rule.


# --------------------------------------------------------------------------- #
# (2) Improvement -> PASS, reported as progress.
# --------------------------------------------------------------------------- #
def test_improvement_passes_and_is_reported() -> None:
    # Baseline HAS one theater entry; the improved ledger cleared it (now reality)
    # AND added a new reality test. Strictly better than baseline.
    theater_entry = {
        "path": "tests/test_ops_legacy.py",
        "subsystem": OPS,
        "target": "substrate.graph.ops.upsert_node",
    }
    baseline = Baseline.from_json(
        _baseline_dict(
            theater=[theater_entry],
            exemptions=[],
            subsystems={
                OPS: {"claiming": 2, "reality": 1, "theater": 1, "indeterminate": 0},
            },
        )
    )
    ledger = {
        "core_modules": [OPS],
        "files": [
            # the formerly-theater test now makes real contact:
            _file("tests/test_ops_legacy.py", {OPS: "reality"}),
            # and a brand-new reality test was added:
            _file("tests/test_ops_new.py", {OPS: "reality"}),
        ],
    }

    result = evaluate(ledger, baseline)

    assert result.exit_code == EXIT_OK
    assert result.new_theater == ()
    assert result.floor_breaches == ()
    # The cleared theater is reported as progress.
    assert len(result.cleared_theater) == 1
    assert result.cleared_theater[0].path == "tests/test_ops_legacy.py"
    assert "Progress" in result.report
    # BITE: an improvement must PASS. If the gate failed on "theater set changed"
    # (rather than "GREW un-exempted"), this would wrongly fail.


# --------------------------------------------------------------------------- #
# (3) Exact-equal (current == baseline) -> PASS. The gate blocks regression, not stasis.
# --------------------------------------------------------------------------- #
def test_exact_equal_passes() -> None:
    baseline, ledger = _clean_baseline_ledger()

    result = evaluate(ledger, baseline)

    assert result.exit_code == EXIT_OK
    assert result.new_theater == ()
    assert result.floor_breaches == ()
    assert "PASS" in result.report
    # BITE: stasis must PASS. A gate that fired on "no change" would be deleted in
    # a day; this asserts equal -> exit 0.


# --------------------------------------------------------------------------- #
# (4) A recorded exemption for that theater test -> PASS.
# --------------------------------------------------------------------------- #
def test_recorded_exemption_passes() -> None:
    # Same offending theater test as (1), but now it is recorded as an exemption
    # with a rationale in the baseline.
    exemption = {
        "path": "tests/test_ops_evil.py",
        "subsystem": OPS,
        "target": "substrate.graph.ops.upsert_node",
        "reason": "Forces upsert_node to raise to exercise the rollback path.",
        "accepted_at": "2026-06-04T00:00:00+00:00",
    }
    baseline = Baseline.from_json(
        _baseline_dict(
            theater=[],
            exemptions=[exemption],
            subsystems={
                OPS: {"claiming": 2, "reality": 2, "theater": 0, "indeterminate": 0},
            },
        )
    )
    ledger = {
        "core_modules": [OPS],
        "files": [
            _file("tests/test_ops_a.py", {OPS: "reality"}),
            _file("tests/test_ops_b.py", {OPS: "reality"}),
            _file(
                "tests/test_ops_evil.py",
                {OPS: "theater"},
                evidence=[_theater_evidence(OPS, "substrate.graph.ops.upsert_node", lineno=42)],
            ),
        ],
    }

    result = evaluate(ledger, baseline)

    assert result.exit_code == EXIT_OK
    assert result.new_theater == ()
    # The exemption gives one subsystem-headroom, so the count floor is not breached.
    assert result.floor_breaches == ()
    # BITE: remove the exemption from the baseline and this exact ledger is (1) — a
    # regression. The recorded rationale is what flips it to PASS.


# --------------------------------------------------------------------------- #
# (5) Bare --accept WITHOUT --reason -> REJECTED, no baseline change.
# --------------------------------------------------------------------------- #
def test_bare_accept_without_reason_is_rejected(tmp_path: Path) -> None:
    # A baseline file + a ledger with a new un-exempted theater test on disk.
    baseline_path = tmp_path / "baseline.json"
    ledger_path = tmp_path / "ledger.json"
    baseline_obj = _baseline_dict(theater=[], exemptions=[])
    baseline_path.write_text(json.dumps(baseline_obj, indent=2), encoding="utf-8")
    before = baseline_path.read_text(encoding="utf-8")
    ledger_obj = {
        "core_modules": [OPS],
        "files": [
            _file(
                "tests/test_ops_evil.py",
                {OPS: "theater"},
                evidence=[_theater_evidence(OPS, "substrate.graph.ops.upsert_node")],
            ),
        ],
    }
    ledger_path.write_text(json.dumps(ledger_obj), encoding="utf-8")

    # Bare --accept (reason=None) is rejected with a usage exit; baseline untouched.
    code = run_accept(reason=None, ledger_path=ledger_path, baseline_path=baseline_path)
    assert code == EXIT_USAGE
    assert baseline_path.read_text(encoding="utf-8") == before  # NO baseline change.

    # Whitespace-only reason is also rejected (it is not a rationale).
    code_ws = run_accept(reason="   ", ledger_path=ledger_path, baseline_path=baseline_path)
    assert code_ws == EXIT_USAGE
    assert baseline_path.read_text(encoding="utf-8") == before

    # Contrast: WITH a reason, the exemption IS recorded and the test then passes —
    # proving the rejection above is about the missing reason, not a broken path.
    code_ok = run_accept(
        reason="Legit error-path mock of upsert_node.",
        ledger_path=ledger_path,
        baseline_path=baseline_path,
    )
    assert code_ok == EXIT_OK
    recorded = load_baseline(baseline_path)
    assert len(recorded.exemptions) == 1
    assert recorded.exemptions[0].subsystem == OPS
    assert "Legit error-path mock" in recorded.exemptions[0].reason
    # provenance was appended:
    assert "ledger sha256:" in recorded.exemptions[0].reason
    # And the ratchet now passes that exact ledger.
    assert evaluate(ledger_obj, recorded).exit_code == EXIT_OK
    # BITE: drop the reason guard in run_accept and the first two asserts go red.


# --------------------------------------------------------------------------- #
# (6) Adding an INDETERMINATE test -> PASS. The mandatory false-alarm-avoidance.
# --------------------------------------------------------------------------- #
def test_added_indeterminate_test_does_not_fail() -> None:
    """The secondary floor must be a theater-COUNT floor, not a raw-RCR floor.

    Adding an indeterminate test RAISES claiming(S) and indeterminate(S) but
    leaves reality(S) and theater(S) flat — so RCR(S) DROPS. A naive RCR floor
    would (wrongly) fail here. The theater-count floor must NOT, because no core
    was mocked: theater(S) did not move. This is the false alarm the design
    explicitly avoids; a green here is load-bearing.
    """
    baseline, ledger = _clean_baseline_ledger()
    # Add an indeterminate ops test: an unresolved mock target the classifier can't
    # prove is core. It has NO core_mock_evidence (it isn't statically a core mock)
    # but the subsystem label is "indeterminate".
    ledger["files"].append(
        _file("tests/test_ops_indeterminate.py", {OPS: "indeterminate"})
    )

    result = evaluate(ledger, baseline)

    # RCR(ops) genuinely dropped: was 2/2 = 1.00, now 2/3 = 0.67. The ratchet must
    # STILL pass, because theater(ops) is unchanged (still 0).
    assert result.exit_code == EXIT_OK
    assert result.new_theater == ()
    assert result.floor_breaches == ()
    # BITE: if the secondary floor compared raw RCR instead of theater count,
    # 0.67 < 1.00 would fail here and this assert would go red.


# --------------------------------------------------------------------------- #
# (7) THE FOOTGUN GUARD (round-2 fix): run_check sources the ledger from the LIVE
# tree, never a stale committed snapshot.
# --------------------------------------------------------------------------- #
def test_run_check_regenerates_from_live_tree_not_stale_committed_ledger(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """``run_check`` must compute the verdict against the LIVE tree (via
    ``build_ledger``), not a committed ``ledger.json`` that drifts as test files
    land. If it read a stale snapshot, a developer who adds a core-mock test and
    runs the ratchet locally would get a false ``PASS`` — exactly the footgun this
    fix closes. Proven by injecting a ``build_ledger`` that returns a tree WITH a
    new un-exempted core-mock (must FAIL) and a clean one (must PASS)."""
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(_baseline_dict(theater=[], exemptions=[])), encoding="utf-8"
    )

    dirty = {
        "core_modules": [OPS],
        "files": [
            _file(
                "tests/test_live_evil.py",
                {OPS: "theater"},
                evidence=[
                    _theater_evidence(OPS, "substrate.graph.ops.upsert_node", lineno=7)
                ],
            ),
        ],
    }
    monkeypatch.setattr(ratchet_mod, "build_ledger", lambda: dirty)
    # ledger_path defaults to None -> regenerate via the (patched) build_ledger.
    assert run_check(baseline_path=baseline_path) == EXIT_REGRESSION

    clean = {
        "core_modules": [OPS],
        "files": [_file("tests/test_live_ok.py", {OPS: "reality"})],
    }
    monkeypatch.setattr(ratchet_mod, "build_ledger", lambda: clean)
    assert run_check(baseline_path=baseline_path) == EXIT_OK
    # BITE: if run_check read a committed ledger instead of build_ledger(), the
    # injected dirty tree would be invisible and the first assert would go red.
