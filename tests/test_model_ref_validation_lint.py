"""Guard for model-emitted parser reference validation.

The KDL provenance sprint made role parsers compare model-emitted IDs against
canonical refs. This lint is the future-surface tripwire: a new role parser that
reads ``*_id`` / ``*_ids`` fields without the shared validator must red before
it can land.
"""

from __future__ import annotations

from pathlib import Path

from tools.lint import model_ref_validation_check as lint

_REPO = Path(__file__).resolve().parent.parent


def test_current_tree_is_clean() -> None:
    assert lint.find_violations(repo=_REPO) == []


def test_unvalidated_model_id_parser_reds(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    parser_dir = repo / "roles" / "new_role"
    parser_dir.mkdir(parents=True)
    (parser_dir / "parser.py").write_text(
        "def parse_new_role_response(obj):\n"
        "    return obj.get('source_chunk_ids')\n",
        encoding="utf-8",
    )

    violations = lint.find_violations(repo=repo)
    assert len(violations) == 1
    assert "roles/new_role/parser.py:2" in violations[0]
    assert "source_chunk_ids" in violations[0]


def test_parser_using_shared_validator_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    parser_dir = repo / "roles" / "new_role"
    parser_dir.mkdir(parents=True)
    (parser_dir / "parser.py").write_text(
        "from substrate.provenance.validate_refs import validate_refs\n\n"
        "def parse_new_role_response(obj, canonical_chunk_ids):\n"
        "    return validate_refs(obj.get('source_chunk_ids'), canonical_chunk_ids)\n",
        encoding="utf-8",
    )

    assert lint.find_violations(repo=repo) == []
