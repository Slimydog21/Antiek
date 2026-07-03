"""Invariant tests for the green-between-buckets rebase executor.

These pin the load-bearing behaviours from SPR-02:

* **Halt-on-red** -- a red scoped gate does NOT checkpoint and exits non-zero
  (both against a mocked gate and against a *genuine* ``git rebase`` + real
  ``pytest`` gate on a synthetic conflict fixture).
* **No-fake-green** -- ``green-complete`` is unreachable unless a passing
  full-suite exit code is recorded; flipping any recorded exit code un-greens it.
* **Checkout guard** -- the executor refuses to mutate the primary/main worktree.

Everything runs against tiny throwaway git repos / mocked gate results -- never
the live 238-commit branch -- and completes in seconds.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ops import rebase_execute as rx
from tools.ops import rebase_preflight
from tools.ops.rebase_preflight import PathBucket


# --------------------------------------------------------------------------- #
# git fixture helpers
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _commit(repo: Path, message: str) -> str:
    assert _git(repo, "add", "-A").returncode == 0
    result = _git(repo, "commit", "-q", "-m", message)
    assert result.returncode == 0, result.stderr
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _init_repo(tmp_path: Path, name: str = "repo") -> tuple[Path, Path]:
    origin = tmp_path / f"{name}-origin.git"
    repo = tmp_path / name
    assert _git(tmp_path, "init", "-q", "--bare", str(origin)).returncode == 0
    assert _git(tmp_path, "init", "-q", str(repo)).returncode == 0
    assert _git(repo, "config", "user.email", "t@t.t").returncode == 0
    assert _git(repo, "config", "user.name", "t").returncode == 0
    assert _git(repo, "remote", "add", "origin", str(origin)).returncode == 0
    return origin, repo


_GATE_TEST = """\
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_state_resolved():
    assert "MERGED" in (ROOT / "substrate" / "state.py").read_text()


def test_rate_resolved():
    assert "RATE = 3" in (ROOT / "acquisition" / "rate.py").read_text()
"""


def _build_conflict_repo(tmp_path: Path) -> tuple[Path, str]:
    """A synthetic repo whose feature branch conflicts with origin/main in two
    trees (substrate + acquisition). Returns (primary_repo, feature_sha).

    The gate test (``tests/test_gate.py``) reads the *resolved* files, so its
    exit code is a genuine function of the resolution content -- a git-clean but
    wrong resolution reds the suite (rigor #3).
    """

    _origin, repo = _init_repo(tmp_path)
    (repo / "substrate").mkdir()
    (repo / "acquisition").mkdir()
    (repo / "tests").mkdir()
    (repo / "substrate" / "state.py").write_text('VALUE = "base"\n')
    (repo / "acquisition" / "rate.py").write_text("RATE = 0\n")
    (repo / "tests" / "test_gate.py").write_text(_GATE_TEST)
    base = _commit(repo, "base")
    assert _git(repo, "push", "-q", "origin", "HEAD:main").returncode == 0

    # origin/main advances (its side of the conflict).
    assert _git(repo, "checkout", "-q", "-b", "advance").returncode == 0
    (repo / "substrate" / "state.py").write_text('VALUE = "origin"\n')
    (repo / "acquisition" / "rate.py").write_text("RATE = 1\n")
    _commit(repo, "origin edits")
    assert _git(repo, "push", "-q", "origin", "advance:main").returncode == 0

    # feature branch (our side of the conflict).
    assert _git(repo, "checkout", "-q", "-b", "feature", base).returncode == 0
    (repo / "substrate" / "state.py").write_text('VALUE = "feature"\n')
    (repo / "acquisition" / "rate.py").write_text("RATE = 2\n")
    feature_sha = _commit(repo, "feature edits")
    assert _git(repo, "fetch", "-q", "origin").returncode == 0
    return repo, feature_sha


@pytest.fixture()
def disposable_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A real *linked* worktree so ``assert_disposable`` passes for unit tests
    that mock the gate (no real rebase needed)."""

    _origin, repo = _init_repo(tmp_path, "wtrepo")
    (repo / "f.txt").write_text("x\n")
    _commit(repo, "base")
    dest = tmp_path / "disposable"
    assert _git(repo, "worktree", "add", "-q", str(dest), "HEAD").returncode == 0
    return repo, dest


# --------------------------------------------------------------------------- #
# M1 -- consume the plan, ordered buckets
# --------------------------------------------------------------------------- #
def test_order_buckets_is_deterministic_ascending_blast_radius() -> None:
    buckets = [
        PathBucket("backend-substrate", 40),
        PathBucket("docs", 3),
        PathBucket("reading-app", 12),
        PathBucket("other", 1),
        PathBucket("tooling", 2),
        PathBucket("acquisition", 5),
    ]
    ordered = [b.name for b in rx.order_buckets(buckets)]
    # docs/tooling before acquisition/reading-app; backend-substrate LAST.
    assert ordered == [
        "docs",
        "tooling",
        "acquisition",
        "reading-app",
        "other",
        "backend-substrate",
    ]
    # Pure + stable: same input, same output.
    assert rx.order_buckets(buckets) == rx.order_buckets(list(reversed(buckets)))


def test_load_plan_roundtrips_preflight_json_and_counts_match(tmp_path: Path) -> None:
    repo, _ = _build_conflict_repo(tmp_path)
    preflight = rebase_preflight.run_preflight(repo)
    assert preflight.status == "conflicts"

    plan_path = tmp_path / "plan.json"
    assert rebase_preflight.main(["--repo", str(repo), "--json"]) == 0  # smoke
    plan_path.write_text(
        json.dumps(__import__("dataclasses").asdict(preflight), indent=2, sort_keys=True)
    )

    loaded = rx.load_plan(plan_path)
    # The executor consumes the planner's buckets verbatim (no recompute).
    assert loaded.merge_tree_conflict_buckets == preflight.merge_tree_conflict_buckets
    ordered = rx.plan_bucket_order(loaded)
    counts = {b.name: b.count for b in ordered}
    plan_counts = {b.name: b.count for b in preflight.merge_tree_conflict_buckets}
    assert counts == plan_counts
    # The two conflicting trees are present and backend-substrate is ordered last.
    assert set(counts) == {"backend-substrate", "acquisition"}
    assert [b.name for b in ordered][-1] == "backend-substrate"


def test_plan_cli_dry_run_matches_preflight_counts(tmp_path: Path, capsys) -> None:
    repo, _ = _build_conflict_repo(tmp_path)
    preflight = rebase_preflight.run_preflight(repo)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(__import__("dataclasses").asdict(preflight), indent=2, sort_keys=True)
    )

    rc = rx.main(["plan", "--plan", str(plan_path), "--dry-run", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    got = {b["name"]: b["count"] for b in payload["ordered_buckets"]}
    want = {b.name: b.count for b in preflight.merge_tree_conflict_buckets}
    assert got == want


# --------------------------------------------------------------------------- #
# M4c -- checkout guard
# --------------------------------------------------------------------------- #
def test_assert_disposable_fires_on_primary_checkout(tmp_path: Path) -> None:
    _origin, repo = _init_repo(tmp_path)
    (repo / "f.txt").write_text("x\n")
    _commit(repo, "base")
    # A plain `git init` repo IS its own main worktree -> not disposable.
    with pytest.raises(rx.DisposableWorktreeError):
        rx.assert_disposable(repo, primary_checkout=repo, cwd=None)


def test_assert_disposable_fires_on_operator_cwd(disposable_worktree) -> None:
    _repo, dest = disposable_worktree
    # Even a linked worktree is refused if it is the operator's cwd.
    with pytest.raises(rx.DisposableWorktreeError):
        rx.assert_disposable(dest, primary_checkout=None, cwd=dest)


def test_assert_disposable_passes_on_linked_worktree(disposable_worktree) -> None:
    repo, dest = disposable_worktree
    assert rx.assert_disposable(dest, primary_checkout=repo, cwd=repo) == dest.resolve()


# --------------------------------------------------------------------------- #
# M4a -- halt-on-red (mocked gate; the guard still runs for real)
# --------------------------------------------------------------------------- #
def _mock_runner(exit_code: int, output: str = "boom"):
    calls: list[rx.GateSpec] = []

    def runner(spec: rx.GateSpec, worktree: Path) -> rx.GateResult:
        calls.append(spec)
        return rx.GateResult(exit_code=exit_code, output=output)

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_advance_bucket_halts_on_red_scoped_gate(disposable_worktree, tmp_path: Path) -> None:
    repo, dest = disposable_worktree
    ledger = rx.RebaseLedger(
        branch="feature", onto="origin/main", ordered_buckets=("acquisition", "backend-substrate")
    )

    checkpoint_called = {"n": 0}

    def never_checkpoint(_wt: Path):
        checkpoint_called["n"] += 1
        return (0, "")

    halt_log = tmp_path / "halt.log"
    outcome = rx.advance_bucket(
        dest,
        ledger=ledger,
        bucket="acquisition",
        order_index=0,
        scope="bucket",
        is_final=False,
        timestamp_in="2026-07-03T00:00:00Z",
        primary_checkout=repo,
        cwd=repo,
        gate_runner=_mock_runner(exit_code=1, output="pytest said FAILED"),
        checkpoint_fn=never_checkpoint,
        head_fn=lambda _wt: "DEADBEEF",
        halt_log_path=halt_log,
    )

    assert outcome.exit_code != 0
    assert outcome.entry.status == "red"
    assert outcome.entry.checkpoint_sha is None  # NO checkpoint on red
    assert checkpoint_called["n"] == 0  # checkpoint fn never invoked
    assert halt_log.read_text() == "pytest said FAILED"  # failing output preserved
    assert not rx.is_green_complete(outcome.ledger)
    assert rx.ledger_status(outcome.ledger) == "halted-red"


def test_advance_bucket_checkpoints_only_on_green(
    disposable_worktree,
) -> None:
    repo, dest = disposable_worktree
    ledger = rx.RebaseLedger(branch="feature", onto="origin/main", ordered_buckets=("acquisition",))

    outcome = rx.advance_bucket(
        dest,
        ledger=ledger,
        bucket="acquisition",
        order_index=0,
        scope="bucket",
        is_final=False,
        timestamp_in="TS",
        primary_checkout=repo,
        cwd=repo,
        gate_runner=_mock_runner(exit_code=0),
        checkpoint_fn=lambda _wt: (0, "continued"),
        head_fn=lambda _wt: "abc123def456",
    )
    assert outcome.exit_code == 0
    assert outcome.entry.status == "green"
    assert outcome.entry.checkpoint_sha == "abc123def456"


def test_advance_bucket_refuses_primary_checkout(tmp_path: Path) -> None:
    _origin, repo = _init_repo(tmp_path)
    (repo / "f.txt").write_text("x\n")
    _commit(repo, "base")
    ledger = rx.RebaseLedger(branch="f", onto="origin/main", ordered_buckets=("acquisition",))
    with pytest.raises(rx.DisposableWorktreeError):
        rx.advance_bucket(
            repo,  # the primary checkout
            ledger=ledger,
            bucket="acquisition",
            order_index=0,
            scope="bucket",
            is_final=False,
            timestamp_in="TS",
            primary_checkout=repo,
            cwd=None,
            gate_runner=_mock_runner(exit_code=0),
        )


def test_final_bucket_forces_full_scope(disposable_worktree) -> None:
    repo, dest = disposable_worktree
    ledger = rx.RebaseLedger(branch="f", onto="origin/main", ordered_buckets=("backend-substrate",))
    runner = _mock_runner(exit_code=0)
    outcome = rx.advance_bucket(
        dest,
        ledger=ledger,
        bucket="backend-substrate",
        order_index=8,
        scope="bucket",  # asked for bucket...
        is_final=True,  # ...but final forces full
        timestamp_in="TS",
        primary_checkout=repo,
        cwd=repo,
        gate_runner=runner,
        checkpoint_fn=lambda _wt: (0, ""),
        head_fn=lambda _wt: "sha",
    )
    assert outcome.entry.scope == "full"
    # The full gate is the cross-stack suite: pytest + vitest (two commands).
    assert len(runner.calls[0].commands) == 2  # type: ignore[attr-defined]
    assert runner.calls[0].scope == "full"  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# M4b -- no-fake-green: green-complete is a pure fn of recorded exit codes
# --------------------------------------------------------------------------- #
def _green_entry(bucket: str, idx: int, scope: str) -> rx.BucketLedgerEntry:
    return rx.BucketLedgerEntry(
        bucket=bucket,
        order_index=idx,
        scope=scope,
        resolved=True,
        gate_label="lbl",
        gate_command="cmd",
        exit_code=0,
        checkpoint_sha=f"sha-{bucket}",
        timestamp_in="TS",
        status="green",
    )


def test_green_complete_requires_a_recorded_full_suite_pass() -> None:
    ledger = rx.RebaseLedger(
        branch="f", onto="origin/main", ordered_buckets=("acquisition", "backend-substrate")
    )
    ledger = rx.upsert_entry(ledger, _green_entry("acquisition", 0, "bucket"))
    # All buckets green BUT only scoped -- no full-suite pass -> NOT complete.
    ledger = rx.upsert_entry(ledger, _green_entry("backend-substrate", 1, "bucket"))
    assert rx.is_green_complete(ledger) is False
    assert rx.ledger_status(ledger) != "green-complete"

    # Record the mandatory full-suite pass on the final bucket -> complete.
    ledger = rx.upsert_entry(ledger, _green_entry("backend-substrate", 1, "full"))
    assert rx.is_green_complete(ledger) is True
    assert rx.ledger_status(ledger) == "green-complete"


def test_green_complete_unreachable_when_recorded_exit_flipped() -> None:
    ledger = rx.RebaseLedger(
        branch="f", onto="origin/main", ordered_buckets=("acquisition", "backend-substrate")
    )
    ledger = rx.upsert_entry(ledger, _green_entry("acquisition", 0, "bucket"))
    ledger = rx.upsert_entry(ledger, _green_entry("backend-substrate", 1, "full"))
    assert rx.is_green_complete(ledger) is True

    # Flip the recorded full-suite exit code to non-zero: status must un-green.
    flipped = rx.upsert_entry(
        ledger,
        rx.BucketLedgerEntry(
            bucket="backend-substrate",
            order_index=1,
            scope="full",
            resolved=True,
            gate_label="lbl",
            gate_command="cmd",
            exit_code=1,  # <-- the only change
            checkpoint_sha=None,
            timestamp_in="TS",
            status="red",
        ),
    )
    assert rx.is_green_complete(flipped) is False
    assert rx.ledger_status(flipped) == "halted-red"

    # Flip a *scoped* (non-final) bucket too -> also un-green.
    flipped2 = rx.upsert_entry(
        ledger,
        rx.BucketLedgerEntry(
            bucket="acquisition",
            order_index=0,
            scope="bucket",
            resolved=True,
            gate_label="lbl",
            gate_command="cmd",
            exit_code=1,
            checkpoint_sha=None,
            timestamp_in="TS",
            status="red",
        ),
    )
    assert rx.is_green_complete(flipped2) is False


def test_green_complete_false_when_a_planned_bucket_is_unresolved() -> None:
    # BLOCKING-fix regression: ordered_buckets has TWO names but only ONE has an
    # entry -- and it is even a green FULL-scope pass. The other bucket is never
    # resolved (the rebase is mid-flight). Must NOT be green-complete.
    ledger = rx.RebaseLedger(
        branch="feature",
        onto="origin/main",
        ordered_buckets=("docs", "backend-substrate"),
    )
    ledger = rx.upsert_entry(ledger, _green_entry("docs", 0, "full"))
    # docs is green + full, but backend-substrate has no entry at all.
    assert rx.is_green_complete(ledger) is False
    assert rx.ledger_status(ledger) != "green-complete"


def test_green_complete_false_when_full_pass_is_not_on_the_final_bucket() -> None:
    # BLOCKING-fix regression: every bucket is green, but the mandatory full-suite
    # pass is on the NON-final bucket (docs) while the final bucket
    # (backend-substrate) is only scoped. The end-state gate never ran full, so
    # this must NOT be green-complete.
    ledger = rx.RebaseLedger(
        branch="feature",
        onto="origin/main",
        ordered_buckets=("docs", "backend-substrate"),
    )
    ledger = rx.upsert_entry(ledger, _green_entry("docs", 0, "full"))
    ledger = rx.upsert_entry(ledger, _green_entry("backend-substrate", 1, "bucket"))
    assert rx.is_green_complete(ledger) is False
    # Making the final bucket's gate full flips it to complete (both green + final full).
    ledger = rx.upsert_entry(ledger, _green_entry("backend-substrate", 1, "full"))
    assert rx.is_green_complete(ledger) is True


def test_gate_cli_guards_before_staging_the_index(tmp_path: Path) -> None:
    # SHOULD-FIX regression: `gate` must call assert_disposable BEFORE stage_all,
    # so a mis-pointed run at a non-disposable checkout stages nothing.
    repo, _feature_sha = _build_conflict_repo(tmp_path)
    # Dirty the (primary) checkout: an unstaged edit + an untracked file.
    (repo / "substrate" / "state.py").write_text('VALUE = "dirty-unstaged"\n')
    (repo / "untracked.txt").write_text("should never be staged\n")

    preflight = rebase_preflight.run_preflight(repo)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(__import__("dataclasses").asdict(preflight), indent=2, sort_keys=True)
    )
    parser = rx.build_parser()
    args = parser.parse_args(
        [
            "gate",
            "--plan",
            str(plan),
            "--worktree",
            str(repo),  # point at the primary checkout itself
            "--primary",
            str(repo),
            "--bucket",
            "acquisition",
            "--timestamp-in",
            "TS",
            "--ledger",
            str(tmp_path / "led.json"),
        ]
    )
    with pytest.raises(rx.DisposableWorktreeError):
        rx._cmd_gate(args)
    # The guard fired before `git add -A`: the index is untouched.
    staged = _git(repo, "diff", "--cached", "--name-only").stdout.strip()
    assert staged == ""


def test_ledger_json_roundtrip_and_text_render() -> None:
    ledger = rx.RebaseLedger(
        branch="feature", onto="origin/main", ordered_buckets=("acquisition", "backend-substrate")
    )
    ledger = rx.upsert_entry(ledger, _green_entry("acquisition", 0, "bucket"))
    ledger = rx.upsert_entry(ledger, _green_entry("backend-substrate", 1, "full"))
    data = rx.ledger_to_dict(ledger)
    assert data["green_complete"] is True
    assert data["status"] == "green-complete"
    restored = rx.ledger_from_dict(data)
    assert rx.is_green_complete(restored) is True
    text = rx.format_ledger_text(ledger)
    assert "rebase-ledger: green-complete" in text
    assert "green_complete: yes" in text


def test_status_cli_exit_code(tmp_path: Path, capsys) -> None:
    # A non-complete ledger exits 1; a green-complete one exits 0.
    ledger = rx.RebaseLedger(branch="f", onto="origin/main", ordered_buckets=("acquisition",))
    ledger = rx.upsert_entry(ledger, _green_entry("acquisition", 0, "bucket"))
    path = tmp_path / "ledger.json"
    rx.write_ledger(ledger, path)
    assert rx.main(["status", "--ledger", str(path)]) == 1

    ledger = rx.upsert_entry(ledger, _green_entry("acquisition", 0, "full"))
    rx.write_ledger(ledger, path)
    capsys.readouterr()
    assert rx.main(["status", "--ledger", str(path)]) == 0


# --------------------------------------------------------------------------- #
# M2 -- real bucket end-to-end on a synthetic conflict fixture (genuine git
# rebase + real pytest gate). NOT the live 238-commit branch.
# --------------------------------------------------------------------------- #
def test_real_bucket_green_checkpoint_on_synthetic_fixture(tmp_path: Path) -> None:
    repo, feature_sha = _build_conflict_repo(tmp_path)
    dest = tmp_path / "disposable-green"
    rx.create_disposable_worktree(repo, dest, feature_sha)
    try:
        code, _out = rx.begin_rebase(dest, "origin/main")
        assert code != 0, "expected the rebase to stop at a conflict"
        assert rx.rebase_in_progress(dest)
        buckets = {b.name for b in rx.current_conflict_buckets(dest)}
        assert buckets == {"backend-substrate", "acquisition"}

        # Resolve BOTH conflicts correctly (git-clean AND code-correct).
        (dest / "substrate" / "state.py").write_text('VALUE = "MERGED"\n')
        (dest / "acquisition" / "rate.py").write_text("RATE = 3\n")
        rx.stage_all(dest)

        ledger = rx.RebaseLedger(
            branch="feature",
            onto="origin/main",
            ordered_buckets=("acquisition", "backend-substrate"),
        )
        outcome = rx.advance_bucket(
            dest,
            ledger=ledger,
            bucket="acquisition",
            order_index=0,
            scope="bucket",
            is_final=False,
            timestamp_in="2026-07-03T12:00:00Z",
            python_exe=sys.executable,  # real pytest, real exit code
            primary_checkout=repo,
            cwd=repo,
        )
        assert outcome.exit_code == 0
        assert outcome.entry.status == "green"
        assert outcome.entry.checkpoint_sha  # a real HEAD sha was recorded
        # The checkpoint advanced the rebase to completion.
        assert not rx.rebase_in_progress(dest)
        assert outcome.entry.checkpoint_sha == rx.head_sha(dest)
    finally:
        rx.remove_disposable_worktree(repo, dest)


def test_real_bucket_halts_on_bad_resolution(tmp_path: Path) -> None:
    repo, feature_sha = _build_conflict_repo(tmp_path)
    dest = tmp_path / "disposable-red"
    rx.create_disposable_worktree(repo, dest, feature_sha)
    try:
        code, _out = rx.begin_rebase(dest, "origin/main")
        assert code != 0
        head_before = rx.head_sha(dest)

        # Git-clean resolution, but WRONG content -> gate must red (rigor #3).
        (dest / "substrate" / "state.py").write_text('VALUE = "feature"\n')  # no MERGED
        (dest / "acquisition" / "rate.py").write_text("RATE = 3\n")
        rx.stage_all(dest)

        ledger = rx.RebaseLedger(
            branch="feature",
            onto="origin/main",
            ordered_buckets=("acquisition", "backend-substrate"),
        )
        halt_log = tmp_path / "halt.log"
        outcome = rx.advance_bucket(
            dest,
            ledger=ledger,
            bucket="acquisition",
            order_index=0,
            scope="bucket",
            is_final=False,
            timestamp_in="TS",
            python_exe=sys.executable,
            primary_checkout=repo,
            cwd=repo,
            halt_log_path=halt_log,
        )
        assert outcome.exit_code != 0
        assert outcome.entry.status == "red"
        assert outcome.entry.checkpoint_sha is None
        # No advancement: the rebase is still in progress at the same HEAD.
        assert rx.rebase_in_progress(dest)
        assert rx.head_sha(dest) == head_before
        assert halt_log.exists() and halt_log.read_text()
    finally:
        rx.remove_disposable_worktree(repo, dest)
