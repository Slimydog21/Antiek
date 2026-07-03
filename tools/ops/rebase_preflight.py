"""Read-only rebase preflight for stale Antiek integration branches.

The merge-age gate tells us when a branch is too far behind ``origin/main``.
This helper answers the next operator question without mutating the worktree:
"what will a rebase have to reconcile?"
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from tools.lint.merge_age_gate import MAX_BEHIND

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RebasePreflight:
    status: str
    branch: str
    head_sha: str
    origin_main_sha: str
    merge_base_sha: str
    commits_behind_origin_main: int
    max_behind: int
    local_commit_count: int
    origin_commit_count: int
    local_changed_file_count: int
    origin_changed_file_count: int
    overlapping_file_count: int
    overlapping_files: tuple[str, ...]
    merge_tree_conflict_count: int
    merge_tree_conflict_files: tuple[str, ...]
    remediation: str
    does_not_rebase: bool = True


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _git_text(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _git_lines(repo: Path, *args: str) -> tuple[str, ...]:
    text = _git_text(repo, *args)
    return tuple(line for line in text.splitlines() if line)


def _changed_files(repo: Path, rev_range: str) -> set[str]:
    return set(_git_lines(repo, "diff", "--name-only", rev_range))


def _count_commits(repo: Path, rev_range: str) -> int:
    value = _git_text(repo, "rev-list", "--count", rev_range)
    if not value.isdigit():
        raise GitError(f"git rev-list --count {rev_range} returned {value!r}")
    return int(value)


def _merge_tree_conflicts(repo: Path, head: str, origin_main: str) -> tuple[str, ...]:
    """Return conflicted paths reported by read-only ``git merge-tree``.

    ``git merge-tree --write-tree`` writes only git objects, not the worktree or
    index. On conflicts it exits non-zero and prints staged entries with a path
    after a tab. Grouping those paths gives the operator the first conflict set.
    """

    result = _git(repo, "merge-tree", "--write-tree", head, origin_main)
    if result.returncode == 0:
        return ()
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        path = line.rsplit("\t", 1)[-1].strip()
        if path:
            paths.add(path)
    return tuple(sorted(paths))


def run_preflight(repo: Path = ROOT) -> RebasePreflight:
    """Build a read-only integration-risk snapshot against ``origin/main``."""

    branch = _git_text(repo, "branch", "--show-current") or "detached"
    head = _git_text(repo, "rev-parse", "HEAD")
    origin_main = _git_text(repo, "rev-parse", "origin/main")
    merge_base = _git_text(repo, "merge-base", "HEAD", "origin/main")

    commits_behind = _count_commits(repo, f"{merge_base}..origin/main")
    local_commit_count = _count_commits(repo, f"{merge_base}..HEAD")
    origin_commit_count = _count_commits(repo, f"{merge_base}..origin/main")
    local_files = _changed_files(repo, f"{merge_base}..HEAD")
    origin_files = _changed_files(repo, f"{merge_base}..origin/main")
    overlapping_files = tuple(sorted(local_files & origin_files))
    conflict_files = _merge_tree_conflicts(repo, "HEAD", "origin/main")

    if conflict_files:
        status = "conflicts"
        remediation = "run the rebase in a disposable worktree and resolve conflicts"
    elif commits_behind > MAX_BEHIND:
        status = "stale"
        remediation = "run `git rebase origin/main`"
    else:
        status = "ready"
        remediation = "branch freshness is within the merge-age budget"

    return RebasePreflight(
        status=status,
        branch=branch,
        head_sha=head[:7],
        origin_main_sha=origin_main[:7],
        merge_base_sha=merge_base[:7],
        commits_behind_origin_main=commits_behind,
        max_behind=MAX_BEHIND,
        local_commit_count=local_commit_count,
        origin_commit_count=origin_commit_count,
        local_changed_file_count=len(local_files),
        origin_changed_file_count=len(origin_files),
        overlapping_file_count=len(overlapping_files),
        overlapping_files=overlapping_files[:50],
        merge_tree_conflict_count=len(conflict_files),
        merge_tree_conflict_files=conflict_files[:50],
        remediation=remediation,
    )


def format_text(preflight: RebasePreflight) -> str:
    lines = [
        f"rebase-preflight: {preflight.status}",
        (
            f"branch: {preflight.branch} HEAD={preflight.head_sha} "
            f"origin/main={preflight.origin_main_sha} base={preflight.merge_base_sha}"
        ),
        (
            "distance: "
            f"{preflight.commits_behind_origin_main}/{preflight.max_behind} "
            "commits behind origin/main"
        ),
        (
            "changes: "
            f"local_commits={preflight.local_commit_count} "
            f"origin_commits={preflight.origin_commit_count} "
            f"local_files={preflight.local_changed_file_count} "
            f"origin_files={preflight.origin_changed_file_count} "
            f"overlap={preflight.overlapping_file_count}"
        ),
        (
            "merge_tree: "
            f"conflicts={preflight.merge_tree_conflict_count}"
        ),
        f"remediation: {preflight.remediation}",
        "does_not_rebase: yes",
    ]
    if preflight.overlapping_files:
        lines.append("overlap_files:")
        lines.extend(f"- {path}" for path in preflight.overlapping_files)
    if preflight.merge_tree_conflict_files:
        lines.append("conflict_files:")
        lines.extend(f"- {path}" for path in preflight.merge_tree_conflict_files)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only preflight before rebasing a stale branch."
    )
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    preflight = run_preflight(args.repo)
    if args.json:
        print(json.dumps(asdict(preflight), indent=2, sort_keys=True))
    else:
        print(format_text(preflight))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
