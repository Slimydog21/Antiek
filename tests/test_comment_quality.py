"""Unit tests for tools/lint/comment_quality.py (AOD SPR-05).

The WHAT/WHY boundary fixtures are the contract: a comment that restates the
next line flags; a why-comment, a magic-number-provenance comment, a comment
inside a string, and a section header all stay quiet.
"""

from __future__ import annotations

from pathlib import Path

from tools.lint.comment_quality import classify_comment, scan_file, scan_paths


def _is_what(comment: str, code: str) -> bool:
    return classify_comment(comment, code)[0]


# --------------------------------------------------------------------------- #
# WHAT — flag                                                                  #
# --------------------------------------------------------------------------- #

def test_what_comment_restates_assignment_flags() -> None:
    assert _is_what("# set the counter to zero", "counter = 0")


def test_what_comment_loop_flags() -> None:
    assert _is_what("# loop over items", "for item in items:")


def test_what_comment_increment_flags() -> None:
    assert _is_what("# increment i", "i += 1")


# --------------------------------------------------------------------------- #
# WHY — do not flag                                                            #
# --------------------------------------------------------------------------- #

def test_why_comment_with_because_not_flagged() -> None:
    assert not _is_what("# counter starts at zero because the loop is 1-indexed", "counter = 0")


def test_magic_number_provenance_not_flagged() -> None:
    # number + unit word -> provenance, not a restatement
    assert not _is_what("# 500 ms p99 budget", "timeout = 500")


def test_section_header_over_class_not_flagged() -> None:
    assert not _is_what("# Models", "class CreatePlanRequest(BaseModel):")


def test_section_header_over_def_not_flagged() -> None:
    assert not _is_what("# Dispatch and parse", "def _dispatch_and_parse(x):")


def test_box_drawing_divider_not_flagged() -> None:
    assert not _is_what("# ── Rubric scoring ──", 'RUBRIC_SCORED = "rubric.scored"')


def test_citation_not_flagged() -> None:
    assert not _is_what("# see §9.0 for the gating rule", "gate = True")


def test_url_not_flagged() -> None:
    assert not _is_what("# per https://example.com/spec", "x = compute()")


def test_directive_not_flagged() -> None:
    assert not _is_what("# type: ignore[arg-type]", "x = foo()")


def test_todo_not_flagged() -> None:
    assert not _is_what("# TODO: revisit the counter", "counter = 0")


def test_adds_info_not_flagged() -> None:
    # a comment whose words are NOT all in the code adds information
    assert not _is_what("# the fallback path when the cache is cold", "counter = 0")


# --------------------------------------------------------------------------- #
# File-level: string masking + multi-line block                               #
# --------------------------------------------------------------------------- #

def test_comment_inside_a_string_not_flagged(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    # the '#' here is inside a string literal — tokenize must not treat it as a comment
    f.write_text('label = "# set x to zero"\nx = 0\n', encoding="utf-8")
    assert scan_file(f) == []


def test_multiline_comment_block_not_flagged(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    # a two-line comment block is prose; the second line must not flag as a restatement
    f.write_text("# this explains the rationale for the value\n# set counter to zero\ncounter = 0\n", encoding="utf-8")
    assert scan_file(f) == []


def test_trailing_what_comment_flags(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("counter = 0  # set counter to zero\n", encoding="utf-8")
    hits = scan_file(f)
    assert len(hits) == 1
    assert hits[0].line == 1


def test_scan_paths_over_dir(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("# increment i\ni += 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("# because it must start empty\nx = []\n", encoding="utf-8")
    hits = scan_paths([tmp_path])
    assert len(hits) == 1  # only a.py's what-comment
    assert hits[0].path.endswith("a.py")
