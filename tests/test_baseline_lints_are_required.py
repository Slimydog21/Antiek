"""Every baselined lint must be enforced by a job that can actually block a merge.

Antiek has seven ``cli_with_baseline enforce`` lints. Until this test, four of
them ran ONLY in workflows that are advisory *and* ``paths:``-filtered, so they
blocked nothing and did not run on main:

    unbounded_external_call, seam_under_write_lock   resilience_floor.yml
    no_raise, bypass                                 substrate_floor.yml

That is not theoretical. Seven PRs merged with ``resilience_floor`` red on their
MERGED HEAD sha (#124, #125, #134, #148, #3127, #3135, #3182), and the floor had
not run on main since 2026-07-02.

A path-filtered check can never simply be added to the ruleset: a required
context behind ``paths:`` is never reported on a PR that misses the filter, so
it stays permanently pending and wedges the queue. Enforcement therefore lives
in ci.yml's ``keystone`` job, which is required and carries no path filter.

This test states the invariant rather than a list, so a lint added to an
advisory floor tomorrow fails here until it is promoted too.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"
_CI = _WORKFLOWS / "ci.yml"

# The job that is BOTH required by the ruleset and free of a paths: filter.
_REQUIRED_JOB = "keystone"

_ENFORCE = re.compile(r"cli_with_baseline\s+enforce\s+(?P<lint>[a-z_]+)\b")
_PATHS_VAR = re.compile(r"--paths\s+\$(?P<var>[A-Z_]+)")
_BASELINE = re.compile(r"--baseline-file\s+(?P<path>\S+)")


def _invocations(path: Path) -> dict[str, dict[str, object]]:
    """Map lint name -> {scope, baseline, check_stale, job} for one workflow.

    Read from PARSED yaml rather than regexed over raw text, so a purely
    cosmetic reformat — a folded ``>-`` block rewritten as a quoted scalar,
    say — cannot make this test silently stop matching. That is exactly how a
    parity check quietly becomes vacuous.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    top_env = dict(doc.get("env") or {})
    found: dict[str, dict[str, object]] = {}
    for job_id, job in (doc.get("jobs") or {}).items():
        job = job or {}
        job_env = {**top_env, **(job.get("env") or {})}
        for step in job.get("steps") or []:
            step = step or {}
            run = step.get("run") or ""
            env = {**job_env, **(step.get("env") or {})}
            for match in _ENFORCE.finditer(run):
                tail = run[match.start() :]
                var = _PATHS_VAR.search(tail)
                baseline = _BASELINE.search(tail)
                # only the flags belonging to THIS invocation, not the next one
                end = _ENFORCE.search(tail[1:])
                segment = tail[: end.start() + 1] if end else tail
                found[match.group("lint")] = {
                    "scope": frozenset(str(env.get(var.group("var"), "")).split())
                    if var
                    else frozenset(),
                    "baseline": Path(baseline.group("path")).name if baseline else "",
                    "check_stale": "--check-stale" in segment,
                    "job": job_id,
                }
    return found


def _all_advisory() -> dict[str, tuple[Path, dict[str, object]]]:
    out: dict[str, tuple[Path, dict[str, object]]] = {}
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        if path == _CI:
            continue
        for lint, meta in _invocations(path).items():
            out.setdefault(lint, (path, meta))
    return out


def _required() -> dict[str, dict[str, object]]:
    return {lint: meta for lint, meta in _invocations(_CI).items() if meta["job"] == _REQUIRED_JOB}


def test_the_parser_finds_lints_at_all() -> None:
    """A parser that silently matches nothing would pass every other test here."""
    required = _required()
    assert len(required) >= 7, (
        f"only {len(required)} lints parsed out of ci.yml's {_REQUIRED_JOB} job; "
        f"refusing to certify the invariant over a broken parse"
    )


def test_no_lint_is_enforced_only_in_an_advisory_workflow() -> None:
    """The invariant. A lint that runs nowhere blocking is decoration."""
    required = _required()
    orphans = {
        lint: str(path.name)
        for lint, (path, _meta) in _all_advisory().items()
        if lint not in required
    }
    assert not orphans, (
        f"these lints are enforced ONLY in advisory, path-filtered workflows and "
        f"cannot block a merge: {orphans}. Promote each into ci.yml's "
        f"{_REQUIRED_JOB} job, which is required and has no paths: filter."
    )


def test_the_required_copy_matches_its_advisory_source() -> None:
    """A narrower scope or different baseline in the required copy reopens the hole."""
    required = _required()
    for lint, (path, advisory) in _all_advisory().items():
        copy = required.get(lint)
        if copy is None:
            continue  # reported by the invariant test above
        assert copy["scope"] == advisory["scope"], (
            f"{lint}: scope drift — {_REQUIRED_JOB}={sorted(copy['scope'])} "
            f"{path.name}={sorted(advisory['scope'])}"
        )
        assert copy["baseline"] == advisory["baseline"], (
            f"{lint}: baseline drift — {copy['baseline']} vs {advisory['baseline']}"
        )
        assert copy["scope"], f"{lint}: scope resolved empty — it would scan nothing"


def test_every_required_lint_checks_for_a_stale_baseline() -> None:
    """Without ``--check-stale`` a baseline can rot and the gate goes quiet.

    A baseline still listing files that no longer exist reports zero NEW
    violations forever. That is the vacuous-gate shape, so the flag is part of
    the contract rather than a nicety.
    """
    missing = [lint for lint, meta in _required().items() if not meta["check_stale"]]
    assert not missing, f"required lints missing --check-stale: {missing}"


def test_the_required_job_has_no_path_filter() -> None:
    """Enforcement inside a path-filtered workflow is what made the floors toothless."""
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8")) or {}
    on = doc.get(True) or doc.get("on") or {}
    pull_request = on.get("pull_request") if isinstance(on, dict) else None
    paths = (pull_request or {}).get("paths") if isinstance(pull_request, dict) else None
    assert not paths, (
        f"ci.yml gained a paths: filter ({paths}); every required context it "
        f"produces would hang permanently pending on a PR that misses the filter"
    )
