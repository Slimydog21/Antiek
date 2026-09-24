"""The orphan probe must tell 'nothing is broken' from 'I could not look'.

A cancelled ci.yml run never re-reports, so a PR whose required checks sit at
``cancelled`` with nothing in flight is dead silently — no failure is shown and
auto-merge never fires. ``tools/ci_orphan_scan.py`` finds exactly that case.

These tests stub the ``gh`` boundary so nothing touches the network.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tools import ci_orphan_scan as scan

_REQUIRED = ["keystone", "tsc", "vitest", "pytest shard 0 of 4", "pytest shard 1 of 4"]


def _fake_gh(
    *,
    rulesets: list[str],
    prs: list[dict[str, Any]],
    checks: dict[str, list[dict[str, Any]]],
    runs: dict[str, list[dict[str, Any]]],
):
    """Stand in for the `gh` CLI, keyed on the arguments the tool actually passes."""

    def _impl(*args: str) -> str:
        joined = " ".join(args)
        if "rulesets" in joined and joined.endswith(".[].id"):
            return "1\n"
        if "rulesets/1" in joined:
            return "\n".join(rulesets)
        if args[:2] == ("pr", "list"):
            return json.dumps(prs)
        if "check-runs" in joined:
            sha = joined.split("commits/")[1].split("/")[0]
            return json.dumps(checks.get(sha, []))
        if "actions/runs?head_sha=" in joined:
            sha = joined.split("head_sha=")[1].split("&")[0]
            return json.dumps(runs.get(sha, []))
        return ""

    return _impl


def _pr(num: int, sha: str) -> dict[str, Any]:
    return {
        "number": num,
        "headRefOid": sha,
        "updatedAt": "2026-09-21T21:00:00Z",
        "title": f"pr {num}",
    }


def test_a_failed_ruleset_read_is_untrusted_not_clean(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reporting 'no orphans' off a truncated required-set is a clean bill over nothing.

    This is the failure this repo keeps producing: a zero measurement read as a
    pass. Exit 2 says "I could not look", which is not exit 0.
    """
    monkeypatch.setattr(scan, "_gh", _fake_gh(rulesets=["keystone"], prs=[], checks={}, runs={}))
    assert scan.main([]) == 2
    assert "UNTRUSTED" in capsys.readouterr().err


def test_a_cancelled_required_check_with_nothing_in_flight_is_an_orphan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        scan,
        "_gh",
        _fake_gh(
            rulesets=_REQUIRED,
            prs=[_pr(101, "aaa")],
            checks={
                "aaa": [{"name": "keystone", "conclusion": "cancelled", "status": "completed"}]
            },
            runs={"aaa": [{"status": "completed"}]},
        ),
    )
    assert scan.main([]) == 1
    out = capsys.readouterr().out
    assert "ORPHANED" in out and "#101" in out


def test_a_cancelled_check_with_a_run_in_flight_is_superseded_not_orphaned(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The distinction the whole tool exists for.

    `cancel-in-progress` cancels the superseded attempt on every push. That is
    normal and self-healing. Flagging it would bury the real cases in noise.
    """
    monkeypatch.setattr(
        scan,
        "_gh",
        _fake_gh(
            rulesets=_REQUIRED,
            prs=[_pr(102, "bbb")],
            checks={
                "bbb": [{"name": "keystone", "conclusion": "cancelled", "status": "completed"}]
            },
            runs={"bbb": [{"status": "in_progress"}]},
        ),
    )
    assert scan.main([]) == 0
    assert "CLEAN" in capsys.readouterr().out


def test_a_cancelled_NON_required_check_is_not_an_orphan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a required context can wedge a merge."""
    monkeypatch.setattr(
        scan,
        "_gh",
        _fake_gh(
            rulesets=_REQUIRED,
            prs=[_pr(103, "ccc")],
            checks={
                "ccc": [{"name": "lostpixel", "conclusion": "cancelled", "status": "completed"}]
            },
            runs={"ccc": [{"status": "completed"}]},
        ),
    )
    assert scan.main([]) == 0


def test_the_probe_is_a_scheduled_alarm_not_a_pr_gate() -> None:
    """Gating a PR on the state of OTHER PRs would punish the wrong author."""
    import pathlib

    import yaml

    wf = (
        pathlib.Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "ci_orphan_probe.yml"
    )
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    triggers = doc.get(True) or doc.get("on") or {}
    assert "schedule" in triggers, "the probe lost its schedule and now runs never"
    assert "pull_request" not in triggers, (
        "the probe became a PR trigger; it reports on OTHER PRs and must not "
        "gate the one being opened"
    )
