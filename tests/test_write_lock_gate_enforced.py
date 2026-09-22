"""The write-lock async floor must stay inside a REQUIRED job.

History: these three lints used to live only in `write_lock_async_floor.yml`,
which is PATH-FILTERED. A required check behind ``paths:`` is never reported on
a PR that misses the filter, so it could not be added to the ruleset and sat in
``emitted_but_not_required`` labelled "a candidate for the fence" — emitted, but
enforcing nothing on the PRs that skipped it.

PR #3329 moved the assertions into ci.yml's ``keystone`` job, which IS required
and carries no path filter. That made the standalone workflow redundant: it
re-ran the identical lints, with identical baselines and identical SCOPE_DIRS,
on every Python PR — 17 of 60 queued runs at the time it was removed, against a
runner pool already delivering a fraction of its entitled concurrency.

This test replaces the old two-file parity test. There is no second copy left to
drift against, so it guards the thing that actually matters: that the required
job still enforces ALL THREE lints, against the committed baselines, over the
full scope. If someone trims one, this fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CI = _ROOT / ".github" / "workflows" / "ci.yml"

_EXPECTED_LINTS = frozenset(
    {"raw_read_only_connect", "blocking_write_in_async", "indirect_write_in_async"}
)
_EXPECTED_BASELINES = frozenset(
    {
        "no_raw_read_only_connect.json",
        "no_blocking_write_in_async.json",
        "no_indirect_write_in_async.json",
    }
)
# One line per directory the lints scan. A directory dropped here is a blind
# spot: enforce simply stops looking at it.
_EXPECTED_SCOPE = frozenset(
    (
        "acquisition",
        "compounding",
        "interfaces",
        "middleware",
        "orchestration",
        "processing",
        "roles",
        "runtime",
        "services",
        "substrate",
        "tools",
    )
)


def _keystone() -> tuple[set[str], set[str], set[str]]:
    """Lints, baseline basenames and SCOPE_DIRS, read from PARSED yaml.

    Parsed rather than regexed over raw text so a cosmetic reformat cannot make
    this test silently stop matching — which is how a gate quietly goes vacuous.
    """
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    job = doc["jobs"]["keystone"]
    lints: set[str] = set()
    baselines: set[str] = set()
    scope: set[str] = set(str((job.get("env") or {}).get("SCOPE_DIRS", "")).split())
    for step in job["steps"]:
        env = step.get("env") or {}
        if "SCOPE_DIRS" in env:
            scope |= set(str(env["SCOPE_DIRS"]).split())
        run = step.get("run") or ""
        lints |= set(re.findall(r"cli_with_baseline\s+enforce\s+([a-z_]+)", run))
        baselines |= {Path(x).name for x in re.findall(r"--baseline-file\s+(\S+)", run)}
    return lints, baselines, scope


def test_keystone_enforces_all_three_write_lock_lints() -> None:
    lints, baselines, scope = _keystone()
    # Anti-vacuity: an empty parse would make every comparison below trivially
    # true, which is exactly how this stops testing anything.
    assert lints, "parsed no enforce invocations from the keystone job"
    assert lints == set(_EXPECTED_LINTS), (
        "the required keystone job no longer enforces the full write-lock floor: "
        f"missing={sorted(set(_EXPECTED_LINTS) - lints)} "
        f"unexpected={sorted(lints - set(_EXPECTED_LINTS))}"
    )
    assert baselines == set(_EXPECTED_BASELINES), (
        f"baseline drift: missing={sorted(set(_EXPECTED_BASELINES) - baselines)} "
        f"unexpected={sorted(baselines - set(_EXPECTED_BASELINES))}"
    )
    assert scope == set(_EXPECTED_SCOPE), (
        "SCOPE_DIRS drifted — a directory the lints no longer scan is a blind "
        f"spot: missing={sorted(set(_EXPECTED_SCOPE) - scope)} "
        f"unexpected={sorted(scope - set(_EXPECTED_SCOPE))}"
    )


def test_keystone_is_required_so_this_actually_enforces() -> None:
    """The premise. If keystone stops being required, these lints go advisory."""
    contract = yaml.safe_load(
        (_ROOT / ".github" / "required-checks.yml").read_text(encoding="utf-8")
    )
    assert "keystone" in contract["required"], (
        "keystone is no longer a required check, so the write-lock floor is not "
        "enforced by anything — restore it or re-home these lints"
    )


def test_the_redundant_standalone_workflow_is_gone() -> None:
    """Guards against someone reinstating the duplicate copy.

    It was removed because it re-ran identical lints on a saturated runner pool.
    If it comes back, either delete it again or restore the two-file parity test
    that used to keep the copies in sync — do not leave them unguarded.
    """
    assert not (_ROOT / ".github" / "workflows" / "write_lock_async_floor.yml").exists()
