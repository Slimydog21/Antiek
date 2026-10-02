"""Caretaker policy and real-git regressions; all GitHub mutations are injected."""

from __future__ import annotations

import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.caretaker import update_stale_branches as caretaker


def payload(number: int, *, draft: bool = False, head: str | None = None) -> dict:
    return {
        "number": number,
        "head": {"sha": head or f"{number:040x}"},
        "draft": draft,
        "base": {"ref": "main"},
        "state": "open",
        "mergeable": True,
        "created_at": "2026-08-12T00:00:00Z",
    }


class GitHub:
    def __init__(self, records: list[dict]):
        self.records = {data["number"]: data for data in records}
        self.calls: list[list[str]] = []
        self.mutations: list[list[str]] = []

    def __call__(self, args: list[str], cwd: Path) -> str:
        if args[0] != "gh":
            return caretaker.run_command(args, cwd)
        self.calls.append(args)
        if args[1:3] == ["repo", "view"]:
            return "test/repo"
        if args[1:4] == ["api", "--paginate", "--slurp"]:
            records = list(self.records.values())
            return json.dumps([records[:1], records[1:]])
        if args[1] == "api":
            return json.dumps(self.records[int(args[-1].rsplit("/", 1)[1])])
        assert args[1:3] == ["pr", "update-branch"], args
        assert args[4:] == ["--repo", "test/repo"], args
        self.mutations.append(args)
        return "updated"


def run_policy(records, distances, github=None, **kwargs):
    github = github or GitHub(records)
    lines = []
    code = caretaker.update_branches(
        [caretaker.parse_pr(data) for data in records],
        lambda pr: distances[pr.number],
        runner=github,
        cwd=Path.cwd(),
        repository="test/repo",
        min_interval=kwargs.pop("min_interval", 0),
        emit=lines.append,
        **kwargs,
    )
    return code, github, lines


def test_threshold_includes_20_excludes_19_and_prioritises_26():
    records = [payload(20), payload(19), payload(26)]
    code, github, lines = run_policy(records, {20: 20, 19: 19, 26: 26}, concurrency=1)
    assert code == 0
    assert [int(args[3]) for args in github.mutations] == [26, 20]
    assert "#19 distance=19 skipped: below threshold 20" in lines
    assert any("#20 distance=20 updated:" in line for line in lines)
    assert any("#26 distance=26 updated:" in line for line in lines)


def test_drafts_are_not_measured_or_updated_without_explicit_opt_in():
    records = [payload(1, draft=True)]
    code, github, lines = run_policy(records, {})
    assert code == 0
    assert github.calls == []
    assert lines == ["#1 distance=- skipped: draft; use --include-drafts to opt in"]
    code, github, lines = run_policy(records, {1: 26}, include_drafts=True)
    assert code == 0
    assert [args[3] for args in github.mutations] == ["1"]


@pytest.mark.parametrize("changed", ["draft", "closed", "base", "head", "conflict"])
def test_refresh_rejects_pr_that_became_ineligible(changed):
    snapshot = payload(1)
    current = payload(1)
    if changed == "draft":
        current["draft"] = True
    elif changed == "closed":
        current["state"] = "closed"
    elif changed == "base":
        current["base"]["ref"] = "release"
    elif changed == "head":
        current["head"]["sha"] = "f" * 40
    else:
        current["mergeable"] = False
    github = GitHub([current])
    code, _, lines = run_policy([snapshot], {1: 26}, github)
    assert code == 0
    assert github.mutations == []
    assert sum("skipped:" in line for line in lines) == 1


@pytest.mark.parametrize("cap", [1, 2, 3])
def test_concurrency_cap_is_honoured(cap):
    records = [payload(n) for n in range(1, 8)]
    github = GitHub(records)
    release = threading.Event()
    saturated = threading.Event()
    guard = threading.Lock()
    active = peak = 0

    def runner(args, cwd):
        nonlocal active, peak
        if args[1:3] != ["pr", "update-branch"]:
            return github(args, cwd)
        with guard:
            active += 1
            peak = max(peak, active)
            if active >= cap:
                saturated.set()
        try:
            assert release.wait(timeout=5), "test did not release update workers"
            return github(args, cwd)
        finally:
            with guard:
                active -= 1

    with ThreadPoolExecutor(max_workers=1) as control:
        result = control.submit(
            run_policy, records, {n: 26 for n in range(1, 8)}, runner, concurrency=cap
        )
        try:
            assert saturated.wait(timeout=5), "caretaker never reached the configured cap"
            with guard:
                assert peak == cap
        finally:
            release.set()
        assert result.result(timeout=5)[0] == 0
    assert peak == cap
    assert len(github.mutations) == 7


def test_minimum_interval_between_update_calls():
    records = [payload(n) for n in range(1, 4)]
    github = GitHub(records)
    now = 0.0
    starts = []
    sleeps = []

    def runner(args, cwd):
        if args[1:3] == ["pr", "update-branch"]:
            starts.append(now)
        return github(args, cwd)

    def sleep(delay):
        nonlocal now
        sleeps.append(delay)
        now += delay

    code, _, _ = run_policy(
        records,
        {n: 26 for n in range(1, 4)},
        runner,
        concurrency=1,
        min_interval=60,
        clock=lambda: now,
        sleep=sleep,
    )
    assert code == 0
    assert starts == [0, 60, 120]
    assert sleeps == [60, 60]


def test_failed_distance_and_update_fail_loud_but_do_not_block_other_prs():
    records = [payload(1), payload(2), payload(3)]
    github = GitHub(records)
    lines = []

    def distance(pr):
        if pr.number == 1:
            raise RuntimeError("missing merge base")
        return 26

    def runner(args, cwd):
        if args[1:4] == ["pr", "update-branch", "2"]:
            raise RuntimeError("GitHub denied update")
        return github(args, cwd)

    code = caretaker.update_branches(
        [caretaker.parse_pr(data) for data in records],
        distance,
        runner=runner,
        cwd=Path.cwd(),
        repository="test/repo",
        min_interval=0,
        emit=lines.append,
    )
    assert code == 1
    assert [args[3] for args in github.mutations] == ["3"]
    assert any("missing merge base" in line for line in lines)
    assert any("GitHub denied update" in line for line in lines)


@pytest.fixture
def history(tmp_path):
    origin = tmp_path / "origin.git"
    source = tmp_path / "source"

    def git(cwd, *args):
        return caretaker.run_command(["git", *args], cwd)

    git(tmp_path, "init", "--bare", "--quiet", str(origin))
    git(origin, "config", "user.name", "Caretaker test")
    git(origin, "config", "user.email", "caretaker@example.invalid")
    tree = subprocess.run(
        ["git", "mktree"], cwd=origin, input="", capture_output=True, text=True, check=True
    ).stdout.strip()
    commits = [git(origin, "commit-tree", tree, "-m", "root")]
    for number in range(26):
        commits.append(git(origin, "commit-tree", tree, "-p", commits[-1], "-m", str(number)))
    git(origin, "update-ref", "refs/heads/main", commits[-1])
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    records = []
    for number in (19, 20, 26):
        head = git(origin, "commit-tree", tree, "-p", commits[26 - number], "-m", f"PR {number}")
        git(origin, "update-ref", f"refs/pull/{number}/head", head)
        records.append(payload(number, head=head))
    git(tmp_path, "clone", "--quiet", str(origin), str(source))
    return source, origin, records, git


def test_real_gate_distances_and_second_run_converges(history, monkeypatch, capsys):
    source, origin, records, git = history
    github = GitHub(records)
    original_head = git(source, "rev-parse", "HEAD")
    original_main = git(origin, "rev-parse", "main")
    monkeypatch.chdir(source)

    def runner(args, cwd):
        result = github(args, cwd)
        if args[1:3] == ["pr", "update-branch"]:
            number = int(args[3])
            previous = github.records[number]["head"]["sha"]
            tree = git(origin, "rev-parse", "main^{tree}")
            head = git(
                origin,
                "commit-tree",
                tree,
                "-p",
                previous,
                "-p",
                original_main,
                "-m",
                "Merge main into PR",
            )
            git(origin, "update-ref", f"refs/pull/{number}/head", head)
            github.records[number]["head"]["sha"] = head
        return result

    assert caretaker.main(["--min-interval", "0", "--concurrency", "1"], runner=runner) == 0
    first = capsys.readouterr().out
    assert "#19 distance=19 skipped" in first
    assert "#20 distance=20 updated" in first
    assert "#26 distance=26 updated" in first
    assert [args[3] for args in github.mutations] == ["26", "20"]
    assert caretaker.main(["--min-interval", "0"], runner=runner) == 0
    second = capsys.readouterr().out
    assert "#20 distance=0 skipped" in second
    assert "#26 distance=0 skipped" in second
    assert len(github.mutations) == 2
    assert git(source, "rev-parse", "HEAD") == original_head
    assert git(origin, "rev-parse", "main") == original_main
    assert git(source, "status", "--porcelain") == ""


def test_cli_dry_run_has_zero_mutating_gh_calls(history, monkeypatch, capsys):
    source, _, records, _ = history
    github = GitHub(records)
    monkeypatch.chdir(source)
    assert caretaker.main(["--dry-run"], runner=github) == 0
    output = capsys.readouterr().out
    assert "#19 distance=19 skipped" in output
    assert "#20 distance=20 dry-run" in output
    assert "#26 distance=26 dry-run" in output
    assert github.calls  # Read calls really happened; this is not a vacuous no-op.
    assert github.mutations == []
    assert all(args[1] == "api" or args[1:3] == ["repo", "view"] for args in github.calls)


def test_changed_fetch_head_cannot_be_updated(history, tmp_path):
    source, _, records, _ = history
    distance = caretaker.GateDistance(source, tmp_path / "scratch.git", caretaker.run_command)
    pr = caretaker.parse_pr(payload(26, head="f" * 40))
    with pytest.raises(RuntimeError, match="head changed during fetch"):
        distance(pr)


@pytest.mark.parametrize(
    "args",
    [
        ["--threshold", "0"],
        ["--concurrency", "0"],
        ["--min-interval", "-1"],
        ["--min-interval", "nan"],
        ["--min-interval", "inf"],
    ],
)
def test_invalid_cli_limits_fail_before_any_command(args):
    def forbidden(args, cwd):
        pytest.fail(f"unexpected command: {args}")

    with pytest.raises(SystemExit) as result:
        caretaker.main(args, runner=forbidden)
    assert result.value.code == 2


def test_draft_recheck_happens_after_rate_limit_wait():
    records = [payload(1), payload(2)]
    github = GitHub(records)
    now = 0.0

    def sleep(delay):
        nonlocal now
        now += delay
        github.records[2]["draft"] = True

    code, _, lines = run_policy(
        records, {1: 26, 2: 20}, github, min_interval=60, clock=lambda: now, sleep=sleep
    )
    assert code == 0
    assert [args[3] for args in github.mutations] == ["1"]
    assert "#2 distance=20 skipped: draft; use --include-drafts to opt in" in lines


def test_gate_unrelated_history_is_not_treated_as_fresh(history, tmp_path):
    source, origin, _, git = history
    tree = git(origin, "rev-parse", "main^{tree}")
    unrelated = git(origin, "commit-tree", tree, "-m", "unrelated root")
    git(origin, "update-ref", "refs/pull/1/head", unrelated)
    distance = caretaker.GateDistance(source, tmp_path / "scratch.git", caretaker.run_command)
    with pytest.raises(RuntimeError, match="cannot determine merge-base"):
        distance(caretaker.parse_pr(payload(1, head=unrelated)))


def test_overlapping_local_run_does_not_even_query_github(history, monkeypatch, capsys):
    source, _, records, git = history
    github = GitHub(records)
    monkeypatch.chdir(source)
    lock_path = source / git(source, "rev-parse", "--git-common-dir") / "merge-age-caretaker.lock"
    with lock_path.open("a+") as lock:
        caretaker.fcntl.flock(lock, caretaker.fcntl.LOCK_EX | caretaker.fcntl.LOCK_NB)
        assert caretaker.main([], runner=github) == 0
    assert github.calls == []
    assert "another run holds the repository lock" in capsys.readouterr().out


@pytest.mark.parametrize("dry_run", [False, True])
def test_ceiling_flags_300_updates_150_and_includes_boundary(dry_run):
    records = [payload(n) for n in (300, 150, 200, 201)]
    code, github, lines = run_policy(
        records,
        {n: n for n in (300, 150, 200, 201)},
        concurrency=1,
        dry_run=dry_run,
        now=datetime(2026, 10, 2, tzinfo=UTC),
    )
    assert code == 0
    assert [int(args[3]) for args in github.mutations] == ([] if dry_run else [200, 150])
    assert "Distance distribution: measured=4; below 20=0; band 20..200=2; above 200=2" in lines
    section = lines.index("Far-behind PRs (operator review; no update requests):")
    assert lines[section + 1].startswith("#300 distance=300 flag: far-behind (300); age=51.0d;")
    assert lines[section + 2].startswith("#201 distance=201 flag: far-behind (201); age=51.0d;")
    assert all(args[3] not in {"300", "201"} for args in github.mutations)


def test_explicit_ceiling_override_changes_update_band():
    records = [payload(300)]
    code, github, lines = run_policy(records, {300: 300}, ceiling=300)
    assert code == 0
    assert [args[3] for args in github.mutations] == ["300"]
    assert not any("flag: far-behind" in line for line in lines)


@pytest.mark.parametrize("args", [["--ceiling", "0"], ["--threshold", "201", "--ceiling", "200"]])
def test_invalid_ceiling_fails_before_any_command(args):
    def forbidden(args, cwd):
        pytest.fail(f"unexpected command: {args}")

    with pytest.raises(SystemExit) as result:
        caretaker.main(args, runner=forbidden)
    assert result.value.code == 2
