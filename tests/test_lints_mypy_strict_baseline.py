"""Tests for tools.lints.mypy_strict_baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.lints import mypy_strict_baseline as msb
from tools.lints.mypy_strict_baseline import (
    MypyError,
    main,
    mypy_error_to_key,
    parse_mypy_output,
)

SAMPLE_MYPY_OUTPUT = """\
runtime/db_lock.py:217: error: Function is missing a type annotation  [no-untyped-def]
runtime/db_lock.py:225: error: Call to untyped function "close" in typed context  [no-untyped-call]
runtime/db_lock.py:510: error: Argument 1 to "open" has incompatible type "str | None"; expected "str"  [arg-type]
substrate/event_log/events.py:617: error: Missing type arguments for generic type "set"  [type-arg]
runtime/db_lock.py:506: note: this is just a note, should be ignored
Found 5 errors in 2 files (checked 3 source files)
"""


def test_parse_extracts_errors_not_notes_or_summary() -> None:
    assert len(parse_mypy_output(SAMPLE_MYPY_OUTPUT)) == 4


def test_parse_captures_code_and_location() -> None:
    by_line = {e.line: e for e in parse_mypy_output(SAMPLE_MYPY_OUTPUT)}
    assert by_line[217].code == "no-untyped-def"
    assert by_line[217].path == "runtime/db_lock.py"
    assert by_line[510].code == "arg-type"
    assert by_line[617].path == "substrate/event_log/events.py"
    assert by_line[617].code == "type-arg"


def test_parse_handles_col_when_present() -> None:
    errors = parse_mypy_output("foo.py:10:4: error: x  [assignment]")
    assert errors[0].col == 4 and errors[0].code == "assignment"


def test_parse_handles_missing_col() -> None:
    assert parse_mypy_output("foo.py:10: error: x  [assignment]")[0].col == 0


def test_parse_handles_missing_code() -> None:
    assert parse_mypy_output("foo.py:10: error: untagged")[0].code == "no-code"


def test_parse_ignores_unmatched_lines() -> None:
    out = "not an error\nfoo.py:1: error: real  [x]\ngarbage"
    assert len(parse_mypy_output(out)) == 1


def test_parse_empty_output_returns_empty() -> None:
    assert parse_mypy_output("") == []
    assert parse_mypy_output("Found 0 errors") == []


def test_mypy_error_to_key_excludes_message() -> None:
    e1 = MypyError(path="foo.py", line=10, col=4, code="arg-type", message="old")
    e2 = MypyError(path="foo.py", line=10, col=4, code="arg-type", message="new")
    assert mypy_error_to_key(e1) == mypy_error_to_key(e2)


def test_mypy_error_to_key_kind_prefix() -> None:
    e = MypyError(path="foo.py", line=1, col=0, code="no-untyped-def", message="x")
    assert mypy_error_to_key(e).kind == "mypy:no-untyped-def"


def test_mypy_error_to_key_distinguishes_codes() -> None:
    e1 = MypyError(path="foo.py", line=1, col=0, code="arg-type", message="x")
    e2 = MypyError(path="foo.py", line=1, col=0, code="type-arg", message="x")
    assert mypy_error_to_key(e1) != mypy_error_to_key(e2)


def _fake_errors() -> list[MypyError]:
    return [
        MypyError(path="runtime/db_lock.py", line=217, col=0,
                  code="no-untyped-def", message="missing annotation"),
        MypyError(path="substrate/event_log/events.py", line=617, col=0,
                  code="type-arg", message="missing type args"),
    ]


def test_capture_writes_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(msb, "run_mypy_strict", lambda paths: _fake_errors())
    baseline = tmp_path / "b.json"
    assert main(["capture", "--paths", "x", "--baseline-file", str(baseline)]) == 0
    data = json.loads(baseline.read_text())
    assert data["lint"] == "mypy_strict_substrate_core"
    kinds = {v["kind"] for v in data["violations"]}
    assert "mypy:no-untyped-def" in kinds and "mypy:type-arg" in kinds


def test_enforce_after_capture_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(msb, "run_mypy_strict", lambda paths: _fake_errors())
    baseline = tmp_path / "b.json"
    main(["capture", "--paths", "x", "--baseline-file", str(baseline)])
    assert main(["enforce", "--paths", "x", "--baseline-file", str(baseline)]) == 0


def test_enforce_flags_new_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(msb, "run_mypy_strict", lambda paths: _fake_errors())
    baseline = tmp_path / "b.json"
    main(["capture", "--paths", "x", "--baseline-file", str(baseline)])

    def _with_new(paths: object) -> list[MypyError]:
        return _fake_errors() + [
            MypyError(path="runtime/db_lock.py", line=900, col=0,
                      code="assignment", message="new"),
        ]

    monkeypatch.setattr(msb, "run_mypy_strict", _with_new)
    assert main(["enforce", "--paths", "x", "--baseline-file", str(baseline)]) == 1


def test_enforce_check_stale_flags_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(msb, "run_mypy_strict", lambda paths: _fake_errors())
    baseline = tmp_path / "b.json"
    main(["capture", "--paths", "x", "--baseline-file", str(baseline)])
    monkeypatch.setattr(msb, "run_mypy_strict", lambda paths: _fake_errors()[:1])
    rc = main(["enforce", "--paths", "x", "--baseline-file", str(baseline),
               "--check-stale"])
    assert rc == 1
    assert "stale baseline" in capsys.readouterr().err


def test_enforce_missing_baseline_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(msb, "run_mypy_strict", lambda paths: _fake_errors())
    assert main(["enforce", "--paths", "x",
                 "--baseline-file", str(tmp_path / "absent.json")]) == 2


def test_capture_handles_mypy_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(paths: object) -> list[MypyError]:
        raise RuntimeError("mypy not found")

    monkeypatch.setattr(msb, "run_mypy_strict", _boom)
    assert main(["capture", "--paths", "x",
                 "--baseline-file", str(tmp_path / "b.json")]) == 2
