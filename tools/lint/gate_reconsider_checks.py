"""Do the test-integrity gates' stated reconsider-ifs actually hold?

`docs/decisions/test-integrity-ci-floor.md` puts three Beck gates on CI as
INFORMATIONAL, each with a **reconsider-if** naming the condition under which it
should flip to blocking. Those conditions are prose. Nothing has ever evaluated
them, so they could not fire:

  * the SPR-05 mock-budget baseline was captured 2026-06-30 and re-captured
    2026-10-03 -- **95 days**, against a stated stability window of 2 weeks;
  * 33 modules drifted upward in that window and the drift was invisible,
    because an unenforced ratchet reports regressions nobody reads.

A reconsider-if that nothing evaluates is a contract with no executable
acceptance, which is the gap an independent grade of this repository named as
its largest. This module makes each one machine-checkable and exits nonzero when
a gate is ELIGIBLE TO FLIP, so the decision comes back to a human with evidence
instead of depending on someone rereading a decision doc.

Deliberately NOT flipping the gates itself: the doc assigns that call to the
operator, and this only reports eligibility.

    python -m tools.lint.gate_reconsider_checks            # report
    python -m tools.lint.gate_reconsider_checks --json     # machine-readable
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
BASELINE = REPO / "tools" / "lints" / "baselines" / "mock_budget.json"
SURVIVORS = REPO / "mutants" / "survivors_baseline.json"

# The doc's words: "stable ... for >=2 weeks". A capture is the thing that
# restarts the window, so age is measured from captured_at.
SPR05_STABILITY_DAYS = 14


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _age_days(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        when = _dt.datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.UTC)
    return (_now() - when).total_seconds() / 86400.0


def check_spr05() -> dict:
    """SPR-05: baseline stable for >= 2 weeks with no upward regression on main."""
    if not BASELINE.exists():
        return {"gate": "SPR-05 mock-budget", "state": "MISSING",
                "detail": f"no baseline at {BASELINE}"}
    doc = json.loads(BASELINE.read_text())
    age = _age_days(doc.get("captured_at"))
    if age is None:
        return {"gate": "SPR-05 mock-budget", "state": "UNREADABLE",
                "detail": "captured_at missing or unparseable"}
    # enforce exits 1 on an UPWARD move only; improvements pass.
    # The absolute path, not one relativized against REPO: relative_to raises when the
    # baseline is not under the repo, which made this branch unreachable in a test and
    # would have raised on CI if the baseline ever moved. Found by the test that tried to
    # drive this state.
    proc = subprocess.run(
        [sys.executable, "-m", "tools.lint.mock_budget_check", "enforce",
         "--baseline-file", str(BASELINE)],
        cwd=REPO, capture_output=True, text=True, timeout=900,
    )
    regressed = proc.returncode != 0
    if age < SPR05_STABILITY_DAYS or regressed:
        return {
            "gate": "SPR-05 mock-budget", "state": "NOT ELIGIBLE",
            "detail": (f"baseline is {age:.1f} days old (needs >="
                       f"{SPR05_STABILITY_DAYS})"
                       + ("; enforce reports an upward regression" if regressed else "")),
            "age_days": round(age, 1),
        }
    return {
        "gate": "SPR-05 mock-budget", "state": "ELIGIBLE TO FLIP",
        "detail": (f"baseline stable {age:.1f} days, enforce clean -- remove the "
                   "trailing exit 0 in test_integrity.yml per the reconsider-if"),
        "age_days": round(age, 1),
    }


def check_spr02() -> dict:
    """SPR-02: flip when the survivor baseline has had zero NEW survivors."""
    if not SURVIVORS.exists():
        return {"gate": "SPR-02 fake-gate", "state": "MISSING",
                "detail": f"no baseline at {SURVIVORS}"}
    doc = json.loads(SURVIVORS.read_text())
    age = _age_days(doc.get("captured_at") or doc.get("generated_at"))
    if age is None:
        return {"gate": "SPR-02 fake-gate", "state": "UNREADABLE",
                "detail": "no captured_at/generated_at to age-check"}
    return {
        "gate": "SPR-02 fake-gate", "state": "AGE ONLY",
        "detail": (f"baseline is {age:.1f} days old. NEW-survivor count needs a "
                   "mutant run, which this check does not perform; treat that "
                   "number as unchecked rather than zero."),
        "age_days": round(age, 1),
    }


def check_spr03() -> dict:
    """SPR-03: flip when the lint finding backlog on main is zero for >= 2 weeks."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", "tools.lint.test_desiderata_lint"],
            cwd=REPO, capture_output=True, text=True, timeout=900,
        ).stdout
    except Exception as exc:  # the tool may be named differently; say so
        return {"gate": "SPR-03 desiderata", "state": "UNCHECKED",
                "detail": f"could not run the lint: {exc!r}"}
    findings = sum(1 for line in out.splitlines()
                   if ".py:" in line and line.strip()[:1].isdigit() is False)
    return {
        "gate": "SPR-03 desiderata", "state": "BACKLOG PRESENT" if findings else "ZERO",
        "detail": (f"{findings} finding line(s) in the lint output. The "
                   "reconsider-if additionally wants zero for 2 weeks, which needs "
                   "history this check does not hold."),
        "findings": findings,
    }


CHECKS = (check_spr02, check_spr03, check_spr05)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as exc:  # a checker that crashes must say so, not pass
            results.append({"gate": fn.__name__, "state": "CRASHED",
                            "detail": repr(exc)})

    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for r in results:
            print(f"{r['state']:18s} {r['gate']:22s} {r['detail']}")

    eligible = [r for r in results if r["state"] == "ELIGIBLE TO FLIP"]
    if eligible:
        print(f"\n{len(eligible)} gate(s) meet their stated reconsider-if. The doc "
              "assigns the flip to the operator; this reports, it does not flip.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
