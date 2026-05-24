"""
End-to-end tests for ``python -m tools.agent_commits``.

Each test spins up a throwaway git repo in a tmp dir, makes synthetic
commits (some operator-only, some with ``Co-Authored-By: Claude`` +
``Prompt-Hash``), then exercises ``list`` / ``show`` / ``stats`` via
the CLI's ``main()``.

Why a real git repo rather than mocks: the production cost of getting
``git log --grep`` semantics wrong is silent (the wrong commits show up
or none do). A real repo catches those regressions immediately.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e6-provenance.html
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from tools.agent_commits.__main__ import build_parser, main


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Fresh git repo with deterministic identity."""
    cwd = tmp_path
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.email", "test@antiek"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=cwd, check=True)
    # commit.gpgsign defaults vary by machine; force off so a missing
    # GPG keyring doesn't break commits in CI.
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=cwd, check=True)
    return cwd


def _commit(repo: Path, *, content: str, message: str) -> str:
    """Write a file + commit. Returns short SHA."""
    file_path = repo / "doc.md"
    file_path.write_text(file_path.read_text(encoding="utf-8") + content if file_path.exists() else content)
    subprocess.run(["git", "add", "doc.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return sha


def _agent_commit(repo: Path, *, content: str, subject: str, prompt: str) -> tuple[str, str]:
    """Make a commit that looks like the hook authored it.

    Returns ``(short_sha, prompt_hash)``.
    """
    normalized = prompt.strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    prompts_dir = repo / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    (prompts_dir / f"{digest}.md").write_text(
        f"---\ncaptured_at: 2026-05-24T00:00:00Z\nagent: claude\nbranch: test\n---\n\n{normalized}\n",
        encoding="utf-8",
    )
    msg = (
        f"{subject}\n"
        "\n"
        "Body of the agent commit.\n"
        "\n"
        "Co-Authored-By: Claude Opus 4.7\n"
        f"Prompt-Hash: {digest}\n"
    )
    sha = _commit(repo, content=content, message=msg)
    return sha, digest


def _run(repo: Path, argv: list[str]) -> tuple[int, str, str]:
    """Run main() with cwd-replaced and capture stdout/stderr."""
    old_cwd = os.getcwd()
    os.chdir(repo)
    out = io.StringIO()
    err = io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    finally:
        os.chdir(old_cwd)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_returns_only_agent_commits(repo: Path) -> None:
    _commit(repo, content="op1\n", message="op: first operator commit")
    _agent_commit(repo, content="a1\n", subject="feat: agent commit 1", prompt="prompt A")
    _commit(repo, content="op2\n", message="op: second operator commit")
    _agent_commit(repo, content="a2\n", subject="feat: agent commit 2", prompt="prompt B")

    code, out, err = _run(repo, ["list"])
    assert code == 0, err
    # Two agent commits, two operator commits — only the agent ones appear.
    assert "agent commit 1" in out
    assert "agent commit 2" in out
    assert "operator commit" not in out
    assert "2 agent commit(s)" in out


def test_list_marks_commits_without_prompt_hash(repo: Path) -> None:
    """Legacy commits (no Prompt-Hash trailer) appear with the · marker.

    The summary footer contains the symbol legend (``✓ = has Prompt-Hash
    trailer``); we therefore assert on the per-row data, not on absence
    of ✓ from the whole output.
    """
    _commit(
        repo,
        content="legacy\n",
        message="feat: legacy agent commit\n\nCo-Authored-By: Claude\n",
    )
    code, out, _ = _run(repo, ["list"])
    assert code == 0
    assert "legacy agent commit" in out
    # The single row must use the · marker, never the ✓ marker.
    row_lines = [ln for ln in out.splitlines() if "legacy agent commit" in ln]
    assert len(row_lines) == 1
    assert "·" in row_lines[0]
    assert "✓" not in row_lines[0]


def test_list_handles_no_agent_commits(repo: Path) -> None:
    _commit(repo, content="op\n", message="op: operator only")
    code, out, _ = _run(repo, ["list"])
    assert code == 0
    assert "no agent commits" in out.lower()


def test_list_since_window_filters(repo: Path) -> None:
    _agent_commit(repo, content="old\n", subject="feat: old", prompt="old")
    # We can't easily back-date a commit in this test, but we can
    # assert that --since=1d works without error and includes today's
    # commits.
    code, out, _ = _run(repo, ["list", "--since=1d"])
    assert code == 0
    assert "feat: old" in out


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_by_short_sha(repo: Path) -> None:
    sha, _ = _agent_commit(
        repo, content="x\n", subject="feat: x", prompt="resolve the puzzle"
    )
    code, out, _ = _run(repo, ["show", sha])
    assert code == 0
    assert "resolve the puzzle" in out
    assert "agent: claude" in out


def test_show_by_prompt_hash(repo: Path) -> None:
    _, digest = _agent_commit(
        repo, content="y\n", subject="feat: y", prompt="another prompt"
    )
    code, out, _ = _run(repo, ["show", digest])
    assert code == 0
    assert "another prompt" in out


def test_show_unknown_identifier_returns_1(repo: Path) -> None:
    _commit(repo, content="op\n", message="op")
    code, out, err = _run(repo, ["show", "0" * 64])
    assert code == 1
    assert "No prompt found" in err


def test_show_commit_without_prompt_hash_returns_1(repo: Path) -> None:
    """A commit that has Co-Authored-By but no Prompt-Hash trailer (legacy)
    cannot resolve to a prompt file. The command must say so loudly."""
    _commit(
        repo,
        content="legacy\n",
        message="feat: legacy\n\nCo-Authored-By: Claude\n",
    )
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    code, _, err = _run(repo, ["show", sha])
    assert code == 1
    assert "No prompt found" in err


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats_reports_ratio(repo: Path) -> None:
    _commit(repo, content="op1\n", message="op: 1")
    _commit(repo, content="op2\n", message="op: 2")
    _agent_commit(repo, content="a\n", subject="feat: a", prompt="p")
    code, out, _ = _run(repo, ["stats", "--since=1d"])
    assert code == 0
    assert "total commits: 3" in out
    assert "agent commits: 1 (33.3%)" in out
    assert "Prompt-Hash trailer: 1/1" in out


def test_stats_handles_zero_commits(repo: Path) -> None:
    """Brand-new repo: nothing in window. Must not crash."""
    code, out, _ = _run(repo, ["stats", "--since=1d"])
    assert code == 0
    assert "no commits" in out.lower()


# ---------------------------------------------------------------------------
# Parser sanity — the subcommand wiring catches typos at import time.
# ---------------------------------------------------------------------------


def test_parser_rejects_unknown_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


def test_parser_requires_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
