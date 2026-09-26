"""deploy_atomic.yml — no tag selection or start point separates the gate from the release.

The identity check and require_green.sh used to be tagged [deploy, gate] while
everything they guard (the checkout of antiek_target_sha, the dependency
sync, the schema migration, the public cutover, the service start) is
[code]. So `--tags code`, `--skip-tags gate` or `--skip-tags deploy` built and
published a supplied SHA with zero calls to require_green.sh (executed on
570cf6f2f with `--list-tasks`: the list ran from "prepare the release root"
to "start antiek into the candidate release" with neither gate task). The
gate has to be carried by the release, not by the caller's choice of tags.

The executed tests run a staged copy of the real playbook against a local
"box": a bare file:// origin whose main holds commits A, B (green) and C
(checks pending). A fake `gh` answers require_green.sh. The only change to
the staged copy is the release root's owner and group (a non-root run cannot
chown to root); it touches no gate. The play fails later on this host (no
systemd, no root), so each test asserts what reached the box before that.

setup.yml is a second entrypoint to the same state: its clone task must
only ever clone into an empty dest. Moving an existing checkout is the gated
release's job alone.
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
ATOMIC = PLAYBOOKS / "deploy_atomic.yml"
SETUP = PLAYBOOKS / "setup.yml"
REQUIRE_GREEN = ROOT / "tools" / "deploy" / "require_green.sh"

GUARD_REFUSAL = "gate did not run or did not clear"

# Refuses by default (`gh auth status` fails, so require_green.sh exits 3).
# With FAKE_GH_GREEN=1 it reports every context require_green.sh requires as
# `success`, in the TSV shape its --jq expression yields; FAKE_GH_GREEN_ONLY=<sha>
# narrows that to one SHA (every other SHA reads `pending`). The on-main check
# (compare/<sha>...main) answers `ahead`: every commit the box makes is on main.
_FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
[ "${FAKE_GH_GREEN:-0}" = 1 ] || exit 1
[ "${1:-}" = api ] || exit 0
case "$*" in
  */compare/*) echo ahead; exit 0 ;;
esac
concl=success
if [ -n "${FAKE_GH_GREEN_ONLY:-}" ]; then
  case "$*" in *"/commits/${FAKE_GH_GREEN_ONLY}/"*) ;; *) concl=pending ;; esac
fi
for c in tsc vitest keystone 'mypy --strict + ruff (declared scope, baselined)' \\
         'pytest shard 0 of 4' 'pytest shard 1 of 4' 'pytest shard 2 of 4' 'pytest shard 3 of 4' \\
         pytest; do
  printf '%s\\tcompleted\\t%s\\t2026-01-01T00:00:00Z\\n' "$c" "$concl"
done
"""

_RELEASE_ROOT_TASK = """    - name: prepare the release root
      ansible.builtin.file:
        path: "{{ antiek_release_root }}"
        state: directory
        owner: root
        group: root
"""


def _git(*args: str, cwd: Path) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def _user_and_group() -> tuple[str, str]:
    user = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
    group = subprocess.run(["id", "-gn"], capture_output=True, text=True, check=True).stdout.strip()
    return user, group


def _stage(tmp: Path) -> Path:
    """A copy of deploy_atomic.yml at its real depth, so its relative path to
    require_green.sh resolves. Only the release root's owner and group change."""
    repo = tmp / "control"
    (repo / "infrastructure" / "ansible" / "playbooks").mkdir(parents=True)
    (repo / "tools" / "deploy").mkdir(parents=True)
    shutil.copy2(REQUIRE_GREEN, repo / "tools" / "deploy" / "require_green.sh")
    text = ATOMIC.read_text()
    assert text.count(_RELEASE_ROOT_TASK) == 1, "the release-root task changed shape"
    user, group = _user_and_group()
    text = text.replace(_RELEASE_ROOT_TASK, _RELEASE_ROOT_TASK.replace(
        "owner: root\n        group: root", f"owner: {user}\n        group: {group}"))
    staged = repo / "infrastructure" / "ansible" / "playbooks" / "deploy_atomic.yml"
    staged.write_text(text)
    return staged


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

    (seed / "f").write_text("b — green\n")
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
            "releases": tmp_path / "releases", "public": tmp_path / "public",
            "sha_a": sha_a, "sha_b": sha_b}


def _env(box: dict, *, green: bool, green_only: str) -> dict[str, str]:
    return {**os.environ, "PATH": f"{box['bin']}{os.pathsep}{os.environ['PATH']}",
            "FAKE_GH_LOG": str(box["gh_log"]), "FAKE_GH_GREEN": "1" if green else "0",
            "FAKE_GH_GREEN_ONLY": green_only,
            # setup.yml pip-installs after the clone; fail that offline, fast.
            "PIP_NO_INDEX": "1",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_LOCAL_TEMP": str(box["tmp"] / "ans-local"),
            "ANSIBLE_REMOTE_TEMP": str(box["tmp"] / "ans-remote"),
            "ANSIBLE_RETRY_FILES_ENABLED": "0"}


def _release(box: dict, *selection: str, sha: str | None, green: bool = False,
             green_only: str = "") -> subprocess.CompletedProcess:
    exe = shutil.which("ansible-playbook")
    assert exe
    extra = [
        "-e", "ansible_become=false",
        "-e", f"antiek_repo_url=file://{box['remote']}",
        "-e", f"antiek_release_root={box['releases']}",
        "-e", f"antiek_install_dir={box['public']}",
        "-e", "antiek_release_min_free_gb=0",
        "-e", f"antiek_secrets_file={box['secrets']}",
    ]
    if sha is not None:
        extra += ["-e", f"antiek_target_sha={sha}"]
    return subprocess.run(
        [exe, "-i", str(box["inv"]), str(_stage(box["tmp"])), *extra, *selection],
        env=_env(box, green=green, green_only=green_only),
        capture_output=True, text=True, timeout=300,
    )


def _checked_out(box: dict, sha: str) -> bool:
    release = box["releases"] / sha
    return (release / ".git").exists() and _git("rev-parse", "HEAD", cwd=release) == sha


def _advance_main(box: dict, text: str) -> str:
    seed = box["tmp"] / "seed"
    (seed / "f").write_text(text)
    _git("commit", "-q", "-am", text.split()[0], cwd=seed)
    _git("push", "-q", "origin", "HEAD:main", cwd=seed)
    return _git("rev-parse", "HEAD", cwd=seed)


def _refused_by_the_gate(out: str) -> bool:
    return "require_green:" in out or GUARD_REFUSAL in out


needs_ansible = pytest.mark.skipif(
    shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed"
)

# Every way an operator can narrow a run. `frontend` is always skipped here:
# its play runs `npm run build` on the control node, and the documented backend
# deploy skips it anyway (docs/operator_gate_actions.md).
SELECTIONS = [
    (("--tags", "code"), True),
    (("--skip-tags", "frontend,gate"), True),
    (("--skip-tags", "frontend,deploy"), True),
    (("--skip-tags", "frontend,always"), True),
    # Starting at the recorder skips the gate but runs the recorder: only its
    # own `rc == 0` condition keeps it from recording an ungated SHA.
    (("--skip-tags", "frontend", "--start-at-task", "record the gate-cleared release identity"), True),
    (("--skip-tags", "frontend", "--start-at-task", "read the candidate release receipt"), True),
    # Entering the build block past its guard: the block's own condition
    # needs the receipt stat that the start point skipped, so the checkout
    # never runs. Only the outcome is pinned here, not the message.
    (("--skip-tags", "frontend", "--start-at-task",
      "check out the gated SHA at its final release path"), False),
]
SELECTION_IDS = ["tags-code", "skip-gate", "skip-deploy", "skip-always",
                 "start-at-recorder", "start-at-receipt", "start-at-checkout"]


@needs_ansible
@pytest.mark.parametrize(("selection", "gate_is_the_refusal"), SELECTIONS, ids=SELECTION_IDS)
def test_a_supplied_pending_sha_never_reaches_the_box(box, selection, gate_is_the_refusal):
    sha_c = _advance_main(box, "c — supplied, checks pending\n")
    proc = _release(box, *selection, sha=sha_c, green=True, green_only=box["sha_b"])
    out = proc.stdout + proc.stderr
    assert not _checked_out(box, sha_c), (
        f"{' '.join(selection)} checked out supplied, pending {sha_c} past the "
        f"required-checks gate.\n{out[-3000:]}"
    )
    assert proc.returncode != 0, out[-3000:]
    if gate_is_the_refusal:
        assert _refused_by_the_gate(out), out[-3000:]


@needs_ansible
def test_tags_code_runs_the_gate_before_touching_the_box(box):
    proc = _release(box, "--tags", "code", sha=box["sha_b"])
    out = proc.stdout + proc.stderr
    assert box["gh_log"].read_text().strip(), (
        "`--tags code` never called gh: require_green.sh was not selected.\n" + out[-3000:]
    )
    assert not box["releases"].exists(), out[-3000:]


@needs_ansible
def test_a_run_without_a_target_sha_is_refused_before_touching_the_box(box):
    proc = _release(box, "--tags", "code", sha=None)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "Refusing a non-exact release identity" in out, out[-3000:]
    assert not box["releases"].exists(), out[-3000:]


@needs_ansible
def test_the_documented_backend_deploy_runs_the_gate_first(box):
    # docs/operator_gate_actions.md: the backend deploys with --skip-tags frontend.
    proc = _release(box, "--skip-tags", "frontend", sha=box["sha_b"])
    out = proc.stdout + proc.stderr
    assert box["gh_log"].read_text().strip(), out[-3000:]
    assert proc.returncode != 0 and "require_green:" in out, out[-3000:]
    assert not box["releases"].exists(), out[-3000:]


@needs_ansible
def test_a_reused_candidate_does_not_go_live_past_a_skipped_gate(box):
    # A receipt from an earlier build skips the build block, so the build
    # block's guard never runs. Starting past the gate must still stop before
    # the release path is quiesced, migrated or cut over.
    sha_c = _advance_main(box, "c — an old candidate, checks pending\n")
    candidate = box["releases"] / sha_c
    candidate.mkdir(parents=True)
    (candidate / ".release-receipt").write_text(f"source_sha={sha_c}\n")
    proc = _release(box, "--skip-tags", "frontend,cloudflared,caddy,systemd",
                    "--start-at-task", "read the candidate release receipt", sha=sha_c)
    out = proc.stdout + proc.stderr
    assert "pause every release-path consumer before cutover" not in out, (
        f"a reused, ungated candidate {sha_c} reached the quiesce and cutover.\n{out[-3000:]}"
    )
    assert proc.returncode != 0
    assert GUARD_REFUSAL in out, out[-3000:]


@needs_ansible
def test_a_green_gate_builds_the_supplied_sha_positive_control(box):
    # main: A -> B (green) -> C (the tip, checks pending). The workflow gated
    # B and passes it in; B is what gets built, while main moved on.
    sha_c = _advance_main(box, "c — merged after B, checks pending\n")
    proc = _release(box, "--tags", "code", sha=box["sha_b"], green=True, green_only=box["sha_b"])
    out = proc.stdout + proc.stderr
    assert _checked_out(box, box["sha_b"]), out[-3000:]
    assert not (box["releases"] / sha_c).exists()
    gh_calls = box["gh_log"].read_text()
    assert box["sha_b"] in gh_calls and sha_c not in gh_calls, gh_calls


@needs_ansible
def test_force_override_still_builds_positive_control(box):
    proc = _release(box, "--tags", "code", "-e", "antiek_force_deploy=true", sha=box["sha_b"])
    out = proc.stdout + proc.stderr
    assert _checked_out(box, box["sha_b"]), out[-3000:]
    assert "Emergency override is deploying" in out, out[-3000:]
    assert box["gh_log"].read_text() == ""


def _setup_env_and_run(box: dict) -> subprocess.CompletedProcess:
    # `--tags code --skip-tags deploy_key` is setup.yml's repo+venv block
    # (the deploy key is the operator's real SSH key); a full re-run of
    # setup.yml on a provisioned box goes through the same clone task.
    exe = shutil.which("ansible-playbook")
    assert exe
    user, group = _user_and_group()
    extra = [
        "-e", "ansible_become=false",
        "-e", f"antiek_repo_url=file://{box['remote']}",
        "-e", "antiek_repo_branch=main",
        "-e", f"antiek_install_dir={box['install']}",
        "-e", f"antiek_user={user}",
        "-e", f"antiek_group={group}",
        "-e", f"antiek_secrets_file={box['secrets']}",
    ]
    return subprocess.run(
        [exe, "-i", str(box["inv"]), str(SETUP), *extra, "--tags", "code", "--skip-tags", "deploy_key"],
        env=_env(box, green=False, green_only=""), capture_output=True, text=True, timeout=300,
    )


@needs_ansible
def test_setup_rerun_never_moves_an_existing_checkout(box):
    proc = _setup_env_and_run(box)
    out = proc.stdout + proc.stderr
    assert "clone Antiek repo" in out, out[-3000:]
    assert _git("rev-parse", "HEAD", cwd=box["install"]) == box["sha_a"], (
        f"setup.yml moved the provisioned checkout to unverified {box['sha_b']} "
        f"with no required-checks gate.\n{out[-3000:]}"
    )
    assert box["gh_log"].read_text() == ""


@needs_ansible
def test_setup_still_clones_a_fresh_box_positive_control(box):
    shutil.rmtree(box["install"])
    proc = _setup_env_and_run(box)
    out = proc.stdout + proc.stderr
    assert (box["install"] / ".git").is_dir(), out[-3000:]
    assert _git("rev-parse", "HEAD", cwd=box["install"]) == box["sha_b"], out[-3000:]


# ── static guard: runs where ansible-playbook is absent (CI test shards) ──
def _play() -> dict:
    plays = yaml.safe_load(ATOMIC.read_text())
    return next(p for p in plays if p.get("hosts") == "antiek_prod")


def _named(tasks: list[dict], name: str) -> dict:
    return next(t for t in tasks if t.get("name", "") == name)


GATE_TASKS = (
    "require an exact 40-hex release identity",
    "require every main-required check green for the target SHA",
    "warn that the required-check gate is deliberately bypassed",
    "record the gate-cleared release identity",
)
BUILD_GUARD = "require the gate to have cleared this exact SHA before building it"
LIVE_GUARD = "require the gate to have cleared this exact SHA before the release goes live"


def test_the_gate_is_tagged_always_and_nothing_else():
    # `always` runs under every --tags selection; any further tag would let
    # `--skip-tags <that tag>` drop the gate while the release still runs.
    pre = _play()["pre_tasks"]
    for name in GATE_TASKS:
        assert _named(pre, name)["tags"] == ["always"], name
    names = [t.get("name", "") for t in pre]
    assert names.index(GATE_TASKS[1]) < names.index(GATE_TASKS[3])
    assert names.index(GATE_TASKS[3]) < names.index("prepare the release root")


def test_the_cleared_ref_is_recorded_only_for_a_full_sha_that_cleared():
    pre = _play()["pre_tasks"]
    assert _named(pre, GATE_TASKS[1])["register"] == "required_checks_gate"
    recorder = _named(pre, GATE_TASKS[3])
    assert recorder["ansible.builtin.set_fact"] == {"antiek_gate_cleared_ref": "{{ antiek_target_sha }}"}
    when = recorder["when"]
    assert "antiek_target_sha is match('^[0-9a-f]{40}$')" in when, when
    assert "antiek_force_deploy" in when and "(required_checks_gate.rc | default(1)) == 0" in when, when


def _guard_assertion(task: dict) -> list[str]:
    return task["ansible.builtin.assert"]["that"]


def test_the_build_is_guarded_by_its_first_task_with_the_checkouts_tags():
    build = _named(_play()["tasks"], "build and validate the exact-SHA release")["block"]
    guard, checkout = build[0], _named(build, "check out the gated SHA at its final release path")
    assert guard["name"] == BUILD_GUARD
    assert guard["tags"] == checkout["tags"]
    assert _guard_assertion(guard) == [
        "antiek_gate_cleared_ref is defined",
        "antiek_gate_cleared_ref == antiek_target_sha",
    ]


def test_the_live_phase_is_guarded_immediately_before_it_starts():
    tasks = _play()["tasks"]
    names = [t.get("name", "") for t in tasks]
    live = names.index("quiesce, migrate, cut over, and verify")
    guard = tasks[live - 1]
    assert guard["name"] == LIVE_GUARD
    assert guard["tags"] == ["code"]
    assert _guard_assertion(guard) == [
        "antiek_gate_cleared_ref is defined",
        "antiek_gate_cleared_ref == antiek_target_sha",
    ]
    assert names.index("assert the candidate release is complete") < live - 1


def _git_tasks() -> list[tuple[str, list[dict], dict]]:
    found: list[tuple[str, list[dict], dict]] = []

    def walk(playbook: str, tasks: list[dict] | None) -> None:
        for t in tasks or []:
            if "ansible.builtin.git" in t or "git" in t:
                found.append((playbook, tasks, t))
            for key in ("block", "rescue", "always"):
                walk(playbook, t.get(key))

    for path in sorted(PLAYBOOKS.glob("*.yml")):
        for play in yaml.safe_load(path.read_text()) or []:
            for key in ("pre_tasks", "tasks", "post_tasks", "handlers"):
                walk(path.name, play.get(key))
    return found


def test_only_the_guarded_release_checkout_can_move_code_onto_the_box():
    git_tasks = _git_tasks()
    assert any(pb == "setup.yml" for pb, _, _ in git_tasks), git_tasks
    guarded = 0
    for pb, siblings, t in git_tasks:
        args = t.get("ansible.builtin.git") or t.get("git")
        if pb == "deploy_atomic.yml" and t.get("name") == "check out the gated SHA at its final release path":
            assert siblings[0].get("name") == BUILD_GUARD
            guarded += 1
            continue
        # The git module defaults to update=yes, which fast-forwards an
        # existing checkout to the branch tip: an ungated deploy.
        assert args.get("update") is False, (
            f"{pb}: '{t.get('name')}' can move an existing checkout past the "
            "required-checks gate; set `update: false` (clone-if-absent only)."
        )
    assert guarded == 1
