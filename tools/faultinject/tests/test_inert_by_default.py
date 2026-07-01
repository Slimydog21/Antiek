"""Load-bearing safety proof: importing the harness changes nothing.

If any of these fail, the harness is not safe to keep in the tree — an import
alone would perturb the default test run or production. Every assertion here is
about behaviour *after import, with nothing armed*.
"""

from __future__ import annotations

import builtins
import io
import os

import tools.faultinject as fj  # noqa: F401  (import is the thing under test)
from tools.faultinject import locked_db, provider_fault, readonly_fs  # noqa: F401


def test_import_installs_no_monkeypatch():
    # The write primitives are the real builtins, not our fakes.
    assert builtins.open.__module__ in ("io", "_io")
    assert io.open is builtins.open
    assert os.replace.__module__ == "os" or os.replace.__qualname__ == "replace"
    assert os.rename.__module__ == "os" or os.rename.__qualname__ == "rename"


def test_writes_work_normally_when_nothing_armed(tmp_path):
    p = tmp_path / "note.txt"
    with open(p, "w") as fh:
        fh.write("hello")
    assert p.read_text() == "hello"
    # Path-based writes (which route through io.open) also work.
    q = tmp_path / "viapath.txt"
    q.write_text("world")
    assert q.read_text() == "world"
    # os.replace works.
    os.replace(q, p)
    assert p.read_text() == "world"


def test_connect_write_works_when_nothing_armed(tmp_path):
    from runtime.db_lock import connect_write, is_locked

    db = str(tmp_path / "t.duckdb")
    con = connect_write(db, timeout_s=5, purpose="inert-test")
    con.execute("CREATE TABLE t (x INTEGER)")
    con.close()
    # Lock released after close.
    assert is_locked(db) is False


def test_arm_registry_lists_the_three_injectors():
    from tools.faultinject import INJECTORS

    assert INJECTORS == ("readonly_fs", "locked_db", "provider_fault")
