"""The Boat runner selector must be the same rule on every job that uses it.

The pytest shards and the `pytest` rollup each carry the expression that sends
a job to Boat.dev (`runs-on: boat`) or keeps it on GitHub. Boat runs jobs from
this public repository only for allowlisted users, so a copy that lost an actor
clause would send a Dependabot run to Boat, where it is refused and its check
never reports. The copies may differ only in their GitHub fallback label.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_FALLBACKS = {"pytest-suite": "ubuntu-24.04", "pytest": "ubuntu-latest"}
_ALLOWLIST_CLAUSES = (
    "github.triggering_actor == 'Slimydog21'",
    "github.actor == 'Slimydog21'",
    "github.event.pull_request.user.login == 'Slimydog21'",
)


def _runs_on(job_id: str) -> str:
    jobs = yaml.safe_load(_CI.read_text(encoding="utf-8"))["jobs"]
    runs_on = jobs[job_id]["runs-on"]
    assert isinstance(runs_on, str), f"{job_id}: runs-on is not a single expression"
    return runs_on


def _rule(job_id: str) -> str:
    """The selector with this job's GitHub fallback label replaced by a placeholder."""
    runs_on = _runs_on(job_id)
    tail = f"&& 'boat' || '{_FALLBACKS[job_id]}' }}}}"
    assert runs_on.endswith(tail), f"{job_id}: selector does not end in {tail!r}"
    return runs_on[: -len(tail)]


def test_every_boat_job_uses_the_same_selector() -> None:
    assert _rule("pytest") == _rule("pytest-suite")


def test_the_selector_keeps_the_boat_allowlist() -> None:
    rule = _rule("pytest-suite")
    assert "vars.ANTIEK_CI_SHARD_RUNNER == 'boat'" in rule
    for clause in _ALLOWLIST_CLAUSES:
        assert clause in rule, f"selector lost {clause!r}"
