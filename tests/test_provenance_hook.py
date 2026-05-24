"""
Unit tests for the .githooks/commit-msg hook script.

The hook is a Python script with a shebang. We load it as a module
via ``importlib.util`` (the file has no ``.py`` extension because
git expects hook executables) and exercise its functions directly.
End-to-end "spin up a temp git repo and commit" coverage is in
``test_provenance_hook_e2e.py`` — slower, fewer cases.

These tests cover:

- normalize_prompt: dedupe-stable whitespace handling
- compute_hash: 64-char hex sha256
- append_trailer: trailer block detection and insertion
- write_prompt_file: dedupe-on-existing, front-matter shape
- process_commit_message: every code path
  (operator commit → noop, idempotent re-run, missing env → block,
   blank env → block, happy path → trailer + file)

Spec: ``~/specs/antiek-hashimoto-engineering/sprint-e6-provenance.html``
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".githooks" / "commit-msg"


@pytest.fixture(scope="module")
def hook():
    """Load the hook script as a module.

    The hook lives at ``.githooks/commit-msg`` (no extension) because
    git invokes hooks by name. ``importlib.util.spec_from_file_location``
    returns ``None`` for files without a recognised suffix, so we
    construct the spec with an explicit ``SourceFileLoader``.
    """
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("antiek_commit_msg_hook", str(HOOK_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader, f"could not load hook spec from {HOOK_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["antiek_commit_msg_hook"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# normalize_prompt / compute_hash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("hello", "hello"),
        ("  hello\n", "hello"),
        ("\n\nhello world\n\n", "hello world"),
        ("hello\nworld", "hello\nworld"),
        ("\n  multiline\n  prompt  \n", "multiline\n  prompt"),
    ],
)
def test_normalize_prompt_strips_outer_whitespace(hook, raw, expected) -> None:
    assert hook.normalize_prompt(raw) == expected


def test_compute_hash_is_sha256_hex(hook) -> None:
    h = hook.compute_hash("a quick brown fox")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_hash_is_stable_under_outer_whitespace(hook) -> None:
    a = hook.compute_hash(hook.normalize_prompt("hello world"))
    b = hook.compute_hash(hook.normalize_prompt("  hello world\n"))
    assert a == b


def test_compute_hash_differs_for_distinct_prompts(hook) -> None:
    assert hook.compute_hash("a") != hook.compute_hash("b")


# ---------------------------------------------------------------------------
# append_trailer
# ---------------------------------------------------------------------------


def test_append_trailer_to_body_only_message(hook) -> None:
    msg = "fix(x): something\n\nA body paragraph.\n"
    out = hook.append_trailer(msg, "abc" + "0" * 61)
    assert out.endswith("\nPrompt-Hash: abc" + "0" * 61 + "\n")
    # There must be a blank line between body and trailer block.
    assert "\n\nPrompt-Hash:" in out


def test_append_trailer_to_existing_trailer_block(hook) -> None:
    msg = (
        "fix(x): something\n"
        "\n"
        "A body paragraph.\n"
        "\n"
        "Co-Authored-By: Claude\n"
    )
    out = hook.append_trailer(msg, "f" * 64)
    # Trailers should remain contiguous: no extra blank between
    # Co-Authored-By and Prompt-Hash.
    assert "Co-Authored-By: Claude\nPrompt-Hash:" in out


def test_append_trailer_to_subject_only(hook) -> None:
    msg = "minor fix\n"
    out = hook.append_trailer(msg, "0" * 64)
    assert out.endswith("Prompt-Hash: " + "0" * 64 + "\n")
    # Subject-only is not a trailer block, so we want a blank line.
    assert "minor fix\n\nPrompt-Hash:" in out


# ---------------------------------------------------------------------------
# write_prompt_file
# ---------------------------------------------------------------------------


def test_write_prompt_file_writes_yaml_front_matter(hook, tmp_path) -> None:
    digest = "a" * 64
    path = hook.write_prompt_file(tmp_path, digest, "hello world", "main")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "agent: claude" in text
    assert "branch: main" in text
    assert "captured_at: 2" in text  # ISO timestamp starts with year
    assert text.rstrip().endswith("hello world")


def test_write_prompt_file_is_dedupe(hook, tmp_path) -> None:
    digest = "b" * 64
    p1 = hook.write_prompt_file(tmp_path, digest, "x", "main")
    first_content = p1.read_text(encoding="utf-8")
    # Second call with a different prompt under the same digest must
    # NOT overwrite (dedupe by hash, not by content). In production the
    # hashes only collide when normalised prompts match, so this is a
    # safety net against a future caller passing the wrong arguments.
    p2 = hook.write_prompt_file(tmp_path, digest, "y", "main")
    assert p1 == p2
    assert p2.read_text(encoding="utf-8") == first_content


def test_write_prompt_file_creates_prompts_dir(hook, tmp_path) -> None:
    nested = tmp_path / "nested" / "prompts"
    assert not nested.exists()
    hook.write_prompt_file(nested, "c" * 64, "x", "main")
    assert nested.exists()


# ---------------------------------------------------------------------------
# process_commit_message
# ---------------------------------------------------------------------------


def _write_msg(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "COMMIT_EDITMSG"
    p.write_text(content, encoding="utf-8")
    return p


def test_process_operator_commit_is_noop(hook, tmp_path) -> None:
    msg = _write_msg(tmp_path, "feat: an operator commit\n\nbody.\n")
    code, summary = hook.process_commit_message(msg, repo_root=tmp_path, env_prompt=None)
    assert code == 0
    assert summary == ""
    # Body unchanged.
    assert msg.read_text(encoding="utf-8") == "feat: an operator commit\n\nbody.\n"


def test_process_already_tagged_is_noop(hook, tmp_path) -> None:
    msg = _write_msg(
        tmp_path,
        "feat: agent thing\n\nbody\n\nCo-Authored-By: Claude Opus 4.7\nPrompt-Hash: "
        + "d" * 64
        + "\n",
    )
    before = msg.read_text(encoding="utf-8")
    code, summary = hook.process_commit_message(msg, repo_root=tmp_path, env_prompt="anything")
    assert code == 0
    assert summary == ""
    assert msg.read_text(encoding="utf-8") == before


def test_process_co_authored_without_env_blocks(hook, tmp_path) -> None:
    msg = _write_msg(tmp_path, "feat: agent thing\n\nbody\n\nCo-Authored-By: Claude\n")
    code, summary = hook.process_commit_message(msg, repo_root=tmp_path, env_prompt=None)
    assert code == 1
    assert "ANTIEK_AGENT_PROMPT" in summary


def test_process_co_authored_with_blank_env_blocks(hook, tmp_path) -> None:
    msg = _write_msg(tmp_path, "feat: agent thing\n\nbody\n\nCo-Authored-By: Claude\n")
    code, summary = hook.process_commit_message(msg, repo_root=tmp_path, env_prompt="   \n\n  ")
    assert code == 1
    assert "blank" in summary.lower()


def test_process_co_authored_happy_path(hook, tmp_path) -> None:
    msg = _write_msg(
        tmp_path, "feat: agent thing\n\nbody\n\nCo-Authored-By: Claude Opus 4.7\n"
    )
    # Initialize a throwaway git repo so current_branch() succeeds.
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "spr-e6"], cwd=str(tmp_path), check=True)
    # Need at least one commit for symbolic-ref to resolve, otherwise
    # the hook's current_branch() falls back to 'detached'. Either is
    # acceptable; we just want determinism.

    code, summary = hook.process_commit_message(
        msg, repo_root=tmp_path, env_prompt="the agent prompt"
    )
    assert code == 0, summary
    # Trailer present.
    new = msg.read_text(encoding="utf-8")
    assert "Prompt-Hash: " in new
    # Prompt file persisted under prompts/<hash>.md.
    expected_hash = hook.compute_hash(hook.normalize_prompt("the agent prompt"))
    prompt_file = tmp_path / "prompts" / f"{expected_hash}.md"
    assert prompt_file.exists()
    assert "the agent prompt" in prompt_file.read_text(encoding="utf-8")


def test_process_idempotent_after_happy_path(hook, tmp_path) -> None:
    """Re-running on a message that already got tagged must be a no-op
    even if the env var changes. This catches a "second commit-msg
    invocation re-hashes a different prompt" regression.
    """
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    msg = _write_msg(
        tmp_path, "feat: agent thing\n\nbody\n\nCo-Authored-By: Claude\n"
    )
    hook.process_commit_message(msg, repo_root=tmp_path, env_prompt="first")
    after_first = msg.read_text(encoding="utf-8")
    code, _ = hook.process_commit_message(msg, repo_root=tmp_path, env_prompt="different prompt")
    assert code == 0
    # Message unchanged on re-run; original Prompt-Hash preserved.
    assert msg.read_text(encoding="utf-8") == after_first


# ---------------------------------------------------------------------------
# CO_AUTHORED detection — case + spacing tolerance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "trailer",
    [
        "Co-Authored-By: Claude",
        "Co-Authored-By:  Claude",         # double space
        "co-authored-by: claude",          # lowercase
        "Co-Authored-By: Claude Opus 4.7", # with model
        "Co-Authored-By: Claude (with parens)",
    ],
)
def test_co_authored_re_detects_variants(hook, trailer) -> None:
    msg = f"feat: x\n\n{trailer}\n"
    assert hook.CO_AUTHORED_RE.search(msg), f"failed to detect: {trailer!r}"


@pytest.mark.parametrize(
    "trailer",
    [
        "Co-Authored: Claude",           # missing -By
        "Co Authored By: Claude",        # no hyphens
        "Co-Authored-By: ClaudeBot",     # different word; \b prevents bleed
        "  Co-Authored-By: Claude",      # not at line start
    ],
)
def test_co_authored_re_rejects_near_misses(hook, trailer) -> None:
    msg = f"feat: x\n\n{trailer}\n"
    assert not hook.CO_AUTHORED_RE.search(msg), f"falsely matched: {trailer!r}"
