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


def test_lint_catches_grounder_parser_without_validator(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "grounder" / "parser.py",
        """
def parse_grounder_response(obj):
    return {"located_chunk_id": obj.get("located_chunk_id")}
""",
    )

    violations = find_violations(tmp_path)

    assert any(
        "roles/grounder/parser.py" in violation
        and "located_chunk_id" in violation
        for violation in violations
    )


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


def test_lint_allows_aliased_validator_import(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "aliased_role" / "parser.py",
        """
from substrate.provenance import validate_refs as check_refs

def parse(obj, canonical):
    source_chunk_ids = check_refs(obj.get("source_chunk_ids", []), canonical).valid
    return {"source_chunk_ids": source_chunk_ids}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_namespaced_validator_import(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "namespaced_role" / "parser.py",
        """
import substrate.provenance as provenance

def parse(obj, canonical):
    question_id = provenance.validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_substrate_package_provenance_import(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "package_import_role" / "parser.py",
        """
from substrate import provenance

def parse(obj, canonical):
    question_id = provenance.validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_rejects_unrelated_validate_ref_attribute(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "spoofed_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical, helper):
    question_id = helper.validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_shadowed_provenance_package_import(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "shadowed_package_role" / "parser.py",
        """
from substrate import provenance

def parse(obj, canonical, provenance):
    question_id = provenance.validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_shadowed_validator_parameter(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "shadowed_param_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical, validate_ref):
    question_id = validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_shadowed_validator_assignment(tmp_path: Path) -> None:
    _write(
        tmp_path / "roles" / "shadowed_assignment_role" / "parser.py",
        """
from substrate.provenance import validate_ref

validate_ref = lambda candidate, canonical: candidate

def parse(obj, canonical):
    question_id = validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_module_import_shadowing_validator_namespace(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "shadowed_import_role" / "parser.py",
        """
from substrate import provenance
import unrelated.provenance as provenance

def parse(obj, canonical):
    question_id = provenance.validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_function_import_shadowing_validator_namespace(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "shadowed_function_import_role" / "parser.py",
        """
from substrate import provenance

def parse(obj, canonical):
    import unrelated.provenance as provenance
    question_id = provenance.validate_ref(obj.get("question_id"), canonical)
    return {"question_id": question_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


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


def test_lint_catches_ref_shaped_output_key_from_remapped_raw_field(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "remapped_role" / "parser.py",
        """
def parse(obj):
    return {"question_id": obj.get("qid")}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_catches_ref_shaped_output_key_from_raw_alias(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "raw_alias_role" / "parser.py",
        """
def parse(obj):
    raw = obj.get("qid")
    return {"question_id": raw}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_catches_ref_shaped_constructor_keyword_from_raw_alias(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "constructor_role" / "parser.py",
        """
from dataclasses import dataclass

@dataclass
class ParsedQuestion:
    question_id: str

def parse(obj):
    raw = obj.get("qid")
    return ParsedQuestion(question_id=raw)
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_catches_ref_shaped_positional_constructor_arg_from_raw_alias(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "positional_constructor_role" / "parser.py",
        """
from dataclasses import dataclass

@dataclass
class ParsedQuestion:
    question_id: str
    text: str

def parse(obj):
    raw = obj.get("qid")
    return ParsedQuestion(raw, "body")
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


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


def test_lint_allows_ref_shaped_positional_constructor_arg_from_validator_alias(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "positional_constructor_good_role" / "parser.py",
        """
from dataclasses import dataclass
from substrate.provenance import validate_ref

@dataclass
class ParsedQuestion:
    question_id: str | None
    text: str

def parse(obj, canonical):
    raw = obj.get("qid")
    question_id = validate_ref(raw, canonical)
    return ParsedQuestion(question_id, "body")
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_ref_shaped_constructor_keyword_from_validator_alias(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "constructor_good_role" / "parser.py",
        """
from dataclasses import dataclass
from substrate.provenance import validate_ref

@dataclass
class ParsedQuestion:
    question_id: str | None

def parse(obj, canonical):
    raw = obj.get("qid")
    question_id = validate_ref(raw, canonical)
    return ParsedQuestion(question_id=question_id)
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_ref_shaped_positional_constructor_arg_from_generated_id(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "positional_generated_role" / "parser.py",
        """
from dataclasses import dataclass

@dataclass
class ExtractedNote:
    note_id: str
    text: str

def _new_note_id():
    return "n-123"

def parse(obj):
    return ExtractedNote(_new_note_id(), "body")
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_ref_shaped_constructor_keyword_from_generated_id(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "generated_role" / "parser.py",
        """
from dataclasses import dataclass

@dataclass
class ExtractedNote:
    note_id: str

def _new_note_id():
    return "n-123"

def parse(obj):
    return ExtractedNote(note_id=_new_note_id())
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_ref_shaped_output_key_from_generated_id_alias(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "generated_alias_role" / "parser.py",
        """
from substrate.graph.ops import new_random_id

def parse(obj):
    cluster_id = new_random_id("cluster")
    return {"cluster_id": cluster_id}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_rejects_generated_id_helper_that_accepts_model_input(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "generated_arg_role" / "parser.py",
        """
def _new_question_id(raw):
    return raw

def parse(obj):
    return {"question_id": _new_question_id(obj.get("qid"))}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_new_random_id_with_model_emitted_prefix(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "dynamic_generated_role" / "parser.py",
        """
from substrate.graph.ops import new_random_id

def parse(obj):
    cluster_id = new_random_id(obj.get("prefix"))
    return {"cluster_id": cluster_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("cluster_id" in violation for violation in violations)


def test_lint_rejects_shadowed_generated_id_factory(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "shadowed_generated_role" / "parser.py",
        """
from substrate.graph.ops import new_random_id

def parse(obj, new_random_id):
    cluster_id = new_random_id("cluster")
    return {"cluster_id": cluster_id}
""",
    )

    violations = find_violations(tmp_path)

    assert any("cluster_id" in violation for violation in violations)


def test_lint_ignores_control_ref_keywords_that_are_not_parser_outputs(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "delegating_role" / "parser.py",
        """
def _parse_child(obj, *, expected_question_id=None, canonical_note_ids=None):
    return {"text": str(obj)}

def parse(obj, expected_question_id, canonical_note_ids):
    return _parse_child(
        obj,
        expected_question_id=expected_question_id,
        canonical_note_ids=canonical_note_ids,
    )
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_ref_shaped_output_key_from_validator_alias(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "remapped_good_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical):
    raw = obj.get("qid")
    question_id = validate_ref(raw, canonical)
    return {"question_id": question_id}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_rejects_output_that_mixes_validator_with_raw_ref(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "mixed_trust_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical):
    return {
        "question_id": (
            validate_ref(obj.get("qid"), canonical),
            obj.get("question_id"),
        )
    }
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_raw_output_even_when_same_field_was_validated_elsewhere(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "same_field_bypass_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical):
    validate_ref(obj.get("question_id"), canonical)
    return {"question_id": obj.get("question_id")}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_rejects_output_alias_that_mixes_trusted_and_raw_refs(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "mixed_alias_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical):
    trusted = validate_ref(obj.get("qid"), canonical)
    mixed = trusted or obj.get("question_id")
    return {"question_id": mixed}
""",
    )

    violations = find_violations(tmp_path)

    assert any("question_id" in violation for violation in violations)


def test_lint_allows_output_alias_that_combines_only_trusted_refs(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "trusted_combo_role" / "parser.py",
        """
from substrate.provenance import validate_ref

def parse(obj, canonical):
    primary = validate_ref(obj.get("qid"), canonical)
    fallback = validate_ref(obj.get("fallback_qid"), canonical)
    selected = primary or fallback
    return {"question_id": selected}
""",
    )

    assert find_violations(tmp_path) == []


def test_lint_allows_none_for_optional_ref_output(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "roles" / "optional_ref_role" / "parser.py",
        """
from dataclasses import dataclass

@dataclass
class GroundingVerdict:
    located_chunk_id: str | None

def parse(obj):
    return GroundingVerdict(None)
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
