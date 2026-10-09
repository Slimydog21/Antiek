#!/usr/bin/env python3
"""Keep open PR heads below the merge-age gate without merging any PR.

Run from a checkout of the target repository:
    python3 tools/caretaker/update_stale_branches.py --dry-run

Only ``gh pr update-branch`` mutates GitHub. Its default merge commit brings
main into the PR branch without rewriting history. This is NOT a PR merge.
Distances use the unchanged merge_age_gate.compute_distance in a disposable
bare repository; no PR code is checked out or executed. Updates are bounded
per process, with a checkout-wide lock against overlapping local runs. Remote
schedulers must also use a single concurrency group.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import math
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_THRESHOLD = 20
# 2026-10-02 dry-run: 7 stale heads were 57..129 behind; 21 were 471..2072.
# 200 is a conservative policy cap inside that empty gap, not a pass guarantee.
# Older heads need operator review rather than automatically spending CI on them.
DEFAULT_CEILING = 200
DEFAULT_CONCURRENCY = 3
DEFAULT_MIN_INTERVAL = 60.0


class Runner(Protocol):
    def __call__(self, args: list[str], cwd: Path) -> str: ...


def run_command(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f"{' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


@dataclass(frozen=True)
class PullRequest:
    number: int
    head: str
    draft: bool
    base: str
    state: str
    mergeable: bool | None
    created_at: datetime


def parse_pr(data: dict[str, Any]) -> PullRequest:
    number, head, draft = data["number"], data["head"]["sha"], data["draft"]
    if type(number) is not int or number < 1 or type(draft) is not bool:
        raise ValueError("invalid PR number or draft flag")
    if (
        not isinstance(head, str)
        or len(head) != 40
        or any(c not in "0123456789abcdef" for c in head)
    ):
        raise ValueError(f"invalid head SHA for PR #{number}")
    base, state, mergeable = data["base"]["ref"], data["state"], data.get("mergeable")
    if not isinstance(base, str) or state not in {"open", "closed"}:
        raise ValueError(f"invalid base or state for PR #{number}")
    if mergeable is not None and type(mergeable) is not bool:
        raise ValueError(f"invalid mergeable flag for PR #{number}")
    created = data["created_at"]
    if not isinstance(created, str):
        raise ValueError(f"invalid creation date for PR #{number}")
    created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
    if created_at.tzinfo is None:
        raise ValueError(f"creation date has no timezone for PR #{number}")
    return PullRequest(number, head, draft, base, state, mergeable, created_at)


def skip_reason(pr: PullRequest, include_drafts: bool) -> str | None:
    if pr.state != "open":
        return "PR is no longer open"
    if pr.base != "main":
        return "base is not main"
    if pr.draft and not include_drafts:
        return "draft; use --include-drafts to opt in"
    return None


class GateDistance:
    """Adapt only the gate's repository root, not its distance algorithm."""

    def __init__(self, source: Path, scratch: Path, runner: Runner):
        self.runner = runner
        self.scratch = scratch
        remote = runner(["git", "remote", "get-url", "origin"], source)
        runner(["git", "clone", "--quiet", "--bare", "--shared", str(source), str(scratch)], source)
        runner(["git", "remote", "set-url", "origin", remote], scratch)
        runner(
            [
                "git",
                "fetch",
                "--quiet",
                "--no-tags",
                "origin",
                "refs/heads/main:refs/remotes/origin/main",
            ],
            scratch,
        )
        gate_path = REPO_ROOT / "tools/lint/merge_age_gate.py"
        spec = importlib.util.spec_from_file_location("_caretaker_merge_age_gate", gate_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot import {gate_path}")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        # Private module instance: no shared gate globals or caller HEAD change.
        gate.__dict__["_REPO"] = scratch
        self.compute_distance: Callable[[], tuple[int | None, str]] = gate.compute_distance

    def __call__(self, pr: PullRequest) -> int:
        self.runner(
            ["git", "fetch", "--quiet", "--no-tags", "origin", f"refs/pull/{pr.number}/head"],
            self.scratch,
        )
        fetched = self.runner(["git", "rev-parse", "FETCH_HEAD"], self.scratch)
        if fetched != pr.head:
            raise RuntimeError("head changed during fetch; retry on the next run")
        self.runner(["git", "update-ref", "--no-deref", "HEAD", fetched], self.scratch)
        distance, error = self.compute_distance()
        if distance is None:
            raise RuntimeError(error)
        return distance


def update_branches(
    prs: Sequence[PullRequest],
    distance: Callable[[PullRequest], int],
    *,
    runner: Runner,
    cwd: Path,
    repository: str,
    threshold: int = DEFAULT_THRESHOLD,
    ceiling: int = DEFAULT_CEILING,
    concurrency: int = DEFAULT_CONCURRENCY,
    min_interval: float = DEFAULT_MIN_INTERVAL,
    include_drafts: bool = False,
    dry_run: bool = False,
    emit: Callable[[str], None] = print,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
) -> int:
    """Measure first, then submit the most stale PRs first. Return an exit code."""
    candidates: list[tuple[int, PullRequest]] = []
    far_behind: list[tuple[int, PullRequest]] = []
    distances: list[int] = []
    now = now or datetime.now(UTC)
    failures = 0
    for pr in prs:
        reason = skip_reason(pr, include_drafts)
        if reason:
            emit(f"#{pr.number} distance=- skipped: {reason}")
            continue
        try:
            behind = distance(pr)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            emit(f"#{pr.number} distance=? error: {exc}")
            failures += 1
            continue
        distances.append(behind)
        if behind < threshold:
            emit(f"#{pr.number} distance={behind} skipped: below threshold {threshold}")
        elif behind > ceiling:
            far_behind.append((behind, pr))
        else:
            candidates.append((behind, pr))
    candidates.sort(key=lambda item: (-item[0], item[1].number))
    if distances:
        below = sum(value < threshold for value in distances)
        emit(
            f"Distance distribution: measured={len(distances)}; below {threshold}={below}; "
            f"band {threshold}..{ceiling}={len(candidates)}; above {ceiling}={len(far_behind)}"
        )
        emit("Measured distances (commits): " + ", ".join(map(str, sorted(distances))))
    if far_behind:
        emit("Far-behind PRs (operator review; no update requests):")
        for behind, pr in sorted(far_behind, key=lambda item: (-item[0], item[1].number)):
            age_days = max(0, (now - pr.created_at).total_seconds()) / 86400
            emit(
                f"#{pr.number} distance={behind} flag: far-behind ({behind}); "
                f"age={age_days:.1f}d; created={pr.created_at.isoformat()}; ceiling={ceiling}"
            )

    if dry_run:
        for behind, pr in candidates:
            emit(
                f"#{pr.number} distance={behind} dry-run: would update branch (band {threshold}..{ceiling})"
            )
        return int(bool(failures))

    pending: dict[Future[str], tuple[int, PullRequest]] = {}
    last_update: float | None = None
    launch_lock = Lock()

    def request_update(pr: PullRequest, started: Event) -> str:
        nonlocal last_update
        try:
            with launch_lock:
                if last_update is not None:
                    delay = min_interval - (clock() - last_update)
                    if delay > 0:
                        sleep(delay)
                current = parse_pr(
                    json.loads(runner(["gh", "api", f"repos/{repository}/pulls/{pr.number}"], cwd))
                )
                reason = skip_reason(current, include_drafts)
                if current.head != pr.head:
                    reason = "head changed since measurement; retry on the next run"
                if current.mergeable is False:
                    reason = "merge conflicts require manual resolution"
                if reason:
                    return f"skipped: {reason}"
                last_update = clock()
                started.set()
            runner(["gh", "pr", "update-branch", str(pr.number), "--repo", repository], cwd)
            return "updated: gh pr update-branch requested"
        finally:
            started.set()

    def collect(done: set[Future[str]]) -> None:
        nonlocal failures
        for future in done:
            behind, pr = pending.pop(future)
            try:
                action = future.result()
                emit(f"#{pr.number} distance={behind} {action}")
            except (
                RuntimeError,
                OSError,
                subprocess.TimeoutExpired,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:
                emit(f"#{pr.number} distance={behind} error: {exc}")
                failures += 1

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for behind, pr in candidates:
            if len(pending) >= concurrency:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                collect(done)
            started = Event()
            future = pool.submit(request_update, pr, started)
            pending[future] = (behind, pr)
            started.wait()
        if pending:
            done, _ = wait(pending)
            collect(done)
    return int(bool(failures))


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def interval(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return seconds


def main(argv: Sequence[str] | None = None, *, runner: Runner = run_command) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=positive_int, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--ceiling",
        type=positive_int,
        default=DEFAULT_CEILING,
        help="flag rather than update above this distance (default: 200)",
    )
    parser.add_argument("--concurrency", type=positive_int, default=DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--min-interval",
        type=interval,
        default=DEFAULT_MIN_INTERVAL,
        help="minimum seconds between update calls (default: 60)",
    )
    parser.add_argument("--include-drafts", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.threshold > args.ceiling:
        parser.error("--threshold must not exceed --ceiling")
    cwd = Path.cwd()
    try:
        common = Path(runner(["git", "rev-parse", "--git-common-dir"], cwd))
        if not common.is_absolute():
            common = cwd / common
        with (common / "merge-age-caretaker.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("caretaker: skipped: another run holds the repository lock")
                return 0
            repository = runner(
                ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd
            )
            pages = json.loads(
                runner(
                    [
                        "gh",
                        "api",
                        "--paginate",
                        "--slurp",
                        f"repos/{repository}/pulls?state=open&base=main&per_page=100",
                    ],
                    cwd,
                )
            )
            prs = [parse_pr(data) for page in pages for data in page]
            if not prs:
                print("caretaker: no open PRs targeting main")
                return 0
            with TemporaryDirectory(prefix="merge-age-caretaker-") as temp:
                distance = GateDistance(cwd, Path(temp) / "repo.git", runner)
                return update_branches(
                    prs, distance, runner=runner, cwd=cwd, repository=repository, **vars(args)
                )
    except (
        RuntimeError,
        OSError,
        subprocess.TimeoutExpired,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        print(f"caretaker: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
