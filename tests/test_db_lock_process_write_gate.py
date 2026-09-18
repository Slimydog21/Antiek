"""In-process write gate: second connect_write fails fast while first holds."""

from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest

from runtime.db_lock import WriteLockTimeout, connect_write


def test_second_writer_times_out_while_first_holds_in_process():
    tmp = tempfile.mkdtemp(prefix="antiek-pwg-")
    db = os.path.join(tmp, "t.duckdb")
    release = threading.Event()
    held = threading.Event()

    def holder():
        with connect_write(db, purpose="test:hold", timeout_s=5) as con:
            con.execute("SELECT 1")
            held.set()
            release.wait(timeout=20)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert held.wait(timeout=5)
    t0 = time.monotonic()
    with pytest.raises(WriteLockTimeout):
        with connect_write(db, purpose="test:second", timeout_s=1.0):
            pass
    elapsed = time.monotonic() - t0
    release.set()
    t.join(timeout=5)
    assert elapsed < 2.5, f"second writer took {elapsed:.3f}s"
