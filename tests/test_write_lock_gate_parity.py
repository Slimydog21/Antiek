"""The required copy of the write-lock async floor must not drift from the one it mirrors.

`write_lock_async_floor.yml` emits the `write-lock-async-gate` context, but it is
PATH-FILTERED, and a required check behind ``paths:`` is never reported on a PR
that misses the filter, so it stays permanently pending. It therefore cannot be
added to the ruleset and has sat in ``emitted_but_not_required`` as "a candidate
for the fence".

The enforcement lives instead in ci.yml's ``keystone`` job, which IS required and
carries no path filter. That means the same three ``enforce`` invocations exist in
two files — a duplicated fact, and duplicated facts drift. This test removes the
duplication risk the only durable way: by READING both files and failing if the
lint names, baseline files or scope directories diverge.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_STANDALONE = _ROOT / ".github" / "workflows" / "write_lock_async_floor.yml"
_CI = _ROOT / ".github" / "workflows" / "ci.yml"

_ENFORCE = re.compile(
    r"cli_with_baseline\s+enforce\s+(?P<lint>[a-z_]+)\b", re.MULTILINE
)
_BASELINE = re.compile(r"--baseline-file\s+(?P<path>\S+)")


def _collect(steps: list[dict], job_env: dict | None = None) -> tuple[set[str], set[str], set[str]]:
    """Lints, baseline basenames and SCOPE_DIRS, read from PARSED yaml.

    Parsed rather than regexed over raw text so that a purely cosmetic
    reformat (a folded ``>-`` block rewritten as a quoted scalar, say) cannot
    make this test silently stop matching — which is how a parity check
    quietly becomes vacuous.
    """
    lints: set[str] = set()
    baselines: set[str] = set()
    scope: set[str] = set()
    if job_env and "SCOPE_DIRS" in job_env:
        scope |= set(str(job_env["SCOPE_DIRS"]).split())
    for step in steps:
        env = step.get("env") or {}
        if "SCOPE_DIRS" in env:
            scope |= set(str(env["SCOPE_DIRS"]).split())
        run = step.get("run") or ""
        lints |= set(_ENFORCE.findall(run))
        baselines |= {Path(x).name for x in _BASELINE.findall(run)}
    return lints, baselines, scope


def _standalone_shape() -> tuple[set[str], set[str], set[str]]:
    doc = yaml.safe_load(_STANDALONE.read_text(encoding="utf-8"))
    job = doc["jobs"]["write-lock-async-gate"]
    return _collect(job["steps"], job.get("env"))


def _keystone_shape() -> tuple[set[str], set[str], set[str]]:
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    job = doc["jobs"]["keystone"]
    return _collect(job["steps"], job.get("env"))


def test_required_copy_enforces_the_same_lints() -> None:
    lints_a, base_a, scope_a = _standalone_shape()
    lints_b, base_b, scope_b = _keystone_shape()

    # Anti-vacuity: an empty set on either side would make every comparison
    # below trivially true, which is exactly how a parity test stops testing.
    assert lints_a, "parsed no lints from the standalone workflow"
    assert lints_b, "parsed no lints from the keystone job"
    assert len(lints_a) == 3, f"expected 3 lints, parsed {sorted(lints_a)}"
    assert scope_a and scope_b, "parsed an empty SCOPE_DIRS"

    assert lints_a == lints_b, (
        "the required keystone copy and write_lock_async_floor.yml enforce "
        f"different lints: standalone-only={sorted(lints_a - lints_b)} "
        f"keystone-only={sorted(lints_b - lints_a)}"
    )
    assert base_a == base_b, (
        "the two copies use different baseline files: "
        f"standalone-only={sorted(base_a - base_b)} "
        f"keystone-only={sorted(base_b - base_a)}"
    )
    assert scope_a == scope_b, (
        "SCOPE_DIRS drifted — a directory enforced in one copy but not the "
        f"other is a blind spot: standalone-only={sorted(scope_a - scope_b)} "
        f"keystone-only={sorted(scope_b - scope_a)}"
    )


def test_keystone_is_the_copy_that_is_actually_required() -> None:
    """The premise: keystone is required, the standalone gate is not."""
    contract = yaml.safe_load(
        (_ROOT / ".github" / "required-checks.yml").read_text(encoding="utf-8")
    )
    required = contract["required"]
    advisory = contract["emitted_but_not_required"]
    assert "keystone" in required, "keystone must be required for this to enforce"
    assert "write-lock-async-gate" in advisory, (
        "write-lock-async-gate became required — if its path filter was also "
        "removed, the keystone copy is now redundant and this parity test "
        "should be reconsidered rather than silently kept"
    )
