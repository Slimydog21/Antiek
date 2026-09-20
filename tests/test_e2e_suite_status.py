"""The e2e suite's status must be explicit.

apps/reading/e2e holds 30 Playwright specs and package.json defines `e2e`,
`e2e:ams`, `e2e:feel`, `e2e:login` and `e2e:passkey` — and no workflow in
.github/workflows runs any of them. visualtest.yml is the only file that
mentions Playwright, and only to install a browser for lost-pixel and the
Storybook test-runner.

Thirty spec files that nothing executes are not a safety net; they read as one.
Two of them assert on `werner-rig-*` classes that no component emits any more,
so they would fail if they ever ran — they look like proofs of a property
nothing has.

This does not decide whether the suite should run. It makes the decision
visible: a spec is either wired into CI or recorded here with a reason, and
adding a thirty-first unwired spec fails instead of joining a silent pile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_E2E = _ROOT / "apps" / "reading" / "e2e"
_WORKFLOWS = _ROOT / ".github" / "workflows"

#: Specs whose SUBJECT no longer exists in the app. These assert on
#: `werner-rig-*` classes; `git grep -lF werner-rig apps/reading/src` returns
#: only waddle.css, so no component renders one. They would FAIL if they ever
#: ran. Recorded rather than deleted because removing a test is a claim about
#: intent, and the mascot wave's owner should make it.
_DEAD_SUBJECT = {
    "_ams/penguin.spec.ts",
    "_werner/rod-in-hand.spec.ts",
}

#: Every spec currently executed by NO workflow — which is all of them. This
#: register exists so the fact is visible in the tree rather than inferable
#: only by grepping the workflows. It is a NO-GROWTH list: a thirty-first
#: unwired spec fails the test below instead of joining a silent pile, and a
#: spec that gets wired in (or deleted) must LEAVE the list, so the register
#: cannot rot into a stale allowance.
_UNWIRED_SPECS = {
    "_ams/penguin.spec.ts",
    "_ams/scene-motion-fps.spec.ts",
    "_werner/endless-loop.spec.ts",
    "_werner/rod-in-hand.spec.ts",
    "ams-shell.spec.ts",
    "ams-v2-experience-matrix.spec.ts",
    "ams-v2-resilience-matrix.spec.ts",
    "feel-experience-matrix.spec.ts",
    "feel-focus-ring.spec.ts",
    "feel-panels-cascade.spec.ts",
    "feel-rw-ide-exempt.spec.ts",
    "flywheel.spec.ts",
    "glass-reduced-motion.spec.ts",
    "glass-surface.spec.ts",
    "hotkeys-command-scheme.spec.ts",
    "login-magic-link.spec.ts",
    "navigation-ia.spec.ts",
    "navrail-labels.spec.ts",
    "operator-day.spec.ts",
    "passkey-roundtrip.spec.ts",
    "popout.spec.ts",
    "research-hard-ceiling.spec.ts",
    "scene-living.spec.ts",
    "smoke.spec.ts",
    "speak-biography.spec.ts",
    "speak-private-journey.spec.ts",
    "speak-publish.spec.ts",
    "thread-navigation.spec.ts",
    "token-retone.spec.ts",
    "windows-default.spec.ts",
}


def _specs() -> set[str]:
    return {
        p.relative_to(_E2E).as_posix()
        for p in _E2E.rglob("*.spec.ts")
    }


def _workflow_runs_playwright() -> bool:
    for path in _WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "playwright test" in line or "npm run e2e" in line:
                return True
    return False


def test_the_premise_still_holds() -> None:
    """Not vacuous: a missing directory would satisfy everything below."""
    assert _E2E.is_dir(), f"{_E2E.relative_to(_ROOT)} is gone"
    assert len(_specs()) >= 10, f"only {len(_specs())} specs found — walk broken"


def test_no_new_unwired_e2e_spec_is_added() -> None:
    """A spec nothing executes must be named, not merely present."""
    if _workflow_runs_playwright():
        pytest.skip("a workflow now runs Playwright; this guard is satisfied")

    unrecorded = sorted(_specs() - _UNWIRED_SPECS)
    assert not unrecorded, (
        f"{len(unrecorded)} new Playwright spec(s) that no workflow executes: "
        + ", ".join(unrecorded)
        + ". Either wire `npx playwright test` into a workflow, or add them to "
        "_UNWIRED_SPECS. Specs nothing runs read as a safety net and are not "
        "one — there are already 30."
    )


def test_the_unwired_register_only_shrinks() -> None:
    """A spec that got wired in or deleted must leave the register.

    A stale entry is a slot a future unwired spec can occupy for free, which
    is how the register would quietly stop meaning anything.
    """
    stale = sorted(_UNWIRED_SPECS - _specs())
    assert not stale, (
        f"these are registered as unwired but no longer exist: {stale}. "
        "Remove them from _UNWIRED_SPECS."
    )


def test_dead_subject_specs_still_have_a_dead_subject() -> None:
    """If the subject comes back, the exemption must go — a stale allowance is
    a slot a future unwired spec occupies for free."""
    src = _ROOT / "apps" / "reading" / "src"
    emitters = [
        p for p in src.rglob("*.tsx") if "werner-rig" in p.read_text(encoding="utf-8")
    ]
    assert not emitters, (
        "a component emits werner-rig-* again: "
        f"{[str(p.relative_to(_ROOT)) for p in emitters]}. The specs in "
        "_DEAD_SUBJECT are no longer dead — wire them into CI or re-justify "
        "the exemption."
    )
