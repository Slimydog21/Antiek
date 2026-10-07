"""The first atomic deploy on a setup.yml-fresh host (restore rehearsal 2026-10-07, D1/D2).

`setup.yml` leaves an antiek-owned git clone at the public path. The rehearsal on
Antiek-v1 measured two refusals on that host's first `deploy_atomic.yml` run:

* D1: root's `git rev-parse` on the antiek-owned clone exits 128 ("detected dubious
  ownership"), so the live block went straight to rescue.
* D2: the clone was at the target SHA, so moving it to `<release root>/<sha>` hit the
  candidate release itself and the cutover refused ("refusing to overwrite legacy
  release").

These tests run the playbook's own shell bodies (rendered from the YAML, not copied)
against a scratch directory tree, the way the arXiv continuation tests do.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jinja2 import Environment

from tests.test_deploy_atomic_release import _load, _walk

SHA_A = "a" * 40


def _jinja() -> Environment:
    env = Environment()
    env.filters["bool"] = lambda value: str(value).strip().lower() in {"true", "1", "yes"}
    env.tests["match"] = lambda value, pattern: re.match(pattern, str(value)) is not None
    return env


def _play() -> dict[str, Any]:
    return _load()[1]


def _task(name: str) -> dict[str, Any]:
    return next(task for task in _walk(_play()["tasks"]) if task.get("name") == name)


def _render(template: str, context: dict[str, Any]) -> str:
    return _jinja().from_string(template).render(**context)


def _context(
    root: Path,
    public: Path,
    target: str,
    previous: str,
    was_directory: bool,
    link_target: str = "",
) -> dict[str, Any]:
    """Resolve the play's own variable templates in the order Ansible would."""
    variables = _play()["vars"]
    ctx: dict[str, Any] = {
        "antiek_public_dir": str(public),
        "antiek_release_root": str(root),
        "antiek_target_sha": target,
        "antiek_previous_sha": previous,
        "antiek_previous_was_directory": was_directory,
        "antiek_previous_link_target": link_target,
    }
    for name in ("antiek_release_dir", "antiek_legacy_release_dir", "antiek_previous_release_dir"):
        ctx[name] = _render(variables[name], ctx).strip()
    return ctx


def _git_env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _clone_at_one_commit(path: Path, home: Path) -> str:
    env = _git_env(home)
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, env=env)
    (path / "README").write_text("setup.yml clone\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True, env=env)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-q",
            "-m",
            "setup clone",
        ],
        check=True,
        env=env,
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def gnu_path(tmp_path: Path) -> str:
    """PATH whose `mv` understands -T (GNU coreutils on the host; a shim on macOS)."""
    probe = tmp_path / "mv-probe"
    probe.mkdir()
    (probe / "a").write_text("", encoding="utf-8")
    supported = (
        subprocess.run(
            ["mv", "-T", str(probe / "a"), str(probe / "b")], capture_output=True
        ).returncode
        == 0
    )
    if supported:
        return os.environ["PATH"]
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "mv"
    real_mv = shutil.which("mv") or "/bin/mv"
    shim.write_text(
        "#!/bin/bash\n"
        "args=(); T=0\n"
        'for a in "$@"; do case "$a" in -T*) T=1; r="${a#-T}"; [ -n "$r" ] && args+=("-$r");; *) args+=("$a");; esac; done\n'
        'if [ "$T" = 1 ]; then rm -f "${args[${#args[@]}-1]}"; fi\n'
        f'exec {real_mv} "${{args[@]}}"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return f"{shim_dir}{os.pathsep}{os.environ['PATH']}"


def _run(
    task_name: str,
    ctx: dict[str, Any],
    home: Path,
    path: str,
    *,
    task_environment: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a task's shell body the way root runs it on a setup-fresh host.

    The scratch repositories belong to the test user, so git's ownership check
    would never fire. GIT_TEST_ASSUME_DIFFERENT_OWNER=1 makes git treat every
    repository as another user's (root reading antiek's clone), so a git read
    succeeds only through the task's own command-scope safe.directory.
    """
    task = _task(task_name)
    script = _render(task["ansible.builtin.shell"], ctx)
    env = _git_env(home)
    env["PATH"] = path
    env["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"
    if task_environment:
        for key, value in (task.get("environment") or {}).items():
            env[key] = _render(str(value), ctx)
    return subprocess.run(
        ["/bin/bash", "-c", script], env=env, capture_output=True, text=True, check=False
    )


def _registered(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """Ansible's command module strips trailing newlines before splitting stdout_lines."""
    return {"stdout_lines": result.stdout.rstrip("\r\n").splitlines()}


def _record(ctx: dict[str, Any], home: Path, path: str) -> tuple[str, bool, str]:
    """Run the record task, the assert and the set_fact templates on its registered result."""
    result = _run("record the current release identity", ctx, home, path)
    assert result.returncode == 0, result.stderr
    registered = {"current_release_lookup": _registered(result)}
    (condition,) = _task("require the rollback identity to be empty or a bare 40-hex SHA")[
        "ansible.builtin.assert"
    ]["that"]
    assert _jinja().compile_expression(condition.strip())(**registered) is True
    facts = _task("set the rollback release identity")["ansible.builtin.set_fact"]
    previous = _render(facts["antiek_previous_sha"], registered)
    was_directory = _render(facts["antiek_previous_was_directory"], registered)
    link_target = _render(facts["antiek_previous_link_target"], registered)
    return previous, was_directory == "True", link_target


def _fresh_host(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "opt" / "antiek-releases"
    public = tmp_path / "opt" / "antiek"
    sha = _clone_at_one_commit(public, home)
    root.mkdir(parents=True)
    return home, root, public, sha


def test_root_git_lookups_carry_a_command_scope_safe_directory_for_their_own_path() -> None:
    """D1. Each root-run `git -C <antiek-owned dir>` names exactly the path it reads."""
    expected = {
        "record the current release identity": "{{ antiek_public_dir }}",
        "restore an interrupted first legacy public-directory move": "{{ antiek_legacy_release_dir }}",
        "restore the previous release pointer": "{{ antiek_public_dir }}",
    }
    for name, path in expected.items():
        task = _task(name)
        assert "git -C" in task["ansible.builtin.shell"]
        assert task["environment"] == {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": path,
        }, name
    wildcard = [
        task.get("name")
        for task in _walk(_play()["tasks"])
        if "*" in (task.get("environment") or {}).values() or "safe.directory=*" in str(task)
    ]
    assert wildcard == []


def test_git_reads_the_task_environment_as_protected_command_scope(tmp_path: Path) -> None:
    """safe.directory is honoured only from system, global or command scope; GIT_CONFIG_COUNT is
    command scope. A repository's own config would be ignored, which is the point of the check."""
    env = _git_env(tmp_path)
    env.update(
        GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0="/opt/antiek"
    )
    out = subprocess.run(
        ["git", "config", "--show-scope", "--get-all", "safe.directory"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert out == ["command", "/opt/antiek"]


def test_same_sha_setup_clone_cuts_over_and_rolls_back_to_the_clone(
    tmp_path: Path, gnu_path: str
) -> None:
    """D2, the normal DR case: setup.yml cloned main's tip and the deploy targets the same SHA."""
    home, root, public, sha = _fresh_host(tmp_path)
    candidate = root / sha
    candidate.mkdir()
    (candidate / ".release-receipt").write_text("ok\n", encoding="utf-8")

    probe = _context(root, public, sha, "", False)
    previous, was_directory, link_target = _record(probe, home, gnu_path)
    assert (previous, was_directory, link_target) == (sha, True, "")

    ctx = _context(root, public, sha, previous, was_directory)
    assert ctx["antiek_legacy_release_dir"] == f"{root}/legacy-{sha}"
    cutover = _run("make the one public API/SPA cutover", ctx, home, gnu_path)
    assert cutover.returncode == 0, cutover.stderr
    assert public.is_symlink() and os.readlink(public) == str(candidate)
    assert (root / f"legacy-{sha}" / "README").is_file()
    assert (candidate / ".release-receipt").is_file()

    rollback = _run("restore the previous release pointer", ctx, home, gnu_path)
    assert rollback.returncode == 0, rollback.stderr
    assert os.readlink(public) == f"{root}/legacy-{sha}"


def test_older_setup_clone_keeps_the_sha_named_move_and_rollback(
    tmp_path: Path, gnu_path: str
) -> None:
    """Control: a clone at an older SHA moves to <root>/<sha> exactly as before this change."""
    home, root, public, old = _fresh_host(tmp_path)
    target = SHA_A if old != SHA_A else "b" * 40
    (root / target).mkdir()
    previous, was_directory, _ = _record(_context(root, public, target, "", False), home, gnu_path)
    ctx = _context(root, public, target, previous, was_directory)
    assert ctx["antiek_legacy_release_dir"] == f"{root}/{old}"
    assert _run("make the one public API/SPA cutover", ctx, home, gnu_path).returncode == 0
    assert (root / old / "README").is_file()
    assert _run("restore the previous release pointer", ctx, home, gnu_path).returncode == 0
    assert os.readlink(public) == f"{root}/{old}"


def test_symlinked_public_path_is_unchanged_by_the_legacy_handling(
    tmp_path: Path, gnu_path: str
) -> None:
    """Prod's shape: the public path is already a release symlink, so nothing legacy applies."""
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "opt" / "antiek-releases"
    public = tmp_path / "opt" / "antiek"
    (root / SHA_A).mkdir(parents=True)
    target = "c" * 40
    (root / target).mkdir()
    public.symlink_to(root / SHA_A)
    previous, was_directory, link_target = _record(
        _context(root, public, target, "", False), home, gnu_path
    )
    assert (previous, was_directory, link_target) == (SHA_A, False, f"{root}/{SHA_A}")
    ctx = _context(root, public, target, previous, was_directory, link_target)
    assert ctx["antiek_previous_release_dir"] == f"{root}/{SHA_A}"
    assert _run("make the one public API/SPA cutover", ctx, home, gnu_path).returncode == 0
    assert os.readlink(public) == str(root / target)
    assert _run("restore the previous release pointer", ctx, home, gnu_path).returncode == 0
    assert os.readlink(public) == f"{root}/{SHA_A}"


def test_an_interrupted_same_sha_move_is_restored_from_the_legacy_name(
    tmp_path: Path, gnu_path: str
) -> None:
    """The window between `mv PUBLIC OLD` and `ln -s`: rescue must look where the move put it."""
    home, root, public, sha = _fresh_host(tmp_path)
    (root / sha).mkdir()
    ctx = _context(root, public, sha, sha, True)
    public.rename(ctx["antiek_legacy_release_dir"])
    assert not public.exists()
    result = _run("restore an interrupted first legacy public-directory move", ctx, home, gnu_path)
    assert result.returncode == 0, result.stderr
    assert (public / "README").is_file() and not public.is_symlink()


def test_a_genuine_collision_still_refuses(tmp_path: Path, gnu_path: str) -> None:
    """The refusal stays for what it was for: never overwrite an existing directory."""
    home, root, public, sha = _fresh_host(tmp_path)
    (root / sha).mkdir()
    ctx = _context(root, public, sha, sha, True)
    Path(ctx["antiek_legacy_release_dir"]).mkdir()
    result = _run("make the one public API/SPA cutover", ctx, home, gnu_path)
    assert result.returncode == 1
    assert "refusing to overwrite legacy release" in result.stderr
    assert (public / "README").is_file() and not public.is_symlink()


def test_after_a_rolled_back_same_sha_deploy_the_next_record_is_the_bare_sha(
    tmp_path: Path, gnu_path: str
) -> None:
    """A failed same-SHA first deploy leaves the public path on legacy-<sha>. The next deploy's
    rollback identity must still be the bare SHA (ANTIEK_BUILD_SHA, /health build_sha, the
    snapshot-prune guard all compare against it), and its rollback target must be the legacy
    directory the host really has, not <root>/<sha>."""
    home, root, public, sha = _fresh_host(tmp_path)
    (root / sha).mkdir()
    previous, was_directory, link_target = _record(
        _context(root, public, sha, "", False), home, gnu_path
    )
    first = _context(root, public, sha, previous, was_directory, link_target)
    assert _run("make the one public API/SPA cutover", first, home, gnu_path).returncode == 0
    assert _run("restore the previous release pointer", first, home, gnu_path).returncode == 0
    legacy = root / f"legacy-{sha}"
    assert os.readlink(public) == str(legacy)

    retry = "d" * 40 if sha != "d" * 40 else "e" * 40
    (root / retry).mkdir()
    previous, was_directory, link_target = _record(
        _context(root, public, retry, "", False), home, gnu_path
    )
    assert (previous, was_directory, link_target) == (sha, False, str(legacy))
    second = _context(root, public, retry, previous, was_directory, link_target)
    assert second["antiek_previous_release_dir"] == str(legacy)
    assert _run("make the one public API/SPA cutover", second, home, gnu_path).returncode == 0
    assert os.readlink(public) == str(root / retry)
    assert _run("restore the previous release pointer", second, home, gnu_path).returncode == 0
    assert os.readlink(public) == str(legacy)
    assert (legacy / "README").is_file()


def test_a_symlink_to_a_non_release_name_refuses_before_any_identity_is_set(
    tmp_path: Path, gnu_path: str
) -> None:
    """Anything but <sha> or legacy-<sha> behind the public path is refused by the record task,
    and the assert on the raw registered line would refuse it again before set_fact."""
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "opt" / "antiek-releases"
    public = tmp_path / "opt" / "antiek"
    (root / "hand-made").mkdir(parents=True)
    public.symlink_to(root / "hand-made")
    result = _run(
        "record the current release identity",
        _context(root, public, SHA_A, "", False),
        home,
        gnu_path,
    )
    assert result.returncode == 1
    assert "not a release named by a 40-hex SHA" in result.stderr
    assert result.stdout == ""
    (condition,) = _task("require the rollback identity to be empty or a bare 40-hex SHA")[
        "ansible.builtin.assert"
    ]["that"]
    check = _jinja().compile_expression(condition.strip())
    for bad in (f"legacy-{SHA_A}", "hand-made", SHA_A[:39]):
        assert check(current_release_lookup={"stdout_lines": [bad, "", "symlink"]}) is False
    assert check(current_release_lookup={"stdout_lines": ["", "", "none"]}) is True


def _assumes_different_owner(tmp_path: Path) -> bool:
    repo = tmp_path / "owner-probe"
    _clone_at_one_commit(repo, tmp_path)
    env = _git_env(tmp_path)
    env["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"
    return (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], env=env, capture_output=True
        ).returncode
        != 0
    )


def test_root_style_git_reads_need_the_task_safe_directory(tmp_path: Path, gnu_path: str) -> None:
    """D1, behaviourally: under a different owner, every git-reading task fails without its own
    environment and succeeds with it, so a wrong safe.directory path fails here."""
    if not _assumes_different_owner(tmp_path):
        pytest.skip("this git does not honour GIT_TEST_ASSUME_DIFFERENT_OWNER")
    home, root, public, sha = _fresh_host(tmp_path)
    (root / sha).mkdir()
    ctx = _context(root, public, sha, sha, True)

    bare = _run("record the current release identity", ctx, home, gnu_path, task_environment=False)
    assert bare.returncode == 128 and "dubious ownership" in bare.stderr
    assert _run("record the current release identity", ctx, home, gnu_path).returncode == 0

    bare = _run("restore the previous release pointer", ctx, home, gnu_path, task_environment=False)
    assert bare.returncode != 0 and "dubious ownership" in bare.stderr
    assert _run("restore the previous release pointer", ctx, home, gnu_path).returncode == 0

    public.rename(ctx["antiek_legacy_release_dir"])
    bare = _run(
        "restore an interrupted first legacy public-directory move",
        ctx,
        home,
        gnu_path,
        task_environment=False,
    )
    assert bare.returncode != 0 and "dubious ownership" in bare.stderr
    moved = _run("restore an interrupted first legacy public-directory move", ctx, home, gnu_path)
    assert moved.returncode == 0, moved.stderr
