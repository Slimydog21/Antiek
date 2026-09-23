"""tools/deploy/require_green.sh — the one gate both deploy paths call.

Exercised end to end against a fake ``gh`` on PATH (no network, no token):
every exit code the two callers branch on (0 green / 1 not yet / 3 cannot
verify), the newest-run-wins rule for a re-run context, the three repo
spellings, the ``--wait`` bounded-poll mode the ansible playbook uses
(poll-until-green, budget expiry, failure fast-fail, exits 3/4 staying
immediate), and — because the CI gate job once called a script it had never
checked out and read the resulting exit 127 as "not green yet" — a
structural guard on the workflow that calls it.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "deploy" / "require_green.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy_backend.yml"
SHA = "0123456789abcdef0123456789abcdef01234567"
REQUIRED = [
    "tsc", "vitest", "keystone",
    "mypy --strict + ruff (declared scope, baselined)",
    "pytest shard 0 of 4", "pytest shard 1 of 4", "pytest shard 2 of 4", "pytest shard 3 of 4",
]

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="fake gh applies --jq with jq")

_FAKE_GH = r'''#!/usr/bin/env bash
cmd="${1:-}"; shift || true
case "$cmd" in
  auth) exit "${FAKE_GH_AUTH_RC:-0}" ;;
  api)
    jqexpr=""; path=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --jq) jqexpr="$2"; shift 2 ;;
        --paginate) shift ;;
        *) path="$1"; shift ;;
      esac
    done
    printf '%s\n' "$path" >> "${FAKE_GH_CALLS:-/dev/null}"
    case "$path" in
      */compare/*)
        [ "${FAKE_GH_COMPARE_RC:-0}" -eq 0 ] || exit "${FAKE_GH_COMPARE_RC}"
        jq -r "$jqexpr" < "$FAKE_GH_COMPARE" ;;
      *)
        [ "${FAKE_GH_API_RC:-0}" -eq 0 ] || exit "${FAKE_GH_API_RC}"
        runsfile="$FAKE_GH_CHECKRUNS"
        if [ -n "${FAKE_GH_CHECKRUNS_DIR:-}" ]; then
          # Sequenced responses for --wait tests: serve N.json on the Nth
          # check-runs call (the call above was already logged), then
          # last.json once the sequence is exhausted.
          n=$(grep -c 'check-runs' "${FAKE_GH_CALLS}")
          runsfile="$FAKE_GH_CHECKRUNS_DIR/$n.json"
          [ -f "$runsfile" ] || runsfile="$FAKE_GH_CHECKRUNS_DIR/last.json"
        fi
        jq -r "$jqexpr" < "$runsfile" ;;
    esac
    ;;
  *) exit 2 ;;
esac
'''


def _run(tmp_path: Path, runs: list[dict], *, repo="Slimydog21/Antiek", sha=SHA,
         auth_rc=0, api_rc=0, with_gh=True, compare_status="identical",
         compare_rc=0, extra_args: list[str] | None = None,
         env_extra: dict[str, str] | None = None) -> tuple[int, str, str, list[str]]:
    binw = tmp_path / "bin"
    binw.mkdir(exist_ok=True)
    for tool in ("bash", "sed", "awk", "jq", "grep", "date", "sleep"):
        real = shutil.which(tool)
        assert real, tool
        link = binw / tool
        if not link.exists():
            link.symlink_to(real)
    if with_gh:
        gh = binw / "gh"
        gh.write_text(_FAKE_GH)
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    checkruns = tmp_path / "checkruns.json"
    checkruns.write_text(json.dumps({"check_runs": runs}))
    compare = tmp_path / "compare.json"
    compare.write_text(json.dumps({"status": compare_status}))
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    env = {
        "PATH": str(binw),
        "FAKE_GH_AUTH_RC": str(auth_rc),
        "FAKE_GH_API_RC": str(api_rc),
        "FAKE_GH_CHECKRUNS": str(checkruns),
        "FAKE_GH_COMPARE": str(compare),
        "FAKE_GH_COMPARE_RC": str(compare_rc),
        "FAKE_GH_CALLS": str(calls),
        "HOME": str(tmp_path),
        **(env_extra or {}),
    }
    p = subprocess.run([str(binw / "bash"), str(SCRIPT), repo, sha, *(extra_args or [])],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    return p.returncode, p.stdout, p.stderr, calls.read_text().split()


def _green(names=REQUIRED, started="2026-09-22T20:00:00Z"):
    return [{"name": n, "status": "completed", "conclusion": "success", "started_at": started} for n in names]


def test_all_eight_green_exits_0(tmp_path):
    rc, out, _, calls = _run(tmp_path, _green())
    assert rc == 0, out
    assert "all 8 required contexts are success" in out
    assert calls == [
        f"repos/Slimydog21/Antiek/compare/{SHA}...main",
        f"repos/Slimydog21/Antiek/commits/{SHA}/check-runs?per_page=100",
    ]


@pytest.mark.parametrize("repo", [
    "https://github.com/Slimydog21/Antiek.git",
    "git@github.com:Slimydog21/Antiek.git",
    "https://github.com/Slimydog21/Antiek/",
])
def test_every_repo_spelling_queries_the_same_path(tmp_path, repo):
    rc, _, _, calls = _run(tmp_path, _green(), repo=repo)
    assert rc == 0
    assert calls == [
        f"repos/Slimydog21/Antiek/compare/{SHA}...main",
        f"repos/Slimydog21/Antiek/commits/{SHA}/check-runs?per_page=100",
    ]


def test_one_pending_exits_1(tmp_path):
    runs = _green()
    runs[1] = {"name": "vitest", "status": "in_progress", "conclusion": None, "started_at": "2026-09-22T20:00:00Z"}
    rc, out, _, _ = _run(tmp_path, runs)
    assert rc == 1
    assert "NOT GREEN: 'vitest' => pending" in out


def test_one_failure_exits_1(tmp_path):
    runs = _green()
    runs[4]["conclusion"] = "failure"
    rc, out, _, _ = _run(tmp_path, runs)
    assert rc == 1
    assert "NOT GREEN: 'pytest shard 0 of 4' => failure" in out


def test_absent_context_exits_1(tmp_path):
    rc, out, _, _ = _run(tmp_path, _green(REQUIRED[:-1]))
    assert rc == 1
    assert "NOT GREEN: 'pytest shard 3 of 4' => absent" in out


@pytest.mark.parametrize("newest_first", [True, False])
def test_rerun_newest_run_wins(tmp_path, newest_first):
    older = {"name": "vitest", "status": "completed", "conclusion": "failure", "started_at": "2026-09-22T19:00:00Z"}
    newer = {"name": "vitest", "status": "completed", "conclusion": "success", "started_at": "2026-09-22T21:00:00Z"}
    base = [r for r in _green() if r["name"] != "vitest"]
    pair = [newer, older] if newest_first else [older, newer]
    rc, out, _, _ = _run(tmp_path, base + pair)
    assert rc == 0, out  # the rerun turned green: deployable
    older, newer = newer | {"conclusion": "failure", "started_at": "2026-09-22T21:00:00Z"}, older | {"conclusion": "success", "started_at": "2026-09-22T19:00:00Z"}
    pair = [older, newer] if newest_first else [newer, older]
    rc, out, _, _ = _run(tmp_path, base + pair)
    assert rc == 1, out  # the rerun turned red: an earlier green never masks it


def test_short_sha_exits_3_without_calling_gh(tmp_path):
    rc, _, err, calls = _run(tmp_path, _green(), sha="0123456")
    assert rc == 3 and "FULL 40-char" in err and calls == []


def test_unauthenticated_gh_exits_3(tmp_path):
    rc, _, err, calls = _run(tmp_path, _green(), auth_rc=1)
    assert rc == 3 and "not authenticated" in err and calls == []


def test_api_failure_exits_3(tmp_path):
    rc, _, err, _ = _run(tmp_path, _green(), api_rc=1)
    assert rc == 3 and "query failed" in err


def test_missing_gh_exits_3(tmp_path):
    rc, _, err, _ = _run(tmp_path, _green(), with_gh=False)
    assert rc == 3 and "gh CLI not found" in err


# ── only merged code deploys ──


@pytest.mark.parametrize("status", ["identical", "ahead"])
def test_main_tip_or_a_main_ancestor_passes(tmp_path, status):
    # identical = main's tip; ahead = main moved past it (a rollback target).
    rc, out, _, _ = _run(tmp_path, _green(), compare_status=status)
    assert rc == 0, out


@pytest.mark.parametrize("status", ["behind", "diverged", ""])
def test_all_green_commit_not_on_main_exits_4(tmp_path, status):
    # A fork PR's head carries the same eight green contexts from its PR CI.
    # Green says it passed, not that it merged: refuse before reading checks.
    rc, out, err, calls = _run(tmp_path, _green(), compare_status=status)
    assert rc == 4, out + err
    assert "not on main" in err
    assert not any("check-runs" in c for c in calls)


def test_compare_failure_exits_3(tmp_path):
    rc, _, err, _ = _run(tmp_path, _green(), compare_rc=1)
    assert rc == 3 and "cannot compare" in err


# ── --wait: bounded polling for the deploy-time merge race ──
# The ansible playbook resolves main's tip AT DEPLOY TIME, so it can race a
# merge that landed after the workflow's gate job passed; the new tip's
# contexts are still pending. --wait turns that transient pending into a
# bounded poll instead of an instant red run. Poll interval is injected via
# REQUIRE_GREEN_POLL_SECONDS so these tests don't sleep 30s.

def _pending_vitest() -> list[dict]:
    runs = _green()
    runs[1] = {"name": "vitest", "status": "in_progress", "conclusion": None, "started_at": "2026-09-22T20:00:00Z"}
    return runs


def _seq_dir(tmp_path: Path, payloads: list[list[dict]]) -> str:
    d = tmp_path / "seq"
    d.mkdir(exist_ok=True)
    for i, runs in enumerate(payloads, start=1):
        (d / f"{i}.json").write_text(json.dumps({"check_runs": runs}))
    (d / "last.json").write_text(json.dumps({"check_runs": payloads[-1]}))
    return str(d)


def _check_calls(calls: list[str]) -> list[str]:
    return [c for c in calls if "check-runs" in c]


def test_wait_repolls_until_green_then_exits_0(tmp_path):
    seq = _seq_dir(tmp_path, [_pending_vitest(), _pending_vitest(), _green()])
    rc, out, _, calls = _run(tmp_path, _green(), extra_args=["--wait", "300"],
                             env_extra={"FAKE_GH_CHECKRUNS_DIR": seq,
                                        "REQUIRE_GREEN_POLL_SECONDS": "1"})
    assert rc == 0, out
    assert len(_check_calls(calls)) == 3  # two pending polls, then green
    assert "all 8 required contexts are success" in out


def test_wait_budget_expires_still_pending_exits_1(tmp_path):
    rc, out, err, calls = _run(tmp_path, _pending_vitest(), extra_args=["--wait", "2"],
                               env_extra={"REQUIRE_GREEN_POLL_SECONDS": "1"})
    assert rc == 1
    assert "NOT deployable" in out
    assert "giving up" in err
    assert len(_check_calls(calls)) >= 2  # it really polled, not instant


def test_wait_fails_fast_on_a_terminal_failure(tmp_path):
    runs = _green()
    runs[4]["conclusion"] = "failure"
    rc, out, err, calls = _run(tmp_path, runs, extra_args=["--wait", "300"],
                               env_extra={"REQUIRE_GREEN_POLL_SECONDS": "1"})
    assert rc == 1
    assert "NOT GREEN: 'pytest shard 0 of 4' => failure" in out
    assert "waiting cannot help" in err
    assert len(_check_calls(calls)) == 1  # no point waiting on a failure


def test_wait_never_polls_exit_3(tmp_path):
    rc, _, err, calls = _run(tmp_path, _green(), api_rc=1, extra_args=["--wait", "300"],
                             env_extra={"REQUIRE_GREEN_POLL_SECONDS": "1"})
    assert rc == 3 and "query failed" in err
    assert len(_check_calls(calls)) == 1  # cannot verify: immediate


@pytest.mark.parametrize("status", ["behind", "diverged"])
def test_wait_never_polls_exit_4(tmp_path, status):
    rc, _, err, calls = _run(tmp_path, _green(), compare_status=status,
                             extra_args=["--wait", "300"],
                             env_extra={"REQUIRE_GREEN_POLL_SECONDS": "1"})
    assert rc == 4 and "not on main" in err
    assert not _check_calls(calls)  # refused before any check-runs call


def test_no_wait_still_exits_1_immediately_when_pending(tmp_path):
    # The default path (workflow gate job, manual/runbook) is unchanged:
    # one poll, instant exit 1.
    rc, out, _, calls = _run(tmp_path, _pending_vitest())
    assert rc == 1
    assert "NOT GREEN: 'vitest' => pending" in out
    assert len(_check_calls(calls)) == 1


# ── the workflow that calls it ──


def _gate_steps() -> list[dict]:
    wf = yaml.safe_load(WORKFLOW.read_text())
    return wf["jobs"]["gate"]["steps"]


def test_gate_job_checks_out_the_script_before_calling_it():
    steps = _gate_steps()
    call_idx = next(i for i, s in enumerate(steps) if s.get("id") == "required")
    checkouts = [
        i for i, s in enumerate(steps[:call_idx])
        if str(s.get("uses", "")).startswith("actions/checkout@")
        and "tools/deploy" in str((s.get("with") or {}).get("sparse-checkout", ""))
    ]
    assert checkouts, "the gate job must check out tools/deploy before it calls require_green.sh"


def test_gate_step_treats_only_exit_1_as_not_yet():
    steps = _gate_steps()
    run = next(s["run"] for s in steps if s.get("id") == "required")
    assert 'test -x tools/deploy/require_green.sh' in run
    assert '"$rc" -ne 1' in run, "any exit code other than 1 must fail the job, not read as 'not green yet'"
    assert 'exit "$rc"' in run


def test_gate_step_names_not_on_main_as_its_own_refusal():
    steps = _gate_steps()
    run = next(s["run"] for s in steps if s.get("id") == "required")
    assert '"$rc" -eq 4' in run


def _resolve_step_run(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Execute the gate's real Resolve step script with the given event data."""
    step = next(s for s in _gate_steps() if s.get("id") == "resolve")
    script = step["run"].replace("${{ github.repository }}", "Slimydog21/Antiek")
    assert "${{" not in script, "resolve step must read event data from env, never interpolate it"
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", **env})


@pytest.mark.parametrize(("run_event", "run_repo", "expect_rc"), [
    ("push", "Slimydog21/Antiek", 0),
    ("pull_request", "someone/Antiek", 4),     # a fork PR whose branch is named main
    ("pull_request", "Slimydog21/Antiek", 4),  # a same-repo PR run never deploys either
    ("push", "someone/Antiek", 4),
])
def test_resolve_refuses_workflow_run_unless_a_push_to_this_repo(tmp_path, run_event, run_repo, expect_rc):
    out = tmp_path / "out"
    out.write_text("")
    env = {
        "EVENT": "workflow_run", "RUN_SHA": SHA, "RUN_EVENT": run_event,
        "RUN_REPO": run_repo, "THIS_REPO": "Slimydog21/Antiek",
        "INPUT_SHA": "", "GH_TOKEN": "", "GITHUB_OUTPUT": str(out),
    }
    p = _resolve_step_run(env)
    assert p.returncode == expect_rc, p.stdout + p.stderr
    assert (f"sha={SHA}" in out.read_text()) == (expect_rc == 0)
