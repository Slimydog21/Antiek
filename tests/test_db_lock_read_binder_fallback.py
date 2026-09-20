"""connect_read LazyRW when RW already open in-process (#3121 / Ads fills)."""

from __future__ import annotations

import os
import tempfile

from runtime.db_lock import _ReadOrientedConnection, connect_read, connect_write


def test_connect_read_falls_back_when_rw_already_open():
    tmp = tempfile.mkdtemp(prefix="antiek-binder-")
    db = os.path.join(tmp, "t.duckdb")
    with connect_write(db, purpose="test:hold-rw", timeout_s=5) as con_w:
        con_w.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        con_w.execute("INSERT INTO t VALUES (1)")
        con_r = connect_read(db)
        try:
            assert isinstance(con_r, _ReadOrientedConnection)
            row = con_r.execute("SELECT x FROM t").fetchone()
            assert row[0] == 1
        finally:
            con_r.close()
