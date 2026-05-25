"""Tests for tools.lints.unannotated_bypass."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.lints.unannotated_bypass import (
    DEFAULT_BYPASS_PATTERNS,
    BypassViolation,
    load_patterns,
    main,
    scan_file,
    scan_paths,
)

FIXTURE = Path(__file__).parent / "fixtures" / "lints" / "bypass_sample.py"


def test_flags_unannotated_duckdb() -> None:
    fns = {v.function_name for v in scan_file(FIXTURE)}
    assert "unannotated_duckdb_violation" in fns


def test_flags_unannotated_requests() -> None:
    fns = {v.function_name for v in scan_file(FIXTURE)}
    assert "unannotated_requests_violation" in fns


def test_not_flagged_inside_with_block() -> None:
    fns = {v.function_name for v in scan_file(FIXTURE)}
    assert "annotated_with_context_is_allowed" not in fns


def test_not_flagged_inside_decorated_fn() -> None:
    fns = {v.function_name for v in scan_file(FIXTURE)}
    assert "annotated_with_decorator_is_allowed" not in fns


def test_not_flagged_when_nested_under_with() -> None:
    fns = {v.function_name for v in scan_file(FIXTURE)}
    assert "nested_with_escape_is_allowed" not in fns


def test_correctly_re_flags_after_with_ends() -> None:
    """One call inside `with escape_hatch` (allowed), second after the
    block ends (must flag). Lint must not silence the second."""
    relevant = [
        v for v in scan_file(FIXTURE)
        if v.function_name == "escape_then_unannotated_violation"
    ]
    assert len(relevant) == 1
    assert relevant[0].qualifier == "duckdb"


def test_default_patterns() -> None:
    flat = set(DEFAULT_BYPASS_PATTERNS)
    assert ("duckdb", "connect") in flat
    assert ("requests", "get") in flat


def test_load_patterns_missing_returns_defaults() -> None:
    result = load_patterns(Path("/nonexistent/x.toml"))
    assert ("duckdb", "connect") in result


def test_load_patterns_reads_toml() -> None:
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tf:
        tf.write('[[patterns]]\nqualifier = "foo"\nmethod = "bar"\n')
        tf.flush()
        result = load_patterns(Path(tf.name))
    assert ("foo", "bar") in result


def test_load_patterns_falls_back_on_bad_toml() -> None:
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as tf:
        tf.write('patterns = "not-a-list"\n')
        tf.flush()
        result = load_patterns(Path(tf.name))
    assert ("duckdb", "connect") in result


def test_violation_format() -> None:
    v = BypassViolation(
        path=Path("/tmp/foo.py"), line=10, col=4,
        qualifier="duckdb", method="connect", function_name="bad_caller",
    )
    s = v.format_line()
    assert "/tmp/foo.py:10:4" in s
    assert "duckdb.connect()" in s
    assert "bad_caller" in s


def test_main_no_paths_returns_2() -> None:
    assert main([]) == 2


def test_main_clean_returns_0(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("def f() -> None:\n    return None\n")
    assert main([str(clean)]) == 0


def test_main_violating_returns_1(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main([str(FIXTURE)]) == 1
    out = capsys.readouterr().out
    assert "duckdb.connect()" in out


def test_scan_paths_walks_directory() -> None:
    names = {v.path.name for v in scan_paths([FIXTURE.parent])}
    assert "bypass_sample.py" in names


def test_dotted_urllib_request_qualifier(tmp_path: Path) -> None:
    src = tmp_path / "url.py"
    src.write_text(
        "import urllib.request\n"
        "def f() -> None:\n"
        "    r = urllib.request.urlopen('https://example.com')\n"
        "    r.close()\n"
    )
    assert any(
        v.qualifier == "urllib.request" and v.method == "urlopen"
        for v in scan_file(src)
    )


def test_async_with_escape_hatch_allowed(tmp_path: Path) -> None:
    src = tmp_path / "async.py"
    src.write_text(
        "import requests\n"
        "async def f() -> None:\n"
        "    async with escape_hatch(reason='x'):\n"
        "        requests.get('https://example.com')\n"
    )
    assert scan_file(src) == []
