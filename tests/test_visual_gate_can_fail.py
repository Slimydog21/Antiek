"""The visual-regression gate must be able to go red.

`npx lost-pixel` alone cannot. In lost-pixel 3.22.0 the exit is nested twice —
it requires `failOnDifference` AND `generateOnly`, and this project must keep
`generateOnly: false` to compare against committed baselines at all. So the
command returns 0 regardless of how many shots regress. A CI run was observed
green with 357 "Difference of" lines, the largest at 85.95% against a 0.4%
threshold, while the `if: failure()` artifact upload meant nobody saw a diff.

The gate therefore has to assert on what lost-pixel WRITES. These tests pin
that it still does, so the step cannot quietly revert to trusting an exit code
that is always zero.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "visualtest.yml"


def _lostpixel_run_step() -> str:
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["lostpixel"]["steps"]
    for step in steps:
        # Match the step that RUNS the comparison, not the Playwright install
        # whose command merely contains "node_modules/lost-pixel/...".
        if "npx lost-pixel" in str(step.get("run", "")):
            return str(step["run"])
    raise AssertionError(
        "no step in the lostpixel job runs lost-pixel — this test's premise "
        "is stale, retarget it rather than deleting it"
    )


def test_the_premise_still_holds() -> None:
    """Not vacuous: a missing job or step would pass every assertion below."""
    assert _WORKFLOW.is_file()
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert "lostpixel" in (doc.get("jobs") or {}), "the lostpixel job is gone"
    assert _lostpixel_run_step().strip(), "the lost-pixel step has an empty body"


def test_the_gate_asserts_on_the_diff_artifact_not_the_exit_code() -> None:
    run = _lostpixel_run_step()
    assert ".lostpixel/diff" in run, (
        "the lost-pixel step no longer inspects the difference directory. "
        "`npx lost-pixel` exits 0 even with hundreds of above-threshold "
        "regressions (runner.js gates exitProcess behind config.generateOnly, "
        "which must stay false here), so without this check the gate is green "
        "by construction."
    )
    assert "exit 1" in run, (
        "the lost-pixel step inspects the diff directory but never fails on "
        "it; a check that cannot change the step's outcome is not a gate"
    )


def test_the_config_still_compares_against_committed_baselines() -> None:
    """generateOnly:false is what makes this a comparison rather than a capture.

    If it ever flips true, lost-pixel overwrites the baselines with the current
    render — every shot matches, and the diff directory this gate reads stays
    empty forever.
    """
    config = (_ROOT / "apps" / "reading" / "lostpixel.config.ts").read_text(
        encoding="utf-8"
    )
    assert "generateOnly: false" in config, (
        "lostpixel.config.ts no longer pins generateOnly:false — the gate "
        "would be capturing new baselines instead of comparing against them, "
        "and could never report a difference"
    )
