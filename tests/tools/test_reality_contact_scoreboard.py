"""Tests for the reality-contact scoreboard (SPR-02).

The arithmetic is pinned to a HAND-BUILT tiny ledger with known counts and
asserted to the digit — a scoreboard whose math is only "eyeballed against real
output" is the self-assessment trap this whole spec exists to kill. On top of the
exact ratios we prove the three structural guarantees the headline must have:

  * un-gameable by n-a padding (adding an n-a file moves NO ratio);
  * the number moves the RIGHT way (a reality -> theater or reality ->
    indeterminate flip LOWERS the subsystem RCR; indeterminate never raises it);
  * mock-free (metric.py and __main__.py import NONE of the CORE modules from
    boundaries.yaml — the scoreboard measures the core without ever touching it);
  * the caveat travels (the rendered output carries the ledger's
    known_blind_spots text adjacent to the number).

By the classifier's own definition this file is ``reality``/``n-a``: it imports the
real metric module and mocks nothing on a core path.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from tools.reality_contact import BOUNDARIES_PATH, REPO_ROOT
from tools.reality_contact.__main__ import render, run
from tools.reality_contact.metric import compute_metric

# Two real CORE subsystem names (so the fixture mirrors the real ledger's keys).
A = "substrate.graph.ops"
B = "substrate.dispatch.router"


def _file(path: str, verdict: str, labels: dict[str, str]) -> dict[str, Any]:
    """A minimal ledger file entry — only the fields metric.py consumes."""
    return {"path": path, "verdict": verdict, "subsystem_labels": labels}


def _fixture_ledger() -> dict[str, Any]:
    """A hand-built ledger with KNOWN counts.

    Subsystem A (graph.ops): f1 reality, f2 reality, f3 theater, f4 reality
        -> claiming 4, reality 3, theater 1, indeterminate 0 -> RCR = 3/4 = 0.75
    Subsystem B (dispatch.router): f4 reality, f5 indeterminate
        -> claiming 2, reality 1, theater 0, indeterminate 1 -> RCR = 1/2 = 0.50
    f4 is MULTI-LABEL (claims both A and B), so it contributes one claim to each.
    f6 is n-a (no labels) — must be inert.

    Pooled headline = (3 + 1) / (4 + 2) = 4/6 = 0.6666...  ← claiming-weighted.
    Naive mean of ratios would be (0.75 + 0.50)/2 = 0.625 — a DIFFERENT number,
    which lets the aggregation-rule test discriminate the two.
    """
    return {
        "core_modules": [A, B],
        "known_blind_spots": {
            "provider_mocks_are_boundary": "PROVIDER-IS-BOUNDARY-SENTINEL",
            "provider_boundary_mock_file_count": 0,
            "static_analysis_limits": "STATIC-LIMITS-SENTINEL",
        },
        "files": [
            _file("f1", "reality", {A: "reality"}),
            _file("f2", "reality", {A: "reality"}),
            _file("f3", "theater", {A: "theater"}),
            _file("f4", "reality", {A: "reality", B: "reality"}),
            _file("f5", "indeterminate", {B: "indeterminate"}),
            _file("f6", "n-a", {}),
        ],
    }


def _row(metric: Any, subsystem: str) -> Any:
    return next(r for r in metric.per_subsystem if r.subsystem == subsystem)


# --------------------------------------------------------------------------- #
# (a) Arithmetic pinned to the digit on the hand-built fixture
# --------------------------------------------------------------------------- #
def test_per_subsystem_ratios_exact() -> None:
    m = compute_metric(_fixture_ledger())
    a, b = _row(m, A), _row(m, B)

    assert (a.claiming, a.reality, a.theater, a.indeterminate) == (4, 3, 1, 0)
    assert a.rcr == 0.75

    assert (b.claiming, b.reality, b.theater, b.indeterminate) == (2, 1, 0, 1)
    assert b.rcr == 0.5


def test_headline_is_claiming_weighted_not_mean_of_ratios() -> None:
    """The headline must be the POOLED claim-weighted ratio (4/6 = 0.666…), NOT
    the naive mean of per-subsystem ratios (0.625). Asserting both pins the chosen
    aggregation rule and rules out the flattering-but-wrong alternative."""
    m = compute_metric(_fixture_ledger())
    assert m.total_reality == 4
    assert m.total_claiming == 6
    assert m.headline_rcr == 4 / 6
    # The rejected alternative would give a measurably different number.
    naive_mean = (0.75 + 0.50) / 2
    assert m.headline_rcr != naive_mean


def test_unclaimed_core_reports_na_not_zero() -> None:
    """A declared core that no file claims is reported claiming=0, rcr=None — never
    coerced to 0.0/1.0, so it cannot silently move the headline."""
    led = _fixture_ledger()
    led["core_modules"] = [A, B, "substrate.attribution.compute"]
    m = compute_metric(led)
    unclaimed = _row(m, "substrate.attribution.compute")
    assert unclaimed.claiming == 0
    assert unclaimed.rcr is None
    # The headline is unchanged by an unclaimed core.
    assert m.headline_rcr == 4 / 6


def test_columns_reconcile_with_claiming() -> None:
    """Every claim is accounted for in exactly one column:
    claiming == reality + theater + indeterminate + other, per subsystem AND in
    total. This is the loud invariant behind the denominator — if SPR-01 ever
    emits a label the metric does not name, ``other`` catches it instead of it
    vanishing silently from the columns and lowering RCR unexplained."""
    m = compute_metric(_fixture_ledger())
    for r in m.per_subsystem:
        assert r.claiming == r.reality + r.theater + r.indeterminate + r.other
        assert r.other == 0  # the fixture uses only recognized labels
    assert m.total_claiming == (
        m.total_reality + m.total_theater + m.total_indeterminate + m.total_other
    )

    # The REAL ledger must reconcile too, with zero unrecognized labels today —
    # this assertion bites the moment the classifier emits a fifth label value.
    real = json.loads(
        (REPO_ROOT / "tools" / "reality_contact" / "ledger.json").read_text(
            encoding="utf-8"
        )
    )
    rm = compute_metric(real)
    assert rm.total_other == 0, (
        "the real ledger carries a subsystem label the metric does not recognize"
    )
    for r in rm.per_subsystem:
        assert r.claiming == r.reality + r.theater + r.indeterminate + r.other


def test_unrecognized_label_surfaces_as_other_and_renders_loudly() -> None:
    """A label outside reality/theater/indeterminate counts toward claiming (so it
    can never inflate RCR) and is captured as ``other`` — and the scoreboard prints
    a loud warning rather than letting it lower the number silently from inside the
    denominator."""
    led = _fixture_ledger()
    led["files"].append(_file("f_weird", "weird", {A: "weird"}))
    m = compute_metric(led)
    a = _row(m, A)
    assert a.other == 1
    assert a.claiming == 5  # the four original A-claims + the weird one
    assert a.reality == 3  # unchanged — "weird" is NOT counted as reality
    assert m.total_other == 1
    out = render(m, led["known_blind_spots"])
    assert "does not recognize" in out


# --------------------------------------------------------------------------- #
# (b) Un-gameable by n-a padding
# --------------------------------------------------------------------------- #
def test_na_padding_leaves_every_rcr_identical() -> None:
    """Adding any number of n-a files (no core labels) must leave the headline and
    EVERY per-subsystem RCR byte-identical — n-a tests are in no denominator."""
    before = compute_metric(_fixture_ledger())

    padded = _fixture_ledger()
    padded["files"].extend(
        _file(f"pad_{i}", "n-a", {}) for i in range(50)
    )
    after = compute_metric(padded)

    assert after.headline_rcr == before.headline_rcr
    assert after.total_claiming == before.total_claiming
    assert {r.subsystem: r.rcr for r in after.per_subsystem} == {
        r.subsystem: r.rcr for r in before.per_subsystem
    }


# --------------------------------------------------------------------------- #
# (c) The number moves the RIGHT way
# --------------------------------------------------------------------------- #
def test_reality_to_theater_lowers_subsystem_rcr() -> None:
    before = compute_metric(_fixture_ledger())

    flipped = _fixture_ledger()
    # f1 claimed A as reality; turn it into theater.
    flipped["files"][0]["subsystem_labels"][A] = "theater"
    after = compute_metric(flipped)

    a_before, a_after = _row(before, A).rcr, _row(after, A).rcr
    assert a_after is not None and a_before is not None
    assert a_after < a_before
    assert a_after == 0.5  # 2 reality / 4 claiming
    # Headline drops too: (2 + 1) / 6 = 0.5.
    assert after.headline_rcr is not None and before.headline_rcr is not None
    assert after.headline_rcr < before.headline_rcr
    assert after.headline_rcr == 0.5


def test_reality_to_indeterminate_lowers_subsystem_rcr_never_raises() -> None:
    """An indeterminate label counts toward claiming but NOT reality, so flipping a
    reality label to indeterminate can only LOWER (or hold) RCR — never raise it."""
    before = compute_metric(_fixture_ledger())

    flipped = _fixture_ledger()
    flipped["files"][1]["subsystem_labels"][A] = "indeterminate"  # f2: reality -> indeterminate
    after = compute_metric(flipped)

    a_before, a_after = _row(before, A), _row(after, A)
    assert a_after.rcr is not None and a_before.rcr is not None
    assert a_after.rcr < a_before.rcr
    assert a_after.rcr == 0.5  # 2 reality / 4 claiming
    assert a_after.indeterminate == 1
    # Claiming is unchanged (an indeterminate still claims the core).
    assert a_after.claiming == a_before.claiming


def test_adding_an_indeterminate_claim_never_raises_rcr() -> None:
    """Independent of flips: appending a NEW indeterminate claim to a subsystem can
    only hold its RCR flat-or-lower (it grows the denominator, not the numerator)."""
    before = compute_metric(_fixture_ledger())
    with_indet = _fixture_ledger()
    with_indet["files"].append(_file("f_extra", "indeterminate", {A: "indeterminate"}))
    after = compute_metric(with_indet)

    assert _row(after, A).rcr is not None and _row(before, A).rcr is not None
    assert _row(after, A).rcr <= _row(before, A).rcr
    assert after.headline_rcr is not None and before.headline_rcr is not None
    assert after.headline_rcr <= before.headline_rcr


# --------------------------------------------------------------------------- #
# (d) Mock-free: the scoreboard imports NO core module
# --------------------------------------------------------------------------- #
def _core_modules_from_boundaries() -> set[str]:
    contract = yaml.safe_load(BOUNDARIES_PATH.read_text(encoding="utf-8"))
    return {entry["module"] for entry in contract["core"]}


def _imported_names(py_file: Path) -> set[str]:
    """Every dotted name introduced by an ``import``/``from`` in a source file
    (static AST walk — never executes the module)."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def test_scoreboard_imports_no_core_module() -> None:
    """metric.py and __main__.py must import NONE of the CORE modules they measure
    — so the scoreboard can never accidentally exercise (or mock) the thing it
    scores. Checked statically against boundaries.yaml's own CORE list."""
    core = _core_modules_from_boundaries()
    pkg = REPO_ROOT / "tools" / "reality_contact"
    offenders: dict[str, set[str]] = {}
    for fname in ("metric.py", "__main__.py"):
        imported = _imported_names(pkg / fname)
        # A module is "imported" if a core name is an import target or a prefix
        # of one (e.g. `from substrate.graph.ops import insert_document`).
        hit = {
            c
            for c in core
            if c in imported or any(name.startswith(c + ".") for name in imported)
        }
        if hit:
            offenders[fname] = hit
    assert not offenders, f"scoreboard imports CORE modules it measures: {offenders}"


# --------------------------------------------------------------------------- #
# (e) The caveat travels with the number
# --------------------------------------------------------------------------- #
def test_render_includes_known_blind_spots_text() -> None:
    """The render output must carry the ledger's known_blind_spots text adjacent to
    the number — a glowing RCR printed without its caveat FAILS this sprint."""
    led = _fixture_ledger()
    m = compute_metric(led)
    out = render(m, led["known_blind_spots"])

    assert "KNOWN BLIND SPOTS" in out
    # The actual ledger text must appear, not just a header.
    assert "PROVIDER-IS-BOUNDARY-SENTINEL" in out
    assert "STATIC-LIMITS-SENTINEL" in out
    assert "provider_boundary_mock_file_count" in out
    # And the headline number is in the same artifact as the caveat.
    assert "HEADLINE RCR" in out


def test_render_warns_when_blind_spots_missing() -> None:
    """If a ledger somehow lacks the caveat, the scoreboard says so loudly rather
    than printing a clean number silently."""
    m = compute_metric(_fixture_ledger())
    out = render(m, {})
    assert "TREAT WITH SUSPICION" in out


# --------------------------------------------------------------------------- #
# CLI exit codes: fresh -> 0, missing -> 2
# --------------------------------------------------------------------------- #
def test_run_exit_2_on_missing_ledger(tmp_path: Path) -> None:
    code = run(ledger_path=tmp_path / "nope.json", boundaries_path=BOUNDARIES_PATH)
    assert code == 2


def test_run_exit_2_on_stale_boundaries_hash(tmp_path: Path) -> None:
    """A ledger whose stored boundaries hash does not match the current contract is
    STALE — exit 2, refusing to print a number against a moved contract."""
    stale = _fixture_ledger()
    stale["boundaries_hash"] = "sha256:deadbeef"
    led_path = tmp_path / "ledger.json"
    led_path.write_text(json.dumps(stale), encoding="utf-8")
    code = run(ledger_path=led_path, boundaries_path=BOUNDARIES_PATH)
    assert code == 2


def test_cli_runs_against_real_ledger_exit_0() -> None:
    """End-to-end: `python -m tools.reality_contact` on the real, fresh ledger
    prints the table + caveat and exits 0."""
    proc = subprocess.run(
        [sys.executable, "-m", "tools.reality_contact"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "HEADLINE RCR" in proc.stdout
    assert "KNOWN BLIND SPOTS" in proc.stdout
