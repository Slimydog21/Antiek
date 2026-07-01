"""Locked-DB injector: a real flock makes connect_write raise the real
WriteLockTimeout; the lock is released on teardown (even on raise)."""

from __future__ import annotations

import pytest

from tools.faultinject import arm, locked_db


def test_connect_write_times_out_while_locked(tmp_path):
    from runtime.db_lock import WriteLockTimeout, connect_write, is_locked

    db = str(tmp_path / "t.duckdb")
    with locked_db(db):
        assert is_locked(db) is True
        with pytest.raises(WriteLockTimeout):
            connect_write(db, timeout_s=0.5, poll_interval_s=0.1, purpose="probe")
    # Disarmed: the lock is released and a writer succeeds.
    assert is_locked(db) is False
    con = connect_write(db, timeout_s=5, purpose="after")
    con.close()


def test_lock_released_even_when_body_raises(tmp_path):
    from runtime.db_lock import connect_write, is_locked

    db = str(tmp_path / "t.duckdb")

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with locked_db(db):
            assert is_locked(db) is True
            raise Boom()
    # The flock is released despite the exception.
    assert is_locked(db) is False
    con = connect_write(db, timeout_s=5, purpose="after-raise")
    con.close()


def test_fail_on_call_rejected_as_state_fault(tmp_path):
    db = str(tmp_path / "t.duckdb")
    with pytest.raises(ValueError):
        with locked_db(db, fail_on_call=2):
            pass


def test_arm_generic_entry_point(tmp_path):
    from runtime.db_lock import WriteLockTimeout, connect_write, is_locked

    db = str(tmp_path / "t.duckdb")
    with arm("locked_db", db_path=db):
        with pytest.raises(WriteLockTimeout):
            connect_write(db, timeout_s=0.5, poll_interval_s=0.1)
    assert is_locked(db) is False
