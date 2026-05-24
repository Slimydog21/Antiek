"""
Tests for ``substrate/role_shape.py`` and ``tools/role_audit.py``.

Flat layout matching the repo's existing test convention. Test names
match what the audit and role-shape system actually promise so that a
future reader can map test -> guarantee directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from substrate.role_shape import RoleMetadata
from tools.role_audit import audit


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# RoleMetadata construction
# ---------------------------------------------------------------------------


def test_polecat_convenience_constructor_defaults():
    md = RoleMetadata.polecat(
        expected_input_tokens=1000,
        expected_output_tokens=200,
        spawn_pattern_doc="A reasonable sentence about the polecat role here.",
    )
    assert md.shape == "polecat"
    assert md.multi_turn is False
    assert md.idempotent is True
    assert md.expected_input_tokens == 1000
    assert md.expected_output_tokens == 200


def test_crew_convenience_constructor_defaults():
    md = RoleMetadata.crew(
        expected_input_tokens=8000,
        expected_output_tokens=2000,
        spawn_pattern_doc="A reasonable sentence about the crew role here.",
    )
    assert md.shape == "crew"
    assert md.multi_turn is True
    assert md.idempotent is False


def test_invalid_shape_raises():
    with pytest.raises(ValueError, match="must be 'polecat' or 'crew'"):
        RoleMetadata(
            shape="hybrid",  # type: ignore[arg-type]
            expected_input_tokens=1000,
            expected_output_tokens=200,
            multi_turn=False,
            idempotent=True,
            spawn_pattern_doc="A doc string long enough to pass length check.",
        )


def test_non_positive_token_count_raises():
    with pytest.raises(ValueError, match="must be positive"):
        RoleMetadata.polecat(
            expected_input_tokens=0,
            expected_output_tokens=200,
            spawn_pattern_doc="A doc string long enough to pass length check.",
        )


def test_too_short_spawn_pattern_doc_raises():
    # 29 chars; below the 30-char minimum on purpose.
    short = "x" * 29
    with pytest.raises(ValueError, match="at least 30 chars"):
        RoleMetadata.polecat(
            expected_input_tokens=1000,
            expected_output_tokens=200,
            spawn_pattern_doc=short,
        )


def test_minimum_length_spawn_pattern_doc_accepted():
    # 30 chars exactly; should pass.
    exact = "x" * 30
    md = RoleMetadata.polecat(
        expected_input_tokens=1000,
        expected_output_tokens=200,
        spawn_pattern_doc=exact,
    )
    assert md.spawn_pattern_doc == exact


def test_metadata_is_frozen():
    md = RoleMetadata.polecat(
        expected_input_tokens=1000,
        expected_output_tokens=200,
        spawn_pattern_doc="A doc string long enough to pass length check.",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        md.shape = "crew"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# audit() function — direct, in-process
# ---------------------------------------------------------------------------


def test_audit_finds_all_existing_roles():
    """Every role package under roles/ must be annotated. If a future
    role lands without the metadata, this fails — exactly the guard the
    audit exists to provide."""
    result = audit()
    assert result["unannotated"] == [], (
        f"unannotated roles found: {result['unannotated']}. Each role "
        f"package's __init__.py must define __role_metadata__."
    )
    assert result["total"] >= 14, (
        f"expected at least 14 roles; found {result['total']}"
    )


def test_audit_classifies_known_roles_correctly():
    """Lock the polecat/crew classifications so a future drift surfaces.
    Listed roles must keep their shape unless intentionally re-classified
    (and this test updated). The test is the audit trail."""
    result = audit()
    by_name = {r["name"]: r for r in result["annotated"]}

    known_polecats = {
        "challenger", "connector", "decomposer", "evidence_retriever",
        "grounder", "note_taker", "parameter_extractor", "visual",
        "voice_note_followup",
    }
    known_crew = {
        "creative_writer", "interviewer", "synthesizer", "thought_partner",
        "user_agent",
    }
    for role in known_polecats:
        assert by_name[role]["shape"] == "polecat", (
            f"{role} is supposed to be polecat. Re-classify here only if you've "
            "made a deliberate decision and documented it in HERESIES.md "
            "or docs/decisions/."
        )
    for role in known_crew:
        assert by_name[role]["shape"] == "crew", (
            f"{role} is supposed to be crew. Same re-classification discipline."
        )


def test_audit_all_docs_are_substantive():
    """Every spawn_pattern_doc must be at least 30 chars (the construction
    check) AND must NOT be filler (e.g. 'xxxxxxxxxxxx...')."""
    result = audit()
    for r in result["annotated"]:
        doc = r["spawn_pattern_doc"].strip()
        assert len(doc) >= 30, f"{r['name']}: doc too short"
        # If the entire doc is one repeated character, it's filler.
        assert len(set(doc)) > 5, (
            f"{r['name']}: spawn_pattern_doc looks like filler: {doc!r}"
        )


# ---------------------------------------------------------------------------
# CLI form — exit code semantics for CI integration
# ---------------------------------------------------------------------------


def test_role_audit_cli_check_mode_exits_zero_when_clean():
    result = subprocess.run(
        [sys.executable, "-m", "tools.role_audit", "--check"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    # --check is silent on success
    assert result.stdout == ""


def test_role_audit_cli_json_mode_returns_valid_json():
    result = subprocess.run(
        [sys.executable, "-m", "tools.role_audit", "--json"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "annotated" in payload
    assert "unannotated" in payload
    assert "by_shape" in payload


def test_role_audit_cli_human_mode_shows_table():
    result = subprocess.run(
        [sys.executable, "-m", "tools.role_audit"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "annotated" in result.stdout
    assert "polecat" in result.stdout
    assert "crew" in result.stdout
