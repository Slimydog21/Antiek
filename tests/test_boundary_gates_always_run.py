"""The boundary gates must not sit behind the shard-result assertion.

ci.yml's `pytest` job carries ~17 boundary/invariant gates — substrate/dispatch,
one-owner-per-layer, serve-guard, arXiv egress and serve-invariants,
retrieval-gate drift, owner-privilege, contact-guard, merge-age
(anti-stranding), reachability (twice), the invariant-registry meta-check,
source-gate, codegen staleness and contract-conformance.

They used to sit AFTER ``Require every pytest shard``, which was the job's first
step. Any cancelled shard — routine under ``concurrency: cancel-in-progress`` —
failed that assertion and skipped all of them.

Measured over 40 recent ci.yml runs before the fix: the gates EXECUTED on 8 and
were SKIPPED on 27. Of 12 sampled active PRs whose `pytest` check was red,
12 of 12 failed on that assertion rather than on any gate. The gates ran on
roughly one CI run in five, so a red gate was far likelier to mean "a shard was
cancelled" than "an invariant broke".

The job is ``if: always()``, so asserting LAST keeps the verdict identical while
letting the gates actually run.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_ASSERT_STEP = "Require every pytest shard"

# Substrings identifying boundary/invariant gate steps inside the pytest job.
_GATE_MARKERS = (
    "boundary check",
    "Reachability gate",
    "reachability gate",
    "conformance",
    "Codegen staleness",
    "Merge-age gate",
    "Invariant-registry",
    "rate-governor",
    "serve-invariants",
    "Retrieval gate",
    "contact-guard",
    "source-onboarding",
)


def _pytest_job() -> dict:
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8")) or {}
    job = (doc.get("jobs") or {}).get("pytest")
    assert job, "ci.yml has no `pytest` job — refusing to assert over nothing"
    return job


def _step_names() -> list[str]:
    names = [s.get("name") or "" for s in (_pytest_job().get("steps") or [])]
    assert len(names) > 5, f"parsed only {len(names)} steps; the parse is broken"
    return names


def test_the_shard_assertion_is_not_first() -> None:
    """As the first step it skipped every gate behind it."""
    names = _step_names()
    assert names[0] != _ASSERT_STEP, (
        f"{_ASSERT_STEP!r} is the first step again — every boundary gate after "
        f"it is skipped whenever a shard is cancelled"
    )


def test_every_boundary_gate_runs_before_the_shard_assertion() -> None:
    """A gate placed after the assertion is a gate that usually does not run."""
    names = _step_names()
    assert _ASSERT_STEP in names, f"{_ASSERT_STEP!r} vanished — the suite result is now unchecked"
    cut = names.index(_ASSERT_STEP)
    gates = [n for n in names if any(m in n for m in _GATE_MARKERS)]
    assert gates, (
        "no boundary-gate steps matched; the markers drifted and this test "
        "would pass vacuously over an empty list"
    )
    stranded = [n for n in gates if names.index(n) > cut]
    assert not stranded, (
        f"these gates sit after {_ASSERT_STEP!r} and are skipped on any cancelled shard: {stranded}"
    )


def test_the_job_still_runs_when_the_suite_is_cancelled() -> None:
    """``if: always()`` is what makes asserting-last safe.

    Without it a cancelled suite would skip the whole job, so moving the
    assertion to the end would hide a failure instead of surfacing it.
    """
    job = _pytest_job()
    cond = str(job.get("if") or "")
    assert "always()" in cond, (
        f"the pytest job lost `if: always()` (got {cond!r}); asserting the "
        f"suite result last is only safe while the job runs unconditionally"
    )


def test_the_suite_result_is_still_asserted() -> None:
    """Moving the check must not weaken it."""
    steps = _pytest_job().get("steps") or []
    match = [s for s in steps if (s.get("name") or "") == _ASSERT_STEP]
    assert match, f"{_ASSERT_STEP!r} is gone"
    run = match[0].get("run") or ""
    assert "PYTEST_SUITE_RESULT" in run and "success" in run, (
        f"the assertion no longer compares the suite result: {run!r}"
    )
