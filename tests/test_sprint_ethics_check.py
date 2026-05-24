"""Tests for ``tools/lint/sprint_ethics_check.py``.

Synthetic spec fixtures with planted trigger terms + valid / invalid
blocks. Plus a real-tree integration test that asserts the current
Antiek tree passes (allowlisted by the forward-only policy).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_LINT_PATH = _REPO / "tools" / "lint" / "sprint_ethics_check.py"
_spec = importlib.util.spec_from_file_location("ethics_check", _LINT_PATH)
assert _spec is not None and _spec.loader is not None
ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ec)


# ---------------------------------------------------------------------------
# Unit: trigger detection
# ---------------------------------------------------------------------------


def test_trigger_detection_case_insensitive() -> None:
    text = "This sprint deals with PUBLISHER consent."
    found = ec._has_trigger(text, ["publisher", "consent", "MDL"])
    assert found == {"publisher", "consent"}


def test_trigger_detection_skips_word_substrings() -> None:
    """``publisher`` should NOT match inside ``unpublished``."""
    text = "This is an unpublished draft."
    found = ec._has_trigger(text, ["publisher"])
    # ``publisher`` is alphabetic-only → whole-word match → no hit.
    assert found == set()


def test_trigger_detection_finds_legal_codes() -> None:
    """Legal codes like 'MDL' must hit on substring (the lint allows
    substring for codes with hyphens / numerics).
    """
    text = "Referenced by the AG MDL theory."
    found = ec._has_trigger(text, ["MDL"])
    assert found == {"MDL"}


# ---------------------------------------------------------------------------
# Unit: block validation
# ---------------------------------------------------------------------------


def test_valid_block_has_all_four_fields(tmp_path: Path) -> None:
    text = """
# Some sprint

## Ethics articulation

- Technical risk: ...
- Societal / user risk: ...
- Reputational risk: ...
- Operator decision: yes-or-no?
"""
    ok, missing = ec._has_valid_block(text)
    assert ok
    assert missing == []


def test_block_missing_field_is_flagged() -> None:
    text = """
## Ethics articulation

- Technical risk: ...
- Reputational risk: ...
- Operator decision: ...
"""
    ok, missing = ec._has_valid_block(text)
    assert not ok
    # Missing the "Societal" field.
    assert "Societal" in missing


def test_na_declaration_accepted() -> None:
    text = "## Ethics articulation\n\nEthics N/A — frontend tooltip only."
    ok, missing = ec._has_valid_block(text)
    assert ok
    assert missing == []


def test_na_without_justification_rejected() -> None:
    """``Ethics N/A`` alone (no justification after the dash) does NOT
    satisfy the lint — author must explain.
    """
    text = "Ethics N/A"
    # No dash + justification → no NA match → falls through to "no block".
    ok, missing = ec._has_valid_block(text)
    assert not ok


def test_html_h2_heading_recognized() -> None:
    """HTML sprint pages use ``<h2>`` — the lint matches both Markdown
    and HTML heading shapes.
    """
    text = """
<h2>Ethics articulation</h2>
<ul>
<li>Technical risk: x</li>
<li>Societal: x</li>
<li>Reputational: x</li>
<li>Operator decision: x</li>
</ul>
"""
    ok, missing = ec._has_valid_block(text)
    assert ok


# ---------------------------------------------------------------------------
# Integration: check_files against synthetic specs/ tree
# ---------------------------------------------------------------------------


def test_check_files_flags_trigger_without_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ec, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ec, "SCAN_DIRS", ["specs"])
    spec_dir = tmp_path / "specs" / "demo"
    spec_dir.mkdir(parents=True)
    bad = spec_dir / "sprint-01.md"
    bad.write_text("# Sprint 1\n\nThis touches publisher consent.\n")
    violations = ec.check_files(
        [bad], triggers=["publisher", "consent"], allowlist=[]
    )
    assert len(violations) == 1
    path, found, missing = violations[0]
    assert {"publisher", "consent"} == found


def test_check_files_accepts_clean_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ec, "REPO_ROOT", tmp_path)
    spec_dir = tmp_path / "specs" / "demo"
    spec_dir.mkdir(parents=True)
    good = spec_dir / "sprint-01.md"
    good.write_text(
        "# Sprint 1\n\n"
        "Touches publisher consent.\n\n"
        "## Ethics articulation\n\n"
        "- Technical risk: ...\n"
        "- Societal: ...\n"
        "- Reputational: ...\n"
        "- Operator decision: yes-or-no?\n"
    )
    violations = ec.check_files(
        [good], triggers=["publisher", "consent"], allowlist=[]
    )
    assert violations == []


def test_check_files_honors_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ec, "REPO_ROOT", tmp_path)
    spec_dir = tmp_path / "specs" / "demo"
    spec_dir.mkdir(parents=True)
    triggered = spec_dir / "sprint-01.md"
    triggered.write_text("# Trigger\n\nMentions publisher.\n")
    violations = ec.check_files(
        [triggered],
        triggers=["publisher"],
        allowlist=["specs/demo/"],
    )
    assert violations == []


# ---------------------------------------------------------------------------
# Real-tree integration: the current Antiek tree passes (forward-only
# policy + allowlist absorbs the existing specs).
# ---------------------------------------------------------------------------


def test_real_tree_clean_under_forward_only_policy() -> None:
    """Whole-tree run. The allowlist covers existing specs/ + docs/.
    New spec docs that touch §9.0 surfaces will fail this test until
    they add the block — exactly the forward-only enforcement P9 wants.
    """
    proc = subprocess.run(
        [sys.executable, str(_LINT_PATH), "--quiet"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"sprint_ethics_check failed unexpectedly:\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_planted_violation_in_tree_is_caught() -> None:
    """Drop a new (non-allowlisted) sprint doc with triggers but no
    block. The lint catches it.
    """
    scratch = _REPO / "specs" / "_ethics_scratch_test"
    scratch.mkdir(parents=True, exist_ok=True)
    planted = scratch / "sprint-01.md"
    planted.write_text(
        "# Sprint X\n\nThis touches publisher consent and Bartz exposure.\n"
    )
    try:
        # The scratch dir is NOT in the allowlist, so the planted
        # violation should fire.
        proc = subprocess.run(
            [sys.executable, str(_LINT_PATH)],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 1, (
            f"expected non-zero exit:\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        assert "publisher" in proc.stderr
        assert "_ethics_scratch_test" in proc.stderr
    finally:
        planted.unlink(missing_ok=True)
        scratch.rmdir()


def test_help_works() -> None:
    proc = subprocess.run(
        [sys.executable, str(_LINT_PATH), "--help"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert "ethics" in proc.stdout.lower()
