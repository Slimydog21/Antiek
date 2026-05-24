"""
The ``prompts/`` directory is append-only: no commit ever deletes a
file under it. This invariant protects the agent-provenance chain so
``Prompt-Hash`` trailers in old commits always resolve.

How we test it: ``git log --diff-filter=D --name-only -- prompts/``
lists every commit that has ever deleted a file under ``prompts/``.
If the output is non-empty, the invariant is broken.

A deliberate redaction (e.g., a prompt accidentally containing a
secret) is allowed only when accompanied by a commit message that
contains the marker ``REDACT-PROMPTS:`` in the body. The test
recognises that marker as an explicit operator-signed exception.
Without the marker, the deletion fails CI loudly.

The append-only rule covers files, not the directory itself: an
empty ``prompts/`` with only ``.gitkeep`` is the legitimate "new
repo" state.

Spec: ``~/specs/antiek-hashimoto-engineering/sprint-e6-provenance.html``
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
REDACTION_MARKER = "REDACT-PROMPTS:"


def _git_lines(*args: str) -> list[str]:
    """Run ``git`` and return stdout split into lines (no trailing blanks)."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def _commits_deleting_under_prompts() -> list[tuple[str, list[str]]]:
    """Return ``[(commit_sha, [deleted_paths])]`` for prompts/ deletions.

    The walk is bounded by repo HEAD; in CI that runs against a PR
    branch the comparison naturally sees only history reachable from
    that branch.
    """
    # First check whether prompts/ exists in history at all. If not,
    # there is nothing to enforce yet (fresh repo before SPR-E6
    # lands). Return empty.
    has_path = _git_lines("log", "--all", "--pretty=", "--name-only", "--", "prompts/")
    if not has_path:
        return []

    # Use --diff-filter=D to surface deletions only; one commit can
    # delete multiple prompt files, which we group.
    raw = subprocess.run(
        [
            "git",
            "log",
            "--diff-filter=D",
            "--name-only",
            "--pretty=format:>>>%H",
            "--",
            "prompts/",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    out: list[tuple[str, list[str]]] = []
    current_sha: str | None = None
    current_files: list[str] = []
    for line in raw.splitlines():
        if line.startswith(">>>"):
            if current_sha is not None and current_files:
                out.append((current_sha, current_files))
            current_sha = line[3:].strip()
            current_files = []
        else:
            stripped = line.strip()
            if stripped:
                current_files.append(stripped)
    if current_sha is not None and current_files:
        out.append((current_sha, current_files))
    return out


def _commit_message_body(sha: str) -> str:
    """Full commit message body for a SHA."""
    return subprocess.run(
        ["git", "log", "-1", "--format=%B", sha],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_prompts_directory_exists() -> None:
    """The directory must exist. ``.gitkeep`` is enough.

    A future maintainer who deletes the entire directory thinking it's
    empty would break the append-only rule by removing its anchor.
    Catch that here.
    """
    prompts_dir = REPO_ROOT / "prompts"
    assert prompts_dir.is_dir(), f"prompts/ directory missing at {prompts_dir}"
    # ``.gitkeep`` or any real prompt file qualifies as anchor.
    contents = sorted(p.name for p in prompts_dir.iterdir())
    assert contents, "prompts/ is empty — needs at least .gitkeep so the dir is tracked"


def test_no_prompt_deletions_in_history() -> None:
    """Walk history. Any deletion under prompts/ that lacks the
    REDACT-PROMPTS: marker in its commit body fails the suite.

    The marker is a small ceremony — it is the operator's signed
    acknowledgement that a prompt is being intentionally removed.
    Catches silent rewrites; allows audited surgery.
    """
    deletions = _commits_deleting_under_prompts()
    silent: list[tuple[str, list[str]]] = []
    for sha, paths in deletions:
        body = _commit_message_body(sha)
        if REDACTION_MARKER not in body:
            silent.append((sha, paths))
    if silent:
        lines = ["prompts/ files were deleted without the REDACT-PROMPTS: marker:"]
        for sha, paths in silent:
            lines.append(f"  {sha[:10]}: " + ", ".join(paths))
        lines.append(
            "If a prompt genuinely needs redaction (e.g., secret material), make "
            "the commit message include the line 'REDACT-PROMPTS: <reason>' so "
            "history shows the deletion was intentional."
        )
        pytest.fail("\n".join(lines), pytrace=False)


def test_readme_describes_the_invariant() -> None:
    """Sanity check on the README so future maintainers reading the
    test see a pointer to the human-readable rule. If the README is
    moved or rewritten without preserving the append-only language,
    catch it here.
    """
    readme = REPO_ROOT / "prompts" / "README.md"
    assert readme.exists(), "prompts/README.md missing — operators read this for the rule"
    text = readme.read_text(encoding="utf-8")
    assert "append-only" in text.lower(), (
        "prompts/README.md does not mention 'append-only'; the rule must be documented "
        "in the human-readable file as well as enforced in this test"
    )
