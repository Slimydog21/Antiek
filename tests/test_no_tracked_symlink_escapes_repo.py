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
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _index_entries(root: Path = ROOT) -> tuple[list[tuple[str, str]], list[str]]:
    """(path, target) for every mode-120000 entry in the index, and every
    tracked path."""
    out = subprocess.run(
        ["git", "ls-files", "-s", "-z"], cwd=root, capture_output=True, check=True
    ).stdout.decode()
    links = []
    paths = []
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        mode, blob, _stage = meta.split()
        paths.append(path)
        if mode == "120000":
            target = subprocess.run(
                ["git", "cat-file", "-p", blob], cwd=root, capture_output=True, check=True
            ).stdout.decode()
            links.append((path, target))
    return links, paths


def _tracked_symlinks(root: Path = ROOT) -> list[tuple[str, str]]:
    return _index_entries(root)[0]


_MAX_LINK_HOPS = 40  # the Linux ELOOP bound; a cycle never resolves


_AMBIGUOUS = object()


def _fold(path: str) -> str:
    """Unicode canonical caseless form (NFD(casefold(NFD(x)))): how a
    case-insensitive, normalization-insensitive checkout (APFS, the macOS
    default) compares names."""
    return unicodedata.normalize("NFD", unicodedata.normalize("NFD", path).casefold())


def _folded_links(links: dict[str, str], tracked: list[str]) -> dict[str, object]:
    """Links keyed by case-folded path, as a case-insensitive checkout (the
    macOS default) resolves them. A link whose folded name collides with any
    other tracked path is ambiguous: which one materializes is not knowable
    from the index."""
    spellings: dict[str, set[str]] = {}
    for p in [*tracked, *links]:
        spellings.setdefault(_fold(p), set()).add(p)
    folded: dict[str, object] = {}
    for path, target in links.items():
        key = _fold(path)
        folded[key] = _AMBIGUOUS if len(spellings.get(key, ())) > 1 else target
    return folded


def _resolve_in_index(path: str, links: dict[str, object], *, fold: bool = False) -> list[str] | None:
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
        target = links.get(_fold(candidate) if fold else candidate)
        if target is None:
            resolved.append(part)
            continue
        hops += 1
        if target is _AMBIGUOUS or hops > _MAX_LINK_HOPS or posixpath.isabs(str(target)):
            return None
        assert isinstance(target, str)
        # The target is read relative to the link's own (resolved) directory.
        pending = [p for p in target.split("/") if p] + pending
    return resolved


def escapes_repo(
    path: str,
    target: str,
    links: dict[str, str] | None = None,
    tracked: list[str] | None = None,
) -> bool:
    """True if the link at ``path`` with ``target`` leaves the tree when
    resolved as a checkout would, following every other tracked symlink in
    ``links`` (path -> target) along the way. It must stay inside under both
    a case-sensitive checkout (CI, the production host) and a case-insensitive
    one (the operator's macOS worktrees); ``tracked`` is every tracked path,
    used to spot case collisions."""
    if posixpath.isabs(target):
        return True
    index: dict[str, str] = dict(links or {})
    index[path] = target
    exact: dict[str, object] = dict(index)
    return (
        _resolve_in_index(path, exact) is None
        or _resolve_in_index(path, _folded_links(index, tracked or list(index)), fold=True) is None
    )


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


def test_a_case_variant_of_a_tracked_link_is_followed():
    # Codex round 2 on #3412: on a case-insensitive checkout (macOS default)
    # `alias` opens the tracked `Alias`, so the chain escapes even though no
    # entry is spelled `dir/alias`.
    links = {"dir/Alias": "..", "dir/link": "alias/../../outside"}
    assert escapes_repo("dir/link", links["dir/link"], links)


def test_a_reverse_case_reference_to_a_tracked_link_is_followed():
    # The mirror of the case above: the link is spelled lower-case, the
    # reference upper-case.
    links = {"dir/alias": "..", "dir/link": "Alias/../../outside"}
    assert escapes_repo("dir/link", links["dir/link"], links)


def test_a_differently_normalized_reference_to_a_tracked_link_is_followed():
    # Codex round 3 on #3412: APFS matches names normalization-insensitively,
    # so a precomposed `\u00c9lan` opens a link stored decomposed (NFD).
    nfd, nfc = "E\u0301lan", "\u00c9lan"
    links = {f"dir/{nfd}": "..", "dir/link": f"{nfc}/../../outside"}
    assert escapes_repo("dir/link", links["dir/link"], links)


def test_case_colliding_entries_are_treated_as_escapes():
    # Two entries that differ only in case collapse into one path on a
    # case-insensitive checkout; which target wins is not knowable from the
    # index, so a link resolved through them is flagged.
    links = {"dir/Up": "..", "dir/up": "sub", "dir/sub": "../docs", "dir/link": "up/x.md"}
    assert escapes_repo("dir/link", links["dir/link"], links)


def test_a_case_variant_chain_that_stays_inside_is_not_flagged():
    links = {"dir/Docs": "../docs", "dir/latest": "docs/x.md"}
    assert not escapes_repo("dir/latest", links["dir/latest"], links)


def _offenders(root: Path) -> list[str]:
    tracked_links, tracked_paths = _index_entries(root)
    links = dict(tracked_links)
    return [f"{p} -> {t}" for p, t in tracked_links if escapes_repo(p, t, links, tracked_paths)]


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


def test_the_case_variant_chain_is_caught_in_a_real_index(tmp_path):
    # Codex's round-2 repro, staged in a real repository.
    repo = tmp_path / "repo"
    (repo / "dir").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "dir" / "Alias").symlink_to("..")
    (repo / "dir" / "link").symlink_to("alias/../../outside")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    if (repo / "DIR").exists():  # a case-insensitive filesystem: it really escapes here
        assert not (repo / "dir" / "link").resolve().is_relative_to(repo.resolve())
    assert _offenders(repo) == ["dir/link -> alias/../../outside"]


def test_a_decomposed_link_name_is_caught_in_a_real_index(tmp_path):
    # Codex's round-3 repro: with precomposeunicode off the index keeps the
    # decomposed name, and a precomposed reference still opens it on APFS.
    nfd, nfc = "E\u0301lan", "\u00c9lan"
    repo = tmp_path / "repo"
    (repo / "dir").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "core.precomposeunicode", "false"], cwd=repo, check=True)
    (repo / "dir" / nfd).symlink_to("..")
    (repo / "dir" / "link").symlink_to(f"{nfc}/../../outside")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    assert _offenders(repo) == [f"dir/link -> {nfc}/../../outside"]


def test_ignored_tool_directories_cannot_enter_the_index_as_symlinks(tmp_path):
    # A trailing slash in .gitignore matches directories only, never a
    # symlink: that is how a worktree's `node_modules -> /abs/path` reached
    # main five times. No tool-directory name this repository ignores may be
    # stageable as a symlink.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text((ROOT / ".gitignore").read_text())
    for name in ("node_modules", ".venv", "venv", ".venv314", "env"):
        (repo / name).symlink_to("/nonexistent/absolute/target")
        (repo / "nested").mkdir(exist_ok=True)
        (repo / "nested" / name).symlink_to("/nonexistent/absolute/target")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    staged = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True).stdout.split()
    assert staged == [".gitignore"], staged


def test_no_tracked_symlink_escapes_the_repository():
    offenders = _offenders(ROOT)
    assert not offenders, (
        "tracked symlink(s) resolve outside the repository (they dangle in any "
        "checkout that lacks the target): " + "; ".join(offenders) + ". `git rm --cached <path>`."
    )
