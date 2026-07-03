from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.ops import rebase_preflight


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


def _build_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    assert _git(tmp_path, "init", "-q", "--bare", str(origin)).returncode == 0
    assert _git(tmp_path, "init", "-q", str(repo)).returncode == 0
    assert _git(repo, "config", "user.email", "t@t.t").returncode == 0
    assert _git(repo, "config", "user.name", "t").returncode == 0
    assert _git(repo, "remote", "add", "origin", str(origin)).returncode == 0
    (repo / "shared.txt").write_text("base\n")
    _commit(repo, "base")
    assert _git(repo, "push", "-q", "origin", "HEAD:main").returncode == 0
    assert _git(repo, "fetch", "-q", "origin").returncode == 0
    return repo


def test_rebase_preflight_reports_stale_clean_branch(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _git(repo, "checkout", "-q", "-b", "advance").returncode == 0
    for i in range(1, rebase_preflight.MAX_BEHIND + 2):
        (repo / f"origin-{i}.txt").write_text(f"origin {i}\n")
        _commit(repo, f"origin {i}")
    assert _git(repo, "push", "-q", "origin", "advance:main").returncode == 0

    assert _git(repo, "checkout", "-q", "-b", "feature", base).returncode == 0
    (repo / "local.txt").write_text("local\n")
    _commit(repo, "local")
    assert _git(repo, "fetch", "-q", "origin").returncode == 0

    result = rebase_preflight.run_preflight(repo)

    assert result.status == "stale"
    assert result.does_not_rebase is True
    assert result.commits_behind_origin_main == rebase_preflight.MAX_BEHIND + 1
    assert result.local_commit_count == 1
    assert result.merge_tree_conflict_count == 0
    assert result.overlapping_buckets == ()
    assert result.merge_tree_conflict_buckets == ()
    assert result.remediation == "run `git rebase origin/main`"
    assert _git(repo, "branch", "--show-current").stdout.strip() == "feature"


def test_rebase_preflight_reports_conflicts_without_mutating_worktree(
    tmp_path: Path,
) -> None:
    repo = _build_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _git(repo, "checkout", "-q", "-b", "advance").returncode == 0
    (repo / "shared.txt").write_text("origin change\n")
    _commit(repo, "origin edits shared")
    assert _git(repo, "push", "-q", "origin", "advance:main").returncode == 0

    assert _git(repo, "checkout", "-q", "-b", "feature", base).returncode == 0
    (repo / "shared.txt").write_text("local change\n")
    _commit(repo, "local edits shared")
    assert _git(repo, "fetch", "-q", "origin").returncode == 0
    before = _git(repo, "status", "--short").stdout

    result = rebase_preflight.run_preflight(repo)
    text = rebase_preflight.format_text(result)

    assert result.status == "conflicts"
    assert result.merge_tree_conflict_count == 1
    assert result.merge_tree_conflict_files == ("shared.txt",)
    assert [(b.name, b.count) for b in result.overlapping_buckets] == [("other", 1)]
    assert [(b.name, b.count) for b in result.merge_tree_conflict_buckets] == [
        ("other", 1)
    ]
    assert "conflict_buckets: other=1" in text
    assert "does_not_rebase: yes" in text
    assert _git(repo, "status", "--short").stdout == before


def test_rebase_preflight_json_cli(tmp_path: Path, capsys) -> None:
    repo = _build_repo(tmp_path)
    assert rebase_preflight.main(["--repo", str(repo), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["status"] == "ready"
    assert payload["does_not_rebase"] is True
    assert payload["commits_behind_origin_main"] == 0
    assert payload["overlapping_buckets"] == []
    assert payload["merge_tree_conflict_buckets"] == []


def test_rebase_preflight_markdown_plan_is_bucketed_and_read_only(
    tmp_path: Path,
    capsys,
) -> None:
    repo = _build_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _git(repo, "checkout", "-q", "-b", "advance").returncode == 0
    (repo / "shared.txt").write_text("origin change\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_shared.py").write_text("origin test\n")
    _commit(repo, "origin conflict files")
    assert _git(repo, "push", "-q", "origin", "advance:main").returncode == 0

    assert _git(repo, "checkout", "-q", "-b", "feature", base).returncode == 0
    (repo / "shared.txt").write_text("local change\n")
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_shared.py").write_text("local test\n")
    _commit(repo, "local conflict files")
    assert _git(repo, "fetch", "-q", "origin").returncode == 0
    before = _git(repo, "status", "--short").stdout

    result = rebase_preflight.run_preflight(repo)
    plan = rebase_preflight.format_markdown_plan(result)

    assert plan.startswith("# Rebase preflight plan")
    assert "- does_not_rebase: yes" in plan
    assert "git worktree add ../antiek-rebase-preflight HEAD" in plan
    assert "- other: 1 files; showing all 1" in plan
    assert "- tests: 1 files; showing all 1" in plan
    assert "  - shared.txt" in plan
    assert "  - tests/test_shared.py" in plan
    assert _git(repo, "status", "--short").stdout == before

    assert rebase_preflight.main(["--repo", str(repo), "--plan-markdown"]) == 0
    captured = capsys.readouterr()
    assert "# Rebase preflight plan" in captured.out
    assert "## Conflict Lanes" in captured.out


def test_rebase_preflight_write_plan_cli(tmp_path: Path, capsys) -> None:
    repo = _build_repo(tmp_path)
    plan_path = tmp_path / "plan.md"

    assert rebase_preflight.main(
        ["--repo", str(repo), "--write-plan", str(plan_path)]
    ) == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == str(plan_path)
    assert plan_path.read_text().startswith("# Rebase preflight plan\n")
