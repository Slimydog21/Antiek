"""Tests for the role-parser provenance reference lint."""

from __future__ import annotations

from pathlib import Path

from tools.lint.provenance_ref_check import find_violations


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_lint_catches_parser_that_surfaces_source_ids_without_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "bad_role" / "parser.py",
        """
def parse(obj):
    return {"source_chunk_ids": obj.get("source_chunk_ids", [])}
""",
    )

    violations = find_violations(tmp_path)

    assert violations
    assert "source_chunk_ids" in violations[0]


def test_lint_catches_parser_that_surfaces_question_ids_without_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "bad_plural_role" / "parser.py",
        """
def parse(obj):
    return {"question_ids": obj.get("question_ids", [])}
""",
    )
    _write(
        tmp_path / "roles" / "bad_singular_role" / "parser.py",
        """
def parse(obj):
    return {"question_id": obj.get("question_id")}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_ids" in violation for violation in violations)
    assert any("question_id" in violation for violation in violations)


def test_lint_allows_parser_that_routes_refs_through_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "good_role" / "parser.py",
        """
from substrate.provenance import validate_refs

def parse(obj, canonical):
    source_chunk_ids = validate_refs(
        obj.get("source_chunk_ids", []),
        canonical,
        on_invalid="raise",
    ).valid
    return {"source_chunk_ids": source_chunk_ids}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_passes_on_current_tree() -> None:
    assert find_violations() == []
