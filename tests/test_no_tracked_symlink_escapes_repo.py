"""No tracked symlink may point outside the repository.

A symlink's target is committed as text. An absolute target
(``/Users/<operator>/...``) or one that climbs out of the tree names a path
on the machine that committed it; on a CI runner or on the production host
after ``git pull`` it dangles, or worse, resolves to something unrelated.

This is not hypothetical: a worktree's convenience symlink
``node_modules -> /Users/slimydog/Antiek/platform/node_modules`` reached main
five times (``git add -A`` in a worktree), because ``.gitignore`` said
``node_modules/`` and a trailing slash matches directories only, never a
symlink. The ignore pattern is fixed alongside this test; this test is the
backstop for every other path a symlink can take into the index.
"""

from __future__ import annotations

import posixpath
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tracked_symlinks() -> list[tuple[str, str]]:
    """(path, target) for every mode-120000 entry in the index."""
    out = subprocess.run(
        ["git", "ls-files", "-s", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    links = []
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        mode, blob, _stage = meta.split()
        if mode == "120000":
            target = subprocess.run(
                ["git", "cat-file", "-p", blob], cwd=ROOT, capture_output=True, check=True
            ).stdout.decode()
            links.append((path, target))
    return links


def escapes_repo(path: str, target: str) -> bool:
    """True if ``target``, read as the link at ``path`` would, leaves the tree."""
    if posixpath.isabs(target):
        return True
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
    return resolved == ".." or resolved.startswith("../")


def test_escape_rule_on_planted_cases():
    assert escapes_repo("node_modules", "/Users/someone/Antiek/platform/node_modules")
    assert escapes_repo("a/link", "../../outside")
    assert escapes_repo("link", "..")
    assert not escapes_repo("a/link", "../sibling")
    assert not escapes_repo("a/b/link", "../../top-level-file")
    assert not escapes_repo("link", "docs/x.md")


def test_no_tracked_symlink_escapes_the_repository():
    offenders = [f"{p} -> {t}" for p, t in _tracked_symlinks() if escapes_repo(p, t)]
    assert not offenders, (
        "tracked symlink(s) point outside the repository (they dangle on CI and in "
        "production): " + "; ".join(offenders) + ". `git rm --cached <path>`."
    )
