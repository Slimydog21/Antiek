"""nygard SPR-05 — bite tests for the seam-call-under-write-lock lint."""

from __future__ import annotations

import textwrap

from tools.lints.no_seam_call_under_write_lock import scan_file


def _write(tmp_path, code: str):
    p = tmp_path / "m.py"
    p.write_text(textwrap.dedent(code))
    return p


def test_flags_seam_call_inside_write_lock(tmp_path):
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write
        def go(db, harvester):
            with connect_write(db) as con:
                for rec in harvester.harvest():   # seam call UNDER the lock
                    con.execute("INSERT INTO t VALUES (?)", [rec])
    """)
    v = scan_file(p)
    assert len(v) == 1
    assert v[0].seam == "harvest"


def test_clean_when_seam_is_outside_lock(tmp_path):
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write
        def go(db, harvester):
            records = list(harvester.harvest())   # seam OUTSIDE the lock — the fix
            with connect_write(db) as con:
                for rec in records:
                    con.execute("INSERT INTO t VALUES (?)", [rec])
    """)
    assert scan_file(p) == []


def test_db_only_writes_are_clean(tmp_path):
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write
        def go(db):
            with connect_write(db) as con:
                con.execute("CREATE TABLE t (x INTEGER)")
                con.executemany("INSERT INTO t VALUES (?)", [[1], [2]])
                con.execute("SELECT count(*) FROM t").fetchone()
    """)
    assert scan_file(p) == []


def test_flags_httpx_dispatch_subprocess(tmp_path):
    p = _write(tmp_path, """
        import httpx, subprocess
        from runtime.db_lock import connect_write
        from substrate.dispatch.router import dispatch
        def go(db):
            with connect_write(db) as con:
                httpx.get("http://x")
                dispatch("p", "role", investigation_id="i")
                subprocess.run(["ls"])
    """)
    seams = sorted(v.seam for v in scan_file(p))
    assert seams == ["dispatch", "httpx.get", "subprocess.run"]


def test_exact_match_avoids_false_positives(tmp_path):
    # fetchone/fetchall (DuckDB cursor) and dict.get are NOT seams.
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write
        def go(db, d):
            with connect_write(db) as con:
                con.execute("q").fetchall()
                con.execute("q").fetchone()
                d.get("k")
    """)
    assert scan_file(p) == []
