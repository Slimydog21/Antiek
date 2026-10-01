"""A retry exhausted on the same-file/different-config error must be retryable.

`_connect_write_after_process_gate` retries TWO transient open failures until
its deadline: the external DuckDB file lock (`_external_duckdb_lock_conflict`)
and DuckDB's "same database file with a different configuration" rejection
(`_SAME_FILE_DIFFERENT_CONFIG`). The deadline handler translated only the
first, so an exhausted same-file retry re-raised the raw
`duckdb.ConnectionException`.

Callers catch `WriteLockTimeout` and map it to a retryable 503 with
`Retry-After` -- `interfaces/research/api/ad_routes.py` does exactly that for
`POST /api/ad/frame-telemetry`. A raw `ConnectionException` matches none of
those handlers and becomes a 500.

Measured on the live box 2026-10-01, release 4fc53a43b, over 60 minutes: 464
requests to that route, 169 of them 500, every one ending in

    _duckdb.ConnectionException: Connection Error: Can't open a connection to
    same database file with a different configuration than existing connections

The two conditions are NOT the same fault and the timeout message must not
conflate them: `_SAME_FILE_DIFFERENT_CONFIG` is raised by DuckDB's IN-PROCESS
instance cache, so the conflicting handle is inside the calling process, while
only the external conflict names a peer. The tests below pin both the
translation and the distinction.
"""

from __future__ import annotations

import re

import duckdb
import pytest

from runtime import db_lock
from runtime.db_lock import WriteLockTimeout, connect_write

_SAME_FILE = (
    f"Connection Error: {db_lock._SAME_FILE_DIFFERENT_CONFIG}"
)
_EXTERNAL = (
    "IO Error: Could not set lock on file "
    '"/tmp/x.duckdb": Conflicting lock is held in /usr/bin/python3.12 '
    "(PID 23337)"
)


def _always(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def open_failing(
        _path: str, *args: object, **kwargs: object
    ) -> duckdb.DuckDBPyConnection:
        raise error

    monkeypatch.setattr(duckdb, "connect", open_failing)


def _timeout(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch,
             error: Exception, name: str) -> WriteLockTimeout:
    _always(monkeypatch, error)
    with pytest.raises(WriteLockTimeout) as caught:
        connect_write(
            str(tmp_path / f"{name}.duckdb"),
            timeout_s=0.05,
            poll_interval_s=0.01,
            purpose=f"test:{name}",
        )
    return caught.value


def test_exhausted_same_file_config_retry_is_a_writelocktimeout(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry condition that was not translated."""
    _timeout(tmp_path, monkeypatch,
             duckdb.ConnectionException(_SAME_FILE), "same-file")


def test_unrelated_open_error_still_propagates_raw(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: widening the translation must not swallow this."""
    _always(monkeypatch, duckdb.ConnectionException("unrelated open failure"))
    with pytest.raises(duckdb.ConnectionException, match="unrelated open failure"):
        connect_write(
            str(tmp_path / "unrelated.duckdb"),
            timeout_s=0.05,
            poll_interval_s=0.01,
            purpose="test:unrelated",
        )


def test_same_file_timeout_names_an_in_process_conflict(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message must not send an operator hunting a peer that does not exist.

    ``_SAME_FILE_DIFFERENT_CONFIG`` is an in-process instance-cache conflict;
    calling it "another process" is false for this case (verified by
    experiment: an in-process read-only holder raises exactly this error with
    no other process present).
    """
    exc = _timeout(tmp_path, monkeypatch,
                   duckdb.ConnectionException(_SAME_FILE), "in-process")
    message = str(exc)
    assert "this process" in message, message
    assert "another process" not in message, message


def test_external_lock_timeout_still_names_another_process(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the distinction: the external case IS a peer."""
    exc = _timeout(tmp_path, monkeypatch,
                   duckdb.IOException(_EXTERNAL), "external")
    message = str(exc)
    assert "another process" in message, message
    assert not re.search(r"this process already holds", message), message
