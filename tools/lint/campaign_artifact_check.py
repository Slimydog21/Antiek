"""Reject generated agent-campaign artifacts from the tracked product tree."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

FORBIDDEN_ROOT = PurePosixPath("docs/campaigns")


def find_forbidden(paths: Iterable[str]) -> tuple[str, ...]:
    """Return normalized tracked paths under the orchestration-scratch root."""
    violations: set[str] = set()
    for raw in paths:
        normalized = raw.strip().replace("\\", "/")
        if not normalized:
            continue
        path = PurePosixPath(normalized)
        if path == FORBIDDEN_ROOT or FORBIDDEN_ROOT in path.parents:
            violations.add(path.as_posix())
    return tuple(sorted(violations))


def tracked_paths(repo: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return tuple(path.decode() for path in result.stdout.split(b"\0") if path)


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    repo = Path(arguments[0]).resolve() if arguments else Path.cwd()
    violations = find_forbidden(tracked_paths(repo))
    if not violations:
        print("campaign-artifact-check: clean")
        return 0
    print(
        "campaign-artifact-check: generated orchestration files are tracked; "
        "move durable conclusions to docs/decisions or docs/htmlspec",
        file=sys.stderr,
    )
    for path in violations:
        print(path, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
