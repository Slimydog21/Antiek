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


def test_lint_catches_research_bridge_gap_question_ids_without_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "substrate" / "research_bridge" / "gap.py",
        """
def parse_gap(obj):
    return {"question_ids": obj.get("question_ids", [])}
""",
    )

    violations = find_violations(tmp_path)

    assert any(
        "substrate/research_bridge/gap.py" in violation
        and "question_ids" in violation
        for violation in violations
    )


def test_lint_catches_research_bridge_gap_cluster_id_without_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "substrate" / "research_bridge" / "gap.py",
        """
def parse_gap(obj):
    return {"cluster_id": obj.get("cluster_id")}
""",
    )

    violations = find_violations(tmp_path)

    assert any(
        "substrate/research_bridge/gap.py" in violation
        and "cluster_id" in violation
        for violation in violations
    )


def test_lint_catches_parser_that_surfaces_echoed_ids_without_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "bad_investigation_role" / "parser.py",
        """
def parse(obj):
    return {"investigation_id": obj.get("investigation_id")}
""",
    )
    _write(
        tmp_path / "roles" / "bad_visual_role" / "parser.py",
        """
def parse(obj):
    return {"page_or_frame_id": obj.get("page_or_frame_id")}
""",
    )
    _write(
        tmp_path / "roles" / "bad_anchor_role" / "parser.py",
        """
def parse(obj):
    return {"anchor_block_id": obj.get("anchor_block_id")}
""",
    )

    violations = find_violations(tmp_path)

    assert any("investigation_id" in violation for violation in violations)
    assert any("page_or_frame_id" in violation for violation in violations)
    assert any("anchor_block_id" in violation for violation in violations)


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


def test_lint_does_not_let_one_parser_function_validate_for_another(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "mixed_role" / "parser.py",
        """
from substrate.provenance import validate_refs

def parse_good(obj, canonical):
    source_chunk_ids = validate_refs(
        obj.get("source_chunk_ids", []),
        canonical,
    ).valid
    return {"source_chunk_ids": source_chunk_ids}

def parse_bad(obj):
    return {"question_id": obj.get("question_id")}
""",
    )

    violations = find_violations(tmp_path)

    assert any("parse_bad" in violation for violation in violations)
    assert not any("parse_good" in violation for violation in violations)


def test_lint_does_not_let_one_parser_field_validate_for_another(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "mixed_role" / "parser.py",
        """
from substrate.provenance import validate_refs

def parse(obj, canonical):
    source_chunk_ids = validate_refs(
        obj.get("source_chunk_ids", []),
        canonical,
    ).valid
    return {
        "source_chunk_ids": source_chunk_ids,
        "question_id": obj.get("question_id"),
    }
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)
    assert not any("source_chunk_ids" in violation for violation in violations)


def test_lint_catches_subscripted_model_emitted_refs_without_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "bad_subscript_role" / "parser.py",
        """
def parse(obj):
    return {"question_id": obj["question_id"]}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_catches_new_ref_shaped_fields_without_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "future_role" / "parser.py",
        """
def parse(obj):
    return {
        "claim_id": obj.get("claim_id"),
        "note_ids": obj.get("note_ids", []),
    }
""",
    )

    violations = find_violations(tmp_path)

    assert any("claim_id" in violation for violation in violations)
    assert any("note_ids" in violation for violation in violations)


def test_lint_allows_new_ref_shaped_fields_routed_through_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "future_good_role" / "parser.py",
        """
from substrate.provenance import validate_ref, validate_refs

def parse(obj, canonical):
    claim_id = validate_ref(obj.get("claim_id"), canonical)
    note_ids = validate_refs(obj.get("note_ids", []), canonical).valid
    return {
        "claim_id": claim_id,
        "note_ids": note_ids,
    }
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_subscripted_refs_routed_through_validator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "good_subscript_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical):
    question_id = validate_ref(obj["question_id"], canonical)
    return {"question_id": question_id}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_passes_on_current_tree() -> None:
    assert find_violations() == []
