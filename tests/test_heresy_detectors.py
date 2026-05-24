"""
Tests for the heresy detectors (tools/heresy_detectors/).

Layout discipline: this file is intentionally flat in tests/ to match
Antiek's existing test layout (205 sibling test_*.py files; no
per-module subdirectories). Every detector gets a positive case (does
trigger), a negative case (does not), and an escape-hatch case (noqa
suppresses).

The tests use pytest's tmp_path to materialize synthetic Python files so
the detectors can be exercised without polluting the real repo. The
detectors take file paths so this is a natural fit.

Spec: ~/specs/antiek-yegge-execute/sprint-02-heresy-registry.html
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

# Importing the package picks up the runtime; this is the public entry
# point a CI script would call.
from tools.heresy_detectors import (
    h001_single_writer_syntheses as h001,
    h002_missing_db_lock as h002,
    h003_fake_quack_db as h003,
    h004_unobservable_spawn as h004,
)
from tools.heresy_detectors._common import parse_noqa

# The subprocess-form ``python -m tools.heresy_detectors.run_all`` tests
# need to spawn from the repo root (where the ``tools`` package is on
# the import path). Compute it once: this file lives at
# ``<repo>/tests/test_heresy_detectors.py``.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# _common — the escape-hatch parser. Detector quality depends on this being
# strict about reason length so the bare-noqa anti-pattern can't take hold.
# ---------------------------------------------------------------------------


def test_parse_noqa_accepts_valid_escape_hatch():
    # Returns the dashed form so it compares cleanly against detector
    # HERESY_ID constants (which use the dashed form to match HERESIES.md).
    assert parse_noqa("foo()  # noqa: H001 -- test fixture seeds") == "H-001"


def test_parse_noqa_rejects_bare_noqa():
    # Bare noqa is exactly the rot-pattern this scheme is designed to
    # prevent. Returning None means the detector continues to flag.
    assert parse_noqa("foo()  # noqa") is None
    assert parse_noqa("foo()  # noqa: H001") is None


def test_parse_noqa_rejects_too_short_reason():
    # Reason of 11 chars — one less than the minimum (12). Must reject so
    # an author can't slip in "TBD" or "later" as justification.
    short = "x" * 11
    assert parse_noqa(f"foo()  # noqa: H001 -- {short}") is None


def test_parse_noqa_accepts_minimum_reason():
    # 12 chars is exactly the minimum (chosen because "test fixture" is
    # 12 chars and is the shortest legitimate reason).
    assert parse_noqa("foo()  # noqa: H001 -- test fixture") == "H-001"


def test_parse_noqa_handles_uppercase_lowercase_ID():
    assert parse_noqa("foo()  # noqa: h001 -- test fixture seeds") == "H-001"


# ---------------------------------------------------------------------------
# H-001 single-writer to syntheses
# ---------------------------------------------------------------------------


def _write(tmp_path, relpath: str, body: str) -> str:
    """Write a synthetic file under tmp_path and return its repo-relative
    string path (the way pre-commit hands paths to a detector)."""
    full = tmp_path / relpath
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(body))
    # Return as a string — detectors operate on path strings, not Path objects.
    return str(full)


def test_h001_flags_insert_outside_whitelist(tmp_path):
    path = _write(tmp_path, "roles/extractor.py", '''
        def bad(con):
            con.execute("INSERT INTO syntheses (id) VALUES (?)", [1])
    ''')
    violations = h001.run([path])
    assert len(violations) == 1
    assert violations[0].heresy_id == "H-001"
    assert violations[0].line == 3  # line of INSERT


def test_h001_whitelists_archive_path(tmp_path):
    # The detector looks at the path prefix, so we use a relative-style
    # path that matches the whitelist. tmp_path is irrelevant to the
    # whitelist matcher (it operates on the string we pass in).
    path = _write(tmp_path, "middleware/archive/archive.py", '''
        def archive(con):
            con.execute("INSERT INTO syntheses (id) VALUES (?)", [1])
    ''')
    # Pass the relative-style path explicitly so the whitelist matches.
    rel = "middleware/archive/archive.py"
    # Re-materialize at that exact relpath under tmp_path so the file
    # actually exists for the detector to open.
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(open(path).read())
    # Call with the relative path AS the input the detector sees.
    os.chdir(tmp_path)
    try:
        violations = h001.run([rel])
    finally:
        os.chdir(os.path.expanduser("~"))
    assert violations == []


def test_h001_honors_noqa_escape_hatch(tmp_path):
    path = _write(tmp_path, "roles/extractor.py", '''
        def bad(con):
            con.execute("INSERT INTO syntheses (id) VALUES (?)", [1])  # noqa: H001 -- one-off migration
    ''')
    violations = h001.run([path])
    assert violations == []


def test_h001_ignores_unrelated_tables(tmp_path):
    path = _write(tmp_path, "roles/other.py", '''
        def fine(con):
            con.execute("INSERT INTO synthesis_drafts (id) VALUES (?)", [1])
    ''')
    violations = h001.run([path])
    assert violations == []


# ---------------------------------------------------------------------------
# H-002 missing db_lock for writes
# ---------------------------------------------------------------------------


def test_h002_flags_raw_duckdb_connect_write(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import duckdb
        con = duckdb.connect("/tmp/foo.duckdb")
    ''')
    violations = h002.run([path])
    assert len(violations) == 1
    assert violations[0].heresy_id == "H-002"


def test_h002_allows_read_only(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import duckdb
        con = duckdb.connect("/tmp/foo.duckdb", read_only=True)
    ''')
    assert h002.run([path]) == []


def test_h002_allows_in_memory(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import duckdb
        con = duckdb.connect(":memory:")
    ''')
    assert h002.run([path]) == []


def test_h002_flags_from_import_form(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        from duckdb import connect
        con = connect("/tmp/foo.duckdb")
    ''')
    violations = h002.run([path])
    assert len(violations) == 1


def test_h002_flags_from_import_with_alias(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        from duckdb import connect as ddc
        con = ddc("/tmp/foo.duckdb")
    ''')
    violations = h002.run([path])
    assert len(violations) == 1


def test_h002_honors_noqa(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import duckdb
        con = duckdb.connect("/tmp/foo.duckdb")  # noqa: H002 -- migration sequencer
    ''')
    assert h002.run([path]) == []


def test_h002_handles_broken_syntax_gracefully(tmp_path):
    path = _write(tmp_path, "roles/x.py", "this is not python at all <<<<")
    # Should not raise; should silently skip the unparseable file.
    assert h002.run([path]) == []


# ---------------------------------------------------------------------------
# H-003 fake Quack DB (multiple write handles to same path)
# ---------------------------------------------------------------------------


def test_h003_flags_two_handles_to_same_path(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        from db_lock import connect_write
        with connect_write("/tmp/g.duckdb") as a:
            pass
        with connect_write("/tmp/g.duckdb") as b:
            pass
    ''')
    violations = h003.run([path])
    # First call is the canonical one; second is the violation.
    assert len(violations) == 1
    assert violations[0].line == 5


def test_h003_allows_single_handle(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        from db_lock import connect_write
        with connect_write("/tmp/g.duckdb") as a:
            pass
    ''')
    assert h003.run([path]) == []


def test_h003_allows_different_paths(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        from db_lock import connect_write
        with connect_write("/tmp/a.duckdb") as a:
            pass
        with connect_write("/tmp/b.duckdb") as b:
            pass
    ''')
    assert h003.run([path]) == []


def test_h003_does_not_flag_variable_bound_paths(tmp_path):
    # Documented behavior: we only check string literals to keep the
    # detector simple and false-positive-free. A path bound to a
    # variable is invisible to us.
    path = _write(tmp_path, "roles/x.py", '''
        from db_lock import connect_write
        DB = "/tmp/g.duckdb"
        with connect_write(DB) as a:
            pass
        with connect_write(DB) as b:
            pass
    ''')
    assert h003.run([path]) == []  # by design


# ---------------------------------------------------------------------------
# H-004 unobservable spawn (warn-only at Wave 1)
# ---------------------------------------------------------------------------


def test_h004_is_warn_only_at_wave_1():
    # This is a structural assertion: the constant must be "warn_only"
    # until SPR-04 lands and flips it. If a future agent flips it
    # prematurely this test catches them.
    assert h004.MODE == "warn_only", (
        "H-004 must remain warn-only until SPR-04 (worker registry) lands. "
        "Flipping it now produces noise the operator will skip."
    )


def test_h004_flags_subprocess_popen(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import subprocess
        p = subprocess.Popen(["ls"])
    ''')
    violations = h004.run([path])
    assert len(violations) == 1


def test_h004_flags_asyncio_create_task(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import asyncio
        async def f():
            asyncio.create_task(g())
    ''')
    violations = h004.run([path])
    assert len(violations) == 1


def test_h004_flags_threading_thread(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import threading
        t = threading.Thread(target=f)
    ''')
    violations = h004.run([path])
    assert len(violations) == 1


def test_h004_honors_noqa_with_ephemeral_reason(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import subprocess
        subprocess.run(["ls"])  # noqa: H004 -- ephemeral, <100ms helper
    ''')
    assert h004.run([path]) == []


def test_h004_whitelists_tests_dir(tmp_path):
    # When passed a path under tests/, the detector should not flag.
    path = _write(tmp_path, "tests/test_subprocess_helper.py", '''
        import subprocess
        subprocess.run(["ls"])
    ''')
    rel = "tests/test_subprocess_helper.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(open(path).read())
    os.chdir(tmp_path)
    try:
        violations = h004.run([rel])
    finally:
        os.chdir(os.path.expanduser("~"))
    assert violations == []


# ---------------------------------------------------------------------------
# run_all integration — the entry point that .githooks/pre-commit calls.
# We run it as a subprocess so we exercise sys.argv parsing and exit
# codes exactly the way the hook does.
# ---------------------------------------------------------------------------


def test_run_all_exits_zero_when_no_violations(tmp_path):
    path = _write(tmp_path, "roles/clean.py", "x = 1\n")
    result = subprocess.run(
        [sys.executable, "-m", "tools.heresy_detectors.run_all", path],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0


def test_run_all_exits_nonzero_on_blocking_violation(tmp_path):
    path = _write(tmp_path, "roles/x.py", '''
        import duckdb
        con = duckdb.connect("/tmp/f.duckdb")
    ''')
    result = subprocess.run(
        [sys.executable, "-m", "tools.heresy_detectors.run_all", path],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 1
    assert "H-002" in result.stderr


def test_run_all_warn_only_does_not_change_exit_code(tmp_path):
    # H-004 violation only — should print to stderr but exit 0.
    path = _write(tmp_path, "roles/x.py", '''
        import subprocess
        subprocess.run(["ls"])
    ''')
    result = subprocess.run(
        [sys.executable, "-m", "tools.heresy_detectors.run_all", path],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0
    assert "WARN-ONLY" in result.stderr


def test_run_all_respects_skip_env(tmp_path):
    # Even with a blocking violation, ANTIEK_HERESY_SKIP=1 should exit 0
    # and print the skip notice.
    path = _write(tmp_path, "roles/x.py", '''
        import duckdb
        con = duckdb.connect("/tmp/f.duckdb")
    ''')
    env = dict(os.environ)
    env["ANTIEK_HERESY_SKIP"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "tools.heresy_detectors.run_all", path],
        capture_output=True, text=True, env=env, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "skipped" in result.stderr.lower()


def test_run_all_empty_input_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "tools.heresy_detectors.run_all"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
