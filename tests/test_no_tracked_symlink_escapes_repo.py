"""No tracked symlink may point outside the repository.

A symlink's target is committed as text. An absolute target
(``/Users/<operator>/...``) or one that climbs out of the tree names a path
on the machine that committed it; in any other checkout (every CI runner) it
dangles, or worse, resolves to something unrelated. A target is resolved the
way a checkout resolves it: through every other tracked symlink, component
by component, never by normalizing ``..`` lexically.

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


def _tracked_symlinks(root: Path = ROOT) -> list[tuple[str, str]]:
    """(path, target) for every mode-120000 entry in the index."""
    out = subprocess.run(
        ["git", "ls-files", "-s", "-z"], cwd=root, capture_output=True, check=True
    ).stdout.decode()
    links = []
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        mode, blob, _stage = meta.split()
        if mode == "120000":
            target = subprocess.run(
                ["git", "cat-file", "-p", blob], cwd=root, capture_output=True, check=True
            ).stdout.decode()
            links.append((path, target))
    return links


_MAX_LINK_HOPS = 40  # the Linux ELOOP bound; a cycle never resolves


def _resolve_in_index(path: str, links: dict[str, str]) -> list[str] | None:
    """The repository-relative components ``path`` resolves to when every
    tracked symlink is followed, or None if resolution leaves the tree, hits
    an absolute target, or cycles.

    Resolution is POSIX-style and uses only the index: each component is
    checked against the tracked links before ``..`` is applied, so
    ``alias/../x`` where ``alias`` is itself a tracked link is followed
    through the link, not normalized away lexically."""
    resolved: list[str] = []
    pending = [part for part in path.split("/") if part]
    hops = 0
    while pending:
        part = pending.pop(0)
        if part == ".":
            continue
        if part == "..":
            if not resolved:
                return None
            resolved.pop()
            continue
        candidate = "/".join([*resolved, part])
        target = links.get(candidate)
        if target is None:
            resolved.append(part)
            continue
        hops += 1
        if hops > _MAX_LINK_HOPS or posixpath.isabs(target):
            return None
        # The target is read relative to the link's own (resolved) directory.
        pending = [p for p in target.split("/") if p] + pending
    return resolved


def escapes_repo(path: str, target: str, links: dict[str, str] | None = None) -> bool:
    """True if the link at ``path`` with ``target`` leaves the tree when
    resolved as a checkout would, following every other tracked symlink in
    ``links`` (path -> target) along the way."""
    if posixpath.isabs(target):
        return True
    index = dict(links or {})
    index[path] = target
    return _resolve_in_index(path, index) is None


def test_escape_rule_on_planted_cases():
    assert escapes_repo("node_modules", "/Users/someone/Antiek/platform/node_modules")
    assert escapes_repo("a/link", "../../outside")
    assert escapes_repo("link", "..")
    assert not escapes_repo("a/link", "../sibling")
    assert not escapes_repo("a/b/link", "../../top-level-file")
    assert not escapes_repo("link", "docs/x.md")


def test_a_chain_through_another_tracked_symlink_is_resolved_not_normalized():
    # Codex round 1 on #3412: `alias/../../outside` normalizes lexically to a
    # path inside the tree, but `alias` is itself a tracked link to `..`, so
    # on disk the chain lands outside the repository.
    links = {"dir/alias": "..", "dir/link": "alias/../../outside"}
    assert escapes_repo("dir/link", links["dir/link"], links)


def test_a_chain_that_stays_inside_the_tree_is_not_flagged():
    links = {"dir/alias": "..", "dir/ok": "alias/docs/x.md", "docs/latest": "../dir/ok"}
    assert not escapes_repo("dir/ok", links["dir/ok"], links)
    assert not escapes_repo("docs/latest", links["docs/latest"], links)


def test_a_target_that_walks_through_another_tracked_link_is_resolved_there():
    # Lexically `../a/up/../outside` from `b/` is `a/outside`, inside the tree.
    # But `a/up` is a tracked link to the root, so `a/up/..` is the root's
    # parent and the target lands outside the repository. (Git cannot track a
    # path beneath a symlink, so a link is only ever reached through another
    # link's target, never as an index entry under a linked directory.)
    links = {"a/up": "..", "b/link": "../a/up/../outside"}
    assert escapes_repo("b/link", links["b/link"], links)


def test_a_symlink_cycle_is_flagged():
    # A cycle never resolves: git checks it out as a link that fails with
    # "too many levels of symbolic links" everywhere.
    links = {"a": "b", "b": "a"}
    assert escapes_repo("a", links["a"], links)


def _offenders(root: Path) -> list[str]:
    tracked = _tracked_symlinks(root)
    links = dict(tracked)
    return [f"{p} -> {t}" for p, t in tracked if escapes_repo(p, t, links)]


def test_the_chain_is_caught_in_a_real_index(tmp_path):
    # Codex's executed reproduction: stage the chain in a real repository and
    # scan its index the way the guard scans this one.
    repo = tmp_path / "repo"
    (repo / "dir").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "dir" / "alias").symlink_to("..")
    (repo / "dir" / "link").symlink_to("alias/../../outside")
    (repo / "dir" / "ok").symlink_to("alias/README.md")
    (repo / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    assert not (repo / "dir" / "link").resolve().is_relative_to(repo.resolve())  # it really escapes
    assert _offenders(repo) == ["dir/link -> alias/../../outside"]


def test_no_tracked_symlink_escapes_the_repository():
    offenders = _offenders(ROOT)
    assert not offenders, (
        "tracked symlink(s) resolve outside the repository (they dangle in any "
        "checkout that lacks the target): " + "; ".join(offenders) + ". `git rm --cached <path>`."
    )
