"""Tests for tools.lints.no_raise_in_substrate_writers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.lints.no_raise_in_substrate_writers import (
    ALLOWED_SYSTEM_EXCEPTIONS,
    Violation,
    load_allowlist,
    main,
    scan_file,
    scan_paths,
)

FIXTURE = Path(__file__).parent / "fixtures" / "lints" / "raise_violation_sample.py"


def test_scan_file_identifies_violating_raises() -> None:
    exc_names = {v.exception_name for v in scan_file(FIXTURE)}
    assert "CustomDomainError" in exc_names
    assert "UnstableThing" in exc_names


def test_scan_file_allows_system_exceptions() -> None:
    exc_names = {v.exception_name for v in scan_file(FIXTURE)}
    assert "OSError" not in exc_names
    assert "AssertionError" not in exc_names
    assert "NotImplementedError" not in exc_names


def test_scan_file_allows_bare_reraise() -> None:
    exc_names = {v.exception_name for v in scan_file(FIXTURE)}
    assert "<bare-reraise>" not in exc_names


def test_violation_carries_function_name() -> None:
    by_name = {v.exception_name: v for v in scan_file(FIXTURE)}
    assert by_name["CustomDomainError"].function_name == "writes_with_violation"
    assert by_name["UnstableThing"].function_name == "writes_with_other_violation"


def test_violation_format_line() -> None:
    v = Violation(
        path=Path("/tmp/foo.py"), line=42, col=4,
        exception_name="WhateverError", function_name="bad_writer",
    )
    s = v.format_line()
    assert "/tmp/foo.py:42:4" in s
    assert "WhateverError" in s
    assert "bad_writer" in s


def test_scan_paths_walks_directory() -> None:
    paths_seen = {v.path.name for v in scan_paths([FIXTURE.parent])}
    assert "raise_violation_sample.py" in paths_seen


def test_allow_extra_silences_a_named_exception() -> None:
    exc_names = {
        v.exception_name
        for v in scan_file(FIXTURE, allow_extra={"CustomDomainError"})
    }
    assert "CustomDomainError" not in exc_names
    assert "UnstableThing" in exc_names


def test_load_allowlist_missing_returns_empty() -> None:
    assert load_allowlist(Path("/nonexistent/x.toml")) == set()


def test_load_allowlist_reads_toml() -> None:
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tf:
        tf.write('allowed_exceptions = ["FooError", "BarError"]\n')
        tf.flush()
        result = load_allowlist(Path(tf.name))
    assert result == {"FooError", "BarError"}


def test_main_no_paths_returns_2() -> None:
    assert main([]) == 2


def test_main_clean_path_returns_0(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("def f() -> None:\n    pass\n")
    assert main([str(clean)]) == 0


def test_main_violating_returns_1(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main([str(FIXTURE)]) == 1
    assert "raise CustomDomainError" in capsys.readouterr().out


def test_system_exceptions_includes_result_unwrap_error() -> None:
    assert "ResultUnwrapError" in ALLOWED_SYSTEM_EXCEPTIONS


def test_scan_file_syntax_error_returns_empty(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(\n")
    assert scan_file(bad) == []
