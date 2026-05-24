"""
``python -m tools.agent_commits`` — inspect Claude-co-authored commits.

Three subcommands:

- ``list``      — every commit on the current branch (or in a window)
                  that carries a ``Co-Authored-By: Claude`` trailer.
                  One short row per commit.
- ``show``      — show a single commit's metadata + its persisted
                  prompt body from ``prompts/<hash>.md``.
- ``stats``     — total agent commits vs operator commits; mean/median
                  agent commits per day for the window.

The CLI is a thin wrapper around ``git log`` plus filesystem reads of
``prompts/<hash>.md``. No new state is introduced: the hook persists,
this tool reads.

Usage:

    python -m tools.agent_commits list --since 7d
    python -m tools.agent_commits show abc1234       # by short SHA
    python -m tools.agent_commits show <prompt-hash> # by prompt hash
    python -m tools.agent_commits stats --since 30d

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e6-provenance.html
"""

from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

CO_AUTHORED_GREP = "Co-Authored-By: Claude"
PROMPT_HASH_RE = re.compile(r"^Prompt-Hash:\s+([0-9a-f]{64})\s*$", re.MULTILINE)


@dataclass(frozen=True)
class AgentCommit:
    sha: str
    short_sha: str
    iso_date: str
    subject: str
    prompt_hash: str | None  # None for legacy commits authored before SPR-E6
    body: str


def _git(*args: str, cwd: Path | None = None) -> str:
    """Run git and return stdout, raising on non-zero."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _git_log_safe(*args: str) -> str:
    """``git log`` that returns empty string on a HEAD-less repo.

    A brand-new repo with zero commits causes ``git log`` to exit
    non-zero with "your current branch does not have any commits yet."
    Treating that as 0 commits is the right operator-facing answer.
    """
    result = subprocess.run(
        ["git", "log", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The headless case is the only failure we tolerate; other
        # errors (e.g. not-a-git-repo) should still surface.
        if "does not have any commits yet" in result.stderr or "bad default revision" in result.stderr:
            return ""
        raise RuntimeError(f"git log failed: {result.stderr.strip()}")
    return result.stdout


def repo_root() -> Path:
    return Path(_git("rev-parse", "--show-toplevel").strip())


def _parse_since(spec: str | None) -> str | None:
    """Translate ``--since`` shorthand. Passes through to git's parser.

    Accepts ``"7d"``, ``"30d"``, ``"2w"``, ``"1y"``, full ISO dates, or
    anything git understands. Returns the value to pass through, or
    ``None`` if no filter was requested.
    """
    return spec


def list_commits(since: str | None) -> list[AgentCommit]:
    """Return agent commits matching the (optional) window, newest first."""
    args = [
        f"--grep={CO_AUTHORED_GREP}",
        "--pretty=format:%H%x1f%h%x1f%cI%x1f%s%x1f%B%x1e",
    ]
    if since:
        args.insert(0, f"--since={since}")
    raw = _git_log_safe(*args)
    if not raw.strip():
        return []
    out: list[AgentCommit] = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.lstrip("\n")
        if not chunk:
            continue
        parts = chunk.split("\x1f", 4)
        if len(parts) < 5:
            continue
        sha, short_sha, iso_date, subject, body = parts
        match = PROMPT_HASH_RE.search(body)
        prompt_hash = match.group(1) if match else None
        out.append(
            AgentCommit(
                sha=sha,
                short_sha=short_sha,
                iso_date=iso_date,
                subject=subject,
                prompt_hash=prompt_hash,
                body=body,
            )
        )
    return out


def find_prompt_file(prompts_dir: Path, identifier: str) -> Path | None:
    """Resolve ``identifier`` to a ``prompts/<hash>.md`` path.

    Accepts either a 64-char hex prompt hash directly, or a short SHA
    of a commit (we then look up the commit and read its trailer).
    """
    if len(identifier) == 64 and all(c in "0123456789abcdef" for c in identifier.lower()):
        candidate = prompts_dir / f"{identifier.lower()}.md"
        return candidate if candidate.exists() else None
    # Treat as a commit SHA; pull its message and read the trailer.
    try:
        body = _git("log", "-1", "--format=%B", identifier).strip()
    except RuntimeError:
        return None
    match = PROMPT_HASH_RE.search(body)
    if not match:
        return None
    candidate = prompts_dir / f"{match.group(1)}.md"
    return candidate if candidate.exists() else None


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    commits = list_commits(since=_parse_since(args.since))
    if not commits:
        print("(no agent commits found in window)")
        return 0
    for c in commits:
        tagged = "✓" if c.prompt_hash else "·"
        print(f"{c.short_sha}  {c.iso_date[:10]}  {tagged}  {c.subject}")
    print()
    print(f"{len(commits)} agent commit(s); ✓ = has Prompt-Hash trailer")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    prompts_dir = repo_root() / "prompts"
    path = find_prompt_file(prompts_dir, args.identifier)
    if not path:
        print(
            f"No prompt found for {args.identifier!r}. Either the commit pre-dates "
            "SPR-E6 (no Prompt-Hash trailer), or the prompt file is missing from "
            "prompts/. Run 'python -m tools.agent_commits list' to see tagged commits.",
            file=sys.stderr,
        )
        return 1
    print(f"# {path.relative_to(repo_root())}")
    print()
    print(path.read_text(encoding="utf-8").rstrip())
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    since = _parse_since(args.since)
    agent_commits = list_commits(since=since)
    # All commits in window for the ratio.
    log_args = ["--pretty=format:%cI"]
    if since:
        log_args.insert(0, f"--since={since}")
    all_dates = [ln for ln in _git_log_safe(*log_args).splitlines() if ln.strip()]
    total = len(all_dates)
    if total == 0:
        print("(no commits in window)")
        return 0
    agent_per_day: Counter[str] = Counter(c.iso_date[:10] for c in agent_commits)
    print(f"window: --since={since or 'beginning of history'}")
    print(f"total commits: {total}")
    print(f"agent commits: {len(agent_commits)} ({100 * len(agent_commits) / total:.1f}%)")
    if agent_per_day:
        counts = list(agent_per_day.values())
        print(f"agent commits/day: mean={statistics.mean(counts):.2f}, median={statistics.median(counts):.1f}, max={max(counts)}")
    tagged = sum(1 for c in agent_commits if c.prompt_hash)
    if agent_commits:
        print(f"agent commits with Prompt-Hash trailer: {tagged}/{len(agent_commits)} ({100 * tagged / len(agent_commits):.0f}%)")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.agent_commits",
        description=(
            "Inspect Claude-co-authored commits and their persisted prompts. "
            "Companion to the .githooks/commit-msg hook (SPR-E6)."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list agent commits, newest first")
    p_list.add_argument(
        "--since",
        default=None,
        help="git --since spec (e.g. '7d', '30d', '2026-05-01'). Default: no window.",
    )
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show a commit's prompt body")
    p_show.add_argument(
        "identifier",
        help="either a 64-char prompt hash or a commit SHA (short or full)",
    )
    p_show.set_defaults(func=cmd_show)

    p_stats = sub.add_parser("stats", help="agent-vs-operator commit ratio + cadence")
    p_stats.add_argument(
        "--since",
        default="30d",
        help="git --since spec (default: 30d)",
    )
    p_stats.set_defaults(func=cmd_stats)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
