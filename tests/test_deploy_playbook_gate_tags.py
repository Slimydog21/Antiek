"""deploy.yml — the required-checks gate must not be tag-selectable apart from the pull.

The gate tasks (resolve SHA, require_green.sh) and the action they guard
(`git pull`, then migrate + restart) used to carry disjoint tags: gate was
[deploy, gate], the pull [code]. So `--tags code` — the obvious way to push
code only — pulled and restarted with zero calls to require_green, and
`--skip-tags gate` / `--start-at-task "git pull"` did the same. The gate has to
be carried by the action, not by the caller's choice of tags.

The executed tests run the real playbook against a local "box": a bare
file:// origin, a clone of it at commit A, and a new unverified commit B on
origin. A fake `gh` refuses (so require_green.sh exits non-zero). Whatever
the tag selection, the box must stay at A unless the logged emergency
override `antiek_force_deploy=true` is passed — which is also the positive
control proving the harness can pull at all. The play itself fails later
(no systemd, no root); only the pull is under test.

setup.yml is a second entrypoint to the same state: its `clone Antiek repo`
task (tagged [code]) used the git module's default update=yes, so re-running
setup.yml on a provisioned box (the runbooks call it idempotent) fast-forwarded
the checkout to the branch tip with no gate, then pip-installed that tree.
It must only ever clone into an empty dest; moving an existing checkout is
deploy.yml's gated pull alone.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOKS = ROOT / "infrastructure" / "ansible" / "playbooks"
PLAYBOOK = PLAYBOOKS / "deploy.yml"
SETUP = PLAYBOOKS / "setup.yml"

# Refuses by default (require_green.sh exits non-zero). With FAKE_GH_GREEN=1
# it reports all eight main-required contexts `success`, in the TSV shape the
# script's --jq expression yields.
_FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
[ "${FAKE_GH_GREEN:-0}" = 1 ] || exit 1
[ "${1:-}" = api ] || exit 0
for c in tsc vitest keystone 'mypy --strict + ruff (declared scope, baselined)' \\
         'pytest shard 0 of 4' 'pytest shard 1 of 4' 'pytest shard 2 of 4' 'pytest shard 3 of 4'; do
  printf '%s\\tcompleted\\tsuccess\\t2026-01-01T00:00:00Z\\n' "$c"
done
"""


def _git(*args: str, cwd: Path) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def box(tmp_path: Path) -> dict:
    remote = tmp_path / "remote.git"
    _git("init", "--bare", "-q", "-b", "main", str(remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", "-q", f"file://{remote}", str(seed), cwd=tmp_path)
    (seed / "f").write_text("a\n")
    _git("add", "f", cwd=seed)
    _git("commit", "-q", "-m", "a", cwd=seed)
    _git("push", "-q", "origin", "HEAD:main", cwd=seed)
    sha_a = _git("rev-parse", "HEAD", cwd=seed)

    install = tmp_path / "install" / "repo"
    install.parent.mkdir()
    _git("clone", "-q", "-b", "main", f"file://{remote}", str(install), cwd=tmp_path)

    (seed / "f").write_text("b — not verified\n")
    _git("commit", "-q", "-am", "b", cwd=seed)
    _git("push", "-q", "origin", "HEAD:main", cwd=seed)
    sha_b = _git("rev-parse", "HEAD", cwd=seed)

    binw = tmp_path / "bin"
    binw.mkdir()
    gh = binw / "gh"
    gh.write_text(_FAKE_GH)
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    gh_log = tmp_path / "gh.log"
    gh_log.write_text("")

    secrets = tmp_path / "secrets.env"
    secrets.write_text("ANTIEK_BUILD_SHA=old\n")
    inv = tmp_path / "inv.ini"
    inv.write_text(
        "[antiek_prod]\n"
        "box ansible_connection=local ansible_python_interpreter=auto_silent\n"
    )
    return {"tmp": tmp_path, "remote": remote, "install": install, "bin": binw,
            "gh_log": gh_log, "secrets": secrets, "inv": inv,
            "sha_a": sha_a, "sha_b": sha_b}


def _deploy(box: dict, *selection: str, green: bool = False,
            playbook: Path = PLAYBOOK) -> subprocess.CompletedProcess:
    exe = shutil.which("ansible-playbook")
    assert exe
    env = {**os.environ, "PATH": f"{box['bin']}{os.pathsep}{os.environ['PATH']}",
           "FAKE_GH_LOG": str(box["gh_log"]), "FAKE_GH_GREEN": "1" if green else "0",
           # setup.yml pip-installs after the clone; fail that offline, fast.
           "PIP_NO_INDEX": "1",
           "ANSIBLE_NOCOLOR": "1",
           "ANSIBLE_LOCAL_TEMP": str(box["tmp"] / "ans-local"),
           "ANSIBLE_REMOTE_TEMP": str(box["tmp"] / "ans-remote"),
           "ANSIBLE_RETRY_FILES_ENABLED": "0"}
    extra = [
        "-e", "ansible_become=false",
        "-e", f"antiek_repo_url=file://{box['remote']}",
        "-e", "antiek_repo_branch=main",
        "-e", f"antiek_install_dir={box['install']}",
        "-e", f"antiek_user={os.environ.get('USER', 'root')}",
        "-e", f"antiek_secrets_file={box['secrets']}",
    ]
    return subprocess.run(
        [exe, "-i", str(box["inv"]), str(playbook), *extra, *selection],
        env=env, capture_output=True, text=True, timeout=300,
    )


def _head(box: dict) -> str:
    return _git("rev-parse", "HEAD", cwd=box["install"])


needs_ansible = pytest.mark.skipif(
    shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed"
)


@needs_ansible
@pytest.mark.parametrize(
    "selection",
    [
        ("--tags", "code"),
        ("--skip-tags", "frontend,gate"),
        ("--skip-tags", "frontend,deploy"),
        ("--skip-tags", "frontend", "--start-at-task", "git pull"),
    ],
    ids=["tags-code", "skip-gate", "skip-deploy", "start-at-pull"],
)
def test_unverified_sha_never_reaches_the_box_under_any_tag_selection(box, selection):
    proc = _deploy(box, *selection)
    out = proc.stdout + proc.stderr
    assert _head(box) == box["sha_a"], (
        f"{' '.join(selection)} pulled unverified {box['sha_b']} past the "
        f"required-checks gate.\n{out[-3000:]}"
    )
    assert proc.returncode != 0, out[-3000:]
    # Stopped by the gate itself or by the pull refusing an uncleared gate,
    # not by some unrelated failure earlier in the play.
    assert "require_green:" in out or "required-checks gate did not" in out, out[-3000:]
    assert "ANTIEK_BUILD_SHA=old" in box["secrets"].read_text()


@needs_ansible
def test_tags_code_actually_runs_the_gate(box):
    proc = _deploy(box, "--tags", "code")
    assert box["gh_log"].read_text().strip(), (
        "`--tags code` never called gh: require_green.sh was not selected.\n"
        + (proc.stdout + proc.stderr)[-3000:]
    )


@needs_ansible
def test_green_gate_pulls_under_tags_code_positive_control(box):
    proc = _deploy(box, "--tags", "code", green=True)
    assert _head(box) == box["sha_b"], (proc.stdout + proc.stderr)[-3000:]
    assert box["sha_b"] in box["gh_log"].read_text()


@needs_ansible
def test_force_override_still_pulls_positive_control(box):
    proc = _deploy(box, "--tags", "code", "-e", "antiek_force_deploy=true")
    out = proc.stdout + proc.stderr
    assert _head(box) == box["sha_b"], out[-3000:]
    assert "WITHOUT" in out and "verifying its required checks" in out, out[-3000:]
    assert box["gh_log"].read_text() == ""


def _setup_code_block(box: dict) -> subprocess.CompletedProcess:
    # `--tags code --skip-tags deploy_key` is setup.yml's repo+venv block
    # (the deploy key is the operator's real SSH key); a full re-run of
    # setup.yml on a provisioned box goes through the same clone task.
    group = subprocess.run(["id", "-gn"], capture_output=True, text=True,
                           check=True).stdout.strip()
    return _deploy(box, "--tags", "code", "--skip-tags", "deploy_key",
                   "-e", f"antiek_group={group}", playbook=SETUP)


@needs_ansible
def test_setup_rerun_never_moves_an_existing_checkout(box):
    proc = _setup_code_block(box)
    out = proc.stdout + proc.stderr
    assert "clone Antiek repo" in out, out[-3000:]
    assert _head(box) == box["sha_a"], (
        f"setup.yml moved the provisioned checkout to unverified {box['sha_b']} "
        f"with no required-checks gate.\n{out[-3000:]}"
    )
    assert box["gh_log"].read_text() == ""


@needs_ansible
def test_setup_still_clones_a_fresh_box_positive_control(box):
    shutil.rmtree(box["install"])
    proc = _setup_code_block(box)
    out = proc.stdout + proc.stderr
    assert (box["install"] / ".git").is_dir(), out[-3000:]
    assert _head(box) == box["sha_b"], out[-3000:]


# ── static guard: runs where ansible-playbook is absent (CI test shards) ──
def _deploy_tasks() -> list[dict]:
    plays = yaml.safe_load(PLAYBOOK.read_text())
    return next(p for p in plays if p.get("hosts") == "antiek_prod")["tasks"]


def _task(name_prefix: str) -> dict:
    return next(t for t in _deploy_tasks() if t.get("name", "").startswith(name_prefix))


def test_every_tag_that_selects_the_pull_also_selects_the_gate():
    pull_tags = set(_task("git pull")["tags"])
    for gate in ("resolve the SHA", "set antiek_target_sha", "require every main-required",
                 "WARN — required-checks gate bypassed", "record the gate-cleared ref"):
        assert pull_tags <= set(_task(gate)["tags"]), gate


def test_pull_version_is_only_resolvable_once_the_gate_cleared():
    pull = _task("git pull")
    version = pull["ansible.builtin.git"]["version"]
    # An undefined fact under `mandatory` fails the pull task itself, so no
    # --skip-tags / --start-at-task that drops the gate can reach the checkout.
    assert "antiek_gate_cleared_ref" in version and "mandatory" in version, version
    setter = _task("record the gate-cleared ref")
    assert "antiek_gate_cleared_ref" in setter["ansible.builtin.set_fact"]
    names = [t.get("name", "") for t in _deploy_tasks()]
    gate_i = next(i for i, n in enumerate(names) if n.startswith("require every main-required"))
    set_i = names.index(setter["name"])
    pull_i = names.index(pull["name"])
    assert gate_i < set_i < pull_i


def _git_tasks() -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []

    def walk(playbook: str, tasks: list[dict] | None) -> None:
        for t in tasks or []:
            if "ansible.builtin.git" in t or "git" in t:
                found.append((playbook, t))
            for key in ("block", "rescue", "always"):
                walk(playbook, t.get(key))

    for path in sorted(PLAYBOOKS.glob("*.yml")):
        for play in yaml.safe_load(path.read_text()) or []:
            for key in ("pre_tasks", "tasks", "post_tasks", "handlers"):
                walk(path.name, play.get(key))
    return found


def test_only_the_gated_pull_can_move_an_existing_checkout():
    git_tasks = _git_tasks()
    assert any(pb == "setup.yml" for pb, _ in git_tasks), git_tasks
    gated = 0
    for pb, t in git_tasks:
        args = t.get("ansible.builtin.git") or t.get("git")
        if pb == "deploy.yml" and t.get("name", "").startswith("git pull"):
            assert "mandatory" in args["version"], args["version"]
            gated += 1
            continue
        # The git module defaults to update=yes, which fast-forwards an
        # existing checkout to the branch tip: an ungated deploy.
        assert args.get("update") is False, (
            f"{pb}: '{t.get('name')}' can move an existing checkout past the "
            "required-checks gate; set `update: false` (clone-if-absent only)."
        )
    assert gated == 1
